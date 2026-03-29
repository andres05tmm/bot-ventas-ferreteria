"""
db.py — Acceso central a PostgreSQL.
Usar este modulo en lugar de psycopg2 directamente.

CORRECCIONES v2:
  - ThreadedConnectionPool thread-safe (D-11)
  - DB_DISPONIBLE flag fijado una vez al arranque (D-04)
  - _init_schema() crea todas las tablas IF NOT EXISTS (D-01)
  - Reconexión automática si el pool devuelve una conexión rota (#1)
  - API pública lanza RuntimeError si DB_DISPONIBLE=False (#2)
"""

# -- stdlib --
import os
import logging
import threading
from contextlib import contextmanager

# ═══════════════════════════════════════════════════════════════════════════════
# MODULO-LEVEL STATE
# ═══════════════════════════════════════════════════════════════════════════════
logger = logging.getLogger("ferrebot.db")

_pool = None
_dsn: str | None = None          # guardado para reconexión
_pool_lock = threading.Lock()    # protege _pool durante reconexión
DB_DISPONIBLE: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# INICIALIZACION
# ═══════════════════════════════════════════════════════════════════════════════

def init_db() -> bool:
    """
    Inicializa el pool de conexiones.
    Llamar desde start.py ANTES de _restaurar_memoria().
    Retorna True si la conexion fue exitosa.
    """
    global _pool, _dsn, DB_DISPONIBLE
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL no configurado — DB deshabilitada")
        return False
    try:
        import psycopg2
        from psycopg2.pool import ThreadedConnectionPool
        from psycopg2.extras import RealDictCursor

        _dsn = database_url
        _pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=database_url,
            cursor_factory=RealDictCursor,
            connect_timeout=5,
            options="-c statement_timeout=8000",   # abortar queries colgadas > 8s
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
        logger.warning(f"Postgres no disponible al arrancar: {e}")
        DB_DISPONIBLE = False
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT MANAGER INTERNO
# ═══════════════════════════════════════════════════════════════════════════════

def _reconectar() -> None:
    """
    Reemplaza el pool completo con uno nuevo.
    Llamar solo cuando se detecta que las conexiones están rotas.
    """
    global _pool
    import psycopg2
    from psycopg2.pool import ThreadedConnectionPool
    from psycopg2.extras import RealDictCursor

    logger.warning("[DB] Reconectando pool de PostgreSQL...")
    try:
        _pool.closeall()
    except Exception:
        pass
    _pool = ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=_dsn,
        cursor_factory=RealDictCursor,
        connect_timeout=5,
        options="-c statement_timeout=8000",   # mismo timeout que init
    )
    logger.info("[DB] Pool reconectado exitosamente")


@contextmanager
def _get_conn():
    """
    Obtiene conexión del pool. Thread-safe.
    Si la conexión está rota (OperationalError / InterfaceError),
    reconecta el pool y reintenta una vez.
    """
    import psycopg2

    _BROKEN = (psycopg2.OperationalError, psycopg2.InterfaceError)

    with _pool_lock:
        conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except _BROKEN as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            _pool.putconn(conn, close=True)
        except Exception:
            pass
        # Reconectar y reintentar una vez
        with _pool_lock:
            _reconectar()
            conn2 = _pool.getconn()
        try:
            yield conn2
            conn2.commit()
        except Exception:
            conn2.rollback()
            raise
        finally:
            with _pool_lock:
                _pool.putconn(conn2)
        return
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            with _pool_lock:
                _pool.putconn(conn)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

