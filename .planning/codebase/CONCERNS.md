# Concerns

**Analysis Date:** 2026-03-25

## Tech Debt

**Monolithic files:**
- `handlers/comandos.py` - 50+ command handlers in one file, very large
- `handlers/mensajes.py` - AI sales capture + message routing, large
- `ai.py` - All AI processing in single file
- Recommendation: Split by domain (sales commands, inventory commands, etc.)

**Global mutable state:**
- `ventas_state.py` uses module-level dicts (`ventas_pendientes`, `clientes_en_proceso`)
- `memoria.py` uses module-level `_cache` dict
- Thread-safe via locks, but hard to test and reason about

**Hardcoded magic numbers:**
- Excel row offsets in `config.py` (EXCEL_FILA_TITULO=1, EXCEL_FILA_HEADERS=3, EXCEL_FILA_DATOS=4)
- Drive debounce timer: 2 seconds hardcoded in `drive.py`
- Sheets cache TTL: 5 minutes hardcoded in `sheets.py`
- Dashboard polling intervals hardcoded in React components

**Duplicated patterns:**
- Some deduplication already done (utils.py centralizes _normalizar, parsear_precio)
- Version correction history in docstrings suggests ongoing cleanup effort

## Known Bugs / Fragile Areas

**Standby message handling:**
- Messages queued in standby can be lost if bot restarts mid-flow
- No persistence for in-flight sales state (only memoria.json is persisted)

**Google Drive concurrent uploads:**
- Debounce timer helps but race conditions possible with threading.Timer
- `cola_drive.json` retry queue is a workaround, not a solution

**Consecutive numbering:**
- Race condition possible when multiple sales confirmed simultaneously
- Lock in ventas_state mitigates but doesn't fully eliminate

**Regex-heavy preprocessing:**
- `utils.corregir_texto_audio()` has many regex patterns that could conflict
- `utils.normalizar_numeros_audio()` converts Spanish numbers to digits - ordering matters
- `alias_handler.py` and `ai.py` alias resolution - implicit, hard to debug

## Security Issues

**Credential exposure:**
- `config.py` validates env vars at import but exception traces could leak values
- Google credentials JSON stored in env var (standard but sensitive)

**No API authentication:**
- FastAPI endpoints have no auth middleware
- CORS is open (configured for dashboard access)
- Anyone with the URL can access all API endpoints

**Unvalidated file operations:**
- `manejar_documento()` accepts Excel uploads from Telegram without size/content validation
- `manejar_foto()` downloads photos without validation

**AI prompt injection:**
- User messages passed directly to Claude for parsing
- No sanitization of user input before AI processing

## Performance Bottlenecks

**Excel operations:**
- `openpyxl` reads are slow for large files
- Full worksheet scans on search operations via `routers/shared.py`
- Monthly sheet rotation means growing file size over time

**Fuzzy index rebuilds:**
- `fuzzy_match.construir_indice()` rebuilds on catalog changes
- No incremental index updates

**Synchronous blocking:**
- Excel writes wrapped in `asyncio.to_thread()` but still block a thread pool worker
- Google Sheets API calls can be slow (429 rate limits)

**Memory usage:**
- Entire catalog/prices/inventory loaded into memory (`memoria.py`)
- No pagination for large datasets
- Dashboard fetches full datasets on each poll

## Scaling Limits

**Single Excel file:**
- `ventas.xlsx` grows indefinitely with monthly sheets
- No archiving strategy for old months
- openpyxl performance degrades with large files

**In-memory state:**
- All state in `memoria.json` loaded to RAM
- Works for small hardware store, won't scale to thousands of products

**Single-threaded bot:**
- python-telegram-bot polling runs in main thread
- API runs in daemon thread
- No horizontal scaling (single Railway instance)

## Dependencies at Risk

**python-telegram-bot v20.x:**
- Major breaking changes between v13 and v20 (all async)
- Ongoing development, API may change

**openpyxl:**
- Maintenance status uncertain
- Performance issues with large files well-known

**Google API libraries:**
- gspread, google-auth, googleapiclient
- Rate limit changes by Google could break workflows

**AI providers:**
- anthropic + openai SDKs
- Model deprecations (Claude model versions) require updates
- Cost implications of AI calls per message

## Test Coverage Gaps

**No async tests:**
- All Telegram handlers are async but test_suite.py only tests sync functions
- No testing of concurrent access patterns

**No integration tests:**
- Google Sheets/Drive not mocked or tested
- No API endpoint tests (FastAPI TestClient not used)
- No Telegram bot simulation

**No error recovery tests:**
- Drive failure -> retry queue flow untested
- Sheets failure -> Excel fallback untested
- Bot restart state recovery untested

**No UI tests:**
- Dashboard React components untested
- No E2E browser tests

## Missing Capabilities

**No audit trail:**
- Sales modifications not tracked
- No history of price changes
- Delete operations not logged

**No backup strategy beyond Drive:**
- Single point of failure (Google Drive)
- No database backup
- memoria.json corruption = data loss

**No transaction rollback:**
- Sales write to multiple destinations (Sheets + Excel + Memory)
- Partial failure leaves inconsistent state

**No monitoring:**
- No health checks beyond keepalive
- No alerting on errors
- No metrics collection

---

*Concerns analysis: 2026-03-25*
