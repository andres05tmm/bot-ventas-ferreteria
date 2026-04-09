"""
services/facturacion_service.py
Integración con MATIAS API v3.0.0 para facturación electrónica DIAN.

Auth:     https://auth-v2.matias-api.com  (login con email + password → JWT renovable)
API base: https://api-v2.matias-api.com/api/ubl2.1

Variables de entorno en Railway:
    MATIAS_EMAIL        tu_email@dominio.com
    MATIAS_PASSWORD     tu_password
    MATIAS_RESOLUTION   18764108150755          (resolución DIAN)
    MATIAS_PREFIX       FPR                     (producción)
    MATIAS_NUM_DESDE    1                       (produccion)

REGLA DE ORO (MATIAS API v3):
    Consultas GET  → códigos DIAN  (CC=13, NIT=31, CE=22...)
    Creación  POST → IDs internos  (CC=1,  NIT=3,  CE=2...)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional

import httpx

import db as _db
from config import COLOMBIA_TZ

logger = logging.getLogger("ferrebot.facturacion")

# ── Configuración (Railway env vars) ──────────────────────────────────────────

MATIAS_API_URL    = os.getenv("MATIAS_API_URL", "https://api-v2.matias-api.com/api/ubl2.1")
MATIAS_EMAIL      = os.getenv("MATIAS_EMAIL")
MATIAS_PASSWORD   = os.getenv("MATIAS_PASSWORD")
MATIAS_RESOLUTION = os.getenv("MATIAS_RESOLUTION")
MATIAS_PREFIX     = os.getenv("MATIAS_PREFIX", "FPR")
MATIAS_NUM_DESDE  = int(os.getenv("MATIAS_NUM_DESDE", "1"))

_MEDIOS_PAGO = {
    "efectivo":      10,
    "transferencia": 42,
    "tarjeta":       48,
    "nequi":         42,
    "daviplata":     42,
    "datafono":      48,
}

# ── Unidades de medida → quantity_units_id MATIAS API (enteros, no strings) ───
# Verificados con GET /quantity-units
_UNIDAD_DIAN: dict[str, int] = {
    "Unidad":  70,
    "unidad":  70,
    "Galón":   686,
    "galon":   686,
    "Gal":     686,
    "Kg":      767,
    "kg":      767,
    "GRM":     692,
    "gramo":   692,
    "Mts":     865,
    "Mt":      865,
    "metro":   865,
    "Cms":     495,
    "Cm":      495,
    "Lt":      821,
    "Lts":     821,
    "litro":   821,
    "MLT":     852,
    "ml":      852,
}

# ── Mapper tipos de identificación ────────────────────────────────────────────
#
# MATIAS API maneja DOS capas según el endpoint:
#
#   POST /invoice  → IDs INTERNOS MATIAS  (identity_document_id)
#   GET  /acquirer → CÓDIGOS DIAN directos (identificationType)
#
# Fuente confirmada por soporte MATIAS API.

# Para POST /invoice (creación de documentos)
_TIPO_ID_MATIAS = {
    "CC":   "1",
    "CE":   "2",
    "NIT":  "3",
    "RC":   "6",
    "TI":   "7",
    "TE":   "8",
    "PA":   "9",
    "PPN":  "9",
    "DE":   "10",
    "NITE": "11",
    "NUIP": "12",
    "PPT":  "13",
    "PEP":  "14",
    "SC":   "15",
    "CD":   "20",
}

# Para GET /acquirer (consultas DIAN)
_TIPO_ID_DIAN = {
    "CC":   "13",
    "CE":   "22",
    "NIT":  "31",
    "RC":   "11",
    "TI":   "12",
    "TE":   "21",
    "PA":   "41",
    "PPN":  "41",
    "DE":   "42",
    "NITE": "50",
    "NUIP": "91",
    "PPT":  "48",
    "PEP":  "47",
    "SC":   "SC",
    "CD":   "CD",
}

# ── Caché de ciudades ─────────────────────────────────────────────────────────

_cities_cache:        dict = {}
_cities_cache_loaded: bool = False
_cities_lock_obj:     threading.Lock = threading.Lock()


def _cargar_ciudades_matias() -> None:
    global _cities_cache, _cities_cache_loaded
    with _cities_lock_obj:
        if _cities_cache_loaded:
            return
        try:
            resp = httpx.get(f"{MATIAS_API_URL}/cities", timeout=15)
            if resp.status_code == 200:
                data   = resp.json()
                cities = (
                    data.get("dataRecords", {}).get("data", [])
                    or data.get("data", [])
                    or []
                )
                for city in cities:
                    code = city.get("code") or city.get("dane_code") or city.get("municipality_code")
                    if code:
                        try:
                            _cities_cache[int(str(code))] = str(city["id"])
                        except (ValueError, KeyError, TypeError):
                            pass
                _cities_cache_loaded = True
                logger.info("Catálogo ciudades MATIAS cargado: %d ciudades", len(_cities_cache))
            else:
                logger.warning("MATIAS /cities devolvió HTTP %s", resp.status_code)
        except Exception as e:
            logger.warning("No se pudo cargar catálogo ciudades MATIAS API: %s", e)


def _matias_city_id(dane_code) -> Optional[str]:
    if not dane_code:
        return None
    _cargar_ciudades_matias()
    try:
        return _cities_cache.get(int(dane_code))
    except (ValueError, TypeError):
        return None


# ── Cache de token JWT ────────────────────────────────────────────────────────

_token_lock:   threading.Lock = threading.Lock()
_cached_token: Optional[str]  = None
_token_expiry: float          = 0.0


def _get_token() -> str:
    global _cached_token, _token_expiry

    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        raise RuntimeError(
            "Faltan variables de entorno: MATIAS_EMAIL y MATIAS_PASSWORD."
        )

    with _token_lock:
        ahora = time.time()
        if _cached_token and ahora < _token_expiry - 60:
            return _cached_token

        logger.info("Renovando token Matias API (login)…")
        resp = httpx.post(
            f"{MATIAS_API_URL}/auth/login",
            json={"email": MATIAS_EMAIL, "password": MATIAS_PASSWORD, "remember_me": 0},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15,
            follow_redirects=True,
        )

        logger.info(
            "Auth Matias API → HTTP %s | body: %s",
            resp.status_code,
            resp.text[:500] if resp.text else "(vacío)",
        )

        resp.raise_for_status()

        if not resp.text or not resp.text.strip():
            raise ValueError(f"Matias API devolvió body vacío (HTTP {resp.status_code}).")

        try:
            data = resp.json()
        except Exception as e:
            raise ValueError(
                f"Matias API no devolvió JSON válido (HTTP {resp.status_code}): {resp.text[:300]} — {e}"
            )

        token = (
            data.get("token") or
            data.get("access_token") or
            (data.get("data") or {}).get("token") or
            (data.get("data") or {}).get("access_token")
        )
        if not token:
            raise ValueError(f"No se encontró token en respuesta de auth: {data}")

        expires_at_str = data.get("expires_at")
        if expires_at_str:
            try:
                expires_dt    = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                _token_expiry = expires_dt.timestamp()
            except Exception:
                _token_expiry = ahora + float(data.get("expires_in") or 86400)
        else:
            _token_expiry = ahora + float(data.get("expires_in") or 86400)

        _cached_token  = token
        mins_restantes = (_token_expiry - ahora) / 60
        logger.info("Token Matias API renovado OK (expira en %.0f min)", mins_restantes)
        return _cached_token


# ── Helpers internos ──────────────────────────────────────────────────────────

def _siguiente_num_dian(cur) -> int:
    cur.execute("LOCK TABLE facturas_electronicas IN SHARE ROW EXCLUSIVE MODE")
    cur.execute(
        """
        SELECT COALESCE(
            MAX(CAST(NULLIF(regexp_replace(numero, '[^0-9]', '', 'g'), '') AS INTEGER)),
            %s - 1
        ) + 1 AS siguiente
        FROM facturas_electronicas
        WHERE estado != 'error'
        """,
        (MATIAS_NUM_DESDE,),
    )
    siguiente = cur.fetchone()["siguiente"]
    return max(siguiente, MATIAS_NUM_DESDE)


def _fmt(valor) -> float:
    return round(float(valor or 0), 2)


_EMAIL_PLACEHOLDER = "sinfactura@ferreteriapuntorojo.com"


def _sin_correo_real(email: str | None) -> bool:
    return not email or email.strip().lower() == _EMAIL_PLACEHOLDER


# ── Envío de PDF al grupo de Telegram ────────────────────────────────────────

async def _enviar_pdf_grupo_telegram(
    cufe: str, numero: str, cliente_nombre: str | None, total
) -> None:
    chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
    token   = os.getenv("TELEGRAM_TOKEN")
    if not chat_id or not token:
        logger.warning("PDF %s no enviado a Telegram: falta TELEGRAM_NOTIFY_CHAT_ID o TELEGRAM_TOKEN", numero)
        return
    try:
        pdf_bytes = await obtener_pdf(cufe)
        caption = (
            f"📄 *Factura {numero}*\n"
            f"👤 {cliente_nombre or 'Consumidor Final'}\n"
            f"💰 ${int(total or 0):,}\n"
            f"_Sin correo registrado — PDF enviado al grupo._"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                files={"document": (f"{numero}.pdf", pdf_bytes, "application/pdf")},
            )
        if resp.status_code == 200:
            logger.info("📤 PDF %s enviado al grupo de Telegram OK", numero)
        else:
            logger.error("Error enviando PDF %s a Telegram: HTTP %s — %s", numero, resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("Error enviando PDF %s al grupo Telegram: %s", numero, e)


# ── Armado del payload ────────────────────────────────────────────────────────

def _armar_payload(venta: dict, detalle: list[dict], num_dian: int) -> dict:
    """
    Construye el JSON de factura para MATIAS API v3.

    Cambios vs versión anterior:
    - currency_id: 272 (COP) agregado — recomendado en habilitación DIAN
    - invoiced_quantity y base_quantity: float (no string) — MATIAS API es estricto
    - quantity_units_id: int (no string) — idem
    - Soporta cantidades decimales: 0.5 galones, 250 gramos, 2.5 metros, etc.
    """
    ahora    = datetime.now(COLOMBIA_TZ)
    es_nit   = (venta.get("tipo_id") or "").upper() == "NIT"
    medio_id = _MEDIOS_PAGO.get(
        (venta.get("metodo_pago") or "efectivo").lower(), 10
    )

    # ── Totales ───────────────────────────────────────────────────────────────
    # Los precios en BD tienen IVA incluido. Se extrae la base gravable dividiendo.
    # Ejemplo: $9.000 con IVA 19% → base = 9000/1.19 = $7.563,03 | IVA = $1.436,97
    total_doc         = sum(_fmt(d.get("total") or 0) for d in detalle)  # total real (con IVA)
    subtotal_gravable = 0.0
    total_iva         = 0.0
    subtotal_exento   = 0.0

    for d in detalle:
        total_item = _fmt(d.get("total") or 0)
        pct        = int(d.get("porcentaje_iva") or 0)
        if d.get("tiene_iva") and pct > 0:
            divisor            = 1 + pct / 100
            base               = round(total_item / divisor, 2)
            subtotal_gravable += base
            total_iva         += round(total_item - base, 2)
        else:
            subtotal_exento += total_item

    subtotal  = round(subtotal_gravable + subtotal_exento, 2)
    total_doc = round(total_doc, 2)

    # ── Comprador - ESTRUCTURA OFICIAL MATIAS API (3 casos) ─────────────────
    id_cliente          = venta.get("identificacion_cliente") or ""
    tipo_id_raw         = (venta.get("tipo_id") or "").upper().strip()
    tiene_correo_real   = not _sin_correo_real(venta.get("correo_cliente"))

    # Caso 1: SIN cliente → Consumidor Final (tipo 6)
    if not id_cliente or id_cliente.strip() == "222222222222":
        es_consumidor_final = True
        customer = {
            "country_id":           "45",
            "identity_document_id": "6",   # Consumidor Final
            "type_organization_id": 2,     # Persona natural
            "tax_regime_id":        2,     # Régimen simplificado
            "tax_level_id":         5,     # No responsable de IVA
            "company_name":         "CONSUMIDOR FINAL",
            "dni":                  "222222222222",
            "mobile":               "3000000000",  # Campo obligatorio
            "email":                "sinfactura@ferreterlapuntorojo.com",
            "address":              "Cartagena",
        }

    # Caso 2: Cliente EMPRESA (NIT)
    elif tipo_id_raw == "NIT":
        es_consumidor_final = False
        # Extraer dígito verificación si existe (ej: "900123456-5" → dv="5")
        nit_parts = id_cliente.split("-")
        nit_sin_dv = nit_parts[0].strip()
        dv = nit_parts[1].strip() if len(nit_parts) > 1 else ""
        
        customer = {
            "country_id":           "45",
            "identity_document_id": "3",    # NIT
            "type_organization_id": 1,      # Empresa/persona jurídica
            "tax_regime_id":        1,      # Responsable IVA (régimen común)
            "tax_level_id":         1,      # Gran contribuyente/responsable
            "company_name":         (venta.get("cliente_nombre") or "").upper(),
            "dni":                  nit_sin_dv,
            "dv":                   dv,     # Dígito verificación (obligatorio para NIT)
            "mobile":               venta.get("telefono_cliente") or "6011234567",
            "email":                venta.get("correo_cliente") if tiene_correo_real else "sinfactura@ferreterlapuntorojo.com",
            "address":              venta.get("direccion_cliente") or "Cartagena",
        }

    # Caso 3: Cliente PERSONA (CC, CE, TI, Pasaporte, etc.)
    else:
        es_consumidor_final = False
        customer = {
            "country_id":           "45",
            "identity_document_id": "1",    # CC (cédula ciudadanía)
            "type_organization_id": 2,      # Persona natural
            "tax_regime_id":        2,      # Régimen simplificado
            "tax_level_id":         5,      # No responsable de IVA
            "company_name":         (venta.get("cliente_nombre") or "").upper(),
            "dni":                  id_cliente,
            "mobile":               venta.get("telefono_cliente") or "3001234567",
            "email":                venta.get("correo_cliente") if tiene_correo_real else "sinfactura@ferreterlapuntorojo.com",
            "address":              venta.get("direccion_cliente") or "Cartagena",
        }

    # Agregar city_id si hay municipio DIAN específico
    municipio_dian = venta.get("municipio_dian")
    if municipio_dian and municipio_dian != "149":
        _resolved_city_id = _matias_city_id(municipio_dian)
        if _resolved_city_id:
            customer["city_id"] = _resolved_city_id
    else:
        customer["city_id"] = "149"  # Cartagena por defecto

    # ── Líneas de detalle ─────────────────────────────────────────────────────
    # quantity_units_id → int (no string)
    # invoiced_quantity / base_quantity → float (soporta fracciones: 0.5, 2.5, 250, etc.)
    lines = []
    for item in detalle:
        # Redondear a 4 decimales para soportar fracciones precisas (ej: 0.0625 = 1/16)
        cantidad  = round(float(item.get("cantidad") or 1), 4)
        tiene_iva = bool(item.get("tiene_iva"))
        pct_iva   = int(item.get("porcentaje_iva") or 0)

        # Precios en BD tienen IVA incluido → extraer base gravable
        total_con_iva  = _fmt(item.get("total") or 0)
        precio_con_iva = _fmt(item.get("precio_unitario") or 0)
        if tiene_iva and pct_iva > 0:
            divisor    = 1 + pct_iva / 100
            total_base = round(total_con_iva / divisor, 2)
            precio_u   = round(precio_con_iva / divisor, 2)
            iva_val    = round(total_con_iva - total_base, 2)
        else:
            total_base = total_con_iva
            precio_u   = precio_con_iva
            iva_val    = 0.0

        unidad_raw   = (item.get("unidad_medida") or "Unidad").strip()
        qty_units_id = _UNIDAD_DIAN.get(unidad_raw, _UNIDAD_DIAN.get(unidad_raw.lower(), 70))

        lines.append({
            "invoiced_quantity":            cantidad,        # float
            "quantity_units_id":            qty_units_id,   # int
            "line_extension_amount":        total_base,     # base sin IVA
            "free_of_charge_indicator":     False,
            "description":                  (item.get("producto_nombre") or "Producto").upper(),
            "code":                         str(item.get("producto_id") or "SC"),
            "type_item_identifications_id": "4",
            "reference_price_id":           "1",
            "price_amount":                 precio_u,       # precio unitario sin IVA
            "base_quantity":                cantidad,        # float
            "tax_totals": [{
                "tax_id":         "1" if tiene_iva else "4",
                "tax_amount":     iva_val,
                "taxable_amount": total_base if tiene_iva else 0.0,
                "percent":        _fmt(pct_iva),
            }],
        })

    # ── Tax totals documento ──────────────────────────────────────────────────
    doc_tax_totals = [{
        "tax_id":         "1" if total_iva > 0 else "4",
        "tax_amount":     _fmt(total_iva),
        "taxable_amount": _fmt(subtotal_gravable) if total_iva > 0 else 0.0,
        "percent":        19.0 if total_iva > 0 else 0.0,
    }]

    # ── legal_monetary_totals ─────────────────────────────────────────────────
    legal_monetary_totals = {
        "line_extension_amount":  _fmt(subtotal),
        "tax_exclusive_amount":   _fmt(subtotal),
        "tax_inclusive_amount":   _fmt(total_doc),
        "allowance_total_amount": 0.0,
        "charge_total_amount":    0.0,
        "pre_paid_amount":        0.0,
        "payable_amount":         _fmt(total_doc),
    }

    es_fiado          = bool(venta.get("es_fiado") or venta.get("fiado"))
    payment_method_id = 2 if es_fiado else 1

    payload: dict = {
        "resolution_number":      MATIAS_RESOLUTION,
        "prefix":                 MATIAS_PREFIX,
        "document_number":        str(num_dian),
        "date":                   str(venta["fecha"])[:10],
        "time":                   ahora.strftime("%H:%M:%S"),
        "type_document_id":       7,    # Factura electrónica (según documentación oficial)
        "operation_type_id":      10 if es_consumidor_final else 1,  # 10=CF, 1=Normal
        "currency_id":            272,   # COP — recomendado en habilitación DIAN
        "notes":                  venta.get("notas") or "Ferretería Punto Rojo",
        "graphic_representation": 1,
        "send_email":             1 if tiene_correo_real else 0,
        "customer":               customer,
        "tax_totals":             doc_tax_totals,
        "legal_monetary_totals":  legal_monetary_totals,
        "payments": [{
            "payment_method_id": payment_method_id,
            "means_payment_id":  medio_id,
            "value_paid":        _fmt(total_doc),
        }],
        "lines": lines,
    }
    return payload


# ── Función principal ─────────────────────────────────────────────────────────

async def emitir_factura(venta_id: int) -> dict:
    """
    Emite la factura electrónica DIAN para una venta ya registrada en PostgreSQL.
    Retorna: { "ok": True,  "cufe": "...", "numero": "FPR1" }
          o  { "ok": False, "error": "mensaje legible" }
    """
    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        return {"ok": False, "error": "MATIAS_EMAIL y MATIAS_PASSWORD no configurados en Railway"}
    if not MATIAS_RESOLUTION:
        return {"ok": False, "error": "MATIAS_RESOLUTION no configurado en Railway"}

    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT v.*,
                       c.tipo_id,
                       c.identificacion  AS identificacion_cliente,
                       c.correo          AS correo_cliente,
                       c.telefono        AS telefono_cliente,
                       c.direccion       AS direccion_cliente,
                       c.municipio_dian
                FROM ventas v
                LEFT JOIN clientes c ON v.cliente_id::text = c.id::text
                WHERE v.id = %s
            """, (venta_id,))
            venta = cur.fetchone()
            if not venta:
                return {"ok": False, "error": f"Venta {venta_id} no encontrada"}

            if (venta.get("factura_estado") or "") == "emitida":
                return {
                    "ok": False,
                    "error": f"La venta {venta_id} ya tiene factura {venta.get('factura_numero')}",
                }

            cur.execute("""
                SELECT vd.*, p.tiene_iva, p.porcentaje_iva
                FROM ventas_detalle vd
                LEFT JOIN productos p ON vd.producto_id = p.id
                WHERE vd.venta_id = %s
            """, (venta_id,))
            detalle  = cur.fetchall()
            num_dian = _siguiente_num_dian(cur)

    payload = _armar_payload(dict(venta), [dict(d) for d in detalle], num_dian)
    numero  = f"{MATIAS_PREFIX}{num_dian}"

    import asyncio
    try:
        token = await asyncio.to_thread(_get_token)
    except (RuntimeError, ValueError, httpx.HTTPStatusError) as e:
        return {"ok": False, "error": str(e)}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    logger.debug("Payload MATIAS API venta %s: %s", venta_id, payload)
    
    # 📤 LOG TEMPORAL: Ver JSON completo enviado a MATIAS
    import json
    logger.info("📤 JSON COMPLETO enviado a MATIAS API:\n%s", json.dumps(payload, indent=2, ensure_ascii=False))

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MATIAS_API_URL}/invoice", json=payload, headers=headers)
        data = resp.json()
    except Exception as e:
        logger.error("MATIAS API conexión fallida venta %s: %s", venta_id, e)
        return {"ok": False, "error": f"Error de conexión con Matias API: {e}"}

    logger.debug("Respuesta MATIAS API venta %s (HTTP %s): %s", venta_id, resp.status_code, data)

    valido = bool(data.get("success"))
    cufe   = data.get("XmlDocumentKey") or data.get("document_key", "")

    if not valido:
        msg    = data.get("message") or ""
        errors = data.get("errors") or {}
        if isinstance(errors, dict) and errors:
            error_msg = f"{msg} | " + " | ".join(f"{k}: {v}" for k, v in errors.items())
        elif errors:
            error_msg = f"{msg} | {errors}"
        else:
            error_msg = msg or str(data)

        logger.error("MATIAS API rechazó factura venta %s: %s", venta_id, error_msg)
        try:
            with _db._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO facturas_electronicas "
                        "(venta_id, numero, cliente_nombre, total, estado, error_msg) "
                        "VALUES (%s, %s, %s, %s, 'error', %s)",
                        (venta_id, f"ERR-{num_dian}", venta.get("cliente_nombre"),
                         venta.get("total"), error_msg[:500]),
                    )
                conn.commit()
        except Exception:
            pass
        return {"ok": False, "error": error_msg}

    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ventas
                SET factura_numero = %s,
                    factura_cufe   = %s,
                    factura_estado = 'emitida',
                    facturada_at   = NOW()
                WHERE id = %s
            """, (numero, cufe, venta_id))
            cur.execute("""
                INSERT INTO facturas_electronicas
                    (venta_id, numero, cufe, cliente_nombre, total)
                VALUES (%s, %s, %s, %s, %s)
            """, (venta_id, numero, cufe, venta.get("cliente_nombre"), venta.get("total")))
        conn.commit()

    logger.info("✅ Factura %s emitida — CUFE: %s…", numero, cufe[:20])
    return {"ok": True, "cufe": cufe, "numero": numero}


# ── Descargar PDF ─────────────────────────────────────────────────────────────

async def obtener_pdf(cufe: str) -> bytes:
    """
    Descarga el PDF desde MATIAS API v3.0.0.
    Endpoint: POST /documents/pdf/{cufe} con regenerate=1.
    MATIAS puede responder con PDF directo O JSON con URL/data en base64.
    """
    import asyncio
    import base64
    token = await asyncio.to_thread(_get_token)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/pdf, application/json",
        "Content-Type": "application/json",
    }

    url = f"{MATIAS_API_URL}/documents/pdf/{cufe}"

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.post(url, headers=headers, json={"regenerate": 1})
            content_type = resp.headers.get("content-type", "")

            if resp.status_code != 200:
                logger.error("MATIAS PDF error HTTP %s: %s", resp.status_code, resp.text[:500])
                raise RuntimeError(f"MATIAS API devolvió HTTP {resp.status_code}")

            # Caso 1: PDF directo
            if "application/pdf" in content_type:
                pdf_bytes = resp.content
                if len(pdf_bytes) < 100:
                    raise RuntimeError(f"PDF muy pequeño ({len(pdf_bytes)} bytes) — posible error")
                logger.info("✅ PDF descargado directo: %s bytes", len(pdf_bytes))
                return pdf_bytes

            # Caso 2: JSON con URL o data en base64
            if "application/json" in content_type:
                json_resp = resp.json()
                logger.info("MATIAS devolvió JSON: %s", json_resp.get("message", "sin mensaje"))
                pdf_info = json_resp.get("pdf", {})

                # Opción A: PDF en base64 en campo "data"
                if pdf_info.get("data"):
                    try:
                        pdf_base64 = pdf_info["data"]
                        if "base64," in pdf_base64:
                            pdf_base64 = pdf_base64.split("base64,")[1]
                        pdf_bytes = base64.b64decode(pdf_base64)
                        if len(pdf_bytes) < 100:
                            raise ValueError(f"PDF decodificado muy pequeño ({len(pdf_bytes)} bytes)")
                        logger.info("✅ PDF decodificado desde base64: %s bytes", len(pdf_bytes))
                        return pdf_bytes
                    except Exception as e:
                        logger.warning("Error decodificando PDF base64: %s", e)

                # Opción B: Descargar desde URL
                if pdf_info.get("url"):
                    pdf_url = pdf_info["url"]
                    logger.info("Descargando PDF desde URL: %s", pdf_url)
                    pdf_resp = await client.get(pdf_url)
                    if pdf_resp.status_code == 200:
                        pdf_bytes = pdf_resp.content
                        if len(pdf_bytes) < 100:
                            raise RuntimeError(f"PDF desde URL muy pequeño ({len(pdf_bytes)} bytes)")
                        logger.info("✅ PDF descargado desde URL: %s bytes", len(pdf_bytes))
                        return pdf_bytes
                    raise RuntimeError(f"Error descargando PDF desde URL: HTTP {pdf_resp.status_code}")

                raise RuntimeError(f"JSON no contiene 'data' ni 'url' válidos: {json_resp}")

            raise RuntimeError(f"Content-Type inesperado: {content_type}")

        except httpx.HTTPError as e:
            logger.error("Error HTTP descargando PDF %s: %s", cufe, e)
            raise RuntimeError(f"Error de conexión con MATIAS API: {e}")


# ── Descargar XML ─────────────────────────────────────────────────────────────

async def obtener_xml(cufe: str) -> bytes:
    """
    Descarga el XML técnico de una factura desde MATIAS API v3.
    Endpoint: GET /documents/xml/{trackId}
    Útil para contabilidad o auditoría.
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(
            f"{MATIAS_API_URL}/documents/xml/{cufe}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/xml, application/json"},
        )
    if resp.status_code == 200:
        return resp.content
    try:
        data = resp.json()
        msg  = data.get("message") or str(data)
    except Exception:
        msg = resp.text[:200] or f"HTTP {resp.status_code}"
    raise RuntimeError(f"MATIAS API /documents/xml ({resp.status_code}): {msg}")


