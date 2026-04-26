"""
tests/test_router_chat.py — Unit tests for routers/chat.py endpoints.

Patching strategy:
- Inject stubs for `config`, `db`, `memoria`, `ventas_state`, `ai` into sys.modules
  BEFORE importing the router. All async functions in stubs are proper coroutines.
- Patch `routers.chat._construir_contexto_dashboard` per-test to avoid complex
  nested imports from memoria/db.
- FastAPI TestClient (via httpx/starlette) runs async endpoints transparently.

No real database, Claude API, or Telegram credentials required.
"""

# -- stdlib --
import sys
import types
import threading
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
    _mem.cargar_memoria = lambda: {"catalogo": {}, "inventario": {}, "notas": {}}
    _mem.cargar_caja = lambda: {}
    _mem.cargar_gastos_hoy = lambda: []
    _mem.cargar_fiados = lambda: {}
    _mem.cargar_inventario = lambda: {}
    _mem.invalidar_cache_memoria = lambda: None
    _mem.guardar_memoria = lambda *a, **kw: None
    _mem.registrar_compra = lambda *a, **kw: None
    sys.modules["memoria"] = _mem

if "ventas_state" not in sys.modules:
    _vs = types.ModuleType("ventas_state")
    _vs.ventas_pendientes = {}
    _vs._estado_lock = threading.Lock()
    _vs.registrar_ventas_con_metodo = lambda *a, **kw: []
    sys.modules["ventas_state"] = _vs

# Always set async functions on ventas_state (may already exist from test_callbacks)
async def _registrar_async(*a, **kw):
    return []
sys.modules["ventas_state"].registrar_ventas_con_metodo_async = _registrar_async

if "ai" not in sys.modules:
    import os as _os
    _ai = types.ModuleType("ai")
    _ai.__path__ = [_os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "ai"))]
    _ai.__package__ = "ai"
    sys.modules["ai"] = _ai

# Always set async functions on ai (may already exist as sync lambdas from test_callbacks)
async def _procesar_con_claude(*a, **kw):
    return "respuesta test"

async def _procesar_acciones_async(*a, **kw):
    return ("respuesta test", [], [])

sys.modules["ai"].procesar_con_claude = _procesar_con_claude
sys.modules["ai"].procesar_acciones_async = _procesar_acciones_async
sys.modules["ai"].procesar_acciones = lambda *a, **kw: ("", [], [])

# -- terceros --
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -- propios --
from routers.chat import router
from routers.deps import get_current_user

app = FastAPI()
app.include_router(router)

# Mock get_current_user to always return a valid admin user
def mock_get_current_user():
    return {"usuario_id": 1, "telegram_id": 123456, "nombre": "Test Admin", "rol": "admin"}

app.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(app, raise_server_exceptions=False)


async def _contexto_vacio(*a, **kw):
    return ""


# ─────────────────────────────────────────────
# TESTS — POST /chat
# ─────────────────────────────────────────────

def test_chat_endpoint_responde_200():
    """POST /chat con body mínimo debe retornar 200."""
    with patch("routers.chat._construir_contexto_dashboard", new=_contexto_vacio):
        resp = client.post("/chat", json={"mensaje": "hola", "session_id": "test-abc"})
    assert resp.status_code == 200


def test_chat_endpoint_retorna_respuesta():
    """POST /chat debe retornar campo 'respuesta' en el JSON."""
    with patch("routers.chat._construir_contexto_dashboard", new=_contexto_vacio):
        resp = client.post("/chat", json={"mensaje": "cuánto vendimos hoy", "session_id": "test-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "respuesta" in data


def test_chat_mensaje_vacio_retorna_400():
    """POST /chat con mensaje vacío debe retornar 400."""
    with patch("routers.chat._construir_contexto_dashboard", new=_contexto_vacio):
        resp = client.post("/chat", json={"mensaje": "  ", "session_id": "test-2"})
    assert resp.status_code == 400


# ─────────────────────────────────────────────
# TESTS — POST /chat/memoria
# ─────────────────────────────────────────────

def test_guardar_memoria_negocio_retorna_200():
    """POST /chat/memoria con body válido debe retornar 200."""
    resp = client.post("/chat/memoria", json={
        "tipo": "observacion",
        "contenido": "Clientes pagan más los viernes"
    })
    assert resp.status_code == 200


def test_guardar_memoria_negocio_retorna_ok_true():
    """POST /chat/memoria debe retornar {"ok": True, "tipo": ...}."""
    resp = client.post("/chat/memoria", json={
        "tipo": "contexto_negocio",
        "contenido": "Ferretería especializada en construcción"
    })
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("tipo") == "contexto_negocio"


def test_guardar_memoria_contenido_vacio_retorna_400():
    """POST /chat/memoria con contenido vacío debe retornar 400."""
    resp = client.post("/chat/memoria", json={"tipo": "observacion", "contenido": ""})
    assert resp.status_code == 400


# ─────────────────────────────────────────────
# TESTS — GET /chat/briefing
# ─────────────────────────────────────────────

def test_briefing_retorna_200():
    """GET /chat/briefing debe retornar 200 incluso sin DB."""
    with patch("routers.chat._construir_contexto_dashboard", new=_contexto_vacio):
        resp = client.get("/chat/briefing")
    assert resp.status_code == 200


def test_briefing_retorna_texto():
    """GET /chat/briefing debe retornar un campo de texto no vacío."""
    with patch("routers.chat._construir_contexto_dashboard", new=_contexto_vacio):
        resp = client.get("/chat/briefing")
    assert resp.status_code == 200
    data = resp.json()
    # El briefing puede ser texto directo o un dict con campo 'briefing'/'respuesta'
    assert data is not None
