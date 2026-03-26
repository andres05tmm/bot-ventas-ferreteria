# Phase 1: DB Infra + Catálogo + Inventario - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Crear la infraestructura de acceso a PostgreSQL (`db.py` con pool de conexiones), desplegar el schema completo en Railway, migrar el catálogo (~576 productos) e inventario desde `memoria.json` a Postgres, y refactorizar `memoria.py` + `fuzzy_match.py` para leer catálogo e inventario desde Postgres. Los comandos `/precios`, `/buscar` e `/inventario` deben funcionar igual que antes. Ventas, histórico, gastos y caja son Fases 2-3 — no tocar.

</domain>

<decisions>
## Implementation Decisions

### Schema Deployment
- **D-01:** `db.py` ejecuta `CREATE TABLE IF NOT EXISTS` para todas las tablas al iniciar (`_init_schema()`). Cero pasos manuales — Railway redespliega y el schema aparece solo.
- **D-02:** Usar el SQL de `MIGRATION.md` como fuente del schema. Las sentencias deben ser idempotentes (IF NOT EXISTS, índices con IF NOT EXISTS).

### Fallback Mechanism
- **D-03:** Flag global `DB_DISPONIBLE = False` en `db.py`. Al arrancar, `init_db()` intenta conectar al pool. Si `DATABASE_URL` no está o la conexión falla, `DB_DISPONIBLE` queda en `False` y toda la sesión corre en modo JSON.
- **D-04:** No hay reintento por query — el modo (Postgres vs JSON) se determina una vez al arranque y no cambia mid-sesión. Simple y predecible.
- **D-05:** `config.py` NO debe incluir `DATABASE_URL` en `_CLAVES_REQUERIDAS` — es opcional. Leerlo con `os.getenv("DATABASE_URL")` sin validación de fallo.

### guardar_memoria() Strategy (Fase 1)
- **D-06:** Doble escritura: `guardar_memoria()` sigue escribiendo `memoria.json` + subiendo a Drive (igual que antes), Y ADEMÁS sincroniza catálogo/inventario a Postgres si `DB_DISPONIBLE`. Drive sigue siendo la fuente de verdad durante la migración.
- **D-07:** La sincronización a Postgres en `guardar_memoria()` usa UPSERT (ON CONFLICT DO UPDATE) — segura de llamar múltiples veces.

### Migration Script (migrate_memoria.py)
- **D-08:** Ejecución manual vía Railway shell: `railway run python migrate_memoria.py`. Se ejecuta una sola vez después del primer deploy de Fase 1 (cuando el schema ya existe).
- **D-09:** Script usa UPSERT (ON CONFLICT DO UPDATE) — seguro re-ejecutar si algo falla a mitad.
- **D-10:** Flujo de deploy: (1) deploy código → db.py crea schema, (2) `railway run python migrate_memoria.py`, (3) verificar `/precios` e `/inventario`, (4) done.

### Pool de Conexiones
- **D-11:** Usar `psycopg2.pool.ThreadedConnectionPool` (no asyncpg) — el bot usa threading, no asyncio puro.

### Claude's Discretion
- Tamaño del pool (mínimo/máximo conexiones) — ajustar según carga Railway
- Timeout de conexión y reintentos del pool
- Exacta API del context manager en `db.py` (`query_one`, `query_all`, `execute`, `execute_returning`)
- Normalización de campos al migrar (ej. campos vacíos vs None)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Schema y Migración
- `MIGRATION.md` — Schema SQL completo de todas las tablas, script de migración `migrate_memoria.py` de ejemplo, plan detallado por fase
- `MIGRATION.md` §"Schema de PostgreSQL" — sentencias CREATE TABLE para las 17 tablas del sistema
- `MIGRATION.md` §"Script de migración inicial (Fase 1)" — patrón UPSERT para productos, fracciones, precio_cantidad, alias, inventario

### Código a Modificar
- `memoria.py` — Interfaz pública (`cargar_memoria()`, `guardar_memoria()`) que NO puede cambiar en firma; refactorizar internamente
- `fuzzy_match.py` — `construir_indice(catalogo: dict)` acepta un dict; cambiar de dónde viene ese dict
- `config.py` — Agregar `DATABASE_URL = os.getenv("DATABASE_URL")` SIN incluirlo en `_CLAVES_REQUERIDAS`
- `start.py` — Punto de entrada; `init_db()` debe llamarse antes de `_restaurar_memoria()`

### Requisitos
- `REQUIREMENTS.md` §"Infraestructura DB" — DB-01 a DB-04
- `REQUIREMENTS.md` §"Catálogo e Inventario (Fase 1)" — CAT-01 a CAT-07

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `memoria.py::_cache_lock` (threading.Lock): proteger acceso al cache; el mismo lock debe proteger la flag `DB_DISPONIBLE`
- `memoria.py::_cache` (dict | None): cache en RAM ya existe; cuando DB_DISPONIBLE=True, `cargar_memoria()` construye este dict desde Postgres en lugar del JSON
- `fuzzy_match.py::construir_indice(catalogo: dict)`: ya acepta un dict — solo cambiar de dónde viene ese dict; interfaz no cambia
- `config.py::COLOMBIA_TZ`, `config.py::MEMORIA_FILE`: usar en db.py y migrate_memoria.py sin cambiar

### Established Patterns
- Thread-safety vía `threading.Lock` en `memoria.py` y `config.py` — `db.py` debe usar `ThreadedConnectionPool` y proteger `DB_DISPONIBLE` con lock si se modifica post-arranque
- Logging por módulo: `logger = logging.getLogger("ferrebot.db")` — seguir la convención
- Validación de env vars en `config.py` al importar — `DATABASE_URL` es excepción (opcional)
- `_bloquear_subida_drive` pattern en `memoria.py`: útil para la migración inicial (no subir mientras se está migrando)

### Integration Points
- `start.py` llama `_restaurar_memoria()` al arrancar — `init_db()` debe ejecutarse ANTES de esta llamada
- `handlers/comandos.py` llama `cargar_memoria()` y `guardar_memoria()` — interfaz pública no cambia
- `handlers/alias_handler.py` y `ai.py` usan `buscar_producto_en_catalogo()` de `memoria.py` — esa función también debe funcionar desde Postgres
- `fuzzy_match.py::construir_indice()` se llama desde `invalidar_cache_memoria()` en `memoria.py` y desde `main.py` al arrancar

</code_context>

<specifics>
## Specific Ideas

- El flag `DB_DISPONIBLE` actúa igual que `_DRIVE_DISPONIBLE` en `config.py` — buen modelo a seguir para la implementación
- El warning "Postgres no disponible — modo JSON" debe loggearse al nivel WARNING para que sea visible en Railway logs

</specifics>

<deferred>
## Deferred Ideas

- OBS-01/02/03 (logging queries lentas, health check, métricas de pool) — v2 requirements, no Fase 1
- Migración automática si tabla vacía al arrancar — descartado, se prefiere control manual

</deferred>

---

*Phase: 01-db-infra-cat-logo-inventario*
*Context gathered: 2026-03-26*
