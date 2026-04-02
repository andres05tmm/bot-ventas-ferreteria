"""
routers/facturacion.py — Facturación Electrónica DIAN vía MATIAS API

Endpoints:
  POST /facturacion/emitir              — emite la FE para una venta registrada
  GET  /facturacion/lista               — lista las últimas facturas emitidas
  GET  /facturacion/pdf/{cufe}          — descarga el PDF desde MATIAS API por CUFE
  GET  /facturacion/ventas-pendientes   — ventas sin FE en una fecha dada (para el dashboard)
  POST /facturacion/webhook             — recibe eventos de MATIAS API (invoice.accepted, email.sent)
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

import db as _db

logger = logging.getLogger("ferrebot.api")
router = APIRouter()


# ── Modelos ───────────────────────────────────────────────────────────────────

class FacturarRequest(BaseModel):
    venta_id: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/facturacion/emitir")
async def emitir(req: FacturarRequest):
    """Emite la factura electrónica DIAN para una venta ya registrada."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    from services.facturacion_service import emitir_factura
    resultado = await emitir_factura(req.venta_id)

    if not resultado["ok"]:
        raise HTTPException(status_code=400, detail=resultado["error"])

    return resultado


@router.get("/facturacion/ventas-pendientes")
def ventas_pendientes(fecha: str = Query(default=None)):
    """
    Retorna las ventas del día indicado (o hoy) que NO tienen factura electrónica emitida.
    Incluye el id interno de la venta (requerido por /facturacion/emitir).
    """
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    fecha_consulta = fecha or str(date.today())

    rows = _db.query_all(
        """
        SELECT
            v.id,
            v.consecutivo,
            COALESCE(v.cliente_nombre, 'Consumidor Final') AS cliente_nombre,
            v.total,
            COALESCE(v.metodo_pago, 'efectivo')            AS metodo_pago,
            COALESCE(v.factura_estado, 'sin_factura')      AS factura_estado,
            v.fecha::text                                   AS fecha,
            COALESCE(v.hora::text, '')                      AS hora,
            COALESCE(v.vendedor, '')                        AS vendedor
        FROM ventas v
        WHERE v.fecha::date = %s
          AND (v.factura_estado IS NULL OR v.factura_estado != 'emitida')
        ORDER BY v.consecutivo DESC
        """,
        (fecha_consulta,),
    )
    return [dict(r) for r in rows]