def _init_schema():
    """Crea todas las tablas si no existen. Idempotente (D-01, D-02)."""
    schema_sql = """
-- ═══════════════════════════════════════════════════════════════
-- FERREBOT — Schema PostgreSQL
-- ═══════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────────────────
-- CATALOGO DE PRODUCTOS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS productos (
    id              SERIAL PRIMARY KEY,
    clave           VARCHAR(200) UNIQUE NOT NULL,
    nombre          VARCHAR(300) NOT NULL,
    nombre_lower    VARCHAR(300) NOT NULL,
    codigo          VARCHAR(100),
    categoria       VARCHAR(200),
    precio_unidad   INTEGER NOT NULL DEFAULT 0,
    unidad_medida   VARCHAR(50) DEFAULT 'Unidad',
    activo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Precios por fraccion (pinturas/disolventes: 1/4, 1/2, 3/4, etc.)
CREATE TABLE IF NOT EXISTS productos_fracciones (
    id              SERIAL PRIMARY KEY,
    producto_id     INTEGER REFERENCES productos(id) ON DELETE CASCADE,
    fraccion        VARCHAR(10) NOT NULL,
    precio_total    INTEGER NOT NULL,
    precio_unitario INTEGER NOT NULL
);

-- Precio por cantidad (tornilleria: precio distinto si compra >= umbral)
CREATE TABLE IF NOT EXISTS productos_precio_cantidad (
    id                   SERIAL PRIMARY KEY,
    producto_id          INTEGER REFERENCES productos(id) ON DELETE CASCADE UNIQUE,
    umbral               INTEGER NOT NULL DEFAULT 50,
    precio_bajo_umbral   INTEGER NOT NULL,
    precio_sobre_umbral  INTEGER NOT NULL
);

-- Alias/sinonimos de productos
CREATE TABLE IF NOT EXISTS productos_alias (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER REFERENCES productos(id) ON DELETE CASCADE,
    alias       VARCHAR(200) NOT NULL,
    UNIQUE(alias)
);

-- ───────────────────────────────────────────────────────────────
-- INVENTARIO
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inventario (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER REFERENCES productos(id) ON DELETE CASCADE UNIQUE,
    cantidad    NUMERIC(10,3) DEFAULT 0,
    minimo      NUMERIC(10,3) DEFAULT 0,
    unidad      VARCHAR(50) DEFAULT 'Unidad',
    updated_at  TIMESTAMP DEFAULT NOW()
);
-- Columnas de metadata añadidas post-v1; idempotentes en DBs ya existentes
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS nombre_original  VARCHAR(300);
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS costo_promedio   NUMERIC(12,2);
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS ultimo_costo     NUMERIC(12,2);
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS ultimo_proveedor VARCHAR(200);
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS ultima_compra    TIMESTAMP;
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS ultima_venta     TIMESTAMP;
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS ultimo_ajuste    TIMESTAMP;
ALTER TABLE inventario ADD COLUMN IF NOT EXISTS fecha_conteo     TIMESTAMP;

-- ───────────────────────────────────────────────────────────────
-- CLIENTES
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clientes (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(300) NOT NULL,
    tipo_id         VARCHAR(10),
    identificacion  VARCHAR(50),
    tipo_persona    VARCHAR(20),
    correo          VARCHAR(200),
    telefono        VARCHAR(50),
    direccion       VARCHAR(300),
    created_at      TIMESTAMP DEFAULT NOW()
);
-- Columna añadida post-v1; idempotente en DBs ya existentes
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS direccion VARCHAR(300);

-- ───────────────────────────────────────────────────────────────
-- VENTAS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ventas (
    id              SERIAL PRIMARY KEY,
    consecutivo     INTEGER NOT NULL,
    fecha           DATE NOT NULL,
    hora            TIME,
    cliente_id      INTEGER REFERENCES clientes(id),
    cliente_nombre  VARCHAR(300) DEFAULT 'Consumidor Final',
    vendedor        VARCHAR(100),
    metodo_pago     VARCHAR(50),
    total           INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (consecutivo, fecha)
);

-- Lineas de cada venta
CREATE TABLE IF NOT EXISTS ventas_detalle (
    id              SERIAL PRIMARY KEY,
    venta_id        INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id     INTEGER REFERENCES productos(id),
    producto_nombre VARCHAR(300) NOT NULL,
    cantidad        NUMERIC(10,3) NOT NULL,
    unidad_medida   VARCHAR(50) DEFAULT 'Unidad',
    precio_unitario INTEGER,
    total           INTEGER NOT NULL,
    alias_usado     VARCHAR(200)
);

-- Indices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_consecutivo ON ventas(consecutivo);
CREATE INDEX IF NOT EXISTS idx_ventas_detalle_venta ON ventas_detalle(venta_id);

-- ───────────────────────────────────────────────────────────────
-- GASTOS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gastos (
    id          SERIAL PRIMARY KEY,
    fecha       DATE NOT NULL,
    hora        TIME,
    concepto    VARCHAR(300) NOT NULL,
    monto       INTEGER NOT NULL,
    categoria   VARCHAR(100),
    origen      VARCHAR(50) DEFAULT 'bot',
    fac_id      VARCHAR(20),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);

-- ───────────────────────────────────────────────────────────────
-- CAJA
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS caja (
    id              SERIAL PRIMARY KEY,
    fecha           DATE UNIQUE NOT NULL,
    abierta         BOOLEAN DEFAULT FALSE,
    monto_apertura  INTEGER DEFAULT 0,
    efectivo        INTEGER DEFAULT 0,
    transferencias  INTEGER DEFAULT 0,
    datafono        INTEGER DEFAULT 0,
    cerrada_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- FIADOS (cuentas de credito a clientes)
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fiados (
    id          SERIAL PRIMARY KEY,
    cliente_id  INTEGER REFERENCES clientes(id),
    nombre      VARCHAR(300) NOT NULL,
    deuda       INTEGER DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fiados_historial (
    id          SERIAL PRIMARY KEY,
    fiado_id    INTEGER REFERENCES fiados(id) ON DELETE CASCADE,
    tipo        VARCHAR(20) NOT NULL,
    monto       INTEGER NOT NULL,
    concepto    VARCHAR(300),
    fecha       DATE NOT NULL,
    hora        TIME,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- FACTURAS DE PROVEEDORES (cuentas por pagar)
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facturas_proveedores (
    id              VARCHAR(20) PRIMARY KEY,
    proveedor       VARCHAR(200) NOT NULL,
    descripcion     VARCHAR(500),
    total           INTEGER NOT NULL,
    pagado          INTEGER DEFAULT 0,
    pendiente       INTEGER NOT NULL,
    estado          VARCHAR(20) DEFAULT 'pendiente',
    fecha           DATE NOT NULL,
    foto_url        TEXT DEFAULT '',
    foto_nombre     VARCHAR(300) DEFAULT '',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS facturas_abonos (
    id          SERIAL PRIMARY KEY,
    factura_id  VARCHAR(20) REFERENCES facturas_proveedores(id) ON DELETE CASCADE,
    monto       INTEGER NOT NULL,
    fecha       DATE NOT NULL,
    foto_url    TEXT DEFAULT '',
    foto_nombre VARCHAR(300) DEFAULT '',
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- HISTORICO DE VENTAS DIARIAS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS historico_ventas (
    fecha           DATE PRIMARY KEY,
    ventas          INTEGER DEFAULT 0,
    efectivo        INTEGER DEFAULT 0,
    transferencia   INTEGER DEFAULT 0,
    datafono        INTEGER DEFAULT 0,
    n_transacciones INTEGER DEFAULT 0,
    gastos          INTEGER DEFAULT 0,
    abonos_proveedores INTEGER DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- COMPRAS DE MERCANCIA
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compras (
    id              SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL,
    hora            TIME,
    proveedor       VARCHAR(200),
    producto_id     INTEGER REFERENCES productos(id),
    producto_nombre VARCHAR(300) NOT NULL,
    cantidad        NUMERIC(10,3) NOT NULL,
    costo_unitario  INTEGER,
    costo_total     INTEGER,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- PRODUCTOS PENDIENTES (no encontrados en catalogo)
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS productos_pendientes (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(300) NOT NULL,
    fecha       DATE NOT NULL,
    hora        TIME,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- CONFIGURACION DEL SISTEMA
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS config_sistema (
    clave   VARCHAR(100) PRIMARY KEY,
    valor   TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Valores iniciales
INSERT INTO config_sistema (clave, valor) VALUES
    ('keepalive_activo', 'false'),
    ('version', 'v8.0-refactor')
ON CONFLICT (clave) DO NOTHING;

-- Indice unico para fracciones (idempotente UPSERT en migrate_memoria.py)
CREATE UNIQUE INDEX IF NOT EXISTS uq_prod_fraccion
    ON productos_fracciones(producto_id, fraccion);
"""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
    logger.info("Schema PostgreSQL verificado/creado")


