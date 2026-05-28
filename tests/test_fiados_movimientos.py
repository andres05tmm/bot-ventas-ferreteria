"""
tests/test_fiados_movimientos.py — Tests del nuevo flujo H-14.

Cubre la persistencia de movimientos en la tabla fiados_movimientos y la
lectura desde PG en detalle_fiado_cliente. No requiere DATABASE_URL — mock
del cursor y del cargar_memoria.
"""

# -- stdlib --
import sys
import types
from unittest.mock import MagicMock, patch

# ── Stubs (deben preceder al import del service) ─────────────────────────────
if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    import pytz
    _cfg.COLOMBIA_TZ = pytz.timezone("America/Bogota")
    _cfg.claude_client = None
    _cfg.openai_client = None
    sys.modules["config"] = _cfg

if "memoria" not in sys.modules:
    _mem = types.ModuleType("memoria")
    _mem.cargar_memoria = lambda: {"fiados": {}}
    _mem._cache = None
    _mem._cache_lock = __import__("threading").Lock()
    sys.modules["memoria"] = _mem


def _cursor_mock(rows):
    """Cursor mock con queries[] e iterador de fetchone()."""
    cur = MagicMock()
    cur.queries = []
    cur._rows = list(rows)
    def _execute(sql, params=None):
        cur.queries.append((sql, params))
    def _fetchone():
        return cur._rows.pop(0) if cur._rows else None
    cur.execute = _execute
    cur.fetchone = _fetchone
    return cur


def _conn_mock(cur):
    """Context manager que devuelve cur al entrar."""
    conn = MagicMock()
    conn.__enter__ = lambda self: conn
    conn.__exit__ = lambda self, *a: False
    cur_cm = MagicMock()
    cur_cm.__enter__ = lambda self: cur
    cur_cm.__exit__ = lambda self, *a: False
    conn.cursor = lambda: cur_cm
    conn.commit = lambda: None
    return conn


def test_guardar_movimiento_inserta_en_fiados_movimientos():
    """guardar_fiado_movimiento debe emitir INSERT en fiados_movimientos."""
    from services import fiados_service

    # 1ra fetchone: existing fiado (id=42)
    cur = _cursor_mock([{"id": 42}])
    conn = _conn_mock(cur)

    db_mod = MagicMock()
    db_mod.DB_DISPONIBLE = True
    db_mod._get_conn = MagicMock()
    db_mod._get_conn.return_value = conn

    with patch.object(fiados_service, "cargar_fiados", return_value={}), \
         patch("memoria.cargar_memoria", return_value={"fiados": {}}), \
         patch.dict(sys.modules, {"db": db_mod}):
        saldo_nuevo = fiados_service.guardar_fiado_movimiento(
            "Pedro Lopez", "Pintura", cargo=50000, abono=0,
        )

    assert saldo_nuevo == 50000
    # Debe haber emitido un INSERT en fiados_movimientos
    sqls = [q[0] for q in cur.queries]
    assert any("INSERT INTO fiados_movimientos" in s for s in sqls)
    # Y el UPDATE del saldo en fiados
    assert any("UPDATE fiados SET saldo_actual" in s for s in sqls)


def test_guardar_movimiento_crea_fiado_si_no_existe():
    """Si SELECT id devuelve None, debe hacer INSERT en fiados antes del movimiento."""
    from services import fiados_service

    # 1ra fetchone: SELECT id retorna None (no existe)
    # 2da fetchone: INSERT RETURNING id retorna {"id": 99}
    cur = _cursor_mock([None, {"id": 99}])
    conn = _conn_mock(cur)

    db_mod = MagicMock()
    db_mod.DB_DISPONIBLE = True
    db_mod._get_conn.return_value = conn

    with patch.object(fiados_service, "cargar_fiados", return_value={}), \
         patch("memoria.cargar_memoria", return_value={"fiados": {}}), \
         patch.dict(sys.modules, {"db": db_mod}):
        fiados_service.guardar_fiado_movimiento(
            "Cliente Nuevo", "Tornillos", cargo=15000, abono=0,
        )

    sqls = [q[0] for q in cur.queries]
    assert any("INSERT INTO fiados" in s and "RETURNING id" in s for s in sqls)
    assert any("INSERT INTO fiados_movimientos" in s for s in sqls)


