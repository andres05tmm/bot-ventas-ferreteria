# Phase 1: DB Infra + Catálogo + Inventario - Research

**Researched:** 2026-03-26
**Domain:** PostgreSQL integration (psycopg2), Python threading, Railway deployment
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema Deployment**
- D-01: `db.py` ejecuta `CREATE TABLE IF NOT EXISTS` para todas las tablas al iniciar (`_init_schema()`). Cero pasos manuales.
- D-02: Usar el SQL de `MIGRATION.md` como fuente del schema. Las sentencias deben ser idempotentes (IF NOT EXISTS).

**Fallback Mechanism**
- D-03: Flag global `DB_DISPONIBLE = False` en `db.py`. Al arrancar, `init_db()` intenta conectar al pool. Si `DATABASE_URL` no está o la conexión falla, `DB_DISPONIBLE` queda en `False` y toda la sesión corre en modo JSON.
- D-04: No hay reintento por query — el modo (Postgres vs JSON) se determina una vez al arranque y no cambia mid-sesión.
- D-05: `config.py` NO debe incluir `DATABASE_URL` en `_CLAVES_REQUERIDAS` — es opcional. Leerlo con `os.getenv("DATABASE_URL")` sin validación de fallo.

**guardar_memoria() Strategy (Fase 1)**
- D-06: Doble escritura: `guardar_memoria()` sigue escribiendo `memoria.json` + subiendo a Drive (igual que antes), Y ADEMÁS sincroniza catálogo/inventario a Postgres si `DB_DISPONIBLE`. Drive sigue siendo la fuente de verdad durante la migración.
- D-07: La sincronización a Postgres en `guardar_memoria()` usa UPSERT (ON CONFLICT DO UPDATE) — segura de llamar múltiples veces.

**Migration Script**
- D-08: Ejecución manual vía Railway shell: `railway run python migrate_memoria.py`. Se ejecuta una sola vez después del primer deploy de Fase 1.
- D-09: Script usa UPSERT (ON CONFLICT DO UPDATE) — seguro re-ejecutar si algo falla a mitad.
- D-10: Flujo de deploy: (1) deploy código → db.py crea schema, (2) `railway run python migrate_memoria.py`, (3) verificar `/precios` e `/inventario`, (4) done.

**Pool de Conexiones**
- D-11: Usar `psycopg2.pool.ThreadedConnectionPool` (no asyncpg) — el bot usa threading, no asyncio puro.

### Claude's Discretion
- Tamaño del pool (mínimo/máximo conexiones) — ajustar según carga Railway
- Timeout de conexión y reintentos del pool
- Exacta API del context manager en `db.py` (`query_one`, `query_all`, `execute`, `execute_returning`)
- Normalización de campos al migrar (ej. campos vacíos vs None)

### Deferred Ideas (OUT OF SCOPE)
- OBS-01/02/03 (logging queries lentas, health check, métricas de pool) — v2 requirements, no Fase 1
- Migración automática si tabla vacía al arrancar — descartado, se prefiere control manual
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DB-01 | Sistema puede conectarse a PostgreSQL usando `DATABASE_URL` desde variables de entorno de Railway | `db.py` con `ThreadedConnectionPool` + `os.getenv("DATABASE_URL")` |
| DB-02 | Módulo `db.py` centraliza todo el acceso a Postgres con context manager, `query_one`, `query_all`, `execute`, `execute_returning` | Patrón documentado en MIGRATION.md; `RealDictCursor` para rows como dicts |
| DB-03 | Schema completo creado en Railway: 17 tablas | SQL completo en MIGRATION.md; `_init_schema()` en `db.py` lo ejecuta al arrancar |
| DB-04 | Sistema arranca sin errores cuando `DATABASE_URL` está presente, y sigue funcionando (con fallback) si no está | Flag `DB_DISPONIBLE`; patrón modelado en `config._DRIVE_DISPONIBLE` |
| CAT-01 | Script `migrate_memoria.py` migra ~576 productos a tabla `productos` con fracciones y precios por cantidad | Script ejemplo en MIGRATION.md; UPSERT idempotente |
| CAT-02 | Script migra alias de productos a tabla `productos_alias` | Requiere migrar `mem["catalogo"][clave].get("alias", [])` — ver análisis de estructura |
| CAT-03 | Script migra inventario a tabla `inventario` | Script ejemplo en MIGRATION.md cubre esto |
| CAT-04 | `memoria.py` lee catálogo desde Postgres manteniendo firma pública de `cargar_memoria()` y `guardar_memoria()` | Refactor interno; `_cache` ya existe; 151 referencias externas no cambian |
| CAT-05 | `fuzzy_match.py` construye el índice de búsqueda leyendo productos desde Postgres | `construir_indice(catalogo: dict)` ya acepta dict; solo cambia de dónde viene ese dict |
| CAT-06 | Comandos `/precios`, `/buscar`, `/inventario` funcionan igual que antes | Preservar interfaz de `buscar_producto_en_catalogo()`; test_suite.py verifica |
| CAT-07 | `test_suite.py` pasa 1096+ tests después de Fase 1 | Test suite inyecta `_mem._cache` directamente — compatible con refactor interno |
</phase_requirements>