# ── Estado DIAN ───────────────────────────────────────────────────────────────

async def consultar_estado_dian(cufe: str | None = None, numero: str | None = None, prefix: str | None = None) -> dict:
    """
    Consulta el estado de validación DIAN de un documento.

    MATIAS API v3 tiene dos endpoints de estado:
    - GET /status/document/{trackId} → PRODUCCIÓN — valida directamente contra DIAN
    - GET /status?number=...         → consulta general por número/prefijo
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=20) as client:
        # Si tenemos CUFE → /status/document/{trackId}
        if cufe:
            resp = await client.get(f"{MATIAS_API_URL}/status/document/{cufe}", headers=headers)

        # Fallback por número → /status?number=...
        else:
            params: dict = {}
            if numero:
                params["number"] = numero
            if prefix:
                params["prefix"] = prefix
            elif MATIAS_PREFIX:
                params["prefix"] = MATIAS_PREFIX
            resp = await client.get(f"{MATIAS_API_URL}/status", params=params, headers=headers)

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /status devolvió respuesta no JSON (HTTP {resp.status_code})")

    if resp.status_code not in (200, 201):
        msg = data.get("message") or str(data)
        raise RuntimeError(f"MATIAS API /status ({resp.status_code}): {msg}")

    logger.info("Estado DIAN: %s", data.get("status") or data.get("StatusDescription") or "OK")
    return data


# ── Buscar documentos ─────────────────────────────────────────────────────────

async def buscar_documentos(
    numero: str | None        = None,
    prefix: str | None        = None,
    start_date: str | None    = None,
    end_date: str | None      = None,
    document_status: int | None = None,  # -1=todos | 0=sin validar | 1=validado
    limit: int                = 20,
) -> list[dict]:
    """
    Busca facturas emitidas en MATIAS API con filtros opcionales.
    Endpoint: GET /documents
    Útil para el dashboard: listar facturas por fecha, ver cuáles están validadas, etc.
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    params: dict = {"limit": limit}
    if numero:
        params["number"] = numero
    if prefix:
        params["prefix"] = prefix
    elif MATIAS_PREFIX:
        params["prefix"] = MATIAS_PREFIX
    if MATIAS_RESOLUTION:
        params["resolution"] = MATIAS_RESOLUTION
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if document_status is not None:
        params["document_status"] = document_status

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{MATIAS_API_URL}/documents",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /documents devolvió respuesta no JSON (HTTP {resp.status_code})")

    if resp.status_code not in (200, 201):
        msg = data.get("message") or str(data)
        raise RuntimeError(f"MATIAS API /documents ({resp.status_code}): {msg}")

    return (
        data.get("data") or
        data.get("dataRecords", {}).get("data") or
        []
    )


