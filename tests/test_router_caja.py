"""
tests/test_router_caja.py — Cobertura básica de routers/caja.py.

Sin DB real. Nota: el router usa `import db as _db` — los patches
deben usar el alias: mocker.patch("routers.caja._db.DB_DISPONIBLE", ...).
"""
import sys
import types

# ── Stubs ANTES de cualquier import propio ────────────────────────────────────

if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = __import__("datetime").timezone.utc
    _cfg.claude_client = None
    _cfg.openai_client = None
    sys.modules["config"] = _cfg

if "db" not in sys.modules:
    _db = types.ModuleType("db")
    _db.DB_DISPONIBLE = False
    _db.query_one = lambda *a, **kw: None
    _db.query_all = lambda *a, **kw: []
    _db.execute = lambda *a, **kw: None
    sys.modules["db"] = _db

_mem_attrs = {
    "cargar_caja": lambda: {},
    "guardar_gasto": lambda *a, **kw: None,
    "cargar_gastos_hoy": lambda: [],
    "obtener_resumen_caja": lambda: {},
    "cargar_memoria": lambda: {},
    "registrar_compra": lambda *a, **kw: (True, "ok", {}),
    "invalidar_cache_memoria": lambda: None,
    "buscar_producto_en_catalogo": lambda x: None,
}
if "memoria" not in sys.modules:
    _mem = types.ModuleType("memoria")
    for _k, _v in _mem_attrs.items():
        setattr(_mem, _k, _v)
    sys.modules["memoria"] = _mem
else:
    _mem = sys.modules["memoria"]
    for _k, _v in _mem_attrs.items():
        if not hasattr(_mem, _k):
            setattr(_mem, _k, _v)

# ── Montar app de test ─────────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.caja import router

app = FastAPI()
app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)


# ── Tests ─────────────────────────────────────────────────────────────────────
# El router usa `import db as _db` — parchear "routers.caja._db.*"

def test_caja_sin_db(mocker):
    """Sin DB → 503 (el router llama _require_db())."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", False)
    resp = client.get("/caja")
    assert resp.status_code == 503


def test_caja_con_db_sin_caja_abierta(mocker):
    """Con DB pero sin caja abierta hoy → 200 con abierta=False."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_one", return_value=None)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/caja")
    assert resp.status_code == 200
    data = resp.json()
    assert data["abierta"] is False


def test_gastos_sin_db(mocker):
    """Sin DB → 503."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", False)
    resp = client.get("/gastos")
    assert resp.status_code == 503


def test_gastos_con_db(mocker):
    """Con DB → 200 con lista."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/gastos")
    assert resp.status_code == 200
    data = resp.json()
    assert "gastos" in data
    assert isinstance(data["gastos"], list)


def test_gastos_param_dias(mocker):
    """?dias=30 → acepta el parámetro sin error."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/gastos?dias=30")
    assert resp.status_code == 200


def test_compras_sin_db(mocker):
    """Sin DB → 503."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", False)
    resp = client.get("/compras")
    assert resp.status_code == 503


def test_compras_con_db(mocker):
    """GET /compras con DB → 200."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/compras")
    assert resp.status_code == 200
    data = resp.json()
    assert "compras" in data or isinstance(resp.json(), list)


def test_abrir_caja_sin_db(mocker):
    """POST /caja/abrir sin DB → 503 (monto_apertura tiene default=0, Pydantic pasa)."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", False)
    resp = client.post("/caja/abrir", json={})
    assert resp.status_code == 503


def test_registrar_gasto_body_vacio():
    """POST /gastos sin body → 422 (concepto y monto son requeridos)."""
    resp = client.post("/gastos", json={})
    assert resp.status_code == 422
