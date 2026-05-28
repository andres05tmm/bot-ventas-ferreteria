"""
db.py — Acceso central a PostgreSQL.
Usar este modulo en lugar de psycopg2 directamente.

CORRECCIONES v2:
  - ThreadedConnectionPool thread-safe (D-11)
  - DB_DISPONIBLE flag fijado una vez al arranque (D-04)
  - El esquema lo gestiona Alembic (alembic upgrade head en run.sh), no este módulo
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
        # El esquema lo gestiona Alembic (run.sh corre `alembic upgrade head`
        # en el arranque del servicio API). Ya no se crea desde aquí.
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


_RETRY_POOL_INTENTOS = 3    # reintentos cuando el pool está exhausto
_RETRY_POOL_ESPERA   = 0.3  # segundos entre reintentos


@contextmanager
def _get_conn():
    """
    Obtiene conexión del pool. Thread-safe.
    Si la conexión está rota (OperationalError / InterfaceError),
    reconecta el pool y reintenta una vez.
    Si el pool está exhausto (PoolError), reintenta hasta _RETRY_POOL_INTENTOS
    veces con _RETRY_POOL_ESPERA segundos entre intentos antes de relanzar.
    """
    import time as _time
    import psycopg2
    from psycopg2.pool import PoolError as _PoolError

    _BROKEN = (psycopg2.OperationalError, psycopg2.InterfaceError)

    conn = None
    for _intento in range(_RETRY_POOL_INTENTOS):
        try:
            with _pool_lock:
                conn = _pool.getconn()
            break
        except _PoolError:
            if _intento < _RETRY_POOL_INTENTOS - 1:
                logger.warning(
                    "[DB] Pool exhausto — reintento %d/%d en %.1fs",
                    _intento + 1, _RETRY_POOL_INTENTOS, _RETRY_POOL_ESPERA,
                )
                _time.sleep(_RETRY_POOL_ESPERA)
            else:
                logger.error("[DB] Pool exhausto tras %d reintentos — abortando", _RETRY_POOL_INTENTOS)
                raise
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

    ⚠️  Esta función NO es atómica — abre y cierra su propia conexión, así que
    entre el SELECT y el INSERT siguiente otra transacción puede tomar el
    mismo número. Úsala solo para consultas informativas (mostrar al usuario).
    Para insertar una venta, usa proximo_consecutivo_atomico(cur, fecha)
    dentro de la misma transacción que el INSERT.
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


def proximo_consecutivo_atomico(cur, fecha: str) -> int:
    """
    Calcula el siguiente consecutivo de venta para la fecha dada, dentro de
    la transacción del cursor recibido. Garantiza atomicidad emitiendo
    LOCK TABLE ventas IN SHARE ROW EXCLUSIVE MODE antes del SELECT, así que
    el lock persiste hasta el commit de la transacción del caller.

    Reset diario: el consecutivo se reinicia cada día. La tabla ventas tiene
    UNIQUE (consecutivo, fecha), así que cada fecha lleva su propia secuencia.

    Args:
        cur: cursor psycopg2 dentro de una transacción en curso.
        fecha: string YYYY-MM-DD en hora Colombia (use COLOMBIA_TZ).

    Returns:
        int — siguiente consecutivo (1 si no hay ventas en la fecha).

    Uso:
        with _db._get_conn() as conn:
            with conn.cursor() as cur:
                consecutivo = _db.proximo_consecutivo_atomico(cur, hoy)
                cur.execute("INSERT INTO ventas ...", (consecutivo, ...))
    """
    cur.execute("LOCK TABLE ventas IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(
        "SELECT COALESCE(MAX(consecutivo), 0) + 1 AS siguiente "
        "FROM ventas WHERE fecha = %s",
        (fecha,),
    )
    row = cur.fetchone()
    # cursor_factory=RealDictCursor → row es dict; algunos mocks devuelven tuple
    if row is None:
        return 1
    if isinstance(row, dict):
        return int(row.get("siguiente") or 1)
    return int(row[0] or 1)


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
