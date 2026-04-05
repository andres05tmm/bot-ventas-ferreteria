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

# ── Mapa de unidades internas → quantity_units_id de MATIAS API ───────────────
# MATIAS API usa IDs numéricos propios (NO códigos UNECE como string).
# IDs verificados con GET /quantity-units (endpoint público):
#   id:70  code:"94"  → "unidad"           ← "70" del código original era correcto
#   id:686 code:"GLL" → "galón"
#   id:767 code:"KGM" → "kilogramo"
#   id:692 code:"GRM" → "gramo"
#   id:821 code:"LTR" → "litro"
#   id:852 code:"MLT" → "mililitro"
#   id:865 code:"MTR" → "metro"
#   id:495 code:"CMT" → "centímetro"
# Los valores internos vienen de _UNIDAD_MAP en routers/catalogo.py.
_UNIDAD_DIAN: dict[str, str] = {
    # unidad genérica (default)
    "Unidad":  "70",
    "unidad":  "70",
    # galón (US — pinturas, solventes, impermeabilizantes)
    "Galón":   "686",
    "galon":   "686",
    "Gal":     "686",
    # kilogramo (puntillas a granel, materiales por peso)
    "Kg":      "767",
    "kg":      "767",
    # gramo (tintes, pigmentos)
    "GRM":     "692",
    "gramo":   "692",
    # metro lineal (cables, mangueras, tubería, perfilería)
    "Mts":     "865",
    "Mt":      "865",
    "metro":   "865",
    # centímetro
    "Cms":     "495",
    "Cm":      "495",
    # litro
    "Lt":      "821",
    "Lts":     "821",
    "litro":   "821",
    # mililitro (tintes en cc/ml)
    "MLT":     "852",
    "ml":      "852",
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
    """
    Siguiente número DIAN respetando el rango autorizado.
    FIX Bug 3: usa LOCK TABLE para evitar duplicados en emisiones concurrentes.
    """
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


def _fmt(valor) -> str:
    """Número → string con 2 decimales (requerido por Matias API)."""
    return f"{float(valor or 0):.2f}"


# ── Detección de correo real vs placeholder ───────────────────────────────────

_EMAIL_PLACEHOLDER = "sinfactura@ferreteriapuntorojo.com"


def _sin_correo_real(email: str | None) -> bool:
    """Retorna True si el email es nulo o es el placeholder de Consumidor Final."""
    return not email or email.strip().lower() == _EMAIL_PLACEHOLDER


# ── Envío de PDF al grupo de Telegram ────────────────────────────────────────

async def _enviar_pdf_grupo_telegram(
    cufe: str, numero: str, cliente_nombre: str | None, total
) -> None:
    """
    Descarga el PDF desde MATIAS API y lo envía como documento al grupo de Telegram.
    Se llama cuando el cliente no tiene correo real registrado.
    Fallo silencioso — no afecta el resultado de la emisión.
    """
    chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
    token   = os.getenv("TELEGRAM_TOKEN")
    if not chat_id or not token:
        logger.warning(
            "PDF %s no enviado a Telegram: falta TELEGRAM_NOTIFY_CHAT_ID o TELEGRAM_TOKEN",
            numero,
        )
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
            logger.error(
                "Error enviando PDF %s a Telegram: HTTP %s — %s",
                numero, resp.status_code, resp.text[:200],
            )
    except Exception as e:
        logger.error("Error enviando PDF %s al grupo Telegram: %s", numero, e)


def _armar_payload(venta: dict, detalle: list[dict], num_dian: int) -> dict:
    """Construye el JSON de factura según Matias API UBL 2.1."""
    ahora    = datetime.now(COLOMBIA_TZ)
    es_nit   = (venta.get("tipo_id") or "").upper() == "NIT"
    medio_id = _MEDIOS_PAGO.get(
        (venta.get("metodo_pago") or "efectivo").lower(), 10
    )

    # ── Totales ───────────────────────────────────────────────────────────────
    subtotal          = sum(int(d.get("total") or 0) for d in detalle)
    # subtotal_gravable: solo ítems con IVA (base imponible real para la DIAN)
    subtotal_gravable = sum(int(d.get("total") or 0) for d in detalle if d.get("tiene_iva"))
    total_iva         = sum(
        int(int(d.get("total") or 0) * int(d.get("porcentaje_iva") or 0) / 100)
        for d in detalle if d.get("tiene_iva")
    )
    total_doc = subtotal + total_iva

    # ── Comprador ─────────────────────────────────────────────────────────────
    # BUGFIX: city_id debe ser el ID interno de MATIAS API, no el código DANE.
    # Se resuelve dinámicamente vía _matias_city_id(). Si no se puede resolver
    # (Consumidor Final, cliente sin municipio_dian), se omite del payload para
    # evitar el error: "El campo customer.city_id no existe en la tabla cities".
    #
    # identity_document_id — IDs internos de MATIAS API.
    # Verificados con GET /identity-documents (endpoint público):
    #   id:1=CC  id:2=CE  id:3=NIT  id:6=RC  id:7=TI  id:8=TE
    #   id:9=PA/PPN  id:10=DE  id:11=NIT extranjero  id:12=NUIP
    #   id:13=PPT  id:14=PEP  id:15=SC  id:20=CD
    # ⚠️ Bug histórico: el código anterior usaba "3" para CC y "6" para NIT,
    #    pero id:3=NIT y id:6=Registro Civil. Corregido con los IDs reales.
    _TIPO_ID_MATIAS = {
        "CC":   "1",   # Cédula de Ciudadanía
        "CE":   "2",   # Cédula de Extranjería
        "NIT":  "3",   # NIT
        "RC":   "6",   # Registro Civil de Nacimiento
        "TI":   "7",   # Tarjeta de Identidad
        "TE":   "8",   # Tarjeta de Extranjería
        "PA":   "9",   # Pasaporte
        "PPN":  "9",   # Pasaporte (alias)
        "DE":   "10",  # Documento de identificación extranjero
        "NITE": "11",  # NIT de otro país
        "NUIP": "12",  # NUIP
        "PPT":  "13",  # Permiso Protección Temporal
        "PEP":  "14",  # Permiso Especial de Permanencia
        "SC":   "15",  # Salvoconducto
        "CD":   "20",  # Carné Diplomático
    }
    tipo_id_raw     = (venta.get("tipo_id") or "CC").upper().strip()
    identity_doc_id = _TIPO_ID_MATIAS.get(tipo_id_raw, "1")   # fallback → CC

    # ── send_email: 1 solo si hay correo real del cliente ─────────────────────
    # Para Consumidor Final o sin correo, poner email genérico de la empresa
    # emisora y enviar send_email=0 (MATIAS API no intenta enviar ese correo).
    # El PDF llega al grupo de Telegram en ese caso (ver lógica en emitir_factura).
    tiene_correo_real = not _sin_correo_real(venta.get("correo_cliente"))
    email_payload     = (
        venta.get("correo_cliente")
        if tiene_correo_real
        else _EMAIL_PLACEHOLDER
    )

    customer = {
        "country_id":            "45",
        "identity_document_id":  identity_doc_id,
        "type_organization_id":  1   if es_nit else 2,
        "tax_regime_id":         1   if es_nit else 2,
        "tax_level_id":          1   if es_nit else 5,
        "company_name":          (venta.get("cliente_nombre") or "CONSUMIDOR FINAL").upper(),
        "dni":                   venta.get("identificacion_cliente") or "222222222222",
        "mobile":                venta.get("telefono_cliente")       or "3000000000",
        "email":                 email_payload,
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

        # Resolver quantity_units_id desde unidad_medida del ítem.
        # ventas_detalle.unidad_medida se pobla al registrar la venta con el
        # valor del catálogo (Galón, Kg, GRM, MLT, Mts, etc.).
        # Fallback "70" = Unidad si no se reconoce el valor.
        unidad_raw     = (item.get("unidad_medida") or "Unidad").strip()
        qty_units_id   = _UNIDAD_DIAN.get(unidad_raw, _UNIDAD_DIAN.get(unidad_raw.lower(), "70"))

        lines.append({
            "invoiced_quantity":            cantidad,
            "quantity_units_id":            qty_units_id,
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
    # taxable_amount = solo la base gravable (ítems con IVA), no el subtotal total.
    # Régimen simple: todos los productos con IVA están al 19% → un único entry.
    doc_tax_totals = [{
        "tax_id":         "1" if total_iva > 0 else "4",
        "tax_amount":     _fmt(total_iva),
        "taxable_amount": _fmt(subtotal_gravable) if total_iva > 0 else "0.00",
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

    # payment_method_id: 1=contado, 2=crédito (fiado)
    es_fiado           = bool(venta.get("es_fiado") or venta.get("fiado"))
    payment_method_id  = 2 if es_fiado else 1

    return {
        "resolution_number":      MATIAS_RESOLUTION,
        "prefix":                 MATIAS_PREFIX,
        "document_number":        str(num_dian),
        "date":                   str(venta["fecha"])[:10],
        "time":                   ahora.strftime("%H:%M:%S"),
        "type_document_id":       7,   # 7 = Factura de Venta en MATIAS API (ID interno, ≠ código DIAN "01")
        "operation_type_id":      1,
        "notes":                  venta.get("notas") or "Ferretería Punto Rojo",
        "graphic_representation": 1,   # MATIAS API espera entero, no booleano
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
    # asyncio.to_thread evita bloquear el event loop durante el HTTP de login.
    import asyncio
    try:
        token = await asyncio.to_thread(_get_token)
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

    # ── Enviar PDF al grupo de Telegram si el cliente no tiene correo real ────
    correo_real = venta.get("correo_cliente")
    pdf_telegram = False
    if _sin_correo_real(correo_real):
        import asyncio
        asyncio.create_task(
            _enviar_pdf_grupo_telegram(
                cufe,
                numero,
                venta.get("cliente_nombre"),
                venta.get("total"),
            )
        )
        pdf_telegram = True
        logger.info("📤 PDF %s programado para envío a grupo Telegram (sin correo real)", numero)

    return {"ok": True, "cufe": cufe, "numero": numero, "pdf_telegram": pdf_telegram}


async def obtener_pdf(cufe: str) -> bytes:
    """
    Descarga el PDF de una factura desde Matias API usando el CUFE (trackId).
    Prueba múltiples variantes de URL ya que el endpoint varía entre versiones.
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/pdf, application/json"}

    candidatas = [
        ("GET",  f"{MATIAS_API_URL}/documents/pdf/{cufe}"),
        ("GET",  f"{MATIAS_API_URL}/documents/{cufe}/pdf"),
        ("GET",  f"{MATIAS_API_URL}/documents/pdf/{cufe}?regenerate=1"),
        ("POST", f"{MATIAS_API_URL}/documents/pdf/{cufe}"),
    ]

    ultimo_error = "Sin respuesta"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for metodo, url in candidatas:
            try:
                resp = await (client.post(url, headers=headers) if metodo == "POST" else client.get(url, headers=headers))
                content_type = resp.headers.get("content-type", "")
                logger.debug("PDF intento %s %s → HTTP %s | %s", metodo, url, resp.status_code, content_type)

                if resp.status_code == 200 and "pdf" in content_type:
                    logger.info("✅ PDF descargado OK (binario) — %s %s", metodo, url)
                    return resp.content

                if resp.status_code == 200 and "json" in content_type:
                    # MATIAS API devuelve el PDF como base64 en campo 'data'
                    # Ejemplo: {"path":"...","url":"...","data":"JVBERi0x..."}
                    try:
                        import base64
                        json_data = resp.json()
                        b64 = json_data.get("data")
                        if b64:
                            pdf_bytes = base64.b64decode(b64)
                            logger.info("✅ PDF descargado OK (base64 JSON) — %s %s", metodo, url)
                            return pdf_bytes
                        # Si no hay 'data' pero hay 'url', descargamos desde esa URL
                        pdf_url = json_data.get("url")
                        if pdf_url:
                            pdf_resp = await client.get(pdf_url, headers=headers)
                            if pdf_resp.status_code == 200:
                                logger.info("✅ PDF descargado OK (url JSON) — %s", pdf_url)
                                return pdf_resp.content
                        ultimo_error = f"JSON sin 'data' ni 'url': {list(json_data.keys())}"
                    except Exception as e:
                        ultimo_error = f"Error decodificando base64: {e}"
                    continue

                if resp.status_code == 405:
                    ultimo_error = f"405 en {url}"
                    continue

                try:
                    err_data = resp.json()
                    ultimo_error = err_data.get("message") or err_data.get("error") or str(err_data)
                except Exception:
                    ultimo_error = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
            except Exception as e:
                ultimo_error = str(e)
                continue

    raise RuntimeError(f"No se pudo descargar el PDF (probadas {len(candidatas)} URLs). Último error: {ultimo_error}")


# ── GET /status — Estado DIAN de un documento ─────────────────────────────────

async def consultar_estado_dian(numero: str, prefix: str | None = None) -> dict:
    """
    Consulta el estado de validación DIAN de un documento emitido.
    Endpoint: GET /status?number={numero}&prefix={prefix}

    Retorna el JSON de MATIAS API con campos como:
        is_valid, status_description, StatusCode, StatusDescription, etc.
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    params: dict = {"number": numero}
    if prefix:
        params["prefix"] = prefix

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{MATIAS_API_URL}/status",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /status devolvió respuesta no JSON (HTTP {resp.status_code})")

    if resp.status_code not in (200, 201):
        msg = data.get("message") or str(data)
        raise RuntimeError(f"MATIAS API /status ({resp.status_code}): {msg}")

    logger.info("Estado DIAN doc %s: %s", numero, data.get("StatusDescription") or data.get("status_description"))
    return data


# ── GET /documents/last — Último número emitido ───────────────────────────────

async def obtener_ultimo_documento(
    resolution: str | None = None, prefix: str | None = None
) -> dict:
    """
    Obtiene el último número de documento emitido en MATIAS API para sincronizar
    contadores locales y detectar desfases con la DIAN.
    Endpoint: GET /documents/last?resolution={resolution}&prefix={prefix}
    """
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
        raise RuntimeError(f"MATIAS API /documents/last devolvió respuesta no JSON (HTTP {resp.status_code})")

    if resp.status_code not in (200, 201):
        msg = data.get("message") or str(data)
        raise RuntimeError(f"MATIAS API /documents/last ({resp.status_code}): {msg}")

    logger.info("Último documento MATIAS API: %s", data)
    return data


# ── GET /acquirer — Validar adquirente en RUT/DIAN ───────────────────────────

async def consultar_adquirente(
    tipo_id: str, numero_identificacion: str
) -> dict:
    """
    Valida los datos de un cliente en el RUT/DIAN antes de emitir factura.
    Endpoint: GET /acquirer?identificationType={tipo}&identificationNumber={numero}

    tipo_id: código interno MATIAS API (CC=1, NIT=3, etc.) — acepta tanto
             el código string ("CC", "NIT") como el ID numérico ("1", "3").

    Retorna dict con datos del adquirente según DIAN:
        razón social, dirección, municipio, régimen, etc.
    """
    import asyncio
    _TIPO_LOOKUP: dict[str, str] = {
        "CC": "1", "CE": "2", "NIT": "3", "RC": "6", "TI": "7",
        "TE": "8", "PA": "9", "PPN": "9", "DE": "10", "NITE": "11",
        "NUIP": "12", "PPT": "13", "PEP": "14", "SC": "15", "CD": "20",
    }
    tipo_normalizado = _TIPO_LOOKUP.get(tipo_id.upper(), tipo_id)

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
        raise RuntimeError(f"MATIAS API /acquirer devolvió respuesta no JSON (HTTP {resp.status_code})")

    if resp.status_code not in (200, 201):
        msg = data.get("message") or str(data)
        raise RuntimeError(f"MATIAS API /acquirer ({resp.status_code}): {msg}")

    logger.info(
        "Adquirente validado — %s %s: %s",
        tipo_id, numero_identificacion,
        data.get("company_name") or data.get("names") or "OK",
    )
    return data


# ── POST /documents/sendmail/{trackId} — Reenviar correo al cliente ───────────

async def reenviar_correo_factura(track_id: str) -> dict:
    """
    Reenvía el PDF de una factura al correo del cliente registrado en MATIAS API.
    Endpoint: POST /documents/sendmail/{trackId}

    Útil cuando el primer envío falló o el cliente solicita reenvío.
    Retorna dict con confirmación de envío.
    """
    import asyncio
    token = await asyncio.to_thread(_get_token)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{MATIAS_API_URL}/documents/sendmail/{track_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept":        "application/json",
                "Content-Type":  "application/json",
            },
        )

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"MATIAS API /documents/sendmail devolvió respuesta no JSON (HTTP {resp.status_code})")

    if resp.status_code not in (200, 201):
        msg = data.get("message") or str(data)
        raise RuntimeError(f"MATIAS API /documents/sendmail ({resp.status_code}): {msg}")

    logger.info("📧 Correo de factura reenviado — trackId: %s…", track_id[:20])
    return data


# ── POST /notes/credit — Nota Crédito ─────────────────────────────────────────

# Razones de discrepancia DIAN para nota crédito (discrepancy_response_id)
RAZONES_NC = {
    1: "Devolución parcial de los bienes",
    2: "Anulación de factura",
    3: "Rebaja o descuento parcial",
    4: "Ajuste de precio",
    5: "Otro",
}


async def emitir_nota_credito(
    factura_cufe: str,
    factura_numero: str,
    factura_fecha: str,
    razon_id: int,
    venta_id: int,
    lineas_devueltas: list[dict],
) -> dict:
    """
    Emite una nota crédito DIAN para anular/corregir una factura emitida.
    Endpoint: POST /notes/credit

    Args:
        factura_cufe    — CUFE de la factura original
        factura_numero  — Número de la factura original (ej: "LZT5280")
        factura_fecha   — Fecha de la factura original (YYYY-MM-DD)
        razon_id        — ID de razón DIAN (1=devolución, 2=anulación, 3=descuento,
                          4=ajuste precio, 5=otro)
        venta_id        — ID interno de la venta (para trazar en la DB)
        lineas_devueltas — Lista de ítems que se devuelven/corrigen. Mismo formato
                           que ventas_detalle (producto_nombre, cantidad, precio_unitario,
                           total, tiene_iva, porcentaje_iva, unidad_medida).
    """
    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        return {"ok": False, "error": "MATIAS_EMAIL/MATIAS_PASSWORD no configurados"}

    ahora    = datetime.now(COLOMBIA_TZ)
    subtotal = sum(int(d.get("total") or 0) for d in lineas_devueltas)
    subtotal_gravable = sum(
        int(d.get("total") or 0) for d in lineas_devueltas if d.get("tiene_iva")
    )
    total_iva = sum(
        int(int(d.get("total") or 0) * int(d.get("porcentaje_iva") or 0) / 100)
        for d in lineas_devueltas if d.get("tiene_iva")
    )
    total_doc = subtotal + total_iva

    lines = []
    for item in lineas_devueltas:
        precio_u  = _fmt(item.get("precio_unitario") or 0)
        cantidad  = str(float(item.get("cantidad") or 1))
        total_l   = _fmt(item.get("total") or 0)
        tiene_iva = bool(item.get("tiene_iva"))
        pct_iva   = int(item.get("porcentaje_iva") or 0)
        iva_val   = _fmt(int(item.get("total") or 0) * pct_iva / 100) if tiene_iva else "0.00"
        unidad_raw   = (item.get("unidad_medida") or "Unidad").strip()
        qty_units_id = _UNIDAD_DIAN.get(unidad_raw, _UNIDAD_DIAN.get(unidad_raw.lower(), "70"))

        lines.append({
            "invoiced_quantity":            cantidad,
            "quantity_units_id":            qty_units_id,
            "line_extension_amount":        total_l,
            "free_of_charge_indicator":     False,
            "description":                  (item.get("producto_nombre") or "Devolución").upper(),
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

    payload = {
        "type_document_id":       5,   # 5 = Nota Crédito en MATIAS API
        "date":                   ahora.strftime("%Y-%m-%d"),
        "time":                   ahora.strftime("%H:%M:%S"),
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
            "taxable_amount": _fmt(subtotal_gravable) if total_iva > 0 else "0.00",
            "percent":        "19.00" if total_iva > 0 else "0.00",
        }],
        "legal_monetary_totals": {
            "line_extension_amount":  _fmt(subtotal),
            "tax_exclusive_amount":   _fmt(subtotal),
            "tax_inclusive_amount":   _fmt(total_doc),
            "allowance_total_amount": "0.00",
            "charge_total_amount":    "0.00",
            "pre_paid_amount":        "0.00",
            "payable_amount":         _fmt(total_doc),
        },
        "lines": lines,
    }

    import asyncio
    try:
        token = await asyncio.to_thread(_get_token)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    logger.debug("Payload nota crédito venta %s: %s", venta_id, payload)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MATIAS_API_URL}/notes/credit", json=payload, headers=headers)
        data = resp.json()
    except Exception as e:
        logger.error("MATIAS API nota crédito venta %s: %s", venta_id, e)
        return {"ok": False, "error": f"Error de conexión con Matias API: {e}"}

    valido = bool(data.get("success"))
    cufe   = data.get("XmlDocumentKey") or data.get("document_key") or data.get("track_id", "")
    numero = data.get("document_number") or data.get("number") or ""

    if not valido:
        msg    = data.get("message") or ""
        errors = data.get("errors") or {}
        if isinstance(errors, dict) and errors:
            error_detail = " | ".join(f"{k}: {v}" for k, v in errors.items())
            error_msg    = f"{msg} | {error_detail}".strip(" |")
        else:
            error_msg = msg or str(data)
        logger.error("Nota crédito rechazada venta %s: %s", venta_id, error_msg)
        _guardar_nota_db("credito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "error", error_msg)
        return {"ok": False, "error": error_msg}

    _guardar_nota_db("credito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "emitida", None)
    logger.info("✅ Nota crédito %s emitida — CUFE: %s…", numero, cufe[:20] if cufe else "?")
    return {"ok": True, "cufe": cufe, "numero": numero, "tipo": "credito"}


# ── POST /notes/debit — Nota Débito ──────────────────────────────────────────

# Razones DIAN para nota débito (discrepancy_response_id)
RAZONES_ND = {
    1: "Intereses",
    2: "Gastos por cobrar",
    3: "Cambio del valor",
    4: "Otro",
}


async def emitir_nota_debito(
    factura_cufe: str,
    factura_numero: str,
    factura_fecha: str,
    razon_id: int,
    venta_id: int,
    lineas: list[dict],
) -> dict:
    """
    Emite una nota débito DIAN para agregar cargos adicionales a una factura.
    Endpoint: POST /notes/debit

    Args:
        factura_cufe   — CUFE de la factura original
        factura_numero — Número de la factura original (ej: "LZT5280")
        factura_fecha  — Fecha de la factura original (YYYY-MM-DD)
        razon_id       — ID de razón DIAN (1=intereses, 2=gastos, 3=cambio valor, 4=otro)
        venta_id       — ID interno de la venta
        lineas         — Ítems del cargo adicional (mismo formato que ventas_detalle)
    """
    if not MATIAS_EMAIL or not MATIAS_PASSWORD:
        return {"ok": False, "error": "MATIAS_EMAIL/MATIAS_PASSWORD no configurados"}

    ahora    = datetime.now(COLOMBIA_TZ)
    subtotal = sum(int(d.get("total") or 0) for d in lineas)
    subtotal_gravable = sum(int(d.get("total") or 0) for d in lineas if d.get("tiene_iva"))
    total_iva = sum(
        int(int(d.get("total") or 0) * int(d.get("porcentaje_iva") or 0) / 100)
        for d in lineas if d.get("tiene_iva")
    )
    total_doc = subtotal + total_iva

    lines_payload = []
    for item in lineas:
        precio_u  = _fmt(item.get("precio_unitario") or 0)
        cantidad  = str(float(item.get("cantidad") or 1))
        total_l   = _fmt(item.get("total") or 0)
        tiene_iva = bool(item.get("tiene_iva"))
        pct_iva   = int(item.get("porcentaje_iva") or 0)
        iva_val   = _fmt(int(item.get("total") or 0) * pct_iva / 100) if tiene_iva else "0.00"
        unidad_raw   = (item.get("unidad_medida") or "Unidad").strip()
        qty_units_id = _UNIDAD_DIAN.get(unidad_raw, _UNIDAD_DIAN.get(unidad_raw.lower(), "70"))

        lines_payload.append({
            "invoiced_quantity":            cantidad,
            "quantity_units_id":            qty_units_id,
            "line_extension_amount":        total_l,
            "free_of_charge_indicator":     False,
            "description":                  (item.get("producto_nombre") or "Cargo adicional").upper(),
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

    payload = {
        "type_document_id":       4,   # 4 = Nota Débito en MATIAS API
        "date":                   ahora.strftime("%Y-%m-%d"),
        "time":                   ahora.strftime("%H:%M:%S"),
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
            "taxable_amount": _fmt(subtotal_gravable) if total_iva > 0 else "0.00",
            "percent":        "19.00" if total_iva > 0 else "0.00",
        }],
        "legal_monetary_totals": {
            "line_extension_amount":  _fmt(subtotal),
            "tax_exclusive_amount":   _fmt(subtotal),
            "tax_inclusive_amount":   _fmt(total_doc),
            "allowance_total_amount": "0.00",
            "charge_total_amount":    "0.00",
            "pre_paid_amount":        "0.00",
            "payable_amount":         _fmt(total_doc),
        },
        "lines": lines_payload,
    }

    import asyncio
    try:
        token = await asyncio.to_thread(_get_token)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    logger.debug("Payload nota débito venta %s: %s", venta_id, payload)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{MATIAS_API_URL}/notes/debit", json=payload, headers=headers)
        data = resp.json()
    except Exception as e:
        logger.error("MATIAS API nota débito venta %s: %s", venta_id, e)
        return {"ok": False, "error": f"Error de conexión con Matias API: {e}"}

    valido = bool(data.get("success"))
    cufe   = data.get("XmlDocumentKey") or data.get("document_key") or data.get("track_id", "")
    numero = data.get("document_number") or data.get("number") or ""

    if not valido:
        msg    = data.get("message") or ""
        errors = data.get("errors") or {}
        if isinstance(errors, dict) and errors:
            error_detail = " | ".join(f"{k}: {v}" for k, v in errors.items())
            error_msg    = f"{msg} | {error_detail}".strip(" |")
        else:
            error_msg = msg or str(data)
        logger.error("Nota débito rechazada venta %s: %s", venta_id, error_msg)
        _guardar_nota_db("debito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "error", error_msg)
        return {"ok": False, "error": error_msg}

    _guardar_nota_db("debito", venta_id, numero, cufe, factura_cufe, razon_id, total_doc, "emitida", None)
    logger.info("✅ Nota débito %s emitida — CUFE: %s…", numero, cufe[:20] if cufe else "?")
    return {"ok": True, "cufe": cufe, "numero": numero, "tipo": "debito"}


# ── Helpers para persistir notas en DB ───────────────────────────────────────

def _guardar_nota_db(
    tipo: str, venta_id: int, numero: str, cufe: str,
    factura_cufe_ref: str, razon_id: int, total: float,
    estado: str, error_msg: str | None,
) -> None:
    """
    Persiste una nota crédito/débito en facturas_electronicas.
    Reutiliza la misma tabla que las facturas; tipo='nota_credito'|'nota_debito'
    distingue el tipo de documento. factura_cufe_ref apunta a la FE original.
    """
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