---

## Summary

Esta fase establece la fundación de la migración: crear `db.py` como módulo central de acceso a PostgreSQL con `ThreadedConnectionPool` (psycopg2 sync, compatible con el modelo de threading del bot), desplegar el schema completo (17 tablas) en Railway de forma idempotente al arrancar, y refactorizar `memoria.py` internamente para que `cargar_memoria()` lea el catálogo e inventario desde Postgres cuando `DB_DISPONIBLE=True`.

El riesgo principal es cero: el flag `DB_DISPONIBLE` sigue exactamente el mismo patrón que `config._DRIVE_DISPONIBLE` ya establecido en el proyecto. Si Postgres no está o falla, el bot corre en modo JSON exactamente igual que antes. La interfaz pública de `memoria.py` (`cargar_memoria()`, `guardar_memoria()`, `buscar_producto_en_catalogo()`) no cambia en firma — solo la implementación interna. El `test_suite.py` inyecta `_mem._cache` directamente, lo que hace que los tests sean completamente agnósticos a la fuente de datos.

La estructura de `memoria.json["catalogo"]` tiene campos adicionales no todos documentados en el schema SQL de MIGRATION.md: `alias` es una lista en el dict del producto (no se extrae en el ejemplo de `migrate_memoria.py`). La migración de alias (CAT-02) requiere iterar sobre `prod.get("alias", [])` además de las tablas de fracciones y precios por cantidad.

**Primary recommendation:** Implementar `db.py` primero (con pool + `_init_schema()` + fallback), luego refactorizar `memoria.py` para leer desde Postgres cuando disponible, luego escribir `migrate_memoria.py` completo incluyendo alias.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg2-binary | >=2.9.9 (latest: 2.9.11) | Adaptador PostgreSQL sync para Python | Única opción sync compatible con threading del bot; asyncpg descartado por decisión D-11 |
| psycopg2.pool.ThreadedConnectionPool | incluido en psycopg2 | Pool de conexiones thread-safe | Thread-safe, sync, no requiere asyncio |
| psycopg2.extras.RealDictCursor | incluido en psycopg2 | Rows como dict en lugar de tuplas | Patrón ya definido en MIGRATION.md |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| contextlib.contextmanager | stdlib | Context manager para `get_conn()` | Garantiza commit/rollback/close |
| threading.Lock | stdlib | Proteger flag `DB_DISPONIBLE` | Si se modifica post-arranque; de lo contrario innecesario (se fija una sola vez) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psycopg2 sync | asyncpg | asyncpg es más rápido pero requiere asyncio event loop — incompatible con threading del bot (D-11 locked) |
| ThreadedConnectionPool | SimpleConnectionPool | SimpleConnectionPool no es thread-safe; ThreadedConnectionPool es el estándar para apps multi-hilo |
| RealDictCursor | NamedTupleCursor | RealDictCursor da rows como dict — más fácil de usar, menos riesgo de indexación errónea |

**Installation:**
```bash
pip install psycopg2-binary>=2.9.9
```

Agregar a `requirements.txt`:
```
psycopg2-binary>=2.9.9
```

**Version verification:** psycopg2-binary 2.9.11 es la versión actual (publicada octubre 2025). La especificación `>=2.9.9` en requirements.txt es correcta.

---

## Architecture Patterns

### Recommended Project Structure

Los archivos nuevos/modificados de esta fase:

```
bot-ventas-ferreteria/
├── db.py                    # NUEVO — módulo central PostgreSQL
├── migrate_memoria.py       # NUEVO — script de migración única
├── memoria.py               # MODIFICAR — refactor interno, interfaz igual
├── config.py                # MODIFICAR — agregar DATABASE_URL (opcional)
└── start.py                 # MODIFICAR — llamar init_db() antes de _restaurar_memoria()
```

### Pattern 1: db.py con ThreadedConnectionPool + Flag DB_DISPONIBLE

**What:** Módulo centralizado con pool de conexiones thread-safe. Al importar ejecuta `init_db()` que intenta conectar; si falla, `DB_DISPONIBLE` queda en `False` y las funciones del módulo degradan a no-ops seguros (retornan None/lista vacía).

**When to use:** Toda lectura/escritura a Postgres pasa por este módulo. Nada importa psycopg2 directamente.

