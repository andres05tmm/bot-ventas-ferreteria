---
phase: 1
slug: db-infra-cat-logo-inventario
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Custom test runner (`test_suite.py`) — sin pytest |
| **Config file** | None — runner standalone |
| **Quick run command** | `python test_suite.py` |
| **Full suite command** | `python test_suite.py` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python test_suite.py`
- **After every plan wave:** Run `python test_suite.py` + smoke test manual en Railway (`/precios`)
- **Before `/gsd:verify-work`:** Full suite must be green (1096+ tests)
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | DB-01, DB-02 | unit | `python -c "import db; assert hasattr(db, 'query_one') and hasattr(db, 'query_all')"` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | DB-01, DB-03, DB-04 | smoke | `python test_suite.py` | ✅ | ⬜ pending |
| 1-02-01 | 02 | 1 | CAT-04 | unit | `python test_suite.py` | ✅ | ⬜ pending |
| 1-02-02 | 02 | 1 | CAT-05, CAT-06 | unit | `python test_suite.py` | ✅ | ⬜ pending |
| 1-03-01 | 03 | 2 | CAT-01, CAT-02, CAT-03 | smoke | `railway run python migrate_memoria.py` (manual) | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 2 | CAT-07 | full suite | `python test_suite.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `db.py` — módulo completo con `init_db()`, `query_one`, `query_all`, `execute`, `execute_returning`, `DB_DISPONIBLE` flag (DB-01, DB-02)
- [ ] `python -c "import db; print(db.DB_DISPONIBLE)"` no lanza excepción cuando `DATABASE_URL` no está presente (DB-04)
- [ ] Smoke test post-deploy: `python -c "import db; db.init_db(); print(db.DB_DISPONIBLE)"` retorna True en Railway (DB-01, DB-03)

*El test_suite.py existente cubre CAT-04, CAT-05, CAT-06, CAT-07 — inyecta `_cache` directamente y es agnóstico a la fuente de datos.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Schema creado (17 tablas) en Railway | DB-03 | Requiere conexión a Railway Postgres live | `railway run python -c "import db; db.init_db(); print(db.query_one('SELECT COUNT(*) FROM pg_tables WHERE schemaname=\'public\''))"` |
| Productos migrados (~576) | CAT-01 | Requiere `memoria.json` + Railway Postgres live | `railway run python -c "import db; db.init_db(); print(db.query_one('SELECT COUNT(*) FROM productos'))"` |
| Alias migrados | CAT-02 | Requiere migración ejecutada en Railway | `railway run python -c "import db; db.init_db(); print(db.query_one('SELECT COUNT(*) FROM productos_alias'))"` |
| Inventario migrado | CAT-03 | Requiere migración ejecutada en Railway | `railway run python -c "import db; db.init_db(); print(db.query_one('SELECT COUNT(*) FROM inventario'))"` |
| `/precios` responde desde Postgres | CAT-06 | Requiere Telegram bot live en Railway | Enviar `/precios` al bot en Telegram y verificar respuesta correcta |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