# ── Consultar consumo del plan ────────────────────────────────────────────────

async def consultar_consumo() -> dict:
    """
    Consulta cuántas facturas has consumido del plan MATIAS.
    Endpoint: GET /ubl2.1/memberships/consumption
    Útil para el dashboard: mostrar alerta cuando se acerque al límite.
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{MATIAS_API_URL}/memberships/consumption",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /memberships/consumption no JSON (HTTP {resp.status_code})")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"MATIAS API consumo ({resp.status_code}): {data.get('message') or data}")
    return data.get("data") or data


# ── Último número emitido ─────────────────────────────────────────────────────

async def obtener_ultimo_documento(
    resolution: str | None = None,
    prefix:     str | None = None,
) -> dict:
    import asyncio
    token = await asyncio.to_thread(_get_token)
    params: dict = {}
    if resolution:
        params["resolution"] = resolution
    elif MATIAS_RESOLUTION:
        params["resolution"] = MATIAS_RESOLUTION
    if prefix:
        params["prefix"] = prefix
    elif MATIAS_PREFIX:
        params["prefix"] = MATIAS_PREFIX

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{MATIAS_API_URL}/documents/last",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /documents/last no JSON (HTTP {resp.status_code})")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"MATIAS API /documents/last ({resp.status_code}): {data.get('message') or data}")

    logger.info("Último documento MATIAS API: %s", data)
    return data


# ── Validar adquirente en RUT/DIAN ────────────────────────────────────────────

async def consultar_adquirente(tipo_id: str, numero_identificacion: str) -> dict:
    """
    Valida datos de un cliente en el RUT/DIAN antes de emitir factura.
    Endpoint: GET /acquirer

    IMPORTANTE: Este endpoint usa CÓDIGOS DIAN directos (NO IDs internos MATIAS):
        CC=13  NIT=31  CE=22  Pasaporte=41  TI=12  TE=21  PPT=48  PEP=47
    Confirmado por soporte MATIAS API v3.
    """
    import asyncio
    # Normalizar: acepta tanto "CC" como "13"
    tipo_normalizado = _TIPO_ID_DIAN.get(tipo_id.upper(), tipo_id)

    token = await asyncio.to_thread(_get_token)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{MATIAS_API_URL}/acquirer",
            params={
                "identificationType":   tipo_normalizado,
                "identificationNumber": numero_identificacion,
            },
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /acquirer no JSON (HTTP {resp.status_code})")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"MATIAS API /acquirer ({resp.status_code}): {data.get('message') or data}")

    logger.info(
        "Adquirente validado — %s %s: %s",
        tipo_id, numero_identificacion,
        data.get("company_name") or data.get("names") or "OK",
    )
    return data


# ── Reenviar correo de factura ────────────────────────────────────────────────

async def reenviar_correo_factura(track_id: str, email_to: str | None = None) -> dict:
    """
    Reenvía el PDF al correo del cliente.
    Endpoint: POST /documents/sendmail/{trackId}
    Si se pasa email_to, usa el endpoint de correo personalizado.
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    }
    body = {}
    if email_to:
        body["email_to"] = email_to

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{MATIAS_API_URL}/documents/sendmail/{track_id}",
            json=body,
            headers=headers,
        )

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /sendmail no JSON (HTTP {resp.status_code})")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"MATIAS API /sendmail ({resp.status_code}): {data.get('message') or data}")

    logger.info("📧 Correo reenviado — trackId: %s…", track_id[:20])
    return data


