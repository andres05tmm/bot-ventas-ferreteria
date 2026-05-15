"""
tests/test_search_service.py — Tests unitarios para services/search_service.py.

Mockean db.query_all con stubs que inspeccionan el SQL que llegó para garantizar
que la función arma correctamente los queries híbridos (FTS + trigram), los
parámetros, los filtros y el fallback cuando FTS devuelve pocos resultados.

No tocan Postgres real — todo es en memoria.
"""
# -- stdlib --
import os
import sys
import types
from datetime import datetime
from unittest.mock import patch

# Permitir importar desde el root del proyecto
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── STUBS de config/db para evitar conexión real a Postgres ─────────────
if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = None
    _cfg.claude_client = None
    _cfg.openai_client = None
    sys.modules["config"] = _cfg

if "db" not in sys.modules:
    _db_stub = types.ModuleType("db")
    _db_stub.DB_DISPONIBLE = False
    _db_stub.query_all = lambda *a, **kw: []
    _db_stub.query_one = lambda *a, **kw: None
    _db_stub.execute = lambda *a, **kw: None
    sys.modules["db"] = _db_stub

# Otro test (test_response_builder) puede haber inyectado un stub de
# services.search_service en sys.modules para evitar tocar Postgres.
# Acá necesitamos el módulo REAL para inspeccionarlo, así que lo evictamos
# antes del import.
sys.modules.pop("services.search_service", None)

from services import search_service as ss


# ─────────────────────────────────────────────────────────────────────────
# HELPERS: query_all spy
# ─────────────────────────────────────────────────────────────────────────

class _QuerySpy:
    """Recolecta (sql, params) de cada llamada y retorna filas canned."""
    def __init__(self, responses: list[list[dict]]):
        # responses[i] es el resultado de la i-ésima llamada a query_all
        self.responses = list(responses)
        self.calls: list[tuple[str, list]] = []

    def __call__(self, sql, params=None):
        self.calls.append((sql, list(params) if params else []))
        if self.responses:
            return self.responses.pop(0)
        return []


# ─────────────────────────────────────────────────────────────────────────
# _limpiar_query — unit
# ─────────────────────────────────────────────────────────────────────────

def test_limpiar_query_vacio():
    assert ss._limpiar_query("") == ""
    assert ss._limpiar_query(None) == ""  # type: ignore[arg-type]

def test_limpiar_query_colapsa_espacios():
    assert ss._limpiar_query("  drywall   6x1 ") == "drywall 6x1"

def test_limpiar_query_recorta_200_chars():
    largo = "x" * 500
    assert len(ss._limpiar_query(largo)) == 200


# ─────────────────────────────────────────────────────────────────────────
# _clamp — unit
# ─────────────────────────────────────────────────────────────────────────

def test_clamp_rango():
    assert ss._clamp(5, 1, 10) == 5
    assert ss._clamp(-1, 1, 10) == 1
    assert ss._clamp(999, 1, 10) == 10


# ─────────────────────────────────────────────────────────────────────────
# buscar_conversaciones
# ─────────────────────────────────────────────────────────────────────────

def test_buscar_conversaciones_query_vacia_retorna_lista_vacia():
    spy = _QuerySpy([])
    with patch.object(ss._db, "query_all", spy):
        out = ss.buscar_conversaciones("", chat_id=123)
    assert out == []
    assert len(spy.calls) == 0  # no se debe tocar la DB


def test_buscar_conversaciones_fts_suficiente_no_usa_trgm():
    filas = [
        {"id": 1, "chat_id": 10, "vendedor_id": 1, "role": "user",
         "content": "fiado juan", "creado": datetime.now(), "rank": 0.9},
        {"id": 2, "chat_id": 10, "vendedor_id": 1, "role": "assistant",
         "content": "ok juan fiado", "creado": datetime.now(), "rank": 0.8},
        {"id": 3, "chat_id": 10, "vendedor_id": 1, "role": "user",
         "content": "fiado pedro", "creado": datetime.now(), "rank": 0.7},
    ]
    spy = _QuerySpy([filas])
    with patch.object(ss._db, "query_all", spy):
        out = ss.buscar_conversaciones("fiado", chat_id=10)
    assert len(out) == 3
    assert len(spy.calls) == 1  # solo FTS, nada de trgm


def test_buscar_conversaciones_fts_pobre_suplementa_con_trgm():
    # FTS devuelve solo 1 fila → debe llamar también a trgm
    filas_fts = [{"id": 1, "chat_id": 10, "vendedor_id": 1, "role": "user",
                  "content": "drywall", "creado": datetime.now(), "rank": 0.9}]
    filas_trgm = [
        {"id": 2, "chat_id": 10, "vendedor_id": 1, "role": "user",
         "content": "drwayll", "creado": datetime.now(), "rank": 0.6},
        {"id": 3, "chat_id": 10, "vendedor_id": 1, "role": "user",
         "content": "drywal", "creado": datetime.now(), "rank": 0.55},
    ]
    spy = _QuerySpy([filas_fts, filas_trgm])
    with patch.object(ss._db, "query_all", spy):
        out = ss.buscar_conversaciones("drywall", chat_id=10)
    assert len(spy.calls) == 2, "debería haber llamado FTS y luego trgm"
    assert len(out) == 3
    # El id=1 de FTS no debe estar duplicado
    ids = [r["id"] for r in out]
    assert ids.count(1) == 1


def test_buscar_conversaciones_filtro_chat_id():
    spy = _QuerySpy([[]])
    with patch.object(ss._db, "query_all", spy):
        ss.buscar_conversaciones("hola", chat_id=12345)
    sql, params = spy.calls[0]
    assert "chat_id = %s" in sql
    assert 12345 in params


