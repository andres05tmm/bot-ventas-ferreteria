"""
Bold Webhook — Notificaciones de pagos QR en Ferretería Punto Rojo.
Recibe eventos SALE_APPROVED de Bold y los reenvía al chat de Telegram.

Variable de entorno requerida:
  TELEGRAM_NOTIFY_CHAT_ID — ID del chat/grupo donde llegan las notificaciones
                            (mismo que se usa en facturacion.py)
"""
import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("ferrebot.bold_webhook")
router = APIRouter()

# ── Mapeo de métodos de pago a emojis/etiquetas legibles ─────────────────────
_METODO_LABEL = {
    "QR_BOLD":            "🟣 QR Bold",
    "NEQUI":              "🟣 Nequi",
    "BANCOLOMBIA_BUTTON": "🔵 Botón Bancolombia",
    "PSE":                "🔵 PSE",
    "CARD_CREDIT":        "💳 Tarjeta crédito",
    "CARD_DEBIT":         "💳 Tarjeta débito",
    "DAVIPLATA":          "🔴 Daviplata",
}


def _fmt_metodo(raw: str) -> str:
    return _METODO_LABEL.get((raw or "").upper(), f"💳 {raw}")


def _fmt_monto(valor) -> str:
    try:
        return f"${int(float(valor)):,}".replace(",", ".")
    except Exception:
        return str(valor)


async def _enviar_telegram(mensaje: str) -> None:
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Bold webhook: falta TELEGRAM_TOKEN o TELEGRAM_NOTIFY_CHAT_ID — notificación no enviada")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": mensaje,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
    except Exception as e:
        logger.warning(f"Bold webhook: error enviando a Telegram: {e}")


@router.post("/bold/webhook")
async def bold_webhook(request: Request):
    """
    Endpoint que recibe eventos de Bold.
    Bold espera siempre HTTP 200 — nunca retornar 4xx/5xx.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "ok"})

    event = body.get("event", "")
    data  = body.get("data", {})

    logger.info(f"Bold webhook recibido — evento: {event}")

    # Solo notificamos ventas aprobadas
    if event != "SALE_APPROVED":
        return JSONResponse({"status": "ok"})

    monto      = _fmt_monto(data.get("amount", 0))
    metodo_raw = data.get("payment_method", "")
    metodo     = _fmt_metodo(metodo_raw)
    referencia = data.get("order_id") or data.get("id", "")

    mensaje = (
        "✅ *Pago recibido — Bold*\n"
        f"💰 Monto: *{monto}*\n"
        f"Método: {metodo}\n"
    )
    if referencia:
        mensaje += f"🔑 Ref: `{referencia}`"

    await _enviar_telegram(mensaje)
    logger.info(f"Bold pago notificado: {monto} vía {metodo_raw}")

    return JSONResponse({"status": "ok"})
