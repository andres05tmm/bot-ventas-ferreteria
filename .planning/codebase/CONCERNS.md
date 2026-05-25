# CONCERNS.md — Technical Debt, Issues & Areas of Concern

## Critical Tech Debt

### Monolithic Files (Primary Refactoring Target)
| File | Size | Problem |
|------|------|---------|
| `ai.py` | 133 KB / ~2685 lines | All AI logic in one file — prompts, Excel gen, price cache, tool dispatch |
| `handlers/comandos.py` | 107 KB / ~2200 lines | 50+ commands in one file — impossible to navigate |
| `handlers/mensajes.py` | 71 KB | Message handling + AI orchestration mixed |
| `memoria.py` | 85 KB | DB queries + business logic + in-memory cache all mixed |

**Impact:** High coupling, slow test cycles, merge conflicts, hard onboarding.

### No Auth Middleware (Tarea A — CRÍTICA)
- `AUTHORIZED_CHAT_IDS` env var defined in spec but **not yet enforced**
- Any Telegram user can message the bot and access commands
- No `@protegido` decorator exists yet
- No rate limiting on any handler

### No Price Cache Module (Tarea B — CRÍTICA)
- Price lookups mixed into `ai.py` without isolation
- Thread-safety of price cache not audited
- Cache lives inside monolith — hard to test independently

### Sync DB in Async Bot
- `psycopg2` (sync) used in python-telegram-bot (async) context
- Each DB call blocks the event loop thread
- No connection pooling validation under concurrent requests

### Migration Scripts in Root
- 7 `migrate_*.py` files pollute the root directory
- Should be in `migrations/` (Tarea C) but not yet moved
- Some scripts are executable (`chmod +x`) — accidental run risk

---

## Known Bugs / Edge Cases

### Product Matching
- Fuzzy match (`fuzzy_match.py`) has known false positives for short product names
- "pele" vs "pelela" — alias system needed to disambiguate
- Size confusion: "1/4" could mean 1/4 kilo OR 1/4 inch (context-dependent)
- Some products have spaces in names that cause split issues

### Sale Processing
- Concurrent sales from same chat can interleave in `ventas_state.py`
- No transaction rollback if Claude API call fails mid-sale
- Excel import via photo (foto_cuaderno) has brittle OCR dependency

---

## Security Concerns

### Authentication Gap
- **HIGH:** No authorization check on bot commands (Tarea A fixes this)
- Any user knowing the bot username can send commands

### CORS Configuration
- FastAPI API (`api.py`) likely has broad CORS — dashboard is local but API is public on Railway
- Should be restricted to dashboard origin

### Environment Variables
- `ADMIN_CHAT_ID` and `AUTHORIZED_CHAT_IDS` not validated at startup
- Missing `AUTHORIZED_CHAT_IDS` silently fails (no users blocked)
- No secrets rotation mechanism

### File Handling
- Excel/image uploads processed without size/type validation
- Cloudinary uploads not validated before sending to API

### Rate Limiting
- No rate limiting on FastAPI endpoints
- No rate limiting on Telegram bot handlers
- Claude API calls not throttled — cost risk

---

## Performance Bottlenecks

### Full Cache Reload
- `memoria.py` reloads entire product catalog on cache miss
- No incremental update — any product change invalidates full cache
- Cache size unbounded for large catalogs

### Blocking DB in Async Context
- `psycopg2` sync calls block the asyncio event loop
- Under load, bot becomes unresponsive while waiting for DB
- Should use `asyncpg` or run DB calls in `run_in_executor`

### AI API Calls
- Claude API calls are synchronous from async handlers (blocking)
- No request queuing — concurrent messages each open new API call
- No response caching for repeated similar queries

### Excel Generation
- `graficas.py` generates charts in-process on request
- Large datasets block the main thread
- No background job queue for heavy exports

---

## Fragile Areas

### `ventas_state.py` — Thread Safety
- Global dict of in-progress sales with `threading.Lock`
- Lock granularity: one global lock for all sales (contention risk)
- No TTL/expiration — abandoned sales accumulate in memory

### `bypass.py` (31 KB)
- Large file with unclear ownership — risk of conflicts during refactoring
- Not mentioned in CLAUDE.md refactoring plan

### Async/Sync Boundary
- `start.py` runs FastAPI in a daemon thread alongside async bot
- Shared state between threads not always protected
- Exception in daemon thread silently kills API without bot knowing

### `handlers/mensajes.py` AI Orchestration
- Complex multi-step sale flow with branching state
- State spread across `ventas_state.py` + handler local vars
- Hard to test without real Telegram context

### Skills Loading
- `skill_loader.py` reads `.md` files at startup
- File not found → silent failure or crash (not verified)
- Skills injected into Claude context — prompt injection risk via skill files

---

## Scaling Limits

| Concern | Current Limit | Risk |
|---------|--------------|------|
| DB connections | psycopg2 pool (size unknown) | Exhaustion under load |
| Bot concurrency | python-telegram-bot default workers | Queued commands |
| Memory cache | Unbounded dict in `memoria.py` | Memory leak |
| Thread pool | `threading.Thread` per long op | Thread exhaustion |
| Railway dyno | Single instance | No horizontal scaling |

---

## Dependency Risks

| Dependency | Version | Risk |
|------------|---------|------|
| `anthropic` SDK | Pinned in requirements.txt | API changes break AI layer |
| `python-telegram-bot` | 21.3 | Major version — async migration complete |
| `psycopg2-binary` | Sync driver | Blocks event loop (long-term) |
| `openpyxl` | Excel generation | Large file memory usage |

---

## Missing Infrastructure

- **No monitoring** — no Sentry, no error tracking, no alerts
- **No structured logging** — `logging` to stdout only (Railway logs)
- **No health check endpoint** — Railway uses keepalive.py workaround
- **No backup strategy** — PostgreSQL on Railway (managed backups unknown)
- **No staging environment** — dev → production directly

---

## Refactoring Risks

### Do Not Touch (per CLAUDE.md)
- `db.py` — correct, stable, do not modify
- `config.py` — correct, stable, do not modify
- `main.py` — correct, stable, do not modify

### `memoria.py` Transition Risk
- Being converted to thin wrapper (Tarea H)
- External callers import from `memoria` — must maintain all public function signatures
- Any rename without alias breaks handlers and routers

### Zero-Downtime Constraint
- Every commit must leave `python main.py` bootable
- Cannot do big-bang refactors — incremental only
- Each Tarea must be independently deployable
