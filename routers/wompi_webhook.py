"""
Wompi Webhook — Notificaciones de pagos en Ferretería Punto Rojo.
Documentación: https://docs.wompi.co/docs/colombia/eventos/

Estructura del evento Wompi:
{
  "event": "transaction.updated",
  "data": {
    "transaction": {
      "id": "...",
      "status": "APPROVED",  # APPROVED, DECLINED, VOIDED, ERROR
      "amount_in_cents": 4490000,
      "reference": "...",
      "payment_method_type": "NEQUI",  # NEQUI, CARD, PSE, BANCOLOMBIA_TRANSFER, etc.
      "customer_email": "...",
    }
  },
  "timestamp": 1530291411
}

Variable de entorno requerida:
  TELEGRAM_NOTIFY_CHAT_ID — ID del grupo de Telegram (número negativo)
"""
import hashlib
import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("ferrebot.wompi_webhook")
router = APIRouter()

# ── Mapeo de métodos de pago ──────────────────────────────────────────────────
_METODO_LABEL = {
    "NEQUI":                  "🟣 Nequi",
    "CARD":                   "💳 Tarjeta",
    "PSE":                    "🔵 PSE",
    "BANCOLOMBIA_TRANSFER":   "🔵 Bancolombia",
    "BANCOLOMBIA_QR":         "🔵 QR Bancolombia",
    "DAVIPLATA":              "🔴 Daviplata",
    "EFECTY":                 "💵 Efecty",
}

_STATUS_LABEL = {
    "APPROVED": "✅ *Pago recibido*",
    "DECLINED": "❌ *Pago rechazado*",
    "VOIDED":   "↩️ *Pago anulado*",
    "ERROR":    "⚠️ *Error en el pago*",
}


def _fmt_metodo(raw: str) -> str:
    return _METODO_LABEL.get((raw or "").upper(), f"💳 {raw}")


def _fmt_monto(centavos) -> str:
    """Wompi maneja montos en centavos."""
    try:
        pesos = int(float(centavos)) // 100
        return f"${pesos:,}".replace(",", ".")
    except Exception:
        return str(centavos)


def _verificar_firma(body: dict, checksum_recibido: str, secret: str) -> bool:
    """
    Verificación de firma Wompi:
    Concatenar los valores de signature.properties + timestamp + secret → SHA256
    """
    if not secret or not checksum_recibido:
        return True
    try:
        properties = body.get("signature", {}).get("properties", [])
        timestamp  = str(body.get("timestamp", ""))
        data       = body.get("data", {})
        tx         = data.get("transaction", {})

        # Extraer valores anidados (ej: "transaction.id" → tx["id"])
        partes = []
        for prop in properties:
            keys = prop.split(".")
            val = tx
            for k in keys[1:]:  # saltar "transaction."
                val = val.get(k, "") if isinstance(val, dict) else ""
            partes.append(str(val))

        cadena = "".join(partes) + timestamp + secret
        checksum_calculado = hashlib.sha256(cadena.encode()).hexdigest().upper()
        return checksum_calculado == checksum_recibido.upper()
    except Exception as e:
        logger.warning(f"Wompi webhook: error verificando firma: {e}")
        return False


async def _enviar_telegram(mensaje: str) -> None:
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Wompi webhook: falta TELEGRAM_TOKEN o TELEGRAM_NOTIFY_CHAT_ID")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": mensaje,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code != 200:
                logger.warning(f"Wompi webhook: Telegram respondió {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Wompi webhook: error enviando a Telegram: {e}")


@router.post("/wompi/webhook")
async def wompi_webhook(request: Request):
    """
    Endpoint que recibe eventos de Wompi.
    Wompi espera HTTP 200 — siempre retornar 200.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "ok"})

    evento = body.get("event", "")
    data   = body.get("data", {})
    tx     = data.get("transaction", {})

    logger.info(f"Wompi webhook recibido — evento: {evento}")

    # Solo procesar actualizaciones de transacciones
    if evento != "transaction.updated":
        return JSONResponse({"status": "ok"})

    # Verificar firma si está configurado el secreto
    secret    = os.getenv("WOMPI_EVENTS_SECRET", "")
    checksum  = body.get("signature", {}).get("checksum", "")
    if secret and not _verificar_firma(body, checksum, secret):
        logger.warning("Wompi webhook: firma inválida — petición ignorada")
        return JSONResponse({"status": "ok"})

    status      = tx.get("status", "")
    centavos    = tx.get("amount_in_cents", 0)
    metodo_raw  = tx.get("payment_method_type", "")
    referencia  = tx.get("reference", "")
    email       = tx.get("customer_email", "")
    tx_id       = tx.get("id", "")

    titulo = _STATUS_LABEL.get(status)
    if not titulo:
        return JSONResponse({"status": "ok"})

    metodo = _fmt_metodo(metodo_raw)
    monto  = _fmt_monto(centavos)

    mensaje = f"{titulo} — Wompi\n💰 Monto: *{monto}*\nMétodo: {metodo}\n"
    if referencia:
        mensaje += f"Ref: `{referencia}`\n"
    if email:
        mensaje += f"📧 {email}\n"
    if tx_id:
        mensaje += f"ID: `{tx_id}`"

    await _enviar_telegram(mensaje)
    logger.info(f"Wompi notificado: {monto} vía {metodo_raw} — {status}")

    return JSONResponse({"status": "ok"})
