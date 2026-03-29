"""
Tests unitarios para middleware/auth.py.

Cubre: RateLimiter (permitir, limpiar_expirados) y decorador @protegido
(fail-open, bloqueo no-autorizado, permitir autorizado, functools.wraps,
message=None en callback queries).

No requiere DATABASE_URL ni TELEGRAM_TOKEN.
"""

# -- stdlib --
import asyncio
import time

# -- terceros --
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# -- propios --
from middleware.auth import RateLimiter, protegido


# ─────────────────────────────────────────────
# TESTS — RateLimiter
# ─────────────────────────────────────────────

def test_rate_limiter_permite_dentro_del_limite():
    """RateLimiter permite mensajes hasta alcanzar el límite configurado."""
    rl = RateLimiter(max_mensajes=5, ventana_segundos=2)
    for _ in range(5):
        assert rl.permitir(chat_id=123) is True


def test_rate_limiter_bloquea_al_superar_limite():
    """RateLimiter rechaza el mensaje siguiente cuando se supera el límite."""
    rl = RateLimiter(max_mensajes=3, ventana_segundos=2)
    for _ in range(3):
        rl.permitir(chat_id=456)
    assert rl.permitir(chat_id=456) is False


def test_rate_limiter_permite_tras_ventana():
    """RateLimiter vuelve a permitir mensajes una vez que expira la ventana."""
    rl = RateLimiter(max_mensajes=2, ventana_segundos=1)
    rl.permitir(chat_id=789)
    rl.permitir(chat_id=789)
    assert rl.permitir(chat_id=789) is False
    time.sleep(1.1)
    assert rl.permitir(chat_id=789) is True


def test_rate_limiter_limpiar_expirados():
    """limpiar_expirados() elimina entradas de chat_ids inactivos."""
    rl = RateLimiter(max_mensajes=5, ventana_segundos=1)
    rl.permitir(chat_id=111)
    time.sleep(1.1)
    rl.limpiar_expirados()
    with rl._lock:
        assert 111 not in rl._historial


# ─────────────────────────────────────────────
# TESTS — @protegido
# ─────────────────────────────────────────────

def test_protegido_fail_open_sin_authorized_ids():
    """Cuando AUTHORIZED_IDS está vacío, el handler se ejecuta para cualquier chat."""
    with patch("middleware.auth.AUTHORIZED_IDS", set()):
        called = []

        @protegido
        async def handler(update, context):
            called.append(True)

        update = MagicMock()
        update.effective_chat.id = 999
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        asyncio.run(handler(update, MagicMock()))
        assert called == [True]


def test_protegido_bloquea_no_autorizado():
    """Si hay IDs autorizados y el chat_id no está en la lista, no llama al handler."""
    with patch("middleware.auth.AUTHORIZED_IDS", {100, 200}):
        called = []

        @protegido
        async def handler(update, context):
            called.append(True)

        update = MagicMock()
        update.effective_chat.id = 999  # no está en {100, 200}
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        asyncio.run(handler(update, MagicMock()))
        assert called == []


def test_protegido_permite_autorizado():
    """Si el chat_id está en AUTHORIZED_IDS, el handler se ejecuta."""
    with patch("middleware.auth.AUTHORIZED_IDS", {100, 200}):
        called = []

        @protegido
        async def handler(update, context):
            called.append(True)

        update = MagicMock()
        update.effective_chat.id = 100  # autorizado
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        asyncio.run(handler(update, MagicMock()))
        assert called == [True]


def test_protegido_preserva_nombre():
    """functools.wraps debe preservar __name__ — requerido por PTB 21.3."""
    @protegido
    async def mi_comando(update, context):
        pass

    assert mi_comando.__name__ == "mi_comando"


def test_protegido_maneja_message_none():
    """update.message puede ser None en callback queries — no debe lanzar AttributeError."""
    with patch("middleware.auth.AUTHORIZED_IDS", set()):
        called = []

        @protegido
        async def handler(update, context):
            called.append(True)

        update = MagicMock()
        update.effective_chat.id = 42
        update.message = None
        update.callback_query = None  # también None

        asyncio.run(handler(update, MagicMock()))
        assert called == [True]