**Example:**
```python
# Source: MIGRATION.md + decisiones D-03, D-11
import os
import logging
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

logger = logging.getLogger("ferrebot.db")

_pool: ThreadedConnectionPool | None = None
DB_DISPONIBLE: bool = False

def init_db() -> bool:
    """
    Inicializa el pool de conexiones.
    Llamar desde start.py ANTES de _restaurar_memoria().
    Retorna True si la conexión fue exitosa.
    """
    global _pool, DB_DISPONIBLE
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL no configurado — modo JSON activo")
        return False
    try:
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=database_url,
            cursor_factory=RealDictCursor,
            connect_timeout=5,
        )
        # Verificar conectividad real
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        DB_DISPONIBLE = True
        logger.info("PostgreSQL conectado — modo DB activo")
        _init_schema()
        return True
    except Exception as e:
        logger.warning(f"Postgres no disponible — modo JSON: {e}")
        DB_DISPONIBLE = False
        return False


def _init_schema():
    """Crea todas las tablas si no existen. Idempotente."""
    # SQL completo de MIGRATION.md
    ...


@contextmanager
def _get_conn():
    """Obtiene conexión del pool. Thread-safe."""
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def query_one(sql: str, params=None) -> dict | None:
    if not DB_DISPONIBLE:
        return None
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def query_all(sql: str, params=None) -> list[dict]:
    if not DB_DISPONIBLE:
        return []
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute(sql: str, params=None) -> int:
    if not DB_DISPONIBLE:
        return 0
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def execute_returning(sql: str, params=None) -> dict | None:
    if not DB_DISPONIBLE:
        return None
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
```

