"""
Telemetría por turno del canal de voz (P0.1 del diagnóstico de FerreVoz).

Dos piezas, ambas aisladas del resto del bot/dashboard:

  1. Sink basado en `contextvars`: `procesar_con_claude` registra el modelo
     elegido y el riel disparado SIN conocer al endpoint. Es **no-op si no hay
     un turno de voz activo** (lo abre solo el endpoint /chat cuando canal=voz),
     así que el bot de Telegram, el dashboard y los tests no se ven afectados.

  2. `registrar_turno_voz()`: inserta UNA fila en `audio_logs` (extendida en la
     migración 016) por etapa del turno (transcribir / chat). Las dos filas de
     un mismo turno se correlacionan por `turn_id`. Es **fail-open**: si la DB
     falla, loguea y nunca rompe el turno de voz.
"""

# -- stdlib --
import contextvars
import logging
from datetime import datetime

# -- propios --
import db as _db
from config import COLOMBIA_TZ

log = logging.getLogger("ferrebot.voz.telemetria")


# ─────────────────────────────────────────────────────────────────────────────
# SINK contextvars — captura modelo/riel desde dentro de procesar_con_claude
# ─────────────────────────────────────────────────────────────────────────────

_turno: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "_turno_voz", default=None
)


def iniciar() -> None:
    """Abre un turno de telemetría en el contexto actual (lo llama /chat voz)."""
    _turno.set({"modelo": None, "riel": "ninguno"})


def reset() -> None:
    """Cierra el turno de telemetría del contexto actual."""
    _turno.set(None)


def set_modelo(model_id: str | None) -> None:
    """
    Registra el modelo usado en el turno. No-op si no hay turno activo.
    Normaliza el ID completo de Claude a "haiku" | "sonnet".
    """
    turno = _turno.get()
    if turno is None:
        return
    _m = (model_id or "").lower()
    if "haiku" in _m:
        turno["modelo"] = "haiku"
    elif "sonnet" in _m:
        turno["modelo"] = "sonnet"
    else:
        turno["modelo"] = model_id or None


def set_riel(riel: str) -> None:
    """
    Registra el riel disparado (R2 | R2-precio | CONFIRM-VOZ). No-op si no hay
    turno activo. Si ningún riel lo llama, el turno queda en "ninguno".
    """
    turno = _turno.get()
    if turno is None:
        return
    turno["riel"] = riel


def capturar() -> dict:
    """Devuelve una copia del estado del turno (modelo/riel) o los defaults."""
    return dict(_turno.get() or {"modelo": None, "riel": "ninguno"})


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTENCIA — una fila por etapa en audio_logs
# ─────────────────────────────────────────────────────────────────────────────

async def registrar_turno_voz(
    *,
    turn_id: str,
    canal: str = "voz",
    chat_id: int = 0,
    vendedor: str = "",
    texto: str = "",
    session_id: str | None = None,
    duracion_seg: float | None = None,
    no_speech_prob: float | None = None,
    descartado_silencio: bool | None = None,
    modelo: str | None = None,
    riel: str | None = None,
    latencia_stt_ms: int | None = None,
    latencia_claude_ms: int | None = None,
    pendiente: bool | None = None,
    resultado: str = "",
) -> None:
    """
    Inserta una fila de telemetría de voz en audio_logs. Fail-open: nunca lanza.

    `texto_original` y `texto_corregido` (NOT NULL en la tabla) se pueblan ambos
    con `texto`. `fecha` se fija explícita con COLOMBIA_TZ (no el NOW() en UTC).
    """
    try:
        _texto = texto or ""
        await _db.execute_async(
            """
            INSERT INTO audio_logs
                (chat_id, vendedor, texto_original, texto_corregido,
                 duracion_seg, fecha, canal, turn_id, session_id,
                 no_speech_prob, descartado_silencio, modelo, riel,
                 latencia_stt_ms, latencia_claude_ms, pendiente, resultado)
            VALUES
                (%s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s)
            """,
            [
                chat_id, vendedor, _texto, _texto,
                duracion_seg, datetime.now(COLOMBIA_TZ), canal, turn_id, session_id,
                no_speech_prob, descartado_silencio, modelo, riel,
                latencia_stt_ms, latencia_claude_ms, pendiente, resultado,
            ],
        )
    except Exception as e:
        log.warning(
            "no se pudo registrar telemetría de voz (turn_id=%s, etapa=%s): %s",
            turn_id, resultado, e
        )
