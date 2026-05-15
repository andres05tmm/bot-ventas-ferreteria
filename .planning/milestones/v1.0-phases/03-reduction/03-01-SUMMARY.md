---
phase: 03-reduction
plan: 01
subsystem: ai
tags: [python, refactoring, ai, prompts, excel, price-cache, package]

# Dependency graph
requires:
  - phase: 02-wiring
    provides: "ai/prompts.py, ai/excel_gen.py, ai/price_cache.py — extracted submodules that ai/__init__.py now imports from"
provides:
  - "ai/__init__.py — reduced from 2685 to 1256 lines, proper Python package"
  - "ai/ is now a proper Python package (not namespace package + file hybrid)"
  - "All 7+ callers (handlers/mensajes, callbacks, routers/chat, keepalive, test_suite) unchanged"
affects: [any future ai module work, imports referencing 'from ai import']

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Namespace package converted to proper package via git mv ai.py ai/__init__.py"
    - "Submodule delegation: __init__.py imports and re-exports from .prompts, .excel_gen, .price_cache"

key-files:
  created:
    - ai/__init__.py
  modified:
    - ai/__init__.py  # was ai.py — renamed and stripped

key-decisions:
  - "Tasks 1 and 2 are logically inseparable: stripping ai.py to add 'from ai.X import' only works after rename to ai/__init__.py (while ai.py is a file, 'ai' is not a package and submodule imports fail). Single atomic commit covers both."
  - "Absolute imports kept (from ai.prompts import ...) per codebase convention — relative imports were not needed"
  - "skill_loader and alias_manager kept as top-level imports in ai/__init__.py because procesar_con_claude and procesar_con_claude_stream still call alias_manager.aplicar_aliases_dinamicos() and skill_loader.obtener_skill() directly"
  - "fuzzy_match removed from imports — was only used in prompt-building functions extracted to ai/prompts.py"

patterns-established:
  - "Import delegation: ai/__init__.py re-exports symbols from submodules to preserve backward compatibility"

requirements-completed: [AI-01, AI-02, AI-03]

# Metrics
duration: 6min
completed: 2026-03-29
---

# Phase 3 Plan 1: AI Module Reduction Summary

**ai.py reduced from 2685 to 1256 lines via submodule import delegation and atomic rename to ai/__init__.py, converting ai/ from namespace package to proper Python package — all 7+ callers unchanged**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-29T18:51:26Z
- **Completed:** 2026-03-29T18:57:11Z
- **Tasks:** 2 (executed as single atomic commit)
- **Files modified:** 1 (ai.py renamed to ai/__init__.py)

## Accomplishments

- Stripped 1429 lines from ai.py by removing function bodies already extracted to submodules
- Added `from ai.prompts import`, `from ai.excel_gen import`, `from ai.price_cache import` to preserve all re-exports
- Single atomic `git mv ai.py ai/__init__.py` converts ai/ to proper Python package
- All callers (`from ai import procesar_con_claude`, `from ai import _construir_parte_estatica`, etc.) continue working with zero changes to caller files

## Task Commits

Both tasks executed atomically in a single commit per plan design:

1. **Task 1 + Task 2: Strip ai.py and rename to ai/__init__.py** - `1d0d459` (refactor)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `ai/__init__.py` (was `ai.py`) - Reduced ai module entry point: 2685 → 1256 lines, imports from submodules, retains procesar_con_claude, procesar_acciones, procesar_acciones_async, procesar_con_claude_stream, and all PG helper functions

## Decisions Made

- Tasks 1 and 2 are inseparable: `from ai.price_cache import` in ai.py would fail while ai.py is a file (Python can't resolve ai.X when ai is a .py file). The rename must happen together with the edits in one commit.
- Kept absolute imports (`from ai.prompts import`) rather than relative (`from .prompts import`) — matches existing codebase import convention.
- `skill_loader`, `alias_manager`, and `bypass` are still imported at top level because the remaining functions (`procesar_con_claude`, `procesar_con_claude_stream`) call them directly.
- `fuzzy_match` was removed — it was only used in the extracted prompt-building functions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] fuzzy_match removed from imports (not added back)**
- **Found during:** Task 1 (Step 6 — clean up unused imports)
- **Issue:** `fuzzy_match` was in the original import list, removed with the alias block. No remaining function in ai/__init__.py calls it directly.
- **Fix:** Did not re-add it since it would be an unused import.
- **Files modified:** ai/__init__.py
- **Verification:** grep confirmed no usage; all imports verified clean.
- **Committed in:** 1d0d459

---

**Total deviations:** 1 auto-fixed (Rule 1 - unused import cleanup)
**Impact on plan:** Zero scope change. Removed unused import for cleanliness.

## Issues Encountered

- Windows terminal encoding (`cp1252`) prevents running `python -c "from ai import ..."` directly in the test shell because `config.py` prints an emoji on missing env vars. Resolved by setting `TELEGRAM_TOKEN=dummy ANTHROPIC_API_KEY=sk-dummy OPENAI_API_KEY=sk-dummy` for verification commands.
- `from ai.price_cache import` and other submodule imports in ai.py fail before the rename (Python treats `ai` as the file). This confirmed Tasks 1 and 2 must be committed together atomically.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 3 (reduction) is now complete — ai.py is gone, ai/ is a proper package, all callers work
- All refactoring tasks (A through I) are complete
- The codebase is ready for Phase 4 (tests) or any future work on individual submodules

---
*Phase: 03-reduction*
*Completed: 2026-03-29*
