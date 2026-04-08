"""
routers/facturacion.py — Facturación Electrónica DIAN vía MATIAS API

Endpoints:
  POST /facturacion/emitir                  — emite la FE para una venta registrada
  GET  /facturacion/lista                   — lista las últimas facturas emitidas
  GET  /facturacion/pdf/{cufe}              — descarga el PDF desde MATIAS API por CUFE
  GET  /facturacion/ventas-pendientes       — ventas sin FE en una fecha dada (para el dashboard)
  POST /facturacion/webhook                 — recibe eventos de MATIAS API (invoice.accepted, email.sent)
  GET  /facturacion/estado/{numero}         — consulta estado DIAN de un documento
  GET  /facturacion/ultimo-numero           — último número emitido en MATIAS API
  GET  /facturacion/validar-cliente         — valida datos de cliente en RUT/DIAN
  POST /facturacion/reenviar-correo/{cufe}  — reenvía PDF de factura al correo del cliente
  POST /facturacion/nota-credito            — emite nota crédito DIAN
  POST /facturacion/nota-debito             — emite nota débito DIAN
  GET  /facturacion/notas                   — lista notas crédito/débito emitidas
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta

_TZ_BOGOTA = timezone(timedelta(hours=-5))

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

import db as _db

logger = logging.getLogger("ferrebot.api")
router = APIRouter()


# ── Modelos ───────────────────────────────────────────────────────────────────

class FacturarRequest(BaseModel):
    venta_id: int


class LineaNotaItem(BaseModel):
    producto_nombre:  str
    producto_id:      int | None = None
    cantidad:         float
    precio_unitario:  float
    total:            float
    tiene_iva:        bool  = False
    porcentaje_iva:   int   = 0
    unidad_medida:    str   = "Unidad"


class NotaCreditoRequest(BaseModel):
    """Cuerpo para emitir una nota crédito DIAN."""
    factura_cufe:    str
    factura_numero:  str
    factura_fecha:   str               # YYYY-MM-DD
    razon_id:        int = 2           # 2=anulación es la más común en ferretería
    venta_id:        int | None = None
    lineas:          list[LineaNotaItem]


class NotaDebitoRequest(BaseModel):
    """Cuerpo para emitir una nota débito DIAN."""
    factura_cufe:    str
    factura_numero:  str
    factura_fecha:   str               # YYYY-MM-DD
    razon_id:        int = 3           # 3=cambio de valor
    venta_id:        int | None = None
    lineas:          list[LineaNotaItem]


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

    fecha_consulta = fecha or datetime.now(_TZ_BOGOTA).strftime('%Y-%m-%d')

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
            COALESCE(
                v.hora::text,
                TO_CHAR(v.created_at AT TIME ZONE 'America/Bogota', 'HH24:MI')
            )                                               AS hora,
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


# ── GET /facturacion/estado/{numero} — Estado DIAN ────────────────────────────

@router.get("/facturacion/estado/{numero}")
async def estado_dian(numero: str, prefix: str = Query(default=None)):
    """
    Consulta el estado de validación DIAN de un documento emitido.
    Ejemplo: GET /facturacion/estado/LZT5280  o  /facturacion/estado/5280?prefix=LZT
    """
    from services.facturacion_service import consultar_estado_dian
    try:
        data = await consultar_estado_dian(numero, prefix)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return data


# ── GET /facturacion/ultimo-numero — Último número emitido ────────────────────

@router.get("/facturacion/ultimo-numero")
async def ultimo_numero(
    resolution: str = Query(default=None),
    prefix:     str = Query(default=None),
):
    """
    Obtiene el último número de documento emitido en MATIAS API.
    Sirve para sincronizar el contador local con el estado real de la DIAN.
    """
    from services.facturacion_service import obtener_ultimo_documento
    try:
        data = await obtener_ultimo_documento(resolution, prefix)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return data


# ── GET /facturacion/validar-cliente — Validar adquirente en RUT ──────────────

@router.get("/facturacion/validar-cliente")
async def validar_cliente(
    tipo_id:             str = Query(..., description="Tipo de identificación: CC, NIT, CE, etc."),
    numero_identificacion: str = Query(..., description="Número de identificación del cliente"),
):
    """
    Valida los datos de un cliente en el RUT/DIAN antes de emitir la factura.
    Útil en el dashboard para autocompletar datos fiscales del cliente.
    """
    from services.facturacion_service import consultar_adquirente
    try:
        data = await consultar_adquirente(tipo_id, numero_identificacion)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return data


# ── POST /facturacion/reenviar-correo/{cufe} — Reenviar PDF por email ─────────

@router.post("/facturacion/reenviar-correo/{cufe}")
async def reenviar_correo(cufe: str):
    """
    Reenvía el PDF de una factura al correo del cliente registrado en MATIAS API.
    Útil cuando el envío original falló o el cliente solicita una copia.
    """
    from services.facturacion_service import reenviar_correo_factura
    try:
        data = await reenviar_correo_factura(cufe)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return data


# ── POST /facturacion/nota-credito — Emitir Nota Crédito ─────────────────────

@router.post("/facturacion/nota-credito")
async def emitir_nota_credito(req: NotaCreditoRequest):
    """
    Emite una nota crédito DIAN para anular o corregir una factura emitida.

    Razones disponibles (razon_id):
        1 — Devolución parcial de los bienes
        2 — Anulación de factura  ← más común en ferretería
        3 — Rebaja o descuento parcial
        4 — Ajuste de precio
        5 — Otro
    """
    from services.facturacion_service import emitir_nota_credito as _emitir_nc

    lineas = [l.model_dump() for l in req.lineas]
    resultado = await _emitir_nc(
        factura_cufe    = req.factura_cufe,
        factura_numero  = req.factura_numero,
        factura_fecha   = req.factura_fecha,
        razon_id        = req.razon_id,
        venta_id        = req.venta_id or 0,
        lineas_devueltas= lineas,
    )
    if not resultado["ok"]:
        raise HTTPException(status_code=400, detail=resultado["error"])
    return resultado


# ── POST /facturacion/nota-debito — Emitir Nota Débito ───────────────────────

@router.post("/facturacion/nota-debito")
async def emitir_nota_debito(req: NotaDebitoRequest):
    """
    Emite una nota débito DIAN para agregar cargos adicionales a una factura.

    Razones disponibles (razon_id):
        1 — Intereses
        2 — Gastos por cobrar
        3 — Cambio del valor  ← más común
        4 — Otro
    """
    from services.facturacion_service import emitir_nota_debito as _emitir_nd

    lineas = [l.model_dump() for l in req.lineas]
    resultado = await _emitir_nd(
        factura_cufe   = req.factura_cufe,
        factura_numero = req.factura_numero,
        factura_fecha  = req.factura_fecha,
        razon_id       = req.razon_id,
        venta_id       = req.venta_id or 0,
        lineas         = lineas,
    )
    if not resultado["ok"]:
        raise HTTPException(status_code=400, detail=resultado["error"])
    return resultado


# ── GET /facturacion/notas — Historial de notas crédito/débito ────────────────

@router.get("/facturacion/notas")
def listar_notas(
    tipo:   str | None = Query(default=None, description="credito | debito"),
    limite: int        = Query(default=50),
):
    """Lista las notas crédito/débito emitidas, más recientes primero."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    filtro_tipo = "AND fe.tipo = %s" if tipo else ""
    params      = [tipo, limite] if tipo else [limite]

    rows = _db.query_all(
        f"""
        SELECT fe.id, fe.tipo, fe.numero, fe.cufe, fe.factura_cufe_ref,
               fe.razon_id, fe.total, fe.estado, fe.error_msg, fe.created_at,
               v.consecutivo AS venta_consecutivo
        FROM facturas_electronicas fe
        LEFT JOIN ventas v ON fe.venta_id = v.id
        WHERE fe.tipo IN ('nota_credito', 'nota_debito') {filtro_tipo}
        ORDER BY fe.created_at DESC
        LIMIT %s
        """,
        params,
    )
    return [dict(r) for r in rows]