# ── Notas crédito y débito ────────────────────────────────────────────────────

RAZONES_NC = {
    1: "Devolución parcial de los bienes",
    2: "Anulación de factura",
    3: "Rebaja o descuento parcial",
    4: "Ajuste de precio",
    5: "Otro",
}

RAZONES_ND = {
    1: "Intereses",
    2: "Gastos por cobrar",
    3: "Cambio del valor",
    4: "Otro",
}


def _armar_lineas_nota(lineas: list[dict]) -> tuple[list, float, float, float]:
    """Helper compartido para armar líneas de notas crédito/débito."""
    subtotal          = sum(int(d.get("total") or 0) for d in lineas)
    subtotal_gravable = sum(int(d.get("total") or 0) for d in lineas if d.get("tiene_iva"))
    total_iva         = sum(
        int(int(d.get("total") or 0) * int(d.get("porcentaje_iva") or 0) / 100)
        for d in lineas if d.get("tiene_iva")
    )

    lines_payload = []
    for item in lineas:
        precio_u  = _fmt(item.get("precio_unitario") or 0)
        cantidad  = round(float(item.get("cantidad") or 1), 4)
        total_l   = _fmt(item.get("total") or 0)
        tiene_iva = bool(item.get("tiene_iva"))
        pct_iva   = int(item.get("porcentaje_iva") or 0)
        iva_val   = _fmt(int(item.get("total") or 0) * pct_iva / 100) if tiene_iva else 0.0
        unidad_raw   = (item.get("unidad_medida") or "Unidad").strip()
        qty_units_id = _UNIDAD_DIAN.get(unidad_raw, _UNIDAD_DIAN.get(unidad_raw.lower(), 70))

        lines_payload.append({
            "invoiced_quantity":            cantidad,
            "quantity_units_id":            qty_units_id,
            "line_extension_amount":        total_l,
            "free_of_charge_indicator":     False,
            "description":                  (item.get("producto_nombre") or "Ítem").upper(),
            "code":                         str(item.get("producto_id") or "SC"),
            "type_item_identifications_id": "4",
            "reference_price_id":           "1",
            "price_amount":                 precio_u,
            "base_quantity":                cantidad,
            "tax_totals": [{
                "tax_id":         "1" if tiene_iva else "4",
                "tax_amount":     iva_val,
                "taxable_amount": total_l if tiene_iva else 0.0,
                "percent":        _fmt(pct_iva),
            }],
        })

    return lines_payload, subtotal, subtotal_gravable, total_iva


