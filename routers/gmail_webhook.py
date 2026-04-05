"""
routers/gmail_webhook.py — Integración Gmail → Compras Fiscal vía Google Pub/Sub

FLUJO COMPLETO:
  Email llega a Gmail
    └─► Gmail notifica a Google Pub/Sub (instantáneo via watch)
          └─► Pub/Sub hace POST a /gmail/webhook (push subscription)
                └─► descargamos el email con Gmail API
                      └─► extraemos el XML adjunto (directo o dentro de un ZIP)
                            └─► parseamos campos UBL 2.1
                                  └─► insertamos en compras_fiscal
                                        └─► notify_all → dashboard se actualiza

ADJUNTOS SOPORTADOS:
  - .xml directo
  - .zip que contiene .xml + .pdf (formato más común de proveedores DIAN)

VARIABLES DE ENTORNO REQUERIDAS:
  GMAIL_CLIENT_ID         → OAuth2 client ID de Google Cloud Console
  GMAIL_CLIENT_SECRET     → OAuth2 client secret
  GMAIL_REFRESH_TOKEN     → token de refresco obtenido con OAuth playground
  GMAIL_USER              → correo de la ferretería (ej: ferreteria@gmail.com)
  GMAIL_PUBSUB_TOPIC      → projects/TU_PROJECT/topics/TU_TEMA
  PUBSUB_TOKEN            → token secreto incluido en la URL del push subscription
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks

import db as _db
from routers.events import notify_all

logger = logging.getLogger("ferrebot.gmail_webhook")
router = APIRouter()

# ── Namespaces UBL 2.1 (DIAN Colombia) ───────────────────────────────────────
_NS = {
    "inv":  "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac":  "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc":  "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ds":   "http://www.w3.org/2000/09/xmldsig#",
    "ext":  "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts":  "dian:gov:co:facturaelectronica:Structures-2-1",
    "xades":"http://uri.etsi.org/01903/v1.3.2#",
}

GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE  = "https://gmail.googleapis.com/gmail/v1"


# ─────────────────────────────────────────────────────────────────────────────
# 1. OAuth2 — obtener access_token desde refresh_token
# ─────────────────────────────────────────────────────────────────────────────

async def _get_access_token() -> str:
    client_id     = (os.getenv("GMAIL_CLIENT_ID")     or "").strip()
    client_secret = (os.getenv("GMAIL_CLIENT_SECRET") or "").strip()
    refresh_token = (os.getenv("GMAIL_REFRESH_TOKEN") or "").strip()

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Faltan variables de entorno: GMAIL_CLIENT_ID, "
            "GMAIL_CLIENT_SECRET o GMAIL_REFRESH_TOKEN"
        )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(GMAIL_TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "client_id":     client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        })
        resp.raise_for_status()
        return resp.json()["access_token"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Extraer XMLs de bytes — directo o desde ZIP
# ─────────────────────────────────────────────────────────────────────────────

def _extraer_xmls_de_bytes(fname: str, raw_bytes: bytes) -> list[tuple[str, bytes]]:
    """
    Dado un archivo (por nombre y bytes), retorna lista de (nombre, xml_bytes).
    - Si es .xml → lo retorna directamente.
    - Si es .zip → lo descomprime y extrae todos los .xml que encuentre dentro.
    - Cualquier otro tipo → retorna lista vacía.
    """
    fname_lower = fname.lower()

    # ── XML directo ───────────────────────────────────────────────────────────
    if fname_lower.endswith(".xml"):
        return [(fname, raw_bytes)]

    # ── ZIP con XML adentro ───────────────────────────────────────────────────
    if fname_lower.endswith(".zip") or raw_bytes[:2] == b"PK":
        resultados = []
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                for zname in zf.namelist():
                    if zname.lower().endswith(".xml"):
                        xml_bytes = zf.read(zname)
                        resultados.append((zname, xml_bytes))
                        logger.info("XML extraído del ZIP %s: %s (%d bytes)", fname, zname, len(xml_bytes))
        except zipfile.BadZipFile:
            logger.warning("Adjunto %s no es un ZIP válido", fname)
        except Exception as e:
            logger.warning("Error descomprimiendo %s: %s", fname, e)
        return resultados

    return []


# ─────────────────────────────────────────────────────────────────────────────
# 3. Gmail API — descargar mensaje y extraer adjuntos
# ─────────────────────────────────────────────────────────────────────────────

async def _get_message_ids_from_history(
    history_id: str,
    token: str,
    user: str,
) -> list[str]:
    url = f"{GMAIL_API_BASE}/users/{user}/history"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"}, params={
            "startHistoryId": history_id,
            "historyTypes":   "messageAdded",
        })
        if resp.status_code == 404:
            logger.warning("historyId %s expirado — sin mensajes que procesar", history_id)
            return []
        resp.raise_for_status()
        data = resp.json()
        logger.info("🔍 history.list raw: %s", data)

    message_ids = []
    for entry in data.get("history", []):
        for msg in entry.get("messagesAdded", []):
            mid = msg.get("message", {}).get("id")
            if mid and mid not in message_ids:
                message_ids.append(mid)
    return message_ids


async def _get_xml_attachments(
    message_id: str,
    token: str,
    user: str,
) -> list[tuple[str, bytes]]:
    """
    Descarga el mensaje y retorna lista de (filename, xml_bytes).
    Soporta adjuntos:
      - .xml directo
      - .zip que contiene .xml (formato más común de proveedores DIAN)
    """
    url = f"{GMAIL_API_BASE}/users/{user}/messages/{message_id}"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"format": "full"},
        )
        resp.raise_for_status()
        msg = resp.json()

    # Recolectamos (filename, bytes_o_attachmentId) de partes XML y ZIP
    candidatos: list[tuple[str, str | bytes]] = []

    def _walk_parts(parts: list) -> None:
        for part in parts:
            mime     = part.get("mimeType", "")
            filename = part.get("filename", "") or ""
            body     = part.get("body", {})
            fname_l  = filename.lower()

            es_xml = fname_l.endswith(".xml") or mime in ("application/xml", "text/xml")
            es_zip = fname_l.endswith(".zip") or mime in ("application/zip", "application/x-zip-compressed")

            if es_xml or es_zip:
                data_b64  = body.get("data")
                attach_id = body.get("attachmentId")

                if data_b64:
                    raw = base64.urlsafe_b64decode(data_b64 + "==")
                    candidatos.append((filename or "adjunto", raw))
                elif attach_id:
                    # adjunto grande — guardamos el ID para descargarlo después
                    candidatos.append((filename or "adjunto", attach_id))

            # Recursión en multipart
            sub = part.get("parts", [])
            if sub:
                _walk_parts(sub)

    payload = msg.get("payload", {})
    parts   = payload.get("parts", [])
    if parts:
        _walk_parts(parts)
    else:
        # Mensaje simple sin multipart
        body = payload.get("body", {})
        mime = payload.get("mimeType", "")
        if mime in ("application/xml", "text/xml") and body.get("data"):
            raw = base64.urlsafe_b64decode(body["data"] + "==")
            candidatos.append(("factura.xml", raw))

    # Descargar attachmentIds pendientes
    resultado_final: list[tuple[str, bytes]] = []

    async with httpx.AsyncClient(timeout=20) as client:
        for fname, content in candidatos:
            if isinstance(content, str):
                # Es un attachmentId — descargamos
                att_url  = f"{GMAIL_API_BASE}/users/{user}/messages/{message_id}/attachments/{content}"
                att_resp = await client.get(att_url, headers={"Authorization": f"Bearer {token}"})
                att_resp.raise_for_status()
                raw = base64.urlsafe_b64decode(att_resp.json().get("data", "") + "==")
            else:
                raw = content

            # Extraer XMLs (directo o desde ZIP)
            xmls = _extraer_xmls_de_bytes(fname, raw)
            resultado_final.extend(xmls)

    return resultado_final


# ─────────────────────────────────────────────────────────────────────────────
# 4. Parser XML — Factura Electrónica DIAN (UBL 2.1)
# ─────────────────────────────────────────────────────────────────────────────

def _txt(el: Optional[ET.Element]) -> str:
    return el.text.strip() if el is not None and el.text else ""


def _int_col(val: str) -> int:
    if not val:
        return 0
    try:
        return round(float(val.replace(",", ".")))
    except ValueError:
        return 0


def parse_ubl_xml(xml_bytes: bytes) -> Optional[dict]:
    """Parsea una factura electrónica DIAN en formato UBL 2.1.

    Soporta dos estructuras:
      - Invoice directa (tag raíz contiene 'Invoice')
      - AttachedDocument: wrapper DIAN donde la Invoice real viene en
        cac:Attachment/cac:ExternalReference/cbc:Description como XML en texto plano.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("XML inválido: %s", e)
        return None

    tag = root.tag
    logger.info("parse_ubl_xml — tag raíz: %s", tag)

    # ── AttachedDocument: extraer Invoice del Description interno ─────────────
    if "AttachedDocument" in tag:
        logger.info("Detectado AttachedDocument — buscando Invoice interna")
        desc_el = root.find(
            "cac:Attachment/cac:ExternalReference/cbc:Description", _NS
        )
        if desc_el is None or not (desc_el.text or "").strip():
            logger.warning("AttachedDocument sin cbc:Description — no se puede extraer Invoice")
            return None
        inner_text = desc_el.text.strip()
        try:
            inner_bytes = inner_text.encode("utf-8")
            return parse_ubl_xml(inner_bytes)
        except Exception as e:
            logger.warning("Error reparsando Invoice desde AttachedDocument: %s", e)
            return None

    if "Invoice" not in tag and "invoice" not in tag.lower():
        logger.warning("XML no es una Invoice UBL ni AttachedDocument — tag=%s", tag)
        return None

    def _find(path: str) -> Optional[ET.Element]:
        return root.find(path, _NS)

    def _findall(path: str) -> list[ET.Element]:
        return root.findall(path, _NS)

    numero_factura = _txt(_find("cbc:ID"))
    fecha_str      = _txt(_find("cbc:IssueDate"))
    try:
        fecha = date.fromisoformat(fecha_str) if fecha_str else date.today()
    except ValueError:
        fecha = date.today()

    supplier      = _find("cac:AccountingSupplierParty")
    proveedor     = ""
    nit_proveedor = ""
    if supplier:
        name_el   = supplier.find("cac:Party/cac:PartyName/cbc:Name", _NS) or \
                    supplier.find("cac:Party/cac:PartyLegalEntity/cbc:RegistrationName", _NS)
        proveedor = _txt(name_el)
        nit_el    = supplier.find("cac:Party/cac:PartyIdentification/cbc:ID", _NS) or \
                    supplier.find("cac:Party/cac:PartyTaxScheme/cbc:CompanyID", _NS)
        nit_proveedor = _txt(nit_el)

    total_iva_el  = _find("cac:TaxTotal/cbc:TaxAmount")
    total_iva     = _int_col(_txt(total_iva_el))
    total_el      = _find("cac:LegalMonetaryTotal/cbc:PayableAmount")
    total_factura = _int_col(_txt(total_el))

    items  = []
    lineas = _findall("cac:InvoiceLine")

    for linea in lineas:
        # Usar 'is not None' — ET.Element con solo texto es falsy en bool context
        desc_el = linea.find("cac:Item/cbc:Description", _NS)
        ref_el  = (
            linea.find("cac:Item/cac:SellersItemIdentification/cbc:ID", _NS)
            or linea.find("cac:Item/cac:StandardItemIdentification/cbc:ID", _NS)
        )
        producto_nombre = _txt(desc_el) if desc_el is not None else (_txt(ref_el) or "Sin descripción")
        codigo_ref      = _txt(ref_el)

        qty_el = linea.find("cbc:InvoicedQuantity", _NS)
        try:
            cantidad = float(_txt(qty_el) or "1")
        except ValueError:
            cantidad = 1.0

        ext_el       = linea.find("cbc:LineExtensionAmount", _NS)
        base_linea   = _int_col(_txt(ext_el))
        iva_linea_el = linea.find("cac:TaxTotal/cbc:TaxAmount", _NS)
        iva_linea    = _int_col(_txt(iva_linea_el))
        pct_el       = linea.find("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent", _NS)
        tarifa       = _int_col(_txt(pct_el)) if pct_el is not None else 0

        incluye_iva = tarifa > 0 and iva_linea > 0
        costo_total = base_linea + iva_linea
        costo_unit  = round(base_linea / cantidad) if cantidad else base_linea

        items.append({
            "producto_nombre": producto_nombre[:300],
            "codigo_ref":      codigo_ref[:100] if codigo_ref else "",
            "cantidad":        cantidad,
            "costo_unitario":  costo_unit,
            "costo_total":     costo_total,
            "incluye_iva":     incluye_iva,
            "tarifa_iva":      tarifa,
        })

    # Si no hay líneas detalladas, crear una línea resumen con el total
    if not items and total_factura > 0:
        tarifa_principal = 19
        tax_sub = _find("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent")
        if tax_sub is not None:
            try:
                tarifa_principal = int(float(_txt(tax_sub)))
            except ValueError:
                pass
        items.append({
            "producto_nombre": f"Factura {numero_factura} — {proveedor}",
            "codigo_ref":      "",
            "cantidad":        1.0,
            "costo_unitario":  total_factura,
            "costo_total":     total_factura,
            "incluye_iva":     total_iva > 0,
            "tarifa_iva":      tarifa_principal if total_iva > 0 else 0,
        })

    return {
        "numero_factura":       numero_factura,
        "fecha":                fecha,
        "proveedor":            proveedor[:200] if proveedor else "Sin proveedor",
        "nit_proveedor":        nit_proveedor,
        "items":                items,
        "total_factura":        total_factura,
        "total_iva":            total_iva,
        "tarifa_iva_principal": items[0]["tarifa_iva"] if items else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Persistencia de historyId en ferrebot_config
# ─────────────────────────────────────────────────────────────────────────────

def _cargar_last_history_id() -> str | None:
    """
    Lee el último historyId procesado exitosamente desde ferrebot_config.
    Retorna None si no hay valor guardado (primera ejecución).
    """
    try:
        row = _db.query_one(
            "SELECT valor FROM ferrebot_config WHERE clave = 'gmail_last_history_id'"
        )
        return row["valor"] if row else None
    except Exception as e:
        logger.warning("Error leyendo gmail_last_history_id de ferrebot_config: %s", e)
        return None


def _guardar_last_history_id(history_id: str) -> None:
    """
    Guarda (upsert) el historyId procesado en ferrebot_config para que la
    próxima notificación arranque desde el punto correcto, incluso tras reinicios.
    """
    try:
        _db.execute(
            """
            INSERT INTO ferrebot_config (clave, valor, updated_at)
            VALUES ('gmail_last_history_id', %s, NOW())
            ON CONFLICT (clave) DO UPDATE
                SET valor = EXCLUDED.valor, updated_at = NOW()
            """,
            (history_id,),
        )
        logger.debug("gmail_last_history_id guardado: %s", history_id)
    except Exception as e:
        logger.warning("Error guardando gmail_last_history_id en ferrebot_config: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Registro en compras_fiscal
# ─────────────────────────────────────────────────────────────────────────────

def _ya_procesado(gmail_message_id: str) -> bool:
    row = _db.query_one(
        "SELECT id FROM compras_fiscal WHERE gmail_message_id = %s LIMIT 1",
        (gmail_message_id,)
    )
    return row is not None


def _registrar_factura(
    factura: dict,
    gmail_message_id: str,
    usuario_id: Optional[int] = None,
) -> list[int]:
    ids_creados = []
    for item in factura["items"]:
        row = _db.query_one(
            """
            INSERT INTO compras_fiscal (
                fecha, proveedor, producto_nombre,
                cantidad, costo_unitario, costo_total,
                incluye_iva, tarifa_iva,
                numero_factura, notas_fiscales,
                gmail_message_id, usuario_id,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
            RETURNING id
            """,
            (
                factura["fecha"],
                factura["proveedor"],
                item["producto_nombre"],
                item["cantidad"],
                item["costo_unitario"],
                item["costo_total"],
                item["incluye_iva"],
                item["tarifa_iva"],
                factura["numero_factura"],
                (
                    f"Importado automáticamente desde Gmail. NIT proveedor: {factura.get('nit_proveedor', '')}"
                    + (f". Ref: {item['codigo_ref']}" if item.get("codigo_ref") else "")
                ),
                gmail_message_id,
                usuario_id,
            )
        )
        if row:
            ids_creados.append(row["id"])
            logger.info(
                "compras_fiscal #%s creado: %s — %s",
                row["id"], factura["numero_factura"], item["producto_nombre"]
            )
    return ids_creados


# ─────────────────────────────────────────────────────────────────────────────
# 8. Procesamiento completo de un mensaje
# ─────────────────────────────────────────────────────────────────────────────

async def _procesar_mensaje(message_id: str, token: str, user: str) -> dict:
    if _ya_procesado(message_id):
        logger.info("Mensaje %s ya procesado — skip", message_id)
        return {"skip": True, "message_id": message_id}

    adjuntos = await _get_xml_attachments(message_id, token, user)
    if not adjuntos:
        logger.info("Mensaje %s sin adjuntos XML (ni directo ni en ZIP) — skip", message_id)
        return {"skip": True, "message_id": message_id, "razon": "sin_xml"}

    ids_totales = []
    facturas_ok = []

    for fname, xml_bytes in adjuntos:
        logger.info("Procesando XML: %s (%d bytes)", fname, len(xml_bytes))
        factura = parse_ubl_xml(xml_bytes)
        if not factura:
            logger.warning("XML %s no es una factura UBL válida — skip", fname)
            continue
        ids = _registrar_factura(factura, message_id)
        ids_totales.extend(ids)
        facturas_ok.append({
            "numero":    factura["numero_factura"],
            "proveedor": factura["proveedor"],
            "total":     factura["total_factura"],
            "items":     len(ids),
        })

    return {
        "skip":         False,
        "message_id":   message_id,
        "facturas":     facturas_ok,
        "registros_db": ids_totales,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Tarea de fondo
# ─────────────────────────────────────────────────────────────────────────────

async def _background_procesar(history_id_notificacion: str) -> None:
    if not _db.DB_DISPONIBLE:
        logger.error("DB no disponible — no se pueden registrar facturas")
        return

    gmail_user = (os.getenv("GMAIL_USER") or "me").strip()

    # Usar el historyId guardado en DB si es anterior al de la notificación,
    # para no perder mensajes entre notificaciones o tras un reinicio.
    history_id_guardado = _cargar_last_history_id()
    if history_id_guardado and int(history_id_guardado) < int(history_id_notificacion):
        start_history_id = history_id_guardado
        logger.info(
            "Usando historyId guardado en DB (%s) en vez del de la notificación (%s)",
            history_id_guardado, history_id_notificacion,
        )
    else:
        start_history_id = history_id_notificacion

    try:
        token = await _get_access_token()
    except Exception as e:
        logger.error("Error obteniendo access_token Gmail: %s", e)
        return

    try:
        message_ids = await _get_message_ids_from_history(start_history_id, token, gmail_user)
    except Exception as e:
        logger.error("Error en history.list (historyId=%s): %s", start_history_id, e)
        return

    if not message_ids:
        logger.debug("historyId %s sin mensajes nuevos en INBOX", start_history_id)
        # Avanzar el puntero aunque no haya mensajes para no reprocessar al siguiente webhook
        _guardar_last_history_id(history_id_notificacion)
        return

    total_registros     = 0
    facturas_importadas = []

    for mid in message_ids:
        try:
            resultado = await _procesar_mensaje(mid, token, gmail_user)
            if not resultado.get("skip"):
                total_registros += len(resultado.get("registros_db", []))
                facturas_importadas.extend(resultado.get("facturas", []))
        except Exception as e:
            logger.error("Error procesando mensaje %s: %s", mid, e, exc_info=True)

    if facturas_importadas:
        try:
            await notify_all("compra_fiscal_importada", {
                "fuente":      "gmail",
                "facturas":    facturas_importadas,
                "total_items": total_registros,
                "timestamp":   datetime.now().isoformat(),
            })
            logger.info(
                "✅ %d factura(s) importadas desde Gmail (%d ítems en compras_fiscal)",
                len(facturas_importadas), total_registros
            )
        except Exception as e:
            logger.warning("Error en notify_all tras importar facturas: %s", e)

    # Avanzar el puntero para que la próxima notificación arranque desde aquí
    _guardar_last_history_id(history_id_notificacion)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/gmail/webhook")
async def gmail_pubsub_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Query(..., description="Token secreto configurado en PUBSUB_TOKEN"),
):
    """Recibe notificaciones push de Google Pub/Sub cuando llega un email nuevo."""
    pubsub_token = (os.getenv("PUBSUB_TOKEN") or "").strip()
    if not pubsub_token or token != pubsub_token:
        logger.warning("Webhook recibido con token inválido: %s", token[:8] if token else "—")
        raise HTTPException(status_code=403, detail="Token inválido")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body inválido — se esperaba JSON")

    message  = body.get("message", {})
    data_b64 = message.get("data", "")

    if not data_b64:
        return {"ok": True, "skip": "sin_data"}

    try:
        data_json  = json.loads(base64.urlsafe_b64decode(data_b64 + "==").decode())
        history_id = str(int(data_json.get("historyId", 0)) - 1)
    except Exception as e:
        logger.warning("Error decodificando data Pub/Sub: %s", e)
        return {"ok": True, "skip": "data_invalida"}

    if not history_id:
        return {"ok": True, "skip": "sin_historyId"}

    logger.info("📬 Webhook Pub/Sub recibido — historyId=%s", history_id)
    background_tasks.add_task(_background_procesar, history_id)
    return {"ok": True, "historyId": history_id}


@router.post("/gmail/webhook/watch")
async def gmail_watch_setup():
    """
    Configura (o renueva) el Gmail watch para recibir notificaciones Pub/Sub.
    Gmail watch expira cada 7 días — llamar este endpoint semanalmente.
    """
    pubsub_topic = (os.getenv("GMAIL_PUBSUB_TOPIC") or "").strip()
    gmail_user   = (os.getenv("GMAIL_USER") or "me").strip()

    if not pubsub_topic:
        raise HTTPException(
            status_code=500,
            detail="Falta variable GMAIL_PUBSUB_TOPIC (ej: projects/mi-proyecto/topics/gmail-facturas)"
        )

    try:
        token = await _get_access_token()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error OAuth Gmail: {e}")

    url = f"{GMAIL_API_BASE}/users/{gmail_user}/watch"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"labelIds": ["INBOX"], "topicName": pubsub_topic},
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Gmail API error {e.response.status_code}: {e.response.text}"
            )
        data = resp.json()

    expire_dt = None
    if "expiration" in data:
        try:
            expire_dt = datetime.fromtimestamp(int(data["expiration"]) / 1000).isoformat()
        except Exception:
            pass

    logger.info("✅ Gmail watch configurado — historyId=%s, expira=%s", data.get("historyId"), expire_dt)
    return {
        "ok":        True,
        "historyId": data.get("historyId"),
        "expira":    expire_dt,
        "topic":     pubsub_topic,
        "nota":      "El watch expira en ~7 días. Renuévalo con POST /gmail/webhook/watch",
    }


@router.get("/gmail/webhook/status")
async def gmail_webhook_status():
    """Estado del webhook: cuántas facturas fueron importadas desde Gmail."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="DB no disponible")

    fila = _db.query_one(
        """
        SELECT
            COUNT(*)                         AS total_items,
            COUNT(DISTINCT gmail_message_id) AS total_emails,
            COUNT(DISTINCT numero_factura)   AS total_facturas,
            MAX(created_at)::text            AS ultima_importacion,
            SUM(costo_total)                 AS monto_total
        FROM compras_fiscal
        WHERE gmail_message_id IS NOT NULL
        """
    )
    return {
        "ok":            True,
        "importaciones": dict(fila) if fila else {},
        "watch_url":     "/gmail/webhook/watch",
    }
