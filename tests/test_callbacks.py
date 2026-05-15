"""
tests/test_callbacks.py — Unit tests for handlers/callbacks.py.

Patching strategy:
- Inject stub modules for `config`, `ventas_state`, `db`, `ai`, `memoria`
  into sys.modules BEFORE any import of handlers.callbacks.
- Real `telegram` library is used for InlineKeyboardMarkup, etc.
- Async functions are tested via asyncio.run() to avoid pytest-asyncio dependency.

No real database, Telegram, or API credentials required.
"""

# -- stdlib --
import sys
import types
import threading
import asyncio
import contextlib

# ── Stubs (must precede all project imports) ──────────────────────────────────

if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = None
    _cfg.claude_client = None
    _cfg.openai_client = None
    sys.modules["config"] = _cfg

if "utils" not in sys.modules:
    # Let real utils load — it only needs config stubbed above
    pass  # will be imported naturally

if "ventas_state" not in sys.modules:
    _vs = types.ModuleType("ventas_state")
    _vs.ventas_pendientes = {}
    _vs.clientes_en_proceso = {}
    _vs.mensajes_standby = {}
    _vs.esperando_correccion = {}
    _vs.ventas_esperando_cliente = {}
    _vs.borrados_pendientes = {}
    _vs.fotos_pendientes_confirmacion = {}
    _vs._estado_lock = threading.Lock()
    _vs.registrar_ventas_con_metodo = lambda *a, **kw: []
    _vs.agregar_a_standby = lambda *a: None
    _vs.limpiar_pendientes_expirados = lambda: None
    _vs.agregar_al_historial = lambda *a: None
    _vs.get_historial = lambda cid: []

    @contextlib.asynccontextmanager
    async def _noop_lock():
        yield
    _vs.get_chat_lock = lambda cid: _noop_lock()

    sys.modules["ventas_state"] = _vs

if "db" not in sys.modules:
    _db = types.ModuleType("db")
    _db.DB_DISPONIBLE = False
    _db.query_one = lambda *a, **kw: None
    _db.query_all = lambda *a, **kw: []
    _db.execute = lambda *a, **kw: None
    sys.modules["db"] = _db

if "ai" not in sys.modules:
    import os as _os
    _ai = types.ModuleType("ai")
    _ai.__path__ = [_os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "ai"))]
    _ai.__package__ = "ai"
    _ai.procesar_con_claude = lambda *a, **kw: ""
    _ai.procesar_acciones = lambda *a, **kw: ("", [], [])
    _ai.procesar_acciones_async = lambda *a, **kw: ("", [], [])
    sys.modules["ai"] = _ai

if "memoria" not in sys.modules:
    _mem = types.ModuleType("memoria")
    _mem.cargar_memoria = lambda: {}
    _mem.invalidar_cache_memoria = lambda: None
    _mem.guardar_fiado_movimiento = lambda *a, **kw: 0.0
    _mem.registrar_compra = lambda *a, **kw: None
    _mem.guardar_memoria = lambda *a, **kw: None
    _mem.cargar_caja = lambda: {}
    _mem.cargar_gastos_hoy = lambda: []
    _mem.cargar_fiados = lambda: {}
    _mem.cargar_inventario = lambda: {}
    sys.modules["memoria"] = _mem

# -- terceros --
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# -- propios --
from handlers.callbacks import _enviar_botones_pago, _formato_cantidad, _procesar_siguiente_standby


# ─────────────────────────────────────────────
# TESTS — _formato_cantidad
# ─────────────────────────────────────────────

def test_formato_cantidad_entero():
    """1.0 debe formatearse como "1" para productos normales."""
    result = _formato_cantidad(1.0, "tornillo")
    assert result == "1"


def test_formato_cantidad_fraccion_media():
    """0.5 debe formatearse como fracción legible para productos normales."""
    result = _formato_cantidad(0.5, "pintura")
    # Acepta "½" (unicode) o "1/2" (ASCII) según la implementación real
    assert result in ("½", "1/2")


def test_formato_cantidad_puntilla_gramos():
    """Productos con "puntilla" en el nombre devuelven gramos en texto."""
    result = _formato_cantidad(133.3, "puntilla 1 pulgada")
    assert "gr" in result
    assert "133" in result


def test_formato_cantidad_entero_mayor():
    """Enteros mayores a 1 deben mostrarse como número limpio."""
    result = _formato_cantidad(3.0, "lija")
    assert result == "3"


# ─────────────────────────────────────────────
# TESTS — _enviar_botones_pago
# ─────────────────────────────────────────────

def test_enviar_botones_pago_genera_teclado():
    """_enviar_botones_pago debe llamar reply_text con un InlineKeyboardMarkup."""
    msg_mock = AsyncMock()
    ventas = [{"producto": "Tornillo", "cantidad": "10", "total": 5000, "precio_unitario": 500}]

    asyncio.run(_enviar_botones_pago(msg_mock, chat_id=123, ventas=ventas))

    msg_mock.reply_text.assert_called_once()
    _, kwargs = msg_mock.reply_text.call_args
    assert "reply_markup" in kwargs


def test_enviar_botones_pago_incluye_texto_ventas():
    """El mensaje de pago debe incluir el nombre del producto."""
    msg_mock = AsyncMock()
    ventas = [{"producto": "Cemento", "cantidad": "2", "total": 70000, "precio_unitario": 35000}]

    asyncio.run(_enviar_botones_pago(msg_mock, chat_id=456, ventas=ventas))

    args, _ = msg_mock.reply_text.call_args
    texto = args[0] if args else ""
    assert "Cemento" in texto or "cemento" in texto.lower()


def test_enviar_botones_pago_con_cliente_agrega_fiado():
    """Si la venta tiene cliente, debe aparecer botón de fiado en el teclado."""
    from telegram import InlineKeyboardMarkup

    msg_mock = AsyncMock()
    ventas = [{"producto": "Tornillo", "cantidad": "5", "total": 2500,
               "precio_unitario": 500, "cliente": "Juan"}]

    asyncio.run(_enviar_botones_pago(msg_mock, chat_id=789, ventas=ventas))

    _, kwargs = msg_mock.reply_text.call_args
    markup = kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    # Verificar que algún botón contiene "fiado"
    todas_las_filas = markup.inline_keyboard
    todos_los_botones = [b for fila in todas_las_filas for b in fila]
    datos = [b.callback_data for b in todos_los_botones]
    assert any("fiado" in d for d in datos)


# ─────────────────────────────────────────────
# TESTS — _procesar_siguiente_standby
# ─────────────────────────────────────────────

def test_procesar_siguiente_standby_con_lista_vacia_no_llama_bot():
    """Con lista vacía no debe hacer ninguna llamada a bot."""
    bot_mock = AsyncMock()
    msg_mock = AsyncMock()

    asyncio.run(_procesar_siguiente_standby(
        bot_mock, msg_mock, chat_id=111, pendientes=[], vendedor="Carlos"
    ))

    bot_mock.send_message.assert_not_called()
