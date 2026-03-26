# Testing

**Analysis Date:** 2026-03-25

## Framework

**No standard framework** - Custom test runner in `test_suite.py`
- Run with: `python test_suite.py`
- No pytest, unittest, or any testing library
- Custom pass/fail/error/skip reporting with colored terminal output
- Global counters: `_passed`, `_failed`, `_errored`, `_skipped`

## Test Structure

**Single file:** `test_suite.py` (large file, comprehensive)

**Sections:**
1. Fuzzy search of products (`memoria.py` / `fuzzy_match.py`)
2. Hardware store aliases (`ai.py`)
3. Bulk price parser (`handlers/mensajes.py`)
4. Fractions and quantity calculations (`utils.py`)
5. Product browser (`handlers/productos.py`)
6. Known edge cases (historical bugs that were fixed)

**Test Pattern:**
```python
def test_fuzzy_search(buscar):
    casos = [
        # (query, expected_substring, description)
        ("Rodillo de 2", "Rodillo de 2\"", "Rodillo 2 bug fix"),
    ]
    for query, esperado_substr, desc in casos:
        caso(desc)
        try:
            resultado = buscar(query)
            if esperado_substr.lower() not in str(resultado.get("nombre","")).lower():
                fail(...)
            else:
                ok(...)
        except Exception as e:
            error(...)
```

## Test Helpers

- `ok(nombre, detalle)` - Print green pass
- `fail(nombre, esperado, obtenido)` - Print red fail with expected vs actual
- `error(nombre, exc)` - Print error with exception
- `skip(nombre, razon)` - Print yellow skip
- `seccion(titulo)` - Print section header
- `caso(descripcion)` - Print test case name

## What's Tested

- **Fuzzy product search:** Various product names with measurements (rodillos, brochas, puntillas, cintas, tornillos, lijas, brocas, lacas, vinilos, esmaltes)
- **Alias resolution:** Hardware abbreviations (s.c -> sin cabeza, c.c -> con cabeza, fractions)
- **Price parsing:** Colombian price formats ($, dots, commas)
- **Fraction conversion:** "1/4", "1 y 1/2", "2-3/4" -> float
- **Edge cases:** Historical bugs that were fixed (Rodillo 2 matching 1, Pele L matching XL)

## What's NOT Tested

- API endpoints (no HTTP test client)
- Telegram bot handlers (no mocking of Update/Context)
- Google Sheets/Drive integration (no mocking)
- Excel read/write operations
- AI responses (Claude/OpenAI)
- Dashboard React components
- End-to-end sales flow
- Concurrent access / thread safety

## Test Execution

- Standalone: `python test_suite.py` (no Telegram, Railway, or Drive needed)
- Tests import actual project modules and call functions directly
- No mocking - tests use real in-memory data structures
- No CI/CD integration visible

## Coverage

**Estimated coverage:** Low-medium for core business logic (fuzzy search, parsing), zero for integrations and UI.

**Well-covered areas:**
- Product search/matching (critical for sales)
- Fraction/quantity parsing (common user input)
- Known bug regressions

**Gaps:**
- No API endpoint tests
- No integration tests with external services
- No UI tests
- No load/performance tests

---

*Testing analysis: 2026-03-25*