def test_listar_movimientos_cliente_lee_desde_pg():
    """listar_movimientos_cliente debe consultar fiados_movimientos por fiado_id."""
    from services import fiados_service

    db_mod = MagicMock()
    db_mod.DB_DISPONIBLE = True
    db_mod.query_all = MagicMock(return_value=[
        {
            "fecha": "2026-05-27",
            "hora": "14:30:00",
            "concepto": "Pintura",
            "cargo": 50000,
            "abono": 0,
            "saldo_resultante": 50000,
        },
    ])

    with patch.dict(sys.modules, {"db": db_mod}):
        movs = fiados_service.listar_movimientos_cliente(42, limit=10)

    assert len(movs) == 1
    assert movs[0]["concepto"] == "Pintura"
    assert movs[0]["cargo"] == 50000.0
    assert movs[0]["saldo"] == 50000.0
    # La query debe filtrar por fiado_id con LIMIT
    sql_called, params = db_mod.query_all.call_args[0]
    assert "WHERE fiado_id = %s" in sql_called
    assert "LIMIT %s" in sql_called
    assert params == (42, 10)


def test_listar_movimientos_sin_db_retorna_vacio():
    """Sin DB disponible, listar_movimientos_cliente retorna lista vacía."""
    from services import fiados_service

    db_mod = MagicMock()
    db_mod.DB_DISPONIBLE = False

    with patch.dict(sys.modules, {"db": db_mod}):
        movs = fiados_service.listar_movimientos_cliente(1, limit=10)

    assert movs == []


def test_detalle_fiado_cliente_lee_desde_pg_cuando_disponible():
    """detalle_fiado_cliente debe llamar listar_movimientos_cliente cuando hay DB."""
    from services import fiados_service

    fiados_mock = {"Pedro Lopez": {"saldo": 50000, "movimientos": []}}

    db_mod = MagicMock()
    db_mod.DB_DISPONIBLE = True
    db_mod.query_one = MagicMock(return_value={"id": 42})

    with patch.object(fiados_service, "cargar_fiados", return_value=fiados_mock), \
         patch.object(fiados_service, "listar_movimientos_cliente",
                      return_value=[{
                          "fecha": "2026-05-27", "hora": "14:30",
                          "concepto": "Pintura", "cargo": 50000,
                          "abono": 0, "saldo": 50000,
                      }]) as mock_listar, \
         patch.dict(sys.modules, {"db": db_mod}):
        resultado = fiados_service.detalle_fiado_cliente("Pedro Lopez")

    assert "Pedro Lopez" in resultado
    assert "Pintura" in resultado
    mock_listar.assert_called_once_with(42, limit=10)


def test_detalle_fiado_cliente_fallback_al_cache_si_pg_vacio():
    """Si PG no devuelve movimientos, usa el cache de memoria."""
    from services import fiados_service

    fiados_mock = {
        "Pedro Lopez": {
            "saldo": 30000,
            "movimientos": [
                {"fecha": "2026-05-26", "concepto": "Legacy", "cargo": 30000,
                 "abono": 0, "saldo": 30000},
            ],
        },
    }

    db_mod = MagicMock()
    db_mod.DB_DISPONIBLE = True
    db_mod.query_one = MagicMock(return_value={"id": 42})

    with patch.object(fiados_service, "cargar_fiados", return_value=fiados_mock), \
         patch.object(fiados_service, "listar_movimientos_cliente", return_value=[]), \
         patch.dict(sys.modules, {"db": db_mod}):
        resultado = fiados_service.detalle_fiado_cliente("Pedro Lopez")

    # Cae al cache → debe ver el movimiento legacy
    assert "Legacy" in resultado
