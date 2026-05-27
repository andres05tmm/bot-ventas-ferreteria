"""
Middleware de autenticación y rate limiting para FerreBot.

Provee el decorador @protegido que:
  1. Verifica que el chat_id esté en AUTHORIZED_CHAT_IDS (fail-open si la lista está vacía).
  2. Aplica rate limiting por chat_id usando threading.Lock (seguro para el thread pool de PTB).

Variables de entorno:
  AUTHORIZED_CHAT_IDS  — IDs separados por coma, ej: "123456,789012"
                         Si está vacío o ausente, se permite todo (fail-open).
  RATE_LIMIT_SEGUNDOS  — Ventana de tiempo en segundos (default: 2)
  RATE_LIMIT_MAX       — Máximo de mensajes por ventana (default: 5)
"""

# -- stdlib --
import functools
import logging
import os
import threading
import time
from typing import Callable

# -- terceros --
from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

# -- propios --
# (ninguno — este módulo es standalone para evitar imports circulares)

logger = logging.getLogger("ferrebot.middleware.auth")

# ─────────────────────────────────────────────
# CONFIGURACIÓN DESDE ENTORNO
# ─────────────────────────────────────────────

def _cargar_authorized_ids() -> set[int]:
    """
    Lee AUTHORIZED_CHAT_IDS del entorno y devuelve un set de ints.
    Si la variable está ausente o vacía, devuelve set vacío (fail-open).
    """
    raw = os.getenv("AUTHORIZED_CHAT_IDS", "").strip()
    if not raw:
        return set()
    ids: set[int] = set()
    for parte in raw.split(","):
        parte = parte.strip()
        if parte:
            try:
                ids.add(int(parte))
            except ValueError:
                logger.warning("AUTHORIZED_CHAT_IDS: valor inválido ignorado: %r", parte)
    return ids


AUTHORIZED_IDS: set[int] = _cargar_authorized_ids()
RATE_LIMIT_SEGUNDOS: int = int(os.getenv("RATE_LIMIT_SEGUNDOS", "2"))
RATE_LIMIT_MAX: int = int(os.getenv("RATE_LIMIT_MAX", "5"))

# ─────────────────────────────────────────────
# ESTADO DE RATE LIMITER
# ─────────────────────────────────────────────

class RateLimiter:
    """
    Rate limiter thread-safe basado en ventana deslizante por chat_id.
    Usa threading.Lock porque el estado es compartido entre threads del pool de PTB.
    """

    def __init__(self, max_mensajes: int = RATE_LIMIT_MAX, ventana_segundos: int = RATE_LIMIT_SEGUNDOS):
        self._lock = threading.Lock()
        self._historial: dict[int, list[float]] = {}  # chat_id → timestamps
        self.max_mensajes = max_mensajes
        self.ventana_segundos = ventana_segundos

    def permitir(self, chat_id: int) -> bool:
        """
        Devuelve True si el chat_id puede enviar un mensaje ahora.
        Devuelve False si ha superado el límite en la ventana actual.
        """
        ahora = time.monotonic()
        with self._lock:
            timestamps = self._historial.get(chat_id, [])
            # Filtrar timestamps fuera de la ventana
            ventana_inicio = ahora - self.ventana_segundos
            timestamps = [t for t in timestamps if t > ventana_inicio]
            if len(timestamps) >= self.max_mensajes:
                self._historial[chat_id] = timestamps
                return False
            timestamps.append(ahora)
            self._historial[chat_id] = timestamps
            return True

    def limpiar_expirados(self) -> None:
        """
        Elimina entradas de chat_ids inactivos para evitar fuga de memoria.
        Llamar periódicamente si el bot tiene muchos usuarios únicos.
        """
        ahora = time.monotonic()
        ventana_inicio = ahora - self.ventana_segundos
        with self._lock:
            expirados = [
                chat_id
                for chat_id, timestamps in self._historial.items()
                if not any(t > ventana_inicio for t in timestamps)
            ]
            for chat_id in expirados:
                del self._historial[chat_id]


# Instancia global compartida
rate_limiter = RateLimiter()


# ─────────────────────────────────────────────
# VERIFICACIÓN DE ACCESO (lógica pura, reutilizable)
# ─────────────────────────────────────────────