# ═══════════════════════════════════════════════════════════════════════════════
# API PUBLICA
# ═══════════════════════════════════════════════════════════════════════════════

def _check_db() -> None:
    """Lanza RuntimeError si la DB no está disponible. Llamar al inicio de cada función pública."""
    if not DB_DISPONIBLE:
        raise RuntimeError(
            "⚠️ Base de datos no disponible. Verifica DATABASE_URL y reinicia el servicio."
        )


def query_one(sql: str, params=None) -> dict | None:
    """Ejecuta SELECT y retorna una fila como dict, o None."""
    _check_db()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def query_all(sql: str, params=None) -> list[dict]:
    """Ejecuta SELECT y retorna todas las filas como lista de dicts."""
    _check_db()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute(sql: str, params=None) -> int:
    """Ejecuta INSERT/UPDATE/DELETE. Retorna rowcount."""
    _check_db()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def execute_returning(sql: str, params=None) -> dict | None:
    """Ejecuta INSERT ... RETURNING. Retorna la fila insertada."""
    _check_db()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


# ───────────────────────────────────────────────────────────────
# HELPERS DE VENTAS (reemplazan excel.py / sheets.py eliminados)
# ───────────────────────────────────────────────────────────────

def obtener_siguiente_consecutivo() -> int:
    """
    Retorna el siguiente consecutivo disponible para hoy (MAX + 1).
    Si no hay ventas hoy retorna 1.
    """
    import config as _cfg
    from datetime import datetime as _dt
    _check_db()
    hoy = _dt.now(_cfg.COLOMBIA_TZ).strftime("%Y-%m-%d")
    row = query_one(
        "SELECT COALESCE(MAX(consecutivo), 0) AS max_c FROM ventas WHERE fecha = %s",
        (hoy,)
    )
    return int(row["max_c"]) + 1 if row else 1


