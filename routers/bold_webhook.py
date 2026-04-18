"""
Bold Webhook — Notificaciones de pagos en Ferretería Punto Rojo.
Documentación oficial: https://developers.bold.co/webhook

Estructura real del JSON de Bold:
  - Campo de tipo de evento: "type"  (NO "event")
  - Monto: data.amount.total         (NO data.amount)
  - ID pago: data.payment_id         (NO data.id)
  - Método QR: "QR"                  (NO "QR_BOLD")

Variable de entorno requerida:
  TELEGRAM_NOTIFY_CHAT_ID — ID del grupo de Telegram (número negativo, ej: -100123456789)
"""
import base64
import hashlib
import hmac
import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("ferrebot.bold_webhook")
router = APIRouter()

# ── Mapeo de métodos de pago ──────────────────────────────────────────────────
_METODO_LABEL = {
    "QR":                 "🟣 QR Bold",
    "CARD":               "💳 Tarjeta (datáfono)",
    "CARD_WEB":           "💳 Tarjeta web",
    "NEQUI":              "🟣 Nequi",
    "BOTON_BANCOLOMBIA":  "🔵 Botón Bancolombia",
    "PSE":                "🔵 PSE",
    "DAVIPLATA":          "🔴 Daviplata",
    "SOFT_POS":           "💳 Tarjeta (móvil)",
}

_TIPO_LABEL = {
    "SALE_APPROVED":  "✅ *Pago recibido*",
    "SALE_REJECTED":  "❌ *Pago rechazado*",
    "VOID_APPROVED":  "↩️ *Anulación aprobada*",
    "VOID_REJECTED":  "⚠️ *Anulación rechazada*",
}


def _fmt_metodo(raw: str) -> str:
    return _METODO_LABEL.get((raw or "").upper(), f"💳 {raw}")


def _fmt_monto(valor) -> str:
    try:
        return f"${int(float(valor)):,}".replace(",", ".")
    except Exception:
        return str(valor)


def _verificar_firma(raw_body: bytes, signature: str, secret: str) -> bool:
    """
    Verificación HMAC-SHA256 según docs de Bold:
    1. Codificar el body crudo en Base64
    2. Cifrar con HMAC-SHA256 usando la llave secreta
    3. Comparar con el header x-bold-signature
    """
    if not secret or not signature:
        return True  # Sin secret configurado, aceptar todo
    try:
        encoded = base64.b64encode(raw_body)
        hashed = hmac.new(
            key=secret.encode("utf-8"),
            msg=encoded,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(hashed.encode(), signature.encode())
    except Exception as e:
        logger.warning(f"Bold webhook: error verificando firma: {e}")
        return False


async def _enviar_telegram(mensaje: str) -> None:
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Bold webhook: falta TELEGRAM_TOKEN o TELEGRAM_NOTIFY_CHAT_ID")
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
                logger.warning(f"Bold webhook: Telegram respondió {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Bold webhook: error enviando a Telegram: {e}")


@router.post("/bold/webhook")
async def bold_webhook(request: Request):
    """
    Endpoint que recibe eventos de Bold.
    IMPORTANTE: Bold espera HTTP 200 en máximo 2 segundos.
    Nunca retornar 4xx/5xx o Bold reintentará hasta 5 veces.
    """
    # Leer body crudo ANTES de parsear (necesario para verificar firma)
    raw_body = await request.body()

    # Verificar firma si está configurada la llave secreta
    secret    = os.getenv("BOLD_WEBHOOK_SECRET", "")
    signature = request.headers.get("x-bold-signature", "")
    if secret and not _verificar_firma(raw_body, signature, secret):
        logger.warning("Bold webhook: firma inválida — petición ignorada")
        return JSONResponse({"status": "ok"})  # Igual 200 para no exponer info

    # Parsear JSON
    try:
        import json
        body = json.loads(raw_body)
    except Exception:
        return JSONResponse({"status": "ok"})

    # ── Campos según estructura real de Bold ─────────────────────────────────
    tipo  = body.get("type", "")           # "SALE_APPROVED", "SALE_REJECTED", etc.
    data  = body.get("data", {})

    payment_id   = data.get("payment_id", "")
    metodo_raw   = data.get("payment_method", "")
    payer_email  = data.get("payer_email", "")
    monto_obj    = data.get("amount", {})
    total        = monto_obj.get("total", 0)
    referencia   = (data.get("metadata") or {}).get("reference") or ""

    logger.info(f"Bold webhook recibido — tipo: {tipo}, método: {metodo_raw}, total: {total}")

    # Solo notificar eventos relevantes
    titulo = _TIPO_LABEL.get(tipo)
    if not titulo:
        return JSONResponse({"status": "ok"})

    metodo = _fmt_metodo(metodo_raw)
    monto  = _fmt_monto(total)

    mensaje = f"{titulo} — Bold\n💰 Monto: *{monto}*\nMétodo: {metodo}\n"
    if referencia:
        mensaje += f"Ref: `{referencia}`\n"
    if payer_email and payer_email not in ("XXXX@XXX.XX", ""):
        mensaje += f"📧 {payer_email}\n"
    if payment_id:
        mensaje += f"ID: `{payment_id}`"

    await _enviar_telegram(mensaje)
    logger.info(f"Bold notificado: {monto} vía {metodo_raw}")

    return JSONResponse({"status": "ok"})