**Pool sizing (Claude's Discretion):** Railway PostgreSQL Free tier soporta ~5 conexiones simultáneas (el valor exacto depende del plan). `minconn=1, maxconn=5` es seguro. Si el plan es Hobby/Pro, puede subirse a `maxconn=10`.

**connect_timeout:** 5 segundos es suficiente para detectar fallo rápido al arranque. No usar timeout muy corto (< 3s) en Railway donde la primera conexión puede tardar por cold start.

### Pattern 2: memoria.py — Refactor Interno con Fallback

**What:** `cargar_memoria()` construye el dict `_cache` desde Postgres cuando `DB_DISPONIBLE=True`, manteniendo exactamente la misma estructura de dict que el JSON actual. Los callers externos (`handlers/comandos.py`, `ai.py`, `alias_handler.py`) no saben nada del cambio.

**When to use:** Toda la lógica de "leer de Postgres vs JSON" vive aquí. El `_cache` es la misma estructura dict de siempre.

**Critical:** El `test_suite.py` inyecta `_mem._cache` directamente (línea 1061-1063). El refactor de `cargar_memoria()` es 100% compatible porque el cache sigue siendo el mismo dict — solo cambia cómo se construye.

**Example:**
```python
# Source: análisis de memoria.py + decisiones D-04, D-06
def cargar_memoria() -> dict:
    global _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
        # Intentar cargar desde Postgres si disponible
        import db as _db
        if _db.DB_DISPONIBLE:
            _cache = _cargar_desde_postgres()
        else:
            # Fallback: comportamiento anterior exacto
            if os.path.exists(config.MEMORIA_FILE):
                with open(config.MEMORIA_FILE, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
            else:
                _cache = _empty_memoria()
        return _cache


def _cargar_desde_postgres() -> dict:
    """Construye el dict de memoria con catálogo e inventario desde Postgres."""
    import db as _db
    # Cargar estructura base desde JSON si existe (para campos que aún no migran: gastos, caja, etc.)
    if os.path.exists(config.MEMORIA_FILE):
        with open(config.MEMORIA_FILE, "r", encoding="utf-8") as f:
            base = json.load(f)
    else:
        base = _empty_memoria()

    # Sobreescribir catálogo e inventario con datos de Postgres
    base["catalogo"] = _leer_catalogo_postgres(_db)
    base["inventario"] = _leer_inventario_postgres(_db)
    return base
```

**Importante — lazy import de `db`:** Para evitar importación circular al arrancar, importar `db` con `import db as _db` DENTRO de las funciones, no en el top-level de `memoria.py`.

### Pattern 3: guardar_memoria() — Doble Escritura

**What:** Agrega sincronización a Postgres (UPSERT) al final de la escritura existente. Si Postgres falla, la escritura JSON/Drive sigue siendo la fuente de verdad.

**When to use:** Decisión D-06 — durante Fase 1, Drive sigue siendo la fuente de verdad.

**Example:**
```python
# Source: decisiones D-06, D-07
def guardar_memoria(memoria: dict, urgente: bool = False):
    # ... comportamiento existente sin cambios ...
    _guardar_json_y_drive(memoria, urgente)

    # Sincronización adicional a Postgres (si disponible)
    import db as _db
    if _db.DB_DISPONIBLE:
        try:
            _sincronizar_catalogo_postgres(memoria.get("catalogo", {}), _db)
            _sincronizar_inventario_postgres(memoria.get("inventario", {}), _db)
        except Exception as e:
            logger.warning(f"Error sincronizando a Postgres (no crítico): {e}")
```

### Pattern 4: start.py — Orden de Inicialización

**What:** `init_db()` debe llamarse después de configurar logging y cargar `config`, pero ANTES de `_restaurar_memoria()`.

**When to use:** Este orden es crítico: si `init_db()` corre después de `_restaurar_memoria()`, el primer `cargar_memoria()` ya se ejecutó en modo JSON y el cache queda sin datos de Postgres.

**Example:**
```python
# Source: decisión D-03 + análisis de start.py
import config  # ya está en start.py

# NUEVO — agregar estas líneas después del import config:
import db as _db
_db.init_db()  # determina DB_DISPONIBLE una vez; no falla si DATABASE_URL ausente

_restaurar_memoria()  # ahora puede usar DB_DISPONIBLE ya fijado
```

### Pattern 5: migrate_memoria.py — Estructura de Alias

**What:** El script de MIGRATION.md no incluye la migración de aliases. `memoria.json["catalogo"][clave]` puede tener un campo `"alias"` (lista de strings). Estos deben insertarse en `productos_alias`.

**When to use:** CAT-02 requiere esto explícitamente.

**Example:**
```python
# Source: análisis de estructura memoria.json + schema MIGRATION.md
# Después de insertar el producto y obtener prod_id:
for alias_str in prod.get("alias", []):
    if alias_str and alias_str.strip():
        db.execute("""
            INSERT INTO productos_alias (producto_id, alias)
            VALUES (%s, %s)
            ON CONFLICT (alias) DO NOTHING
        """, (prod_id, alias_str.strip()))
```

**Nota:** `ON CONFLICT (alias) DO NOTHING` es correcto — `alias` tiene `UNIQUE` constraint en el schema. Si el mismo alias existe para otro producto (duplicado en JSON), se silencia el conflicto.

### Anti-Patterns to Avoid

- **Importar psycopg2 directamente en otros módulos:** Todo acceso a Postgres debe ir por `db.py`. Facilita testeo y centraliza el manejo de errores.
- **Verificar `DB_DISPONIBLE` en cada función de `memoria.py`:** Verificar una vez en `cargar_memoria()` y construir el `_cache` completo. Los callers posteriores usan el cache sin saber la fuente.
- **No proteger `DB_DISPONIBLE` con lock:** Según D-04 el modo se fija una vez al arranque y no cambia mid-sesión, por lo que el lock es innecesario para `DB_DISPONIBLE` en `db.py`. El `_cache_lock` de `memoria.py` ya es suficiente para proteger el cache.
- **Modificar la firma de `cargar_memoria()` o `guardar_memoria()`:** El CONTEXT.md dice explícitamente que hay 151 referencias externas. No agregar parámetros opcionales si no son necesarios.
- **Incluir `DATABASE_URL` en `_CLAVES_REQUERIDAS` de config.py:** Decisión D-05 — es opcional. Agregarlo ahí haría fallar el bot en Railway si Postgres no está configurado.
- **Abrir/cerrar conexiones individuales en cada operación (patrón `get_conn()` sin pool):** El MIGRATION.md muestra un ejemplo sin pool. Para producción con threading, usar `ThreadedConnectionPool` (D-11).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pool de conexiones thread-safe | Pool manual con dict de conexiones | `psycopg2.pool.ThreadedConnectionPool` | Maneja concurrencia, timeout, reconexión automática |
| Rows como dicts | Mapeo manual de índice a nombre de columna | `RealDictCursor` en el pool | Sin riesgo de desincronización entre query y mapping |
| Queries parametrizadas seguras | Formateo de strings con f-strings | Parámetros `%s` de psycopg2 | Previene SQL injection; psycopg2 escapa correctamente |
| Schema idempotente | Verificar si tabla existe antes de crear | `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` | Estándar SQL, seguro de re-ejecutar |
| UPSERT | SELECT + UPDATE/INSERT manual | `INSERT ... ON CONFLICT DO UPDATE` | Atómico, thread-safe |

**Key insight:** El patrón más importante es el "dead mode" para el fallback: cuando `DB_DISPONIBLE=False`, cada función del módulo `db.py` retorna un valor vacío seguro (None/[]/0) en lugar de lanzar excepción. Esto permite que `memoria.py` use `db.query_all(...)` sin envolver cada llamada en try/except adicional.

---

## Runtime State Inventory

> Esta fase es una migración. Se aplica el inventario completo.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `memoria.json` en Google Drive (catálogo ~576 productos, inventario, gastos, caja) | Script `migrate_memoria.py` copia datos de `memoria.json` local → Postgres via UPSERT. No elimina Drive. |
| Live service config | Railway PostgreSQL — configurado al crear la DB en Railway, provee `DATABASE_URL` como variable de entorno automática | Ninguno — Railway la inyecta al deploy |
| OS-registered state | Ninguno — aplicación stateless en Railway containers | None — verificado por análisis de start.py |
| Secrets/env vars | `DATABASE_URL` — nuevo, Railway lo crea automáticamente al agregar PostgreSQL al proyecto | Confirmar que Railway lo inyecta antes del primer deploy de Fase 1 |
| Build artifacts | `requirements.txt` — falta `psycopg2-binary>=2.9.9` | Agregar al archivo antes del deploy |

---

## Common Pitfalls

### Pitfall 1: import circular entre db.py y memoria.py

**What goes wrong:** Si `db.py` importa `config` y `memoria.py` importa `db` al top-level, y `config` importa algo que importa `memoria`, se puede crear un ciclo en ciertos órdenes de carga.

**Why it happens:** Python resuelve imports en el orden en que se encuentran. Si `memoria.py` importa `db` en el top-level y `db.py` importa `config`, y `config.py` inicializa clientes que a su vez importan `memoria`, hay ciclo.

**How to avoid:** Importar `db` de forma lazy (dentro de las funciones que lo usan, no en el top-level de `memoria.py`). El patrón `import db as _db` dentro de `cargar_memoria()` y `guardar_memoria()` evita el ciclo. El CONTEXT.md documenta este patrón explícitamente en Established Patterns.

**Warning signs:** `ImportError: cannot import name 'X' from partially initialized module` al arrancar.

### Pitfall 2: ThreadedConnectionPool sin putconn() — connection leak

**What goes wrong:** Si se olvida llamar `_pool.putconn(conn)` al finalizar (especialmente en rutas de error), el pool se agota y el bot se cuelga silenciosamente.

**Why it happens:** A diferencia de una conexión simple que se puede cerrar, el pool requiere devolver la conexión explícitamente.

**How to avoid:** Usar exclusivamente el `@contextmanager` `_get_conn()` con try/finally. Nunca obtener conexiones con `_pool.getconn()` directamente fuera del context manager.

**Warning signs:** El bot responde en los primeros minutos pero luego empieza a timeout silenciosamente en comandos Postgres; Railway logs muestran "pool exhausted".

### Pitfall 3: _restaurar_memoria() usa el cache antes de que Postgres esté listo

**What goes wrong:** Si `init_db()` se llama DESPUÉS de `_restaurar_memoria()`, la primera llamada a `cargar_memoria()` (dentro de `_restaurar_memoria()`) ya construyó el cache en modo JSON y lo guardó en `_cache`. Las llamadas posteriores retornan ese cache JSON aunque `DB_DISPONIBLE` sea True.

**Why it happens:** `cargar_memoria()` tiene un early return si `_cache is not None` (línea 32 de memoria.py actual). Si el cache se pobló antes de que `DB_DISPONIBLE=True`, ya no se vuelve a consultar Postgres.

**How to avoid:** En `start.py`, llamar `init_db()` ANTES de `_restaurar_memoria()`. Orden correcto: logging → config → `init_db()` → `_restaurar_memoria()`.

**Warning signs:** El bot arranca con `DB_DISPONIBLE=True` en logs pero `/precios` devuelve datos vacíos si `memoria.json` no existe en el filesystem local.

### Pitfall 4: migrate_memoria.py falla silenciosamente en fracciones sin ON CONFLICT robusto

**What goes wrong:** `productos_fracciones` no tiene UNIQUE constraint en `(producto_id, fraccion)` en el schema de MIGRATION.md. El `ON CONFLICT DO NOTHING` del ejemplo funciona con UNIQUE constraints implícitos, pero si no existe constraint, el ON CONFLICT no aplica y se insertan duplicados en re-ejecuciones.

**Why it happens:** El schema define `productos_fracciones` sin UNIQUE constraint explícito en `(producto_id, fraccion)`.

**How to avoid:** Agregar índice único en `_init_schema()` o en el script:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_prod_fraccion
    ON productos_fracciones(producto_id, fraccion);
```
O cambiar la estrategia de inserción de fracciones a DELETE + INSERT por producto (más simple en Fase 1).

**Warning signs:** Después de re-ejecutar `migrate_memoria.py`, la tabla `productos_fracciones` tiene el doble de filas esperadas.

### Pitfall 5: test_suite.py falla si db module se importa sin DATABASE_URL

**What goes wrong:** Si `db.py` falla al importar (no al llamar `init_db()`) cuando `DATABASE_URL` no está presente, el test_suite.py —que mockea `config` pero no `db`— falla con ImportError al cargar `memoria.py`.

**Why it happens:** El test suite usa `mock.patch.dict(sys.modules, {"config": mock.MagicMock()})` pero no mockea `db`.

**How to avoid:** `db.py` debe importar correctamente incluso sin `DATABASE_URL`. La inicialización del pool solo ocurre en `init_db()`, no al importar el módulo. Al importar, `DB_DISPONIBLE = False` y `_pool = None` — sin errores.

**Warning signs:** `test_suite.py` empieza a fallar en "Sección 1 FUZZY SEARCH" con `ImportError` o `AttributeError` relacionado a `db`.

### Pitfall 6: Alias duplicados en memoria.json

**What goes wrong:** Si el mismo string de alias aparece en dos productos distintos del catálogo, el UPSERT en `productos_alias` con `ON CONFLICT (alias) DO NOTHING` inserta el primero y silencia el segundo. El segundo producto pierde su alias.

**Why it happens:** La constraint `UNIQUE(alias)` en el schema previene duplicados, pero el JSON puede tener inconsistencias históricas.

**How to avoid:** En `migrate_memoria.py`, loggear un WARNING cuando se silencia un conflicto de alias (cambiar `DO NOTHING` por un bloque que detecte y logee). No es un error crítico para Fase 1.

**Warning signs:** Alias que funcionaban antes de la migración no encuentran el producto correcto.

---

## Code Examples

Verified patterns from official sources and MIGRATION.md:

### ThreadedConnectionPool initialization (psycopg2 docs pattern)
```python
# Source: psycopg2 docs + MIGRATION.md adaptado con pool
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

_pool = ThreadedConnectionPool(
    minconn=1,
    maxconn=5,
    dsn=os.getenv("DATABASE_URL"),
    cursor_factory=RealDictCursor,
    connect_timeout=5,
)
```

### Context manager con pool (patrón correcto para thread-safety)
```python
# Source: análisis de patrones psycopg2 + MIGRATION.md
@contextmanager
def _get_conn():
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)  # SIEMPRE devolver al pool
```

### UPSERT de producto (patrón migrate_memoria.py)
```python
# Source: MIGRATION.md §"Script de migración inicial (Fase 1)"
row = db.execute_returning("""
    INSERT INTO productos (clave, nombre, nombre_lower, categoria, precio_unidad, unidad_medida)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (clave) DO UPDATE SET
        nombre = EXCLUDED.nombre,
        nombre_lower = EXCLUDED.nombre_lower,
        precio_unidad = EXCLUDED.precio_unidad,
        updated_at = NOW()
    RETURNING id
""", (
    clave,
    prod["nombre"],
    prod.get("nombre_lower", prod["nombre"].lower()),
    prod.get("categoria") or "",
    prod.get("precio_unidad", 0),
    prod.get("unidad_medida", "Unidad"),
))
prod_id = row["id"]
```

### Construcción del catalogo dict desde Postgres (para cargar_memoria)
```python
# Source: análisis de estructura memoria.json + schema MIGRATION.md
def _leer_catalogo_postgres(db_module) -> dict:
    """
    Reconstruye memoria["catalogo"] desde Postgres.
    La estructura dict debe ser IDÉNTICA a la que tenía el JSON.
    """
    productos = db_module.query_all("SELECT * FROM productos WHERE activo = TRUE")
    fracciones = db_module.query_all("SELECT * FROM productos_fracciones")
    precios_cant = db_module.query_all("SELECT * FROM productos_precio_cantidad")
    aliases = db_module.query_all("SELECT * FROM productos_alias")

    # Indexar por producto_id para joins eficientes en Python
    frac_by_prod = {}
    for f in fracciones:
        frac_by_prod.setdefault(f["producto_id"], []).append(f)

    pxc_by_prod = {p["producto_id"]: p for p in precios_cant}
    alias_by_prod = {}
    for a in aliases:
        alias_by_prod.setdefault(a["producto_id"], []).append(a["alias"])

    catalogo = {}
    for p in productos:
        prod_dict = {
            "nombre": p["nombre"],
            "nombre_lower": p["nombre_lower"],
            "categoria": p["categoria"] or "",
            "precio_unidad": p["precio_unidad"],
            "unidad_medida": p["unidad_medida"] or "Unidad",
        }
        # Fracciones
        if p["id"] in frac_by_prod:
            prod_dict["precios_fraccion"] = {
                f["fraccion"]: {
                    "precio": f["precio_total"],
                    "precio_unitario": f["precio_unitario"],
                }
                for f in frac_by_prod[p["id"]]
            }
        # Precio por cantidad
        if p["id"] in pxc_by_prod:
            pxc = pxc_by_prod[p["id"]]
            prod_dict["precio_por_cantidad"] = {
                "umbral": pxc["umbral"],
                "precio_bajo_umbral": pxc["precio_bajo_umbral"],
                "precio_sobre_umbral": pxc["precio_sobre_umbral"],
            }
        # Alias
        if p["id"] in alias_by_prod:
            prod_dict["alias"] = alias_by_prod[p["id"]]

        catalogo[p["clave"]] = prod_dict

    return catalogo