# ── Webhook MATIAS API ────────────────────────────────────────────────────────

@router.post("/facturacion/webhook")
async def webhook_matias(request: Request):
    """
    Recibe eventos de MATIAS API en tiempo real (compatible v2 y v3.0.0).

    Configura esta URL en el panel de MATIAS API:
        https://tu-app.railway.app/facturacion/webhook

    v3.0.0: verifica firma HMAC-SHA256 si MATIAS_WEBHOOK_SECRET está configurado.
    Header: X-Webhook-Signature: sha256=<hash>

    Eventos soportados:
        document.accepted  — DIAN aceptó → actualiza estado en DB + notifica bot
        document.rejected  — DIAN rechazó → guarda error
        document.voided    — Factura anulada
        email.sent / email.delivered — confirmación correo al cliente
    """
    import hashlib, hmac as _hmac, os as _os

    raw_body = await request.body()

    # ── Verificar firma HMAC-SHA256 (v3.0.0) ─────────────────────────────────
    webhook_secret = _os.getenv("MATIAS_WEBHOOK_SECRET")
    if webhook_secret:
        sig_header = request.headers.get("x-webhook-signature", "")
        if sig_header:
            expected = "sha256=" + _hmac.new(
                webhook_secret.encode(), raw_body, hashlib.sha256
            ).hexdigest()
            if not _hmac.compare_digest(sig_header, expected):
                logger.warning("Webhook MATIAS API: firma HMAC inválida — posible request falso")
                raise HTTPException(status_code=401, detail="Firma webhook inválida")

    try:
        payload = __import__("json").loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON inválido")

    evento = payload.get("event") or payload.get("type") or ""
    data   = payload.get("data") or payload.get("document") or payload

    # ── Extraer CUFE compatible con v2 (XmlDocumentKey) y v3 (track_id) ──────
    cufe = (
        data.get("track_id")        or   # v3.0.0
        data.get("XmlDocumentKey")  or   # v2
        data.get("document_key")    or
        data.get("cufe")            or
        ""
    )
    numero   = data.get("document_number") or data.get("number") or ""
    email_ok = data.get("email_sent") or data.get("email_delivered")

    logger.info("Webhook MATIAS API — evento: %s | cufe: %s…", evento, cufe[:20] if cufe else "?")

    if not _db.DB_DISPONIBLE:
        return {"ok": True, "msg": "DB no disponible, evento ignorado"}

    # ── document.accepted (v3) / invoice.accepted (v2) ───────────────────────
    if "accept" in evento.lower() or evento == "document.emitted" or payload.get("success"):
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

    # ── document.rejected (v3) / invoice.rejected (v2) ───────────────────────
    elif "reject" in evento.lower() or "error" in evento.lower() or evento == "document.voided":
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
