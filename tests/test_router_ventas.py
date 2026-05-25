"""
tests/test_router_ventas.py — Unit tests for routers/ventas.py endpoints.

Patching strategy:
- Inject stub modules for `config`, `db`, `memoria` into sys.modules BEFORE
  importing any router. `routers.caja` (imported by routers.ventas) also needs
  the stubs in place.
- FastAPI TestClient runs the router synchronously — no event loop needed.
- DB calls are patched via `routers.ventas._leer_ventas_postgres` and
  `routers.ventas.cargar_memoria` to avoid real PG connections.

No real database or API credentials required.
"""

# -- stdlib --
import sys
import types
from datetime import timezone

# ── Stubs (must precede all project imports) ──────────────────────────────────

if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = timezone.utc   # datetime.now(config.COLOMBIA_TZ) must work
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
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -- propios --
from routers.ventas import router
from routers.deps import get_current_user

app = FastAPI()
app.include_router(router)

# Mock get_current_user to always return a valid admin user
def mock_get_current_user():
    return {"usuario_id": 1, "telegram_id": 123456, "nombre": "Test Admin", "rol": "admin"}

app.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────
# TESTS — GET /ventas/hoy
# ─────────────────────────────────────────────

def test_ventas_hoy_devuelve_lista_con_db_mockeado():
    """GET /ventas/hoy debe retornar 200 con lista vacía cuando DB mock devuelve []."""
    with patch("routers.ventas._leer_ventas_postgres", return_value=[]):
        resp = client.get("/ventas/hoy")
    assert resp.status_code == 200
    data = resp.json()
    assert "ventas" in data
    assert isinstance(data["ventas"], list)


def test_ventas_hoy_estructura_de_respuesta():
    """La respuesta de /ventas/hoy debe incluir fecha, ventas y total."""
    with patch("routers.ventas._leer_ventas_postgres", return_value=[]):
        resp = client.get("/ventas/hoy")
    data = resp.json()
    assert "fecha" in data
    assert "total" in data
    assert isinstance(data["total"], int)


# ─────────────────────────────────────────────
# TESTS — GET /ventas/semana
# ─────────────────────────────────────────────

def test_ventas_semana_devuelve_200():
    """GET /ventas/semana debe retornar 200 con DB mockeado."""
    with patch("routers.ventas._leer_ventas_postgres", return_value=[]):
        resp = client.get("/ventas/semana")
    assert resp.status_code == 200


def test_ventas_semana_devuelve_lista():
    """GET /ventas/semana debe retornar un campo 'ventas' con lista."""
    with patch("routers.ventas._leer_ventas_postgres", return_value=[]):
        resp = client.get("/ventas/semana")
    data = resp.json()
    assert "ventas" in data
    assert isinstance(data["ventas"], list)


# ─────────────────────────────────────────────
# TESTS — GET /ventas/top
# ─────────────────────────────────────────────

def test_ventas_top_semana_devuelve_200():
    """GET /ventas/top con periodo=semana debe retornar 200."""
    with patch("routers.ventas._leer_ventas_postgres", return_value=[]):
        with patch("routers.ventas.cargar_memoria", return_value={"catalogo": {}}):
            resp = client.get("/ventas/top?periodo=semana")
    assert resp.status_code == 200


def test_ventas_top_mes_devuelve_200():
    """GET /ventas/top con periodo=mes debe retornar 200."""
    with patch("routers.ventas._leer_ventas_postgres", return_value=[]):
        with patch("routers.ventas.cargar_memoria", return_value={"catalogo": {}}):
            resp = client.get("/ventas/top?periodo=mes")
    assert resp.status_code == 200


def test_ventas_top_periodo_invalido_retorna_422():
    """GET /ventas/top con periodo inválido debe retornar 422 por validación de Query."""
    resp = client.get("/ventas/top?periodo=anio")
    assert resp.status_code == 422


# ─────────────────────────────────────────────
# TESTS — DELETE /ventas/{numero}
# ─────────────────────────────────────────────

def test_eliminar_venta_sin_db_retorna_error():
    """DELETE /ventas/999 sin DB disponible debe retornar 4xx o 5xx."""
    resp = client.delete("/ventas/999")
    assert resp.status_code >= 400
