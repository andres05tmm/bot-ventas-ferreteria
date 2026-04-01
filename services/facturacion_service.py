"""
services/facturacion_service.py
Integración con MATIAS API v2 para facturación electrónica DIAN.

Auth:     https://auth-v2.matias-api.com  (login con email + password → JWT renovable)
API base: https://api-v2.matias-api.com/api/ubl2.1

Variables de entorno en Railway:
    MATIAS_EMAIL        demo@lopezsoft.net.co
    MATIAS_PASSWORD     DEMO123456
    MATIAS_RESOLUTION   18764074347312
    MATIAS_PREFIX       LZT
    MATIAS_NUM_DESDE    5280   (primer número del rango autorizado DIAN)
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

MATIAS_AUTH_URL   = os.getenv("MATIAS_API_URL", "https://api-v2.matias-api.com/api/ubl2.1").split("/api/ubl2.1")[0]
MATIAS_API_URL    = os.getenv("MATIAS_API_URL", "https://api-v2.matias-api.com/api/ubl2.1")
MATIAS_EMAIL      = os.getenv("MATIAS_EMAIL")
MATIAS_PASSWORD   = os.getenv("MATIAS_PASSWORD")
MATIAS_RESOLUTION = os.getenv("MATIAS_RESOLUTION")
MATIAS_PREFIX     = os.getenv("MATIAS_PREFIX", "LZT")
MATIAS_NUM_DESDE  = int(os.getenv("MATIAS_NUM_DESDE", "5280"))

_MEDIOS_PAGO = {
    "efectivo":      10,
    "transferencia": 42,
    "tarjeta":       48,
    "nequi":         42,
    "daviplata":     42,
    "datafono":      48,
}

# ── Caché de ciudades MATIAS API (dane_code → matias_id interno) ──────────────
#
# IMPORTANTE: MATIAS API usa sus propios IDs secuenciales internos para ciudades,
# NO los códigos DANE municipales (ej: DANE 13001 ≠ ID MATIAS de Cartagena).
# El endpoint público GET /cities devuelve el catálogo con la correspondencia.
# Enviando un código DANE directamente como city_id causa el error:
#   "El campo customer.city_id no existe en la tabla cities"

_cities_cache:        dict = {}
_cities_cache_loaded: bool = False
_cities_lock_obj:     threading.Lock = threading.Lock()


def _cargar_ciudades_matias() -> None:
    """Carga el catálogo de ciudades de MATIAS API una sola vez y lo cachea."""
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
                    # MATIAS API almacena el código DANE en el campo "code"
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
    """
    Resuelve el city_id interno de MATIAS API a partir de un código DANE municipal.
    Retorna None si no se encuentra o si dane_code es nulo; en ese caso se omite
    city_id del payload (campo opcional en MATIAS para Consumidor Final).
    """
    if not dane_code:
        return None
    _cargar_ciudades_matias()
    try:
        return _cities_cache.get(int(dane_code))
    except (ValueError, TypeError):
        return None


# ── Cache de token JWT con auto-renovación ────────────────────────────────────

_token_lock:   threading.Lock = threading.Lock()
_cached_token: Optional[str]  = None
_token_expiry: float          = 0.0   # timestamp Unix


def _get_token() -> str:
    """
    Devuelve un JWT válido, haciendo login automáticamente si expiró.
    Se cachea en memoria — renueva solo cuando faltan menos de 60 s.

    Raises:
        RuntimeError  si MATIAS_EMAIL o MATIAS_PASSWORD no están configurados.
        httpx.HTTPStatusError  si el login falla (credenciales incorrectas).
    """
    global _cached_token, _token_expiry

    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        raise RuntimeError(
            "Faltan variables de entorno: MATIAS_EMAIL y MATIAS_PASSWORD. "
            "Agrégalas en Railway → Variables."
        )

    with _token_lock:
        ahora = time.time()
        # Reutilizar token si le quedan más de 60 segundos de vida
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

        # Loguear respuesta cruda SIEMPRE para facilitar debugging
        logger.info(
            "Auth Matias API → HTTP %s | body: %s",
            resp.status_code,
            resp.text[:500] if resp.text else "(vacío)",
        )

        resp.raise_for_status()

        if not resp.text or not resp.text.strip():
            raise ValueError(
                f"Matias API devolvió body vacío (HTTP {resp.status_code}). "
                "Verifica la URL de auth y las credenciales."
            )

        try:
            data = resp.json()
        except Exception as e:
            raise ValueError(
                f"Matias API no devolvió JSON válido (HTTP {resp.status_code}): "
                f"{resp.text[:300]} — Error: {e}"
            )

        # Matias API puede devolver el token en distintas claves según versión
        token = (
            data.get("token") or
            data.get("access_token") or
            (data.get("data") or {}).get("token") or
            (data.get("data") or {}).get("access_token")
        )
        if not token:
            raise ValueError(f"No se encontró token en respuesta de auth: {data}")

        expires_in    = float(data.get("expires_in") or 3600)
        _cached_token = token
        _token_expiry = ahora + expires_in
        logger.info("Token Matias API renovado OK (expira en %.0f min)", expires_in / 60)
        return _cached_token


# ── Helpers internos ──────────────────────────────────────────────────────────

def _siguiente_num_dian(cur) -> int:
    """
    Siguiente número DIAN respetando el rango autorizado.
    Usa el MAX de facturas ya emitidas; si no hay ninguna arranca
    desde MATIAS_NUM_DESDE.
    """
    cur.execute(
        """
        SELECT COALESCE(
            MAX(CAST(NULLIF(regexp_replace(numero, '[^0-9]', '', 'g'), '') AS INTEGER)),
            %s - 1
        ) + 1 AS siguiente
        FROM facturas_electronicas
        WHERE estado = 'emitida'
        """,
        (MATIAS_NUM_DESDE,),
    )
    siguiente = cur.fetchone()["siguiente"]
    return max(siguiente, MATIAS_NUM_DESDE)


def _fmt(valor) -> str:
    """Número → string con 2 decimales (requerido por Matias API)."""
    return f"{float(valor or 0):.2f}"


def _armar_payload(venta: dict, detalle: list[dict], num_dian: int) -> dict:
    """Construye el JSON de factura según Matias API UBL 2.1."""
    ahora    = datetime.now(COLOMBIA_TZ)
    es_nit   = (venta.get("tipo_id") or "").upper() == "NIT"
    medio_id = _MEDIOS_PAGO.get(
        (venta.get("metodo_pago") or "efectivo").lower(), 10
    )

    # ── Totales ───────────────────────────────────────────────────────────────
    subtotal  = sum(int(d.get("total") or 0) for d in detalle)
    total_iva = sum(
        int(int(d.get("total") or 0) * int(d.get("porcentaje_iva") or 0) / 100)
        for d in detalle if d.get("tiene_iva")
    )
    total_doc = subtotal + total_iva

    # ── Comprador ─────────────────────────────────────────────────────────────
    # BUGFIX: city_id debe ser el ID interno de MATIAS API, no el código DANE.
    # Se resuelve dinámicamente vía _matias_city_id(). Si no se puede resolver
    # (Consumidor Final, cliente sin municipio_dian), se omite del payload para
    # evitar el error: "El campo customer.city_id no existe en la tabla cities".
    customer = {
        "country_id":            "45",
        "identity_document_id":  "6" if es_nit else "3",
        "type_organization_id":  1   if es_nit else 2,
        "tax_regime_id":         1   if es_nit else 2,
        "tax_level_id":          1   if es_nit else 5,
        "company_name":          (venta.get("cliente_nombre") or "CONSUMIDOR FINAL").upper(),
        "dni":                   venta.get("identificacion_cliente") or "222222222222",
        "mobile":                venta.get("telefono_cliente")       or "3000000000",
        "email":                 venta.get("correo_cliente")         or "sinfactura@ferreteriapuntorojo.com",
        "address":               venta.get("direccion_cliente")      or "Cartagena",
    }
    # Agregar city_id solo si se puede resolver el ID interno de MATIAS API
    _resolved_city_id = _matias_city_id(venta.get("municipio_dian"))
    if _resolved_city_id:
        customer["city_id"] = _resolved_city_id
    else:
        logger.debug(
            "city_id omitido del payload (dane=%s no resuelto en MATIAS API)",
            venta.get("municipio_dian"),
        )

    # ── Líneas de detalle ─────────────────────────────────────────────────────
    lines = []
    for item in detalle:
        precio_u  = _fmt(item.get("precio_unitario") or 0)
        cantidad  = str(float(item.get("cantidad") or 1))
        total_l   = _fmt(item.get("total") or 0)
        tiene_iva = bool(item.get("tiene_iva"))
        pct_iva   = int(item.get("porcentaje_iva") or 0)
        iva_val   = _fmt(int(item.get("total") or 0) * pct_iva / 100) if tiene_iva else "0.00"

        lines.append({
            "invoiced_quantity":            cantidad,
            "quantity_units_id":            "70",
            "line_extension_amount":        total_l,
            "free_of_charge_indicator":     False,
            "description":                  (item.get("producto_nombre") or "Producto").upper(),
            "code":                         str(item.get("producto_id") or "SC"),
            "type_item_identifications_id": "4",
            "reference_price_id":           "1",
            "price_amount":                 precio_u,
            "base_quantity":                cantidad,
            "tax_totals": [{
                "tax_id":         "1" if tiene_iva else "4",
                "tax_amount":     iva_val,
                "taxable_amount": total_l if tiene_iva else "0.00",
                "percent":        _fmt(pct_iva),
            }],
        })

    # ── Tax totals a nivel documento ──────────────────────────────────────────
    doc_tax_totals = [{
        "tax_id":         "1" if total_iva > 0 else "4",
        "tax_amount":     _fmt(total_iva),
        "taxable_amount": _fmt(subtotal) if total_iva > 0 else "0.00",
        "percent":        "19.00" if total_iva > 0 else "0.00",
    }]

    # ── legal_monetary_totals (campo obligatorio) ─────────────────────────────
    legal_monetary_totals = {
        "line_extension_amount":  _fmt(subtotal),
        "tax_exclusive_amount":   _fmt(subtotal),
        "tax_inclusive_amount":   _fmt(total_doc),
        "allowance_total_amount": "0.00",
        "charge_total_amount":    "0.00",
        "pre_paid_amount":        "0.00",
        "payable_amount":         _fmt(total_doc),
    }

    return {
        "resolution_number":      MATIAS_RESOLUTION,
        "prefix":                 MATIAS_PREFIX,
        "document_number":        str(num_dian),
        "date":                   str(venta["fecha"])[:10],
        "time":                   ahora.strftime("%H:%M:%S"),
        "type_document_id":       7,
        "operation_type_id":      1,
        "graphic_representation": True,
        "send_email":             True,
        "customer":               customer,
        "tax_totals":             doc_tax_totals,
        "legal_monetary_totals":  legal_monetary_totals,
        "payments": [{
            "payment_method_id": 1,
            "means_payment_id":  medio_id,
            "value_paid":        _fmt(total_doc),
        }],
        "lines": lines,
    }


# ── Función principal ─────────────────────────────────────────────────────────

async def emitir_factura(venta_id: int) -> dict:
    """
    Emite la factura electrónica DIAN para una venta ya registrada en PostgreSQL.

    Retorna:
        { "ok": True,  "cufe": "...", "numero": "LZT5280" }
        { "ok": False, "error": "mensaje legible" }
    """
    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        return {"ok": False, "error": "MATIAS_EMAIL y MATIAS_PASSWORD no están configurados en Railway"}
    if not MATIAS_RESOLUTION:
        return {"ok": False, "error": "MATIAS_RESOLUTION no configurado en Railway"}

    # ── Leer venta + cliente + detalle desde PostgreSQL ───────────────────────
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

    # ── Obtener token (login automático si expiró) ────────────────────────────
    try:
        token = _get_token()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"Login Matias API falló ({e.response.status_code}): revisa MATIAS_EMAIL/MATIAS_PASSWORD"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    logger.debug("Payload MATIAS API venta %s: %s", venta_id, payload)

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

    # ── Factura rechazada ─────────────────────────────────────────────────────
    if not valido:
        msg    = data.get("message") or ""
        errors = data.get("errors") or {}
        if isinstance(errors, dict) and errors:
            error_detail = " | ".join(f"{k}: {v}" for k, v in errors.items())
            error_msg    = f"{msg} | {error_detail}".strip(" |")
        elif errors:
            error_msg = f"{msg} | {errors}".strip(" |")
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

    # ── Factura emitida OK ────────────────────────────────────────────────────
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


async def obtener_pdf(cufe: str) -> bytes:
    """
    Descarga el PDF de una factura desde Matias API usando el CUFE.
    También usa token auto-renovado.
    """
    token = _get_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{MATIAS_API_URL}/pdf/{cufe}",
            headers={"Authorization": f"Bearer {token}"},
        )
    resp.raise_for_status()
    return resp.content