def obtener_nombre_id_cliente(termino: str) -> tuple[str, str]:
    """
    Busca cliente en la DB por nombre o identificación.
    Retorna (identificacion, nombre) o ('CF', 'Consumidor Final') si no encuentra.
    """
    if not termino:
        return "CF", "Consumidor Final"
    _check_db()
    row = query_one(
        """SELECT identificacion, nombre FROM clientes
           WHERE LOWER(nombre) LIKE LOWER(%s) OR identificacion = %s
           ORDER BY id LIMIT 1""",
        (f"%{termino}%", termino),
    )
    if row:
        return str(row.get("identificacion") or "CF"), str(row.get("nombre") or "Consumidor Final")
    return "CF", "Consumidor Final"


# ═══════════════════════════════════════════════════════════════════════════════
# WRAPPERS ASYNC — no bloquean el event loop de FastAPI/asyncio
# Uso: await db.query_all_async(sql, params)  en vez de db.query_all(sql, params)
# ═══════════════════════════════════════════════════════════════════════════════

import asyncio as _asyncio


async def query_all_async(sql: str, params=None) -> list[dict]:
    """Versión async de query_all — delega a un thread del pool para no bloquear asyncio."""
    return await _asyncio.to_thread(query_all, sql, params)


async def query_one_async(sql: str, params=None) -> dict | None:
    """Versión async de query_one."""
    return await _asyncio.to_thread(query_one, sql, params)


async def execute_async(sql: str, params=None) -> int:
    """Versión async de execute."""
    return await _asyncio.to_thread(execute, sql, params)


async def execute_returning_async(sql: str, params=None) -> dict | None:
    """Versión async de execute_returning."""
    return await _asyncio.to_thread(execute_returning, sql, params)