def test_buscar_conversaciones_sin_chat_id_omite_filtro():
    spy = _QuerySpy([[]])
    with patch.object(ss._db, "query_all", spy):
        ss.buscar_conversaciones("hola", chat_id=None)
    sql, _ = spy.calls[0]
    assert "chat_id = %s" not in sql


def test_buscar_conversaciones_limit_clampeado():
    spy = _QuerySpy([[]])
    with patch.object(ss._db, "query_all", spy):
        ss.buscar_conversaciones("hola", limit=9999)
    _, params = spy.calls[0]
    # Hard cap = 50 (ver _HARD_LIMIT)
    assert 50 in params


def test_buscar_conversaciones_db_error_retorna_lista_vacia():
    def _boom(*a, **kw):
        raise RuntimeError("pool agotado")
    with patch.object(ss._db, "query_all", _boom):
        out = ss.buscar_conversaciones("hola")
    assert out == []


# ─────────────────────────────────────────────────────────────────────────
# buscar_ventas_por_producto
# ─────────────────────────────────────────────────────────────────────────

def test_buscar_ventas_producto_query_vacia():
    spy = _QuerySpy([])
    with patch.object(ss._db, "query_all", spy):
        assert ss.buscar_ventas_por_producto("") == []
    assert len(spy.calls) == 0


def test_buscar_ventas_producto_arma_join():
    spy = _QuerySpy([[]])
    with patch.object(ss._db, "query_all", spy):
        ss.buscar_ventas_por_producto("drywall")
    sql, _ = spy.calls[0]
    assert "FROM ventas_detalle vd" in sql
    assert "JOIN ventas v" in sql
    assert "to_tsvector('spanish', vd.producto_nombre)" in sql


def test_buscar_ventas_producto_filtro_vendedor():
    spy = _QuerySpy([[]])
    with patch.object(ss._db, "query_all", spy):
        ss.buscar_ventas_por_producto("drywall", vendedor="andres")
    sql, params = spy.calls[0]
    assert "v.vendedor ILIKE" in sql
    assert "%andres%" in params


def test_buscar_ventas_producto_sin_vendedor():
    spy = _QuerySpy([[]])
    with patch.object(ss._db, "query_all", spy):
        ss.buscar_ventas_por_producto("drywall")
    sql, params = spy.calls[0]
    assert "v.vendedor ILIKE" not in sql


def test_buscar_ventas_producto_dedup_entre_fts_y_trgm():
    # Misma (venta_id, producto_nombre) aparece en ambas → debe aparecer solo 1 vez
    fila_comun = {
        "venta_id": 42, "consecutivo": 100, "fecha": datetime.now().date(),
        "hora": None, "cliente_nombre": "Pedro", "vendedor": "andres",
        "metodo_pago": "efectivo", "producto_nombre": "Drywall 6x1",
        "cantidad": 3, "unidad_medida": "u", "precio_unitario": 5000,
        "linea_total": 15000, "rank": 0.9,
    }
    filas_trgm = [fila_comun]  # duplicado → debe descartarse
    spy = _QuerySpy([[fila_comun], filas_trgm])
    with patch.object(ss._db, "query_all", spy):
        out = ss.buscar_ventas_por_producto("drywall")
    assert len(out) == 1, "el duplicado debería haberse filtrado"


# ─────────────────────────────────────────────────────────────────────────
# buscar_ventas_por_cliente
# ─────────────────────────────────────────────────────────────────────────

def test_buscar_ventas_cliente_usa_ilike():
    spy = _QuerySpy([[]])
    with patch.object(ss._db, "query_all", spy):
        ss.buscar_ventas_por_cliente("pedro")
    sql, params = spy.calls[0]
    assert "cliente_nombre ILIKE" in sql
    assert "%pedro%" in params


def test_buscar_ventas_cliente_vacio():
    spy = _QuerySpy([])
    with patch.object(ss._db, "query_all", spy):
        assert ss.buscar_ventas_por_cliente("") == []
    assert spy.calls == []


# ─────────────────────────────────────────────────────────────────────────
# formatear_resultados_*
# ─────────────────────────────────────────────────────────────────────────

def test_formatear_ventas_sin_resultados():
    assert "No encontré" in ss.formatear_resultados_ventas([])

def test_formatear_ventas_con_producto():
    fila = {
        "fecha": datetime(2026, 4, 17).date(), "cliente_nombre": "Pedro",
        "vendedor": "andres", "producto_nombre": "Drywall",
        "cantidad": 3, "unidad_medida": "u", "linea_total": 15000,
    }
    out = ss.formatear_resultados_ventas([fila])
    assert "2026-04-17" in out
    assert "Pedro" in out
    assert "Drywall" in out
    assert "15,000" in out  # thousands separator


def test_formatear_ventas_sin_producto_usa_total():
    fila = {
        "fecha": datetime(2026, 4, 17).date(), "consecutivo": 99,
        "cliente_nombre": "CF", "vendedor": "andres", "total": 5000,
    }
    out = ss.formatear_resultados_ventas([fila])
    assert "#99" in out
    assert "5,000" in out


def test_formatear_conversaciones():
    fila = {
        "creado": datetime(2026, 4, 17, 10, 30),
        "role": "user",
        "content": "quiero pagar el fiado",
    }
    out = ss.formatear_resultados_conversaciones([fila])
    assert "2026-04-17 10:30" in out
    assert "user" in out
    assert "quiero pagar el fiado" in out


def test_formatear_conversaciones_sin_resultados():
    assert "No encontré" in ss.formatear_resultados_conversaciones([])
