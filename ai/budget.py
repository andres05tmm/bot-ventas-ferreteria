"""
ai/budget.py — Control de gasto de Claude por vendedor y día.

Provee dos funciones principales:

    puede_llamar(vendedor_id, modelo) -> (bool, str)
        Verifica si el vendedor puede hacer otra llamada al modelo.
        Retorna (True, "") si está OK, (False, mensaje_usuario) si agotó budget.
        Si vendedor_id es None o la DB no está disponible, retorna (True, "")
        — nunca bloquea por falta de información.

    registrar_uso(vendedor_id, modelo, usage_obj)
        UPSERT en api_costo_diario incrementando contadores y costo en USD.
        Calcula el costo real usando precios vigentes de Claude Sonnet 4.6
        y Haiku 4.5 (incluyendo cache read/write con TTL 1h).

Los límites diarios se configuran vía env vars:

    BUDGET_SONNET_DIARIO  (default 300 llamadas/vendedor/día)
    BUDGET_HAIKU_DIARIO   (default 1000 llamadas/vendedor/día)
"""

# -- stdlib --
import os
import logging
from datetime import datetime

# -- propios --
import db as _db
from config import COLOMBIA_TZ

log = logging.getLogger("ferrebot.ai.budget")


# ═════════════════════════════════════════════════════════════════════════════
# LIMITES (configurables por env)
# ═════════════════════════════════════════════════════════════════════════════
BUDGET_SONNET_DIARIO = int(os.getenv("BUDGET_SONNET_DIARIO", "300"))
BUDGET_HAIKU_DIARIO  = int(os.getenv("BUDGET_HAIKU_DIARIO",  "1000"))


# ═════════════════════════════════════════════════════════════════════════════
# PRECIOS CLAUDE (USD por millón de tokens) — actualizados Abr 2026
# ═════════════════════════════════════════════════════════════════════════════
# Sonnet 4.6
_PRECIO_SONNET = {
    "input":         3.00,   # input normal
    "cache_read":    0.30,   # token cacheado leído (90% descuento vs input)
    "cache_write_1h": 6.00,  # token cacheado escrito con TTL 1h (2× base)
    "cache_write_5m": 3.75,  # token cacheado escrito con TTL 5min (1.25× base)
    "output":       15.00,
}
# Haiku 4.5
_PRECIO_HAIKU = {
    "input":         1.00,
    "cache_read":    0.10,
    "cache_write_1h": 2.00,
    "cache_write_5m": 1.25,
    "output":        5.00,
}


def _tag_modelo(modelo: str) -> str:
    """'claude-sonnet-4-6' → 'sonnet'; 'claude-haiku-4-5-...' → 'haiku'. Otro → 'otro'."""
    m = (modelo or "").lower()
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    return "otro"


def _limite_diario(tag: str) -> int | None:
    """Retorna el límite diario para el modelo, o None si no aplica."""
    if tag == "sonnet":
        return BUDGET_SONNET_DIARIO
    if tag == "haiku":
        return BUDGET_HAIKU_DIARIO
    return None


def _hoy() -> str:
    """Fecha Colombia YYYY-MM-DD."""
    return datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d")


# ═════════════════════════════════════════════════════════════════════════════
# API PUBLICA
# ═════════════════════════════════════════════════════════════════════════════

def puede_llamar(vendedor_id: int | None, modelo: str) -> tuple[bool, str]:
    """
    Verifica si el vendedor tiene budget disponible para llamar al modelo.

    Casos que retornan (True, "") sin consultar DB:
      - vendedor_id es None  (no se conoce el vendedor)
      - la DB no está disponible
      - el modelo no es sonnet ni haiku
    """
    if vendedor_id is None or not _db.DB_DISPONIBLE:
        return True, ""

    tag = _tag_modelo(modelo)
    limite = _limite_diario(tag)
    if limite is None:
        return True, ""

    try:
        row = _db.query_one(
            """SELECT llamadas FROM api_costo_diario
               WHERE fecha = %s AND vendedor_id = %s AND modelo = %s""",
            (_hoy(), vendedor_id, tag),
        )
        usadas = int(row["llamadas"]) if row else 0
        if usadas >= limite:
            log.warning(
                f"[BUDGET] ⛔ vendedor={vendedor_id} modelo={tag} "
                f"usadas={usadas} limite={limite} — bloqueado"
            )
            return False, (
                f"⚠️ Límite diario de IA alcanzado ({limite} llamadas {tag}). "
                f"Podés registrar ventas manualmente con el formato: "
                f"'anadir N producto = total'. Se resetea mañana a medianoche."
            )
        # Warning al 80% del budget, sin bloquear
        if usadas >= int(limite * 0.8):
            log.warning(
                f"[BUDGET] ⚠️ vendedor={vendedor_id} modelo={tag} "
                f"usadas={usadas}/{limite} ({usadas * 100 // limite}%)"
            )
        return True, ""
    except Exception as e:
        # Fail-open: si algo rompe en el check, dejamos pasar la llamada.
        # Es preferible gastar de más que bloquear al vendedor.
        log.error(f"[BUDGET] error chequeando budget: {e}")
        return True, ""


