---
phase: 04-tests
plan: "01"
subsystem: tests
tags: [tests, unit-tests, price-cache, middleware, thread-safety, tdd]
dependency_graph:
  requires: []
  provides: [tests/test_price_cache.py, tests/test_middleware.py]
  affects: [ai/price_cache.py, middleware/auth.py]
tech_stack:
  added: []
  patterns: [sys.modules stub for isolated submodule import, pytest fixture autouse for cache isolation]
key_files:
  created:
    - tests/__init__.py
    - tests/test_price_cache.py
    - tests/test_middleware.py
  modified: []
decisions:
  - "sys.modules stub for ai package to bypass ai/__init__.py → config → SystemExit on import"
metrics:
  duration: "3m 25s"
  completed: "2026-03-29T23:30:10Z"
  tasks_completed: 4
  files_changed: 3
---

# Phase 04 Plan 01: Unit Tests for Phase 1 Modules Summary

**One-liner:** 17 pytest tests covering ai/price_cache.py (thread-safety, TTL, CRUD) and middleware/auth.py (RateLimiter + @protegido) without requiring any env credentials.

## What Was Built

Created `tests/` package with two test modules covering the Phase 1 refactoring artifacts:

- **tests/test_price_cache.py** — 8 tests: registrar, get_activos with TTL expiry, invalidar (multi-entry), limpiar_expirados, tamaño, and a concurrent thread-safety test with 10 writer + 10 reader threads
- **tests/test_middleware.py** — 9 tests: RateLimiter allow/block/window-expiry/cleanup, and @protegido decorator (fail-open when no IDs, blocks unauthorized, allows authorized, functools.wraps preserves __name__, handles message=None)

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create tests/ directory with __init__.py | 649494c | tests/__init__.py |
| 2 | Write tests/test_price_cache.py | 649494c | tests/test_price_cache.py |
| 3 | Write tests/test_middleware.py | 649494c | tests/test_middleware.py |
| 4 | Run full pytest suite and commit | 649494c | (verification only) |

## Decisions Made

**sys.modules stub for ai package isolation**

`ai/__init__.py` imports `config` at module load time, and `config.py` raises `SystemExit(1)` when `TELEGRAM_TOKEN`/`ANTHROPIC_API_KEY` are absent (which is always the case in the test environment). Injecting a stub `ModuleType` with `__path__` set to the `ai/` directory into `sys.modules["ai"]` before the import allows Python to find and load `ai/price_cache.py` as a submodule without executing `ai/__init__.py`. This is the standard isolation technique for submodule testing in packages with heavyweight top-level imports.

`middleware/auth.py` imports `from telegram import Update` which is available as `python-telegram-bot` is installed in the dev environment, so no stub was needed there.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ai/__init__.py triggers SystemExit via config.py on test import**
- **Found during:** Task 2 (first test run)
- **Issue:** `from ai.price_cache import` triggers `ai/__init__.py` → `import config` → `config.py` raises `SystemExit(1)` because `TELEGRAM_TOKEN`/`ANTHROPIC_API_KEY` env vars are absent in the test environment
- **Fix:** Added `sys.modules["ai"]` stub with `__path__` pointing to the `ai/` directory at the top of `test_price_cache.py`. This causes Python to skip executing `ai/__init__.py` and load `ai.price_cache` directly as a submodule
- **Files modified:** tests/test_price_cache.py
- **Commit:** 649494c

## Known Stubs

None — no placeholder data or hardcoded stubs in the test files.

## Verification Results

```
python -m pytest tests/test_price_cache.py tests/test_middleware.py -v
→ 17 passed in 3.18s

grep "def test_concurrent" tests/test_price_cache.py
→ def test_concurrent_reads_writes

grep "def test_protegido" tests/test_middleware.py
→ def test_protegido_fail_open_sin_authorized_ids
→ def test_protegido_bloquea_no_autorizado
→ def test_protegido_permite_autorizado
→ def test_protegido_preserva_nombre
→ def test_protegido_maneja_message_none

git diff test_suite.py → empty (unmodified)
```

## Self-Check: PASSED
