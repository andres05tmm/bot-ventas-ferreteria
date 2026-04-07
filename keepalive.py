"""
Keep-alive del prompt cache de Anthropic.

Envía un ping a la API cada 4 minutos durante 7:00-17:00 (hora Colombia)
para mantener el cache activo y reducir costos en las horas de mayor volumen.

Control manual via Telegram:
  /keepalive on  → activa el keep-alive (útil en tardes movidas)
  /keepalive off → desactiva (días de lluvia, festivos, etc.)
  /keepalive     → muestra el estado actual

Si se activa manualmente, se apaga solo al cerrar la ferretería:
  - Lunes a sábado: 5:00pm
  - Domingos: 1:00pm

El estado se guarda en memoria.json para sobrevivir reinicios.
"""

import asyncio
import logging
from datetime import datetime, time

import config
from memoria import cargar_memoria, guardar_memoria

logger = logging.getLogger("ferrebot.keepalive")

# Horario automático: 7:00 - 17:00 hora Colombia
HORA_INICIO   = time(7, 0)
HORA_FIN      = time(17, 0)

# Hora de cierre por día (apagado automático del modo manual)
HORA_CIERRE_SEMANA  = time(17, 0)   # L-S: 5:00pm
HORA_CIERRE_DOMINGO = time(13, 0)   # D:   1:00pm

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
    """Retorna True si estamos en el horario automático (7:00-17:00 Colombia)."""
    ahora = datetime.now(config.COLOMBIA_TZ).time()
    return HORA_INICIO <= ahora <= HORA_FIN


def _hora_cierre_hoy() -> time:
    """Retorna la hora de cierre según el día de la semana."""
    # weekday(): 0=lunes ... 5=sábado, 6=domingo
    es_domingo = datetime.now(config.COLOMBIA_TZ).weekday() == 6
    return HORA_CIERRE_DOMINGO if es_domingo else HORA_CIERRE_SEMANA


def _pasada_hora_cierre() -> bool:
    """Retorna True si ya pasó la hora de cierre del día."""
    ahora = datetime.now(config.COLOMBIA_TZ).time()
    return ahora >= _hora_cierre_hoy()


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

    Lógica:
    - Horario automático 8-11am: pinguea siempre (independiente del estado manual)
    - Modo manual (/keepalive on): pinguea fuera del horario automático,
      pero se apaga solo a las 5pm (L-S) o 1pm (D)
    """
    logger.info("[KEEPALIVE] Iniciado. Horario automático: 07:00-17:00 Colombia.")
    while True:
        await asyncio.sleep(INTERVALO_SEG)

        en_horario_auto = _en_horario_keepalive()
        manual_activo   = keepalive_activo()
        cierre_pasado   = _pasada_hora_cierre()

        # Apagado automático del modo manual al llegar la hora de cierre
        if manual_activo and cierre_pasado and not en_horario_auto:
            set_keepalive(False)
            hora_cierre = _hora_cierre_hoy().strftime("%I:%M%p")
            logger.info(f"[KEEPALIVE] 🔴 Apagado automático — hora de cierre ({hora_cierre} Colombia)")
            continue

        # Hacer ping si: horario automático O manual activo (sin haber pasado cierre)
        if en_horario_auto or (manual_activo and not cierre_pasado):
            await _ping_cache()
        else:
            ahora = datetime.now(config.COLOMBIA_TZ)
            if ahora.minute % 30 == 0:
                estado  = "ON" if manual_activo else "OFF"
                horario = "en horario auto" if en_horario_auto else "fuera de horario"
                logger.debug(f"[KEEPALIVE] Inactivo — estado:{estado} | {horario}")
