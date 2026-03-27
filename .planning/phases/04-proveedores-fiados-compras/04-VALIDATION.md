---
phase: 4
slug: proveedores-fiados-compras
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-26
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Custom test runner (`test_suite.py`) — no pytest |
| **Config file** | none — standalone script |
| **Quick run command** | `PYTHONIOENCODING=utf-8 python3 test_suite.py` |
| **Full suite command** | `PYTHONIOENCODING=utf-8 python3 test_suite.py` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONIOENCODING=utf-8 python3 test_suite.py`
- **After every plan wave:** Run `PYTHONIOENCODING=utf-8 python3 test_suite.py`
- **Before `/gsd:verify-work`:** Full suite must be green (201+ tests passing)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | PROV-04 | regression | `PYTHONIOENCODING=utf-8 python3 test_suite.py` | ✅ | ⬜ pending |
| 04-01-02 | 01 | 1 | PROV-04 | regression | `PYTHONIOENCODING=utf-8 python3 test_suite.py` | ✅ | ⬜ pending |
| 04-02-01 | 02 | 2 | PROV-04, PROV-06 | regression | `PYTHONIOENCODING=utf-8 python3 test_suite.py` | ✅ | ⬜ pending |
| 04-02-02 | 02 | 2 | PROV-05 | regression | `PYTHONIOENCODING=utf-8 python3 test_suite.py` | ✅ | ⬜ pending |
| 04-03-01 | 03 | 1 | PROV-01, PROV-02 | syntax + manual | `python3 -c "import ast; ast.parse(open('migrate_proveedores.py').read())"` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 1 | PROV-03 | syntax + manual | `python3 -c "import ast; ast.parse(open('migrate_compras.py').read())"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all regression requirements. No new test files needed.

- Migration scripts (04-03 outputs): verified by syntax check + Railway log output at execution time.

*Wave 0 is complete — no pre-creation of test stubs required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `cuentas_por_pagar` migrated to Postgres | PROV-01 | Migration script runs in Railway environment only | `railway run python migrate_proveedores.py` — verify log shows count of rows inserted |
| `fiados` migrated to Postgres | PROV-02 | Migration script runs in Railway environment only | `railway run python migrate_fiados.py` — verify log shows count of rows inserted |
| Compras migrated (empty source) | PROV-03 | Migration script runs in Railway; local source is empty | `railway run python migrate_compras.py` — must exit 0 with "nada que migrar" message |
| Tab Proveedores reads Postgres | PROV-06 | Requires live Railway deploy + browser | Load dashboard Proveedores tab after deploy — verify facturas and abonos appear from Postgres |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (migration scripts created in 04-03)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
