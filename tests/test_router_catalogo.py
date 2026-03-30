"""
tests/test_router_catalogo.py — Cobertura básica de routers/catalogo.py.

Sin DB real. Usa stubs en sys.modules y mocker para parchear db.query_all/query_one.
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
    "cargar_memoria": lambda: {"catalogo": {}, "inventario": {}},
    "invalidar_cache_memoria": lambda: None,
    "buscar_producto_en_catalogo": lambda x: None,
    "actualizar_precio_en_catalogo": lambda *a, **kw: None,
    "importar_catalogo_desde_excel": lambda *a, **kw: {},
    "registrar_compra": lambda *a, **kw: (True, "ok", {}),
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

if "utils" not in sys.modules:
    _utils = types.ModuleType("utils")
    _utils._normalizar = lambda texto: texto.strip().lower()
    sys.modules["utils"] = _utils

# routers.shared NO se stubea — se deja importar el módulo real.
# Solo necesita `config` (ya stubado arriba) para importar sin errores.

# ── Montar app de test ─────────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.catalogo import router

app = FastAPI()
app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_productos_sin_db(mocker):
    """DB no disponible → 503 (el router lanza HTTPException)."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.get("/productos")
    assert resp.status_code == 503


def test_productos_con_db_vacia(mocker):
    """DB disponible pero sin productos → 200 con lista vacía."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/productos")
    assert resp.status_code == 200
    data = resp.json()
    assert "productos" in data
    assert isinstance(data["productos"], list)
    assert data["total"] == 0


def test_inventario_bajo_sin_db(mocker):
    """Sin DB → 503."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.get("/inventario/bajo")
    assert resp.status_code == 503


def test_inventario_bajo_con_db(mocker):
    """Con DB vacía → 200 con lista."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/inventario/bajo")
    assert resp.status_code == 200
    data = resp.json()
    assert "alertas" in data
    assert isinstance(data["alertas"], list)


def test_catalogo_nav_sin_db(mocker):
    """Sin DB → 503."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.get("/catalogo/nav?q=")
    assert resp.status_code == 503


def test_catalogo_nav_query_vacio(mocker):
    """q='' con DB → 200 (no falla con query vacío)."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/catalogo/nav?q=")
    assert resp.status_code == 200


def test_catalogo_nav_con_termino(mocker):
    """q=tornillo con DB → 200."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/catalogo/nav?q=tornillo")
    assert resp.status_code == 200


def test_kardex_sin_param(mocker):
    """GET /kardex sin param 'producto' → 422 (param requerido)."""
    resp = client.get("/kardex")
    assert resp.status_code == 422


def test_kardex_sin_db(mocker):
    """GET /kardex con DB no disponible → 503."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.get("/kardex?producto=tornillo")
    assert resp.status_code == 503


def test_kardex_producto_no_encontrado(mocker):
    """Con DB pero producto no en catálogo → 404."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    # buscar_producto_en_catalogo ya retorna None en el stub
    resp = client.get("/kardex?producto=inexistente")
    assert resp.status_code == 404


def test_crear_producto_body_vacio():
    """POST /catalogo sin campos requeridos → 422 (validación Pydantic)."""
    resp = client.post("/catalogo", json={})
    assert resp.status_code == 422


def test_actualizar_precio_sin_db(mocker):
    """PATCH precio sin DB → 503."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.patch("/catalogo/tornillo/precio", json={"precio": 1000})
    assert resp.status_code == 503


def test_actualizar_precio_producto_inexistente(mocker):
    """PATCH precio de producto que no existe en DB → 404."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_one", return_value=None)
    resp = client.patch("/catalogo/tornillo-inexistente/precio", json={"precio": 1000})
    assert resp.status_code == 404