async def emitir_nota_credito(
    factura_cufe: str, factura_numero: str, factura_fecha: str,
    razon_id: int, venta_id: int, lineas_devueltas: list[dict],
) -> dict:
    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        return {"ok": False, "error": "MATIAS_EMAIL/MATIAS_PASSWORD no configurados"}

    ahora = datetime.now(COLOMBIA_TZ)
    lines, subtotal, subtotal_gravable, total_iva = _armar_lineas_nota(lineas_devueltas)
    total_doc = subtotal + total_iva

    payload = {
        "type_document_id":       5,
        "date":                   ahora.strftime("%Y-%m-%d"),
        "time":                   ahora.strftime("%H:%M:%S"),
        "currency_id":            272,
        "notes":                  RAZONES_NC.get(razon_id, "Nota crédito"),
        "graphic_representation": 1,
        "send_email":             0,
        "discrepancy_response": {
            "discrepancy_response_id": razon_id,
            "description":             RAZONES_NC.get(razon_id, "Otro"),
        },
        "billing_reference": {
            "number": factura_numero,
            "uuid":   factura_cufe,
            "date":   factura_fecha,
        },
        "tax_totals": [{
            "tax_id":         "1" if total_iva > 0 else "4",
            "tax_amount":     _fmt(total_iva),
            "taxable_amount": _fmt(subtotal_gravable) if total_iva > 0 else 0.0,
            "percent":        19.0 if total_iva > 0 else 0.0,
        }],
        "legal_monetary_totals": {
            "line_extension_amount":  _fmt(subtotal),
            "tax_exclusive_amount":   _fmt(subtotal),
            "tax_inclusive_amount":   _fmt(total_doc),
            "allowance_total_amount": 0.0,
            "charge_total_amount":    0.0,
            "pre_paid_amount":        0.0,
            "payable_amount":         _fmt(total_doc),
        },
        "lines": lines,
    }

    import asyncio
    try:
        token = await asyncio.to_thread(_get_token)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    logger.debug("Payload nota crédito venta %s: %s", venta_id, payload)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MATIAS_API_URL}/notes/credit", json=payload, headers=headers)
        data = resp.json()
    except Exception as e:
        return {"ok": False, "error": f"Error de conexión: {e}"}

    valido = bool(data.get("success"))
    cufe   = data.get("XmlDocumentKey") or data.get("document_key") or data.get("track_id", "")
    numero = data.get("document_number") or data.get("number") or ""

    if not valido:
        msg       = data.get("message") or ""
        errors    = data.get("errors") or {}
        error_msg = (f"{msg} | " + " | ".join(f"{k}: {v}" for k, v in errors.items())).strip(" |") if isinstance(errors, dict) and errors else msg or str(data)
        logger.error("Nota crédito rechazada venta %s: %s", venta_id, error_msg)
        _guardar_nota_db("credito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "error", error_msg)
        return {"ok": False, "error": error_msg}

    _guardar_nota_db("credito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "emitida", None)
    logger.info("✅ Nota crédito %s emitida — CUFE: %s…", numero, cufe[:20] if cufe else "?")
    return {"ok": True, "cufe": cufe, "numero": numero, "tipo": "credito"}


async def emitir_nota_debito(
    factura_cufe: str, factura_numero: str, factura_fecha: str,
    razon_id: int, venta_id: int, lineas: list[dict],
) -> dict:
    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        return {"ok": False, "error": "MATIAS_EMAIL/MATIAS_PASSWORD no configurados"}

    ahora = datetime.now(COLOMBIA_TZ)
    lines_payload, subtotal, subtotal_gravable, total_iva = _armar_lineas_nota(lineas)
    total_doc = subtotal + total_iva

    payload = {
        "type_document_id":       4,
        "date":                   ahora.strftime("%Y-%m-%d"),
        "time":                   ahora.strftime("%H:%M:%S"),
        "currency_id":            272,
        "notes":                  RAZONES_ND.get(razon_id, "Nota débito"),
        "graphic_representation": 1,
        "send_email":             0,
        "discrepancy_response": {
            "discrepancy_response_id": razon_id,
            "description":             RAZONES_ND.get(razon_id, "Otro"),
        },
        "billing_reference": {
            "number": factura_numero,
            "uuid":   factura_cufe,
            "date":   factura_fecha,
        },
        "tax_totals": [{
            "tax_id":         "1" if total_iva > 0 else "4",
            "tax_amount":     _fmt(total_iva),
            "taxable_amount": _fmt(subtotal_gravable) if total_iva > 0 else 0.0,
            "percent":        19.0 if total_iva > 0 else 0.0,
        }],
        "legal_monetary_totals": {
            "line_extension_amount":  _fmt(subtotal),
            "tax_exclusive_amount":   _fmt(subtotal),
            "tax_inclusive_amount":   _fmt(total_doc),
            "allowance_total_amount": 0.0,
            "charge_total_amount":    0.0,
            "pre_paid_amount":        0.0,
            "payable_amount":         _fmt(total_doc),
        },
        "lines": lines_payload,
    }

    import asyncio
    try:
        token = await asyncio.to_thread(_get_token)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MATIAS_API_URL}/notes/debit", json=payload, headers=headers)
        data = resp.json()
    except Exception as e:
        return {"ok": False, "error": f"Error de conexión: {e}"}

    valido = bool(data.get("success"))
    cufe   = data.get("XmlDocumentKey") or data.get("document_key") or data.get("track_id", "")
    numero = data.get("document_number") or data.get("number") or ""

    if not valido:
        msg       = data.get("message") or ""
        errors    = data.get("errors") or {}
        error_msg = (f"{msg} | " + " | ".join(f"{k}: {v}" for k, v in errors.items())).strip(" |") if isinstance(errors, dict) and errors else msg or str(data)
        logger.error("Nota débito rechazada venta %s: %s", venta_id, error_msg)
        _guardar_nota_db("debito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "error", error_msg)
        return {"ok": False, "error": error_msg}

    _guardar_nota_db("debito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "emitida", None)
    logger.info("✅ Nota débito %s emitida — CUFE: %s…", numero, cufe[:20] if cufe else "?")
    return {"ok": True, "cufe": cufe, "numero": numero, "tipo": "debito"}


def _guardar_nota_db(
    tipo: str, venta_id: int, numero: str, cufe: str,
    factura_cufe_ref: str, razon_id: int, total: float,
    estado: str, error_msg: str | None,
) -> None:
    try:
        _db.execute(
            """
            INSERT INTO facturas_electronicas
                (venta_id, numero, cufe, total, estado, error_msg,
                 tipo, razon_id, factura_cufe_ref)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [venta_id, numero or "", cufe or "", int(total or 0),
             estado, error_msg, tipo, razon_id, factura_cufe_ref],
        )
    except Exception as e:
        logger.warning("No se pudo guardar nota %s en DB: %s", tipo, e)