@router.get("/facturacion/lista")
def listar_facturas(limite: int = 50):
    """Lista las últimas facturas electrónicas emitidas."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    rows = _db.query_all(
        """
        SELECT fe.id,
               fe.numero,
               fe.cufe,
               fe.fecha_emision,
               fe.estado,
               fe.cliente_nombre,
               fe.total,
               fe.error_msg,
               v.consecutivo AS venta_consecutivo
        FROM facturas_electronicas fe
        LEFT JOIN ventas v ON fe.venta_id = v.id
        ORDER BY fe.fecha_emision DESC
        LIMIT %s
        """,
        (limite,),
    )
    return [dict(r) for r in rows]


@router.get("/facturacion/pdf/{cufe}")
async def descargar_pdf(cufe: str):
    """
    Descarga el PDF de una factura desde MATIAS API usando el CUFE.
    Retorna el PDF como application/pdf para abrir o descargar desde el dashboard.
    El token se obtiene automáticamente con login (no requiere MATIAS_API_TOKEN fijo).
    """
    from services.facturacion_service import obtener_pdf
    try:
        pdf_bytes = await obtener_pdf(cufe)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error obteniendo PDF desde Matias API: {e}")

    return Response(content=pdf_bytes, media_type="application/pdf")


# ── Webhook MATIAS API ────────────────────────────────────────────────────────

@router.post("/facturacion/webhook")
async def webhook_matias(request: Request):
    """
    Recibe eventos de MATIAS API en tiempo real.

    Configura esta URL en el panel de MATIAS API:
        https://tu-app.railway.app/facturacion/webhook

    Eventos que maneja:
        invoice.accepted  — DIAN aceptó la factura → actualiza estado en DB + notifica bot
        invoice.rejected  — DIAN rechazó → guarda error
        email.sent        — confirmación de que el correo llegó al cliente

    MATIAS API envía un POST con JSON, sin firma HMAC en v2 pública.
    Si en el futuro agregan firma, validarla aquí con MATIAS_WEBHOOK_SECRET.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON inválido")

    evento   = payload.get("event") or payload.get("type") or ""
    data     = payload.get("data") or payload.get("document") or payload
    cufe     = data.get("XmlDocumentKey") or data.get("document_key") or data.get("cufe") or ""
    numero   = data.get("number") or data.get("document_number") or ""
    email_ok = data.get("email_sent") or data.get("email_delivered")

    logger.info("Webhook MATIAS API — evento: %s | cufe: %s…", evento, cufe[:20] if cufe else "?")

    if not _db.DB_DISPONIBLE:
        return {"ok": True, "msg": "DB no disponible, evento ignorado"}

    # ── invoice.accepted ─────────────────────────────────────────────────────
    if "accept" in evento.lower() or payload.get("success"):
        if cufe:
            try:
                _db.execute(
                    """
                    UPDATE facturas_electronicas
                    SET estado = 'emitida', error_msg = NULL
                    WHERE cufe = %s AND estado != 'emitida'
                    """,
                    [cufe],
                )
                _db.execute(
                    """
                    UPDATE ventas
                    SET factura_estado = 'emitida', facturada_at = NOW()
                    WHERE factura_cufe = %s AND factura_estado != 'emitida'
                    """,
                    [cufe],
                )
                logger.info("✅ Webhook: factura %s marcada como emitida", numero or cufe[:16])

                # Notificar al bot de Telegram si está disponible
                _notificar_bot_factura_aceptada(cufe, numero, email_ok)

            except Exception as e:
                logger.error("Webhook: error actualizando DB para cufe %s: %s", cufe[:20], e)

    # ── invoice.rejected ─────────────────────────────────────────────────────
    elif "reject" in evento.lower() or "error" in evento.lower():
        error_msg = data.get("message") or data.get("errors") or "Rechazada por DIAN"
        if isinstance(error_msg, dict):
            error_msg = " | ".join(f"{k}: {v}" for k, v in error_msg.items())
        if cufe:
            try:
                _db.execute(
                    "UPDATE facturas_electronicas SET estado = 'error', error_msg = %s WHERE cufe = %s",
                    [str(error_msg)[:500], cufe],
                )
                logger.warning("❌ Webhook: factura %s rechazada — %s", numero or cufe[:16], str(error_msg)[:100])
            except Exception as e:
                logger.error("Webhook: error guardando rechazo cufe %s: %s", cufe[:20], e)

    # ── email.sent ───────────────────────────────────────────────────────────
    elif "email" in evento.lower():
        logger.info("📧 Webhook: correo de factura %s entregado al cliente", numero or cufe[:16])
        # Aquí puedes guardar timestamp de entrega de correo si lo necesitas

    return {"ok": True, "evento": evento}


def _notificar_bot_factura_aceptada(cufe: str, numero: str, email_ok) -> None:
    """
    Intenta notificar al grupo/canal de Telegram que la DIAN aceptó la factura.
    Solo actúa si hay un TELEGRAM_NOTIFY_CHAT_ID configurado en Railway.
    No bloquea — fallo silencioso.
    """
    import os, threading, httpx as _httpx

    chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
    token   = os.getenv("TELEGRAM_TOKEN")
    if not chat_id or not token:
        return

    email_txt = " · 📧 correo enviado al cliente" if email_ok else ""
    texto = (
        f"✅ *DIAN aceptó factura {numero}*\n"
        f"CUFE: `{cufe[:24]}…`{email_txt}"
    )

    def _send():
        try:
            _httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"},
                timeout=8,
            )
        except Exception as e:
            logger.debug("Notificación Telegram webhook fallida: %s", e)

    threading.Thread(target=_send, daemon=True).start()