```

### Flag pattern modelado en config._DRIVE_DISPONIBLE (referencia existente)
```python
# Source: config.py líneas 162-196 — patrón establecido en el proyecto
# En db.py, replicar el mismo patrón (sin el setter público ya que D-04 dice que no cambia mid-sesión)
DB_DISPONIBLE: bool = False  # se fija en init_db(), no cambia después
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `get_conn()` abriendo conexión nueva por cada query | `ThreadedConnectionPool` con conexiones reutilizadas | Estándar desde psycopg2 2.x | Evita overhead de auth + TLS handshake por cada operación |
| asyncpg para apps modernas | psycopg2 sync para apps con threading | N/A — decisión arquitectural del proyecto | Compatible con `threading.Lock` y bot Telegram sin asyncio puro |
| SQL en strings directas sin pool | `RealDictCursor` + pool + context manager | N/A | Seguro, ergonómico, thread-safe |

**Deprecated/outdated:**
- `psycopg2.connect()` sin pool en cada operación: funcional pero ineficiente en apps con múltiples hilos. El MIGRATION.md muestra este patrón simplificado como referencia, pero para producción se usa `ThreadedConnectionPool`.

---

## Open Questions

1. **Estructura exacta de alias en memoria.json**
   - What we know: El schema de MIGRATION.md tiene tabla `productos_alias` con `UNIQUE(alias)`. El script de ejemplo no incluye migración de aliases.
   - What's unclear: ¿Es `prod["alias"]` siempre una lista de strings, o puede ser un string o estar ausente? ¿Hay aliases duplicados entre productos distintos en el JSON real?
   - Recommendation: `migrate_memoria.py` debe hacer `prod.get("alias", [])` defensivamente, normalizar a lista si es string, y loggear conflictos en lugar de fallar.

