# TESTING.md — Test Structure & Practices

## Test Framework

**Custom runner** — `test_suite.py` (root level, not pytest)

```bash
python test_suite.py          # Run all tests
python -m pytest tests/ -v    # Future pytest suite (Tarea J)
python -m pytest tests/ -v --ignore=test_suite.py
```

## Current Test File

### `test_suite.py` (root)
- **Framework:** Custom runner with colored terminal output
- **Style:** Imperative test functions, global pass/fail counters
- **No fixtures, no parametrize, no mocking**
- **Covers:**
  1. Fuzzy product search (`memoria.py` / `fuzzy_match.py`)
  2. Ferretería aliases (`ai.py`)
  3. Bulk price parser (`mensajes.py`)
  4. Fractions and quantity calculations
  5. `/productos` section (`productos.py`)
  6. Known edge cases (regression tests for fixed bugs)

### Custom Assertion Helpers
```python
def ok(nombre, detalle=""):    # Pass
def fail(nombre, esperado, obtenido):  # Fail with expected/actual
def error(nombre, exc):        # Unexpected exception
def skip(nombre, razon=""):    # Skipped test
```

### Running
```
python test_suite.py
# Output: ✅ PASS / ❌ FAIL / ⚠️ ERROR / ⏭ SKIP
# Final: Passed: N | Failed: N | Errors: N | Skipped: N
```

## Test Coverage

### Covered
- Fuzzy matching algorithm (product name search)
- Product alias resolution
- Text message parsing (sale capture from free text)
- Quantity/fraction math (e.g. "1/2 kilo", "3 docenas")
- Product catalog navigation

### Not Covered (gaps)
- Database operations (`db.py`, `memoria.py` DB functions)
- Telegram handler flows (require real bot context)
- FastAPI endpoints (`routers/`)
- Claude AI integration (`ai.py` — 2685 lines)
- Concurrency / thread-safety (`ventas_state.py` locks)
- Cache invalidation (`memoria.py` cache)
- File upload / Cloudinary integration
- Excel generation (`graficas.py`, `routers/reportes.py`)
- Authentication / authorization (pending Tarea A)
- Error handling paths

## Testing Constraints

- **No mocking** — tests call real functions with real data
- **No database** — tests avoid DB calls (no Railway connection needed)
- **No Telegram** — tests run offline
- **No env vars required** for current test_suite.py

## Planned Test Suite (Tarea J)

Target: `tests/` directory with pytest

```
tests/
├── test_middleware.py       # Auth + rate_limit (after Tarea A)
├── test_price_cache.py      # Thread-safe cache (after Tarea B)
├── test_catalogo_service.py # Catalog service (after Tarea D)
├── test_inventario_service.py
├── test_caja_service.py
├── test_fiados_service.py
├── test_prompts.py
├── conftest.py              # Shared fixtures
└── fixtures/
    └── test_data.json
```

### Planned Patterns
```python
# Fixtures
@pytest.fixture
def catalogo_mock(): ...

# Parametrize
@pytest.mark.parametrize("entrada,esperado", [...])
def test_precio_parseado(entrada, esperado): ...

# Thread safety
def test_price_cache_concurrent():
    with ThreadPoolExecutor(max_workers=10) as ex:
        ...
```

## CI Integration

- No CI pipeline configured (Railway deploy on push)
- Tests run manually before commits
- CLAUDE.md verification sequence:
  ```bash
  python -c "from <modulo_nuevo> import *; print('imports OK')"
  python -m pytest tests/test_<modulo>.py -v
  python -m pytest tests/ -v --ignore=test_suite.py
  python -c "import main; print('main OK')"
  ```

## Known Issues

- `test_suite.py` imports from `memoria.py` which requires DB connection at module level — may fail if `DATABASE_URL` not set
- No test isolation — tests share global state
- Test file is excluded from future pytest runs (`--ignore=test_suite.py`)
