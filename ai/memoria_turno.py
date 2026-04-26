"""
ai/memoria_turno.py — Capa 1 de memoria del bot: persistencia de turnos.

Provee tres funciones:

    guardar_turno(chat_id, role, content, vendedor_id=None, modelo=None,
                  tokens_input=None, tokens_output=None)
        INSERT en conversaciones_bot. Best-effort: jamás lanza excepción —
        si la DB está caída solo loggea un warning y sigue.

    cargar_turnos_recientes(chat_id, limite=8) -> list[dict]
        SELECT de los últimos N turnos del chat ordenados ASC por creado,
        en formato {"role": ..., "content": ...} listo para pasar a Claude.
        Retorna [] si la DB no está disponible o no hay nada.

    limpiar_antiguos(dias=14) -> int
        DELETE de turnos más viejos que `dias`. Uso desde un job nightly.
        Retorna # filas borradas.

DISEÑO:

  - La in-memory cache de ventas_state.historiales sigue siendo la fuente de
    verdad en caliente (lecturas O(1) sin tocar PG).
  - Esta capa es un "espejo" persistente: cada turno que entra a la cache
    también se escribe en PG (best-effort, no bloquea al usuario si falla).
  - En cold start (Railway redeploy), get_historial() detecta cache vacía
    y llama cargar_turnos_recientes() para hidratar — así el bot no
    "olvida" la conversación tras un deploy.

  - Errores de DB JAMÁS se propagan: el bot debe seguir vivo aunque PG esté
    intermitente. Sí se loggean para no perder visibilidad.
"""

# -- stdlib --
import logging

# -- propios --
import db as _db

log = logging.getLogger("ferrebot.ai.memoria_turno")


# Cap defensivo al tamaño del content que persistimos.
# Mensajes ridículamente largos (foto OCR con 50 productos, dump de inventario)
# se truncan para no llenar la DB con basura.
_MAX_CONTENT_BYTES = 20_000


# ═════════════════════════════════════════════════════════════════════════════
# WRITE
# ═════════════════════════════════════════════════════════════════════════════

def guardar_turno(
    chat_id: int,
    role: str,
    content: str,
    vendedor_id: int | None = None,
    modelo: str | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
) -> None:
    """
    Persiste un turno en conversaciones_bot. Best-effort.

    `role` debe ser 'user', 'assistant' o 'system' (constraint en la tabla).
    Cualquier otro valor se descarta con un warning.
    """
    if not _db.DB_DISPONIBLE:
        return
    if role not in ("user", "assistant", "system"):
        log.warning(f"role inválido descartado: {role!r}")
        return
    if not content:
        return

    # Truncar contenidos enormes (foto OCR, dumps) para no inflar la DB.
    safe_content = content if len(content) <= _MAX_CONTENT_BYTES else (
        content[:_MAX_CONTENT_BYTES] + "…[truncado]"
    )

    try:
        _db.execute(
            """
            INSERT INTO conversaciones_bot
                (chat_id, vendedor_id, role, content,
                 modelo, tokens_input, tokens_output)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                chat_id,
                vendedor_id,
                role,
                safe_content,
                modelo,
                tokens_input,
                tokens_output,
            ),
        )
    except Exception as e:
        # No re-lanzar: la persistencia es best-effort. La cache en memoria
        # ya tiene el turno y el usuario no debe ver un error por esto.
        log.warning(f"no pude persistir turno chat={chat_id} role={role}: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# READ
# ═════════════════════════════════════════════════════════════════════════════

def cargar_turnos_recientes(chat_id: int, limite: int = 8) -> list[dict]:
    """
    Retorna los últimos N turnos del chat en orden cronológico ASC,
    en formato compatible con messages=[] de Claude:

        [{"role": "user", "content": "..."}, {"role": "assistant", ...}, ...]

    Si la DB no está disponible o el chat no tiene historia, retorna [].
    Nunca lanza.
    """
    if not _db.DB_DISPONIBLE:
        return []
    try:
        # Tomamos los últimos N por creado DESC y luego invertimos a orden
        # cronológico ASC, que es como lo espera Claude.
        rows = _db.query_all(
            """
            SELECT role, content
              FROM conversaciones_bot
             WHERE chat_id = %s
          ORDER BY creado DESC, id DESC
             LIMIT %s
            """,
            (chat_id, max(1, int(limite))),
        )
        # Invertir para que quede ASC y solo dejar las claves que Claude consume
        return [
            {"role": str(r["role"]), "content": str(r["content"])}
            for r in reversed(rows)
        ]
    except Exception as e:
        log.warning(f"no pude leer turnos chat={chat_id}: {e}")
        return []


# ═════════════════════════════════════════════════════════════════════════════
# CLEANUP
# ═════════════════════════════════════════════════════════════════════════════

def limpiar_antiguos(dias: int = 14) -> int:
    """
    Borra turnos con `creado < NOW() - INTERVAL 'N days'`.
    Pensado para job nightly. Retorna # filas borradas.
    """
    if not _db.DB_DISPONIBLE:
        return 0
    try:
        n = _db.execute(
            """
            DELETE FROM conversaciones_bot
             WHERE creado < NOW() - (%s || ' days')::INTERVAL
            """,
            (str(int(dias)),),
        )
        log.info(f"[cleanup] borrados {n} turnos > {dias} días")
        return int(n or 0)
    except Exception as e:
        log.warning(f"no pude limpiar turnos antiguos: {e}")
        return 0