2. **Campos adicionales en memoria.json no cubiertos por schema**
   - What we know: El schema cubre `precio_unidad`, `nombre`, `nombre_lower`, `categoria`, `unidad_medida`, fracciones y precio_cantidad.
   - What's unclear: `memoria.json` puede tener campos extra por producto (ej. `codigo`, `notas_internas`) que no están en el schema PostgreSQL pero sí en el dict que `buscar_producto_en_catalogo()` retorna.
   - Recommendation: En `_leer_catalogo_postgres()`, incluir solo los campos del schema. Si algún handler consume campos extra, se detectará en `test_suite.py` (CAT-07). Agregar columna `codigo` al SELECT ya que el schema la tiene.

3. **Railway PostgreSQL connection limit por plan**
   - What we know: `maxconn=5` es conservador.
   - What's unclear: El plan específico de Railway del proyecto puede tener límite diferente.
   - Recommendation: Comenzar con `maxconn=5`. Si Railway logs muestran "too many connections", ajustar. Es un parámetro fácil de cambiar post-deploy.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| psycopg2-binary | db.py | ✗ (no en requirements.txt) | — | Agregar a requirements.txt antes del deploy |
| PostgreSQL en Railway | DB_DISPONIBLE=True | Pendiente — se configura en Railway dashboard | — | Fallback a JSON (D-03) |
| Python 3.11 | psycopg2-binary >=2.9.9 | ✓ (especificado en .python-version) | 3.11 | — |
| `memoria.json` local | Fallback JSON + migrate_memoria.py | ✓ (existe en repo local) | — | Script falla si no existe; bot arranca vacío |