def verificar_acceso(chat_id: int | None) -> tuple[bool, str | None]:
    """
    Verifica si un chat_id puede ejecutar un handler.

    Reglas:
      - Sin chat_id → False, motivo 'sin_chat_id'.
      - AUTHORIZED_IDS vacío → True (fail-open en dev).
      - chat_id fuera de AUTHORIZED_IDS → False, motivo 'no_autorizado'.
      - Rate limit superado → False, motivo 'rate_limit'.
      - Caso feliz → True, None.

    Retorna (autorizado, motivo). Usado tanto por @protegido (handlers
    individuales) como por global_guard (TypeHandler PTB).
    """
    if chat_id is None:
        return False, "sin_chat_id"

    if AUTHORIZED_IDS and chat_id not in AUTHORIZED_IDS:
        return False, "no_autorizado"

    if not rate_limiter.permitir(chat_id):
        return False, "rate_limit"

    return True, None


# ─────────────────────────────────────────────
# GUARD GLOBAL (TypeHandler PTB)
# ─────────────────────────────────────────────

async def global_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler global para registrar con TypeHandler en group=-1.

    Se ejecuta ANTES que cualquier otro handler del bot y bloquea el flujo
    levantando ApplicationHandlerStop si el chat no está autorizado o
    supera el rate limit.

    Garantiza que TODO update procesado por el bot (texto, audio, foto,
    documento, callback query, etc.) pase por el chequeo de auth, sin
    depender de que cada handler lleve el decorador @protegido.

    Uso en main.build_app():
        from telegram.ext import TypeHandler
        from telegram import Update
        from middleware.auth import global_guard
        app.add_handler(TypeHandler(Update, global_guard), group=-1)
    """
    chat_id: int | None = None
    if update.effective_chat:
        chat_id = update.effective_chat.id

    autorizado, motivo = verificar_acceso(chat_id)
    if autorizado:
        return  # deja seguir al handler real

    # No autorizado o rate-limited — responder y detener el flujo.
    reply = (
        update.message
        or (update.callback_query and update.callback_query.message)
    )

    if motivo == "no_autorizado":
        logger.warning("global_guard: acceso denegado chat_id=%s", chat_id)
        if reply:
            try:
                await reply.reply_text("🔒 No tienes acceso a este bot.")
            except Exception as e:
                logger.error("global_guard: error enviando denegación: %s", e)

    elif motivo == "rate_limit":
        logger.info("global_guard: rate limit superado chat_id=%s", chat_id)
        if reply:
            try:
                await reply.reply_text("⏳ Demasiados mensajes seguidos. Espera un momento.")
            except Exception as e:
                logger.error("global_guard: error enviando aviso rate limit: %s", e)

    elif motivo == "sin_chat_id":
        logger.warning("global_guard: update sin effective_chat — ignorado")

    # Detiene la propagación a todos los demás handlers del bot.
    raise ApplicationHandlerStop


# ─────────────────────────────────────────────
# DECORADOR @protegido (defensa en profundidad, mantenido)
# ─────────────────────────────────────────────

def protegido(func: Callable) -> Callable:
    """
    Decorador para handlers de PTB que aplica autenticación y rate limiting.

    Uso:
        @protegido
        async def mi_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...

    Comportamiento:
      - Si AUTHORIZED_CHAT_IDS está vacío → permite todo (fail-open).
      - Si el chat_id no está en la lista → responde con mensaje de acceso denegado y retorna.
      - Si el chat_id supera el rate limit → responde con aviso y retorna.
      - En cualquier otro caso → llama al handler original.

    Notas:
      - Usa functools.wraps para preservar __name__ (requerido por PTB 21.3).
      - Maneja update.message = None (callback queries no tienen .message).
      - threading.Lock en RateLimiter — nunca asyncio.Lock.
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id: int | None = None
        if update.effective_chat:
            chat_id = update.effective_chat.id

        reply = (
            update.message
            or (update.callback_query and update.callback_query.message)
        )

        autorizado, motivo = verificar_acceso(chat_id)
        if autorizado:
            return await func(update, context, *args, **kwargs)

        # Logging + respuesta al usuario (idéntico a global_guard para coherencia).
        if motivo == "no_autorizado":
            logger.warning(
                "@protegido: acceso denegado chat_id=%s intentó %s", chat_id, func.__name__,
            )
            if reply:
                try:
                    await reply.reply_text("🔒 No tienes acceso a este bot.")
                except Exception as e:
                    logger.error("@protegido: error enviando denegación: %s", e)
        elif motivo == "rate_limit":
            logger.info(
                "@protegido: rate limit superado chat_id=%s en %s", chat_id, func.__name__,
            )
            if reply:
                try:
                    await reply.reply_text("⏳ Demasiados mensajes seguidos. Espera un momento.")
                except Exception as e:
                    logger.error("@protegido: error enviando aviso rate limit: %s", e)
        elif motivo == "sin_chat_id":
            logger.warning("@protegido: update sin effective_chat — ignorado (%s)", func.__name__)
        # Sin raise — el handler simplemente no se ejecuta y el flujo PTB continúa.
        return

    return wrapper
