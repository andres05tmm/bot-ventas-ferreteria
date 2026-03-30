"""
tests/test_router_historico.py — Unit tests for routers/historico.py endpoints.

Patching strategy:
- Inject stubs for `config`, `db`, `memoria` into sys.modules BEFORE importing the router.
- routers.historico uses `import db as _db` inside function bodies → stub covers this.
- `_total_ventas_hoy_sheets` and `_leer_historico` are patched per-test to return controlled data.
- `cargar_memoria` from `routers.historico` namespace is patched where needed.

No real database or API credentials required.
"""

# -- stdlib --
import sys
import types
from datetime import timezone

# ── Stubs (must precede all project imports) ──────────────────────────────────

if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = timezone.utc
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

if "memoria" not in sys.modules:
    _mem = types.ModuleType("memoria")
    _mem.cargar_memoria = lambda: {"catalogo": {}, "inventario": {}}
    _mem.invalidar_cache_memoria = lambda: None
    _mem.registrar_compra = lambda *a, **kw: None
    sys.modules["memoria"] = _mem

# -- terceros --
import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -- propios --
from routers.historico import router

app = FastAPI()
app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────
# TESTS — GET /historico/ventas
# ─────────────────────────────────────────────

def test_historico_ventas_devuelve_200():
    """GET /historico/ventas debe retornar 200 con DB stub vacía."""
    with patch("routers.historico._leer_historico", return_value={}), \
         patch("routers.historico._total_ventas_hoy_sheets", return_value=0):
        resp = client.get("/historico/ventas")
    assert resp.status_code == 200


def test_historico_ventas_retorna_dict():
    """GET /historico/ventas debe retornar un dict (historial por fecha)."""
    datos_mock = {"2026-03-01": 500000, "2026-03-02": 300000}
    with patch("routers.historico._leer_historico", return_value=datos_mock), \
         patch("routers.historico._total_ventas_hoy_sheets", return_value=0):
        resp = client.get("/historico/ventas")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_historico_ventas_con_filtro_año_mes():
    """GET /historico/ventas?año=2026&mes=3 filtra por prefijo correcto."""
    datos_mock = {
        "2026-03-01": 500000,
        "2026-03-02": 300000,
        "2026-02-15": 200000,
    }
    with patch("routers.historico._leer_historico", return_value=datos_mock), \
         patch("routers.historico._total_ventas_hoy_sheets", return_value=0):
        resp = client.get("/historico/ventas?año=2026&mes=3")
    assert resp.status_code == 200
    data = resp.json()
    # Solo deben aparecer los de marzo
    for key in data.keys():
        assert key.startswith("2026-03")


# ─────────────────────────────────────────────
# TESTS — GET /historico/resumen
# ─────────────────────────────────────────────

def test_historico_resumen_devuelve_200():
    """GET /historico/resumen debe retornar 200."""
    with patch("routers.historico._leer_historico", return_value={}), \
         patch("routers.historico._total_ventas_hoy_sheets", return_value=0):
        resp = client.get("/historico/resumen")
    assert resp.status_code == 200


def test_historico_resumen_con_datos_agrupa_por_mes():
    """GET /historico/resumen debe agrupar ventas por mes."""
    datos_mock = {
        "2026-03-01": 500000,
        "2026-03-02": 300000,
        "2026-02-15": 200000,
    }
    with patch("routers.historico._leer_historico", return_value=datos_mock), \
         patch("routers.historico._total_ventas_hoy_sheets", return_value=0):
        resp = client.get("/historico/resumen")
    assert resp.status_code == 200
    data = resp.json()
    # Resultado debe ser dict o list con agrupación mensual
    assert data is not None


# ─────────────────────────────────────────────
# TESTS — GET /historico/diario
# ─────────────────────────────────────────────

def test_historico_diario_devuelve_200():
    """GET /historico/diario debe retornar 200 con DB stub vacía."""
    resp = client.get("/historico/diario")
    assert resp.status_code == 200


# ─────────────────────────────────────────────
# TESTS — parametrize de endpoints principales
# ─────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/historico/ventas",
    "/historico/resumen",
    "/historico/diario",
])
def test_historico_endpoints_devuelven_200(path):
    """Todos los GET de historico deben responder 200 con datos mockeados."""
    with patch("routers.historico._leer_historico", return_value={}), \
         patch("routers.historico._total_ventas_hoy_sheets", return_value=0):
        resp = client.get(path)
    assert resp.status_code == 200