def registrar_uso(
    vendedor_id: int | None,
    modelo: str,
    usage_obj,
    *,
    cache_ttl: str = "1h",
) -> float:
    """
    UPSERT en api_costo_diario con los contadores del objeto .usage de Claude.

    Retorna el costo estimado en USD de esta llamada específica (útil para logs).
    Si vendedor_id es None se usa 0 (bucket 'sin vendedor').
    Si la DB no está disponible solo calcula y retorna el costo, sin persistir.
    """
    tag = _tag_modelo(modelo)
    precio = _PRECIO_SONNET if tag == "sonnet" else _PRECIO_HAIKU if tag == "haiku" else None

    # Extraer counters del usage — soporta objeto Pydantic o dict
    def _g(attr, default=0):
        if usage_obj is None:
            return default
        if isinstance(usage_obj, dict):
            return int(usage_obj.get(attr, default) or default)
        return int(getattr(usage_obj, attr, default) or default)

    inp    = _g("input_tokens")
    cr     = _g("cache_read_input_tokens")
    cc     = _g("cache_creation_input_tokens")
    outp   = _g("output_tokens")

    # Calcular costo en USD
    costo = 0.0
    if precio is not None:
        cache_write_key = "cache_write_1h" if cache_ttl == "1h" else "cache_write_5m"
        costo = (
            (inp  / 1_000_000) * precio["input"]
            + (cr  / 1_000_000) * precio["cache_read"]
            + (cc  / 1_000_000) * precio[cache_write_key]
            + (outp / 1_000_000) * precio["output"]
        )

    # Persistir si podemos
    if _db.DB_DISPONIBLE:
        try:
            _db.execute(
                """
                INSERT INTO api_costo_diario
                    (fecha, vendedor_id, modelo,
                     llamadas, input_tokens, cache_read_tokens,
                     cache_created_tokens, output_tokens, costo_usd)
                VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s)
                ON CONFLICT (fecha, vendedor_id, modelo) DO UPDATE SET
                    llamadas             = api_costo_diario.llamadas + 1,
                    input_tokens         = api_costo_diario.input_tokens         + EXCLUDED.input_tokens,
                    cache_read_tokens    = api_costo_diario.cache_read_tokens    + EXCLUDED.cache_read_tokens,
                    cache_created_tokens = api_costo_diario.cache_created_tokens + EXCLUDED.cache_created_tokens,
                    output_tokens        = api_costo_diario.output_tokens        + EXCLUDED.output_tokens,
                    costo_usd            = api_costo_diario.costo_usd            + EXCLUDED.costo_usd,
                    actualizado          = NOW()
                """,
                (
                    _hoy(),
                    vendedor_id if vendedor_id is not None else 0,
                    tag,
                    inp, cr, cc, outp, costo,
                ),
            )
        except Exception as e:
            log.error(f"[BUDGET] error registrando uso: {e}")

    return costo


def resumen_dia(fecha: str | None = None) -> list[dict]:
    """
    Resumen por vendedor/modelo para reportería.
    Si fecha es None se usa hoy Colombia.
    """
    if not _db.DB_DISPONIBLE:
        return []
    fecha = fecha or _hoy()
    rows = _db.query_all(
        """SELECT vendedor_id, modelo, llamadas,
                  input_tokens, cache_read_tokens, cache_created_tokens,
                  output_tokens, costo_usd
             FROM api_costo_diario
            WHERE fecha = %s
         ORDER BY costo_usd DESC""",
        (fecha,),
    )
    return [dict(r) for r in rows]
