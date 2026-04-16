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
                TO_CHAR(v.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota', 'HH24:MI')
            )                                               AS hora,
            COALESCE(v.vendedor, '')                        AS vendedor
        FROM ventas v
        WHERE v.fecha::date = %s
          AND (v.factura_estado IS NULL OR v.factura_estado NOT IN ('emitida'))
          -- FIX: 'error' ahora aparece en pendientes para poder reintentar
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

def _verificar_firma_matias(
    raw_body:       bytes,
    sig_header:     str,
    webhook_id:     str,
    timestamp:      str,
    webhook_secret: str,
) -> bool:
    """
    Verifica la firma HMAC-SHA256 de los webhooks de MATIAS API v3.0.0.

    ── Algoritmo principal (documentación oficial MATIAS API v3.0.0) ──────────
        key       = webhook_secret (string completo, incluyendo prefijo "whsec_")
        content   = raw_body (bytes del body tal como llega, sin re-serializar)
        hash      = HMAC-SHA256(key.encode(), content) → hexdigest
        expected  = "sha256=<hexdigest>"
        Header HTTP recibido: X-Webhook-Signature

    Referencia docs: https://docs.matias-api.com/docs/endpoints#verificar-firma-hmac

    ── Fallback Svix (por si MATIAS cambia internamente) ─────────────────────
        secret_bytes   = base64_decode(secret.removeprefix("whsec_"))
        signed_content = f"{webhook_id}\\n{timestamp}\\n" + raw_body
        mac            = HMAC-SHA256(secret_bytes, signed_content)
        signature      = base64(mac) → "v1,<base64>"
        También acepta hex sin prefijo.
    """
    import hashlib
    import hmac as _hmac
    import base64 as _b64

    if not sig_header:
        logger.warning("Webhook MATIAS: header X-Webhook-Signature vacío — no se puede verificar")
        return False

    # ── Algoritmo 1: formato oficial MATIAS API v3 ────────────────────────────
    # La clave es el secret completo (incluido "whsec_") tal como lo muestra la doc.
    # El contenido firmado es el raw_body (no JSON.stringify → mismo resultado si
    # el body ya es el JSON canónico que envía MATIAS).
    try:
        mac_hex   = _hmac.new(
            webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        expected  = f"sha256={mac_hex}"
        if _hmac.compare_digest(expected, sig_header.strip()):
            return True
    except Exception as e:
        logger.warning("Webhook MATIAS: error en algoritmo v3: %s", e)

    # ── Algoritmo 2: fallback Svix (legacy / por si MATIAS usa Svix internamente)
    # Formato: secret decodificado en base64, contenido = id+ts+body, output base64
    try:
        secret_stripped = webhook_secret.removeprefix("whsec_")
        secret_bytes    = _b64.b64decode(secret_stripped)
        signed_content  = f"{webhook_id}\n{timestamp}\n".encode() + raw_body
        mac_svix        = _hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
        sig_b64         = _b64.b64encode(mac_svix).decode()
        sig_hex_svix    = mac_svix.hex()

        # Acepta "v1,<firma>" (múltiples: "v1,aaa v1,bbb") o hex directo
        candidatos = [
            s.removeprefix("v1,").strip()
            for s in sig_header.replace(",", " ").split()
            if s.strip()
        ]
        candidatos.append(sig_header.strip())

        if sig_b64 in candidatos or sig_hex_svix in candidatos:
            return True
    except Exception as e:
        logger.warning("Webhook MATIAS: error en fallback Svix: %s", e)

    return False


@router.post("/facturacion/webhook")
async def webhook_matias(request: Request):
    """
    Recibe eventos de MATIAS API en tiempo real (compatible v2 y v3.0.0).

    Configura esta URL en el panel de MATIAS API:
        https://tu-app.railway.app/facturacion/webhook

    Seguridad: verifica firma HMAC-SHA256 estilo Svix si MATIAS_WEBHOOK_SECRET
    está configurado en Railway.  El secreto debe empezar con "whsec_" y se
    obtiene/regenera desde el panel de MATIAS API → Webhooks → Signing Secret.

    Flujo de entrega al aceptarse una factura:
        - Consumidor Final (sin correo real) → PDF enviado al grupo de Telegram
        - Cliente con correo real            → Matias ya envió el email (send_email=1),
                                               solo se actualiza la DB y se notifica
                                               al grupo de Telegram con un mensaje de texto
    """
    import json as _json
    import os

    raw_body = await request.body()

    # ── Verificar firma HMAC-SHA256 (Svix) ───────────────────────────────────
    webhook_secret = os.getenv("MATIAS_WEBHOOK_SECRET", "")
    if webhook_secret:
        sig_header  = request.headers.get("x-webhook-signature", "")
        webhook_id  = request.headers.get("x-webhook-id", "")
        timestamp   = request.headers.get("x-webhook-timestamp", "")

        firma_ok = _verificar_firma_matias(
            raw_body, sig_header, webhook_id, timestamp, webhook_secret
        )

        if firma_ok:
            logger.info("Webhook MATIAS: firma HMAC verificada OK")
        else:
            # Loguear para diagnóstico pero NO rechazar todavía —
            # descomentar el raise cuando la firma esté confirmada estable.
            logger.warning(
                "Webhook MATIAS: firma HMAC inválida — "
                "sig_header=%s  wh_id=%s  ts=%s  secret_len=%d. "
                "Si acabas de regenerar el secreto en Matias API actualiza "
                "MATIAS_WEBHOOK_SECRET en Railway y redeploya.",
                sig_header[:30], webhook_id, timestamp, len(webhook_secret),
            )
            # raise HTTPException(status_code=401, detail="Firma webhook inválida")

    logger.info("Webhook MATIAS recibido")

    try:
        payload = _json.loads(raw_body)
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

    # ── Eventos de aceptación DIAN ────────────────────────────────────────────
    # Matias API puede disparar cualquiera de estos eventos cuando la DIAN
    # acepta el documento:
    #   document.created   — FIX: era el que faltaba; Matias lo dispara primero
    #   document.accepted  — v3 confirmación final DIAN
    #   document.emitted   — alias legacy
    #   invoice.accepted   — v2
    _EVENTOS_ACEPTACION = {
        "document.created",
        "document.accepted",
        "document.emitted",
        "invoice.accepted",
    }
    es_aceptacion = (
        evento in _EVENTOS_ACEPTACION
        or "accept" in evento.lower()
        or payload.get("success")
    )

    if es_aceptacion:
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

                # Despachar PDF a Telegram (Consumidor Final) o notificación
                # de texto (cliente con correo real). Corre en background thread.
                _despachar_post_aceptacion(cufe, numero, email_ok)

            except Exception as e:
                logger.error("Webhook: error actualizando DB para cufe %s: %s", cufe[:20], e)

    # ── Eventos de rechazo DIAN ───────────────────────────────────────────────
    elif "reject" in evento.lower() or "error" in evento.lower() or evento == "document.voided":
        logger.warning("🔍 Webhook payload completo (rechazo): %s", _json.dumps(payload, ensure_ascii=False)[:1000])

        raw_errors = (
            data.get("errors")        or
            data.get("message")       or
            data.get("error")         or
            data.get("StatusMessage") or
            data.get("description")   or
            payload.get("message")    or
            "Rechazada por DIAN"
        )

        if isinstance(raw_errors, list):
            error_msg = " | ".join(str(e) for e in raw_errors)
        elif isinstance(raw_errors, dict):
            parts = []
            for k, v in raw_errors.items():
                parts.extend(str(i) for i in v) if isinstance(v, list) else parts.append(f"{k}: {v}")
            error_msg = " | ".join(parts)
        else:
            error_msg = str(raw_errors)

        if cufe:
            try:
                _db.execute(
                    "UPDATE facturas_electronicas SET estado = 'error', error_msg = %s WHERE cufe = %s",
                    [error_msg[:500], cufe],
                )
                _db.execute(
                    """
                    UPDATE ventas SET factura_estado = 'error'
                    WHERE factura_cufe = %s AND factura_estado = 'emitida'
                    """,
                    [cufe],
                )
                logger.warning("❌ Webhook: factura %s rechazada — %s", numero or cufe[:16], error_msg[:200])
            except Exception as e:
                logger.error("Webhook: error guardando rechazo cufe %s: %s", cufe[:20], e)

    # ── email.sent / email.delivered ─────────────────────────────────────────
    elif "email" in evento.lower():
        logger.info("📧 Webhook: correo de factura %s entregado al cliente", numero or cufe[:16])

    return {"ok": True, "evento": evento}


# ── Despacho post-aceptación DIAN ─────────────────────────────────────────────

def _despachar_post_aceptacion(cufe: str, numero: str, email_ok) -> None:
    """
    Lógica post-aceptación DIAN. Ejecuta en background thread.

    Flujo:
      - Consumidor Final (sin correo real):
            → Descarga PDF desde Matias y lo envía al grupo de Telegram.
              El caption del PDF ya tiene toda la info; no se manda texto adicional.

      - Cliente con correo real:
            → Matias ya envió el email (send_email=1 en el payload de emisión).
              Solo se envía un mensaje de texto al grupo de Telegram como
              notificación interna para el equipo.
    """
    import os
    import threading

    def _run():
        try:
            row = _db.query_one(
                """
                SELECT v.cliente_nombre, v.total, c.correo
                FROM facturas_electronicas fe
                JOIN ventas v ON fe.venta_id = v.id
                LEFT JOIN clientes c ON v.cliente_id::text = c.id::text
                WHERE fe.cufe = %s
                """,
                [cufe],
            )
            if not row:
                logger.warning("Post-aceptación: no se encontró venta para CUFE %s", cufe[:16])
                return

            from services.facturacion_service import _sin_correo_real

            es_consumidor_final = _sin_correo_real(row.get("correo"))

            chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
            token   = os.getenv("TELEGRAM_TOKEN")

            if es_consumidor_final:
                # ── Consumidor Final → PDF al grupo de Telegram ───────────────
                if not chat_id or not token:
                    logger.warning("PDF Telegram: falta TELEGRAM_NOTIFY_CHAT_ID o TELEGRAM_TOKEN")
                    return
                logger.info("📤 Descargando PDF %s para Telegram (Consumidor Final)…", numero)
                import asyncio
                from services.facturacion_service import _enviar_pdf_grupo_telegram
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        _enviar_pdf_grupo_telegram(
                            cufe, numero,
                            row.get("cliente_nombre"),
                            row.get("total"),
                        )
                    )
                finally:
                    loop.close()

            else:
                # ── Cliente con correo → solo notificación de texto al grupo ──
                # El email ya fue enviado por Matias (send_email=1).
                if not chat_id or not token:
                    return
                email_txt = " · 📧 correo enviado al cliente" if email_ok else ""
                texto = (
                    f"✅ *DIAN aceptó factura {numero}*\n"
                    f"👤 {row.get('cliente_nombre') or 'Cliente'}\n"
                    f"💰 ${int(row.get('total') or 0):,}{email_txt}"
                )
                import httpx as _httpx
                try:
                    _httpx.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"},
                        timeout=8,
                    )
                except Exception as e:
                    logger.debug("Notificación Telegram (cliente) fallida: %s", e)

        except Exception as e:
            logger.error("Error en _despachar_post_aceptacion cufe %s: %s", cufe[:16], e)

    threading.Thread(target=_run, daemon=True).start()
