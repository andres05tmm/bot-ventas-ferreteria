"""
services/facturacion_service.py
Integración con MATIAS API v2 para facturación electrónica DIAN.
URL base: https://api-v2.matias-api.com/api/ubl2.1
Docs:     https://docs.matias-api.com/docs/intro/
"""
import os
import logging
import httpx
from datetime import datetime

import db as _db
from config import COLOMBIA_TZ

logger = logging.getLogger("ferrebot.facturacion")

# ── Configuración desde variables de entorno (Railway) ────────────────────────
MATIAS_API_URL    = os.getenv("MATIAS_API_URL",    "https://api-v2.matias-api.com/api/ubl2.1")
MATIAS_API_TOKEN  = os.getenv("MATIAS_API_TOKEN")
MATIAS_RESOLUTION = os.getenv("MATIAS_RESOLUTION")  # Ej: "18764074347312"
MATIAS_PREFIX     = os.getenv("MATIAS_PREFIX", "LZT")
MATIAS_NUM_DESDE  = int(os.getenv("MATIAS_NUM_DESDE", "5280"))  # Inicio del rango DIAN asignado

_MEDIOS_PAGO = {
    "efectivo":      10,
    "transferencia": 42,
    "tarjeta":       48,
    "nequi":         42,
    "daviplata":     42,
}


def _siguiente_num_dian(cur) -> int:
    """
    Calcula el próximo número DIAN respetando el rango asignado en la resolución.
    Usa el MAX del número real guardado en la tabla; si no hay ninguno, arranca
    desde MATIAS_NUM_DESDE (variable de entorno, por defecto 5280).
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
        (MATIAS_NUM_DESDE,)
    )
    siguiente = cur.fetchone()["siguiente"]
    # Garantizar que nunca baje del mínimo del rango asignado
    return max(siguiente, MATIAS_NUM_DESDE)


def _fmt(valor) -> str:
    """Número → string con 2 decimales como exige MATIAS API."""
    return f"{float(valor or 0):.2f}"


def _armar_payload(venta: dict, detalle: list[dict], num_dian: int) -> dict:
    """
    Construye el JSON de factura según MATIAS API UBL 2.1.

    CORRECCIONES vs versión anterior:
      ✅ legal_monetary_totals  — ahora incluido (era el error #1)
      ✅ tax_totals a nivel doc  — ahora incluido (error #2)
      ✅ type_document_id = 7   — factura electrónica de venta (código DIAN/MATIAS)
      ✅ operation_type_id = 1  — estándar
      ✅ graphic_representation / send_email como booleanos (eran enteros)
      ✅ Todos los montos con 2 decimales como strings
    """
    ahora    = datetime.now(COLOMBIA_TZ)
    es_nit   = (venta.get("tipo_id") or "").upper() == "NIT"
    medio_id = _MEDIOS_PAGO.get(
        (venta.get("metodo_pago") or "efectivo").lower(), 10
    )

    # ── Totales consolidados ──────────────────────────────────────────────────
    subtotal  = sum(int(d.get("total") or 0) for d in detalle)
    total_iva = sum(
        int(int(d.get("total") or 0) * int(d.get("porcentaje_iva") or 0) / 100)
        for d in detalle if d.get("tiene_iva")
    )
    total_doc = subtotal + total_iva

    # ── Comprador ─────────────────────────────────────────────────────────────
    customer = {
        "country_id":            "45",
        "city_id":               str(venta.get("municipio_dian") or 149),
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

    # ── Líneas ────────────────────────────────────────────────────────────────
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

    # ── Tax totals consolidados (nivel documento) ─────────────────────────────
    if total_iva > 0:
        doc_tax_totals = [{
            "tax_id":         "1",
            "tax_amount":     _fmt(total_iva),
            "taxable_amount": _fmt(subtotal),
            "percent":        "19.00",
        }]
    else:
        doc_tax_totals = [{
            "tax_id":         "4",
            "tax_amount":     "0.00",
            "taxable_amount": "0.00",
            "percent":        "0.00",
        }]

    # ── legal_monetary_totals  ←── CAMPO OBLIGATORIO QUE ANTES FALTABA ───────
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
        "type_document_id":       7,     # 7 = Factura electrónica de venta (DIAN/MATIAS)
        "operation_type_id":      1,     # 1 = Estándar
        "graphic_representation": True,  # booleano
        "send_email":             True,  # booleano
        "customer":               customer,
        "tax_totals":             doc_tax_totals,          # ← nivel raíz
        "legal_monetary_totals":  legal_monetary_totals,   # ← REQUERIDO
        "payments": [{
            "payment_method_id": 1,
            "means_payment_id":  medio_id,
            "value_paid":        _fmt(total_doc),
        }],
        "lines": lines,
    }


async def emitir_factura(venta_id: int) -> dict:
    """
    Emite la factura electrónica DIAN para una venta registrada en PostgreSQL.
    Retorna: {"ok": bool, "cufe": str, "numero": str, "error": str}
    """
    if not MATIAS_API_TOKEN:
        return {"ok": False, "error": "MATIAS_API_TOKEN no configurado en Railway"}
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
            detalle = cur.fetchall()
            num_dian = _siguiente_num_dian(cur)

    payload = _armar_payload(dict(venta), [dict(d) for d in detalle], num_dian)

    headers = {
        "Authorization": f"Bearer {MATIAS_API_TOKEN}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    logger.debug(f"Payload MATIAS API venta {venta_id}: {payload}")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{MATIAS_API_URL}/invoice",
                json=payload,
                headers=headers,
            )
        data = resp.json()
    except Exception as e:
        logger.error(f"MATIAS API conexión fallida venta {venta_id}: {e}")
        return {"ok": False, "error": f"Error de conexión con MATIAS API: {e}"}

    logger.debug(f"Respuesta MATIAS API venta {venta_id} (HTTP {resp.status_code}): {data}")

    # MATIAS API devuelve 'success' y 'XmlDocumentKey' (no 'is_valid' ni 'document_key')
    valido = bool(data.get("success"))
    cufe   = data.get("XmlDocumentKey") or data.get("document_key", "")
    numero = f"{MATIAS_PREFIX}{num_dian}"

    if not valido:
        # Extraer mensaje: primero message, luego errors (dict o lista)
        msg     = data.get("message") or ""
        errors  = data.get("errors") or {}
        if isinstance(errors, dict) and errors:
            error_detail = " | ".join(f"{k}: {v}" for k, v in errors.items())
            error_msg = f"{msg} | {error_detail}".strip(" |")
        elif errors:
            error_msg = f"{msg} | {errors}".strip(" |")
        else:
            error_msg = msg or str(data)

        logger.error(f"MATIAS API rechazó factura venta {venta_id}: {error_msg}")

        try:
            with _db._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO facturas_electronicas "
                        "(venta_id, numero, cliente_nombre, total, estado, error_msg) "
                        "VALUES (%s, %s, %s, %s, 'error', %s)",
                        (
                            venta_id,
                            f"ERR-{num_dian}",
                            venta.get("cliente_nombre"),
                            venta.get("total"),
                            error_msg[:500],
                        ),
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

    logger.info(f"✅ Factura {numero} emitida — CUFE: {cufe[:20]}...")
    return {"ok": True, "cufe": cufe, "numero": numero}
