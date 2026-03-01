"""
Keep-alive del prompt cache de Anthropic.

Envía un ping a la API cada 4 minutos durante 8:00-11:00 (hora Colombia)
para mantener el cache activo y reducir costos en las horas de mayor volumen.

Control manual via Telegram:
  /keepalive on  → activa el keep-alive (útil en tardes movidas)
  /keepalive off → desactiva (días de lluvia, festivos, etc.)
  /keepalive     → muestra el estado actual

El estado se guarda en memoria.json para sobrevivir reinicios.
"""

import asyncio
import logging
from datetime import datetime, time

import config
from memoria import cargar_memoria, guardar_memoria

logger = logging.getLogger("ferrebot.keepalive")

# Horario por defecto: 8:00 - 11:00 hora Colombia
HORA_INICIO  = time(8, 0)
HORA_FIN     = time(11, 0)
INTERVALO_SEG = 4 * 60  # 4 minutos

# Mensaje mínimo para renovar cache sin generar respuesta visible
_PING_MSG = "."


def keepalive_activo() -> bool:
    """Lee el estado del keep-alive desde memoria.json."""
    mem = cargar_memoria()
    return mem.get("keepalive_activo", True)  # activo por defecto


def set_keepalive(activo: bool):
    """Guarda el estado del keep-alive en memoria.json."""
    mem = cargar_memoria()
    mem["keepalive_activo"] = activo
    guardar_memoria(mem)
    logger.info(f"Keep-alive {'ACTIVADO' if activo else 'DESACTIVADO'} manualmente.")


def _en_horario_keepalive() -> bool:
    """Retorna True si estamos en el horario de keep-alive (8:00-11:00 Colombia)."""
    ahora = datetime.now(config.COLOMBIA_TZ).time()
    return HORA_INICIO <= ahora <= HORA_FIN


async def _ping_cache():
    """
    Llama a la API con un mensaje mínimo para renovar el cache de la parte estática.
    Usa el mismo system prompt cacheado que las ventas normales.
    """
    try:
        from ai import _construir_parte_estatica
        from memoria import cargar_memoria as _cm

        mem           = _cm()
        parte_estatica = _construir_parte_estatica(mem)

        loop = asyncio.get_event_loop()
        respuesta = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: config.claude_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=10,
                    system=[
                        {
                            "type": "text",
                            "text": parte_estatica,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": _PING_MSG}],
                )
            ),
            timeout=15.0,
        )

        uso          = respuesta.usage
        cache_read   = getattr(uso, "cache_read_input_tokens",    0) or 0
        cache_created= getattr(uso, "cache_creation_input_tokens", 0) or 0
        output_tok   = getattr(uso, "output_tokens",               0) or 0

        if cache_read > 0:
            logger.info(f"[KEEPALIVE] ✅ Cache renovado — hit={cache_read} tok | output={output_tok} tok")
        elif cache_created > 0:
            logger.info(f"[KEEPALIVE] 🔄 Cache creado — created={cache_created} tok")
        else:
            logger.warning("[KEEPALIVE] ⚠️ Ping sin cache")

    except asyncio.TimeoutError:
        logger.warning("[KEEPALIVE] ⏱ Timeout en ping")
    except Exception as e:
        logger.error(f"[KEEPALIVE] Error: {e}")


async def loop_keepalive():
    """
    Bucle principal del keep-alive. Corre indefinidamente en background.
    Solo hace ping si: (1) está activado y (2) estamos en horario 8-11am.
    """
    logger.info("[KEEPALIVE] Iniciado. Horario activo: 08:00-11:00 Colombia.")
    while True:
        await asyncio.sleep(INTERVALO_SEG)
        if keepalive_activo() and _en_horario_keepalive():
            await _ping_cache()
        else:
            # Log silencioso cada 30 min para saber que sigue corriendo
            ahora = datetime.now(config.COLOMBIA_TZ)
            if ahora.minute % 30 == 0:
                estado  = "ON" if keepalive_activo() else "OFF (manual)"
                horario = "en horario" if _en_horario_keepalive() else "fuera de horario"
                logger.debug(f"[KEEPALIVE] Inactivo — estado:{estado} | {horario}")