**Missing dependencies with no fallback:**
- `psycopg2-binary` no está en `requirements.txt` — debe agregarse antes del deploy a Railway o Railway no podrá importar `db.py`.

**Missing dependencies with fallback:**
- PostgreSQL en Railway: si `DATABASE_URL` no está configurado, el bot corre en modo JSON (D-03 y D-04).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Custom test runner (`test_suite.py`) sin pytest |
| Config file | None — runner standalone |
| Quick run command | `python test_suite.py` |
| Full suite command | `python test_suite.py` (es el mismo) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | Conecta a Postgres con DATABASE_URL | smoke | `python -c "import db; db.init_db(); print(db.DB_DISPONIBLE)"` | ❌ Wave 0 |
| DB-02 | db.py expone query_one, query_all, execute, execute_returning | unit | `python -c "import db; assert hasattr(db, 'query_one')"` | ❌ Wave 0 |
| DB-03 | Schema creado en Railway (17 tablas) | smoke | `python -c "import db; db.init_db(); db.query_one('SELECT COUNT(*) FROM productos')"` | ❌ Wave 0 |
| DB-04 | Arranca sin DATABASE_URL (fallback JSON) | unit | `python test_suite.py` (ya testea memoria.py en modo JSON) | ✅ |
| CAT-01..03 | Productos, alias, inventario migrados | smoke | `railway run python migrate_memoria.py` — manual, retorna conteos | ❌ Wave 0 |
| CAT-04 | cargar_memoria() retorna catálogo correcto | unit | `python test_suite.py` — Sección 1 y 7 | ✅ |
| CAT-05 | fuzzy_match construye índice | unit | `python test_suite.py` — Sección 1 FUZZY SEARCH | ✅ |
| CAT-06 | /precios, /buscar, /inventario funcionan | integration | `python test_suite.py` (búsquedas en catálogo) | ✅ |
| CAT-07 | test_suite.py pasa 1096+ tests | full suite | `python test_suite.py` | ✅ |

