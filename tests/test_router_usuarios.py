"""
tests/test_router_usuarios.py — Tests del router /usuarios/vendedores.

Cubre la restricción por rol:
  - Admin recibe lista completa de vendedores activos.
  - Vendedor recibe solo su propio nombre.
  - Sin rol → comportamiento de vendedor (fail-safe).
"""

# -- stdlib --
import sys
import types

# ── Stubs (deben preceder a los imports de proyecto) ──────────────────────────

if "config" not in sys.modules:
    sys.modules["config"] = types.ModuleType("config")

if "db" not in sys.modules:
    _db = types.ModuleType("db")
    _db.DB_DISPONIBLE = True
    _db.query_all = lambda *a, **kw: []
    _db.query_one = lambda *a, **kw: None
    sys.modules["db"] = _db

# -- terceros --
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -- propios --
from routers.usuarios import router
from routers.deps import get_current_user

import db as _db_module


ADMIN = {"usuario_id": 1, "telegram_id": 1831034712, "nombre": "Andrés", "rol": "admin"}
VENDEDOR = {"usuario_id": 2, "telegram_id": 1, "nombre": "Farid M", "rol": "vendedor"}

_VENDEDORES_EN_DB = [
    {"id": 1, "nombre": "Andrés"},
    {"id": 2, "nombre": "Farid M"},
    {"id": 3, "nombre": "Karolay"},
    {"id": 4, "nombre": "Papá"},
]


def _make_app(user: dict):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_admin_ve_todos_los_vendedores(monkeypatch):
    """Admin recibe la lista completa de vendedores activos."""
    monkeypatch.setattr(_db_module, "query_all", lambda *a, **kw: list(_VENDEDORES_EN_DB))
    client = _make_app(ADMIN)
    resp = client.get("/usuarios/vendedores")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    nombres = [d["nombre"] for d in data]
    assert "Farid M" in nombres
    assert "Karolay" in nombres


def test_vendedor_solo_se_ve_a_si_mismo(monkeypatch):
    """Vendedor recibe lista de un elemento con su propio nombre."""
    def _query_all(sql, params=None):
        # La query del rol vendedor lleva WHERE id = %s
        assert "WHERE id = %s" in sql
        assert params == (VENDEDOR["usuario_id"],)
        return [{"id": VENDEDOR["usuario_id"], "nombre": VENDEDOR["nombre"]}]

    monkeypatch.setattr(_db_module, "query_all", _query_all)
    client = _make_app(VENDEDOR)
    resp = client.get("/usuarios/vendedores")
    assert resp.status_code == 200
    data = resp.json()
    assert data == [{"id": 2, "nombre": "Farid M"}]


def test_sin_rol_se_trata_como_vendedor(monkeypatch):
    """Si el JWT no trae rol, fail-safe a vendedor: solo se ve a sí mismo."""
    sin_rol = {"usuario_id": 99, "telegram_id": 0, "nombre": "?"}

    def _query_all(sql, params=None):
        assert "WHERE id = %s" in sql
        assert params == (99,)
        return [{"id": 99, "nombre": "?"}]

    monkeypatch.setattr(_db_module, "query_all", _query_all)
    client = _make_app(sin_rol)
    resp = client.get("/usuarios/vendedores")
    assert resp.status_code == 200
    assert resp.json() == [{"id": 99, "nombre": "?"}]


def test_sin_rol_y_sin_usuario_id_retorna_vacio(monkeypatch):
    """Defensa extrema: sin rol y sin usuario_id → lista vacía."""
    monkeypatch.setattr(_db_module, "query_all", lambda *a, **kw: list(_VENDEDORES_EN_DB))
    sin_id = {"telegram_id": 0, "nombre": "?"}
    client = _make_app(sin_id)
    resp = client.get("/usuarios/vendedores")
    assert resp.status_code == 200
    assert resp.json() == []