### Sampling Rate
- **Per task commit:** `python test_suite.py` (verifica que el refactor no rompió nada)
- **Per wave merge:** `python test_suite.py` + smoke test manual en Railway (`/precios`)
- **Phase gate:** `python test_suite.py` 1096+ tests green antes de `/gsd:verify-work`

### Wave 0 Gaps

- [ ] Smoke tests para `db.py` — verificar conectividad y schema en Railway post-deploy
- [ ] Verificación manual de conteos post-migración (`SELECT COUNT(*) FROM productos` debe ser ~576)

*(El test_suite.py existente cubre CAT-04, CAT-05, CAT-06, CAT-07 porque inyecta `_cache` directamente y es agnóstico a la fuente de datos)*

---

## Project Constraints (from CLAUDE.md)

Directivas obligatorias que el planner debe verificar en cada tarea:

| Constraint | Directive |
|-----------|-----------|
| Driver sync | Usar `psycopg2-binary` (sync), no `asyncpg` — el bot usa threading |
| Interfaz pública | `cargar_memoria()`, `guardar_memoria()` firmas NO pueden cambiar |
| Uptime | Cada commit debe dejar el sistema funcionando (fallback JSON siempre activo) |
| Tests | `test_suite.py` 1096+ tests deben pasar después de cada tarea que modifique `memoria.py` |
| Dependencia circular | Importar `db` de forma lazy (dentro de funciones), no en top-level de `memoria.py` |
| Logging | `logger = logging.getLogger("ferrebot.db")` en `db.py` |
| DATABASE_URL | No incluir en `_CLAVES_REQUERIDAS` de `config.py` — es opcional |
| Nomenclatura | Funciones snake_case, constantes UPPER_SNAKE, privadas con `_` |
| Error handling | Excepciones amplias (`except Exception as e:`) para estabilidad del bot |
| Thread-safety | `threading.Lock` para estado compartido; `ThreadedConnectionPool` para Postgres |

---

## Sources

### Primary (HIGH confidence)
- `MIGRATION.md` del proyecto — Schema SQL completo, script de migración, módulo db.py base
- `memoria.py` — Código fuente completo; interfaces públicas verificadas
- `config.py` — Patrón `_DRIVE_DISPONIBLE` verificado (líneas 162-196)
- `start.py` — Secuencia de arranque verificada; posición de `_restaurar_memoria()`
- `fuzzy_match.py` — Firma de `construir_indice(catalogo: dict)` verificada
- `test_suite.py` — Mecánica de inyección de `_cache` verificada (líneas 1061-1063)
- `CONTEXT.md` — Todas las decisiones D-01 a D-11 verificadas

### Secondary (MEDIUM confidence)
- [psycopg2-binary PyPI](https://pypi.org/project/psycopg2-binary/) — versión 2.9.11 verificada, publicada octubre 2025
- [psycopg2 install docs](https://www.psycopg.org/docs/install.html) — ThreadedConnectionPool confirmado

### Tertiary (LOW confidence)
- Railway PostgreSQL connection limits — límites exactos por plan no verificados; `maxconn=5` conservador

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — psycopg2-binary es la única opción viable dado D-11; versión verificada en PyPI
- Architecture: HIGH — todos los patrones derivan de decisiones D-01 a D-11 + código fuente existente del proyecto
- Pitfalls: HIGH — derivados del análisis del código real (start.py, memoria.py, test_suite.py)

**Research date:** 2026-03-26
**Valid until:** 2026-09-26 (psycopg2 es estable; Railway API puede cambiar en ~6 meses)
