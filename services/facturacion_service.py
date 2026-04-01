"""
services/facturacion_service.py
Integración con MATIAS API v3 para facturación electrónica DIAN.
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
MATIAS_API_TOKEN  = os.getenv("MATIAS_API_TOKEN")   # PAT de app.matias-api.com
MATIAS_RESOLUTION = os.getenv("MATIAS_RESOLUTION")  # Número Formato 1876 DIAN
MATIAS_PREFIX     = os.getenv("MATIAS_PREFIX", "LZT")

# means_payment_id según medio de pago
_MEDIOS_PAGO = {
    "efectivo":      10,
    "transferencia": 42,
    "tarjeta":       48,
    "nequi":         42,
    "daviplata":     42,
}


def _siguiente_num_dian(cur) -> int:
    """
    Consecutivo propio de facturas DIAN.
    Completamente independiente del consecutivo de ventas — garantiza
    numeración secuencial sin huecos como exige la DIAN.
    """
    cur.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 AS siguiente FROM facturas_electronicas"
    )
    return cur.fetchone()["siguiente"]


def _armar_payload(venta: dict, detalle: list[dict], num_dian: int) -> dict:
    """
    Construye el JSON de factura según la estructura real de MATIAS API
    confirmada en https://docs.matias-api.com/docs/jsons-billing/invoice/
    """
    ahora    = datetime.now(COLOMBIA_TZ)
    es_nit   = (venta.get("tipo_id") or "").upper() == "NIT"
    medio_id = _MEDIOS_PAGO.get(
        (venta.get("metodo_pago") or "efectivo").lower(), 10
    )
    total_v = int(venta.get("total") or 0)

    # ── Datos del comprador ───────────────────────────────────────────────────
    customer = {
        "country_id":            "45",   # Colombia
        "city_id":               str(venta.get("municipio_dian") or 149),  # 149=Cartagena
        "identity_document_id":  "6" if es_nit else "3",   # 6=NIT, 3=CC
        "type_organization_id":  1   if es_nit else 2,     # 1=Jurídica, 2=Natural
        "tax_regime_id":         1   if es_nit else 2,     # 1=Resp.IVA, 2=No resp.
        "tax_level_id":          1   if es_nit else 5,     # 1=Responsable, 5=No resp.
        "company_name":          (venta.get("cliente_nombre") or "CONSUMIDOR FINAL").upper(),
        "dni":                   venta.get("identificacion_cliente") or "222222222222",
        "mobile":                venta.get("telefono_cliente")       or "0000000000",
        "email":                 venta.get("correo_cliente")         or "sinfactura@ferreteriapuntorojo.com",
        "address":               venta.get("direccion_cliente")      or "Cartagena",
    }

    # ── Líneas de factura ─────────────────────────────────────────────────────
    lines = []
    for item in detalle:
        precio_u  = str(int(item.get("precio_unitario") or 0))
        cantidad  = str(float(item.get("cantidad") or 1))
        total_l   = str(int(item.get("total") or 0))
        tiene_iva = bool(item.get("tiene_iva"))
        pct_iva   = int(item.get("porcentaje_iva") or 0)
        iva_val   = str(int(int(total_l) * pct_iva / 100)) if tiene_iva else "0"

        lines.append({
            "invoiced_quantity":            cantidad,
            "quantity_units_id":            "70",       # 70 = Unidad (tabla DIAN)
            "line_extension_amount":        total_l,
            "free_of_charge_indicator":     False,
            "description":                  (item.get("producto_nombre") or "Producto").upper(),
            "code":                         str(item.get("producto_id") or "SC"),
            "type_item_identifications_id": "4",
            "reference_price_id":           "1",
            "price_amount":                 precio_u,
            "base_quantity":                cantidad,
            "tax_totals": [{
                "tax_id":        "1" if tiene_iva else "4",  # 1=IVA, 4=Excluido
                "tax_amount":    iva_val,
                "taxable_amount": total_l if tiene_iva else "0",
                "percent":       str(pct_iva),
            }],
        })

    return {
        "resolution_number":      MATIAS_RESOLUTION,
        "prefix":                 MATIAS_PREFIX,
        "document_number":        str(num_dian),
        "date":                   str(venta["fecha"])[:10],
        "time":                   ahora.strftime("%H:%M:%S"),
        "type_document_id":       7,   # 7 = Factura electrónica de venta
        "operation_type_id":      1,   # 1 = Estándar
        "graphic_representation": 0,
        "send_email":             1,   # MATIAS envía el PDF al email del cliente
        "customer":               customer,
        "payments": [{
            "payment_method_id": 1,          # 1 = Contado
            "means_payment_id":  medio_id,
            "value_paid":        str(total_v),
        }],
        "lines": lines,
    }


async def emitir_factura(venta_id: int) -> dict:
    """
    Emite la factura electrónica DIAN para una venta ya registrada en PostgreSQL.
    Retorna: {"ok": bool, "cufe": str, "numero": str, "error": str}
    """
    if not MATIAS_API_TOKEN:
        return {"ok": False, "error": "MATIAS_API_TOKEN no configurado en Railway"}
    if not MATIAS_RESOLUTION:
        return {"ok": False, "error": "MATIAS_RESOLUTION no configurado en Railway"}

    # ── 1. Leer venta + detalle + calcular consecutivo DIAN ──────────────────
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

            # Evitar duplicados
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

    # ── 2. Llamar a MATIAS API ────────────────────────────────────────────────
    headers = {
        "Authorization": f"Bearer {MATIAS_API_TOKEN}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
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

    # ── 3. Verificar respuesta ────────────────────────────────────────────────
    cufe   = data.get("document_key", "")
    numero = data.get("document_number", f"{MATIAS_PREFIX}{num_dian}")
    valido = bool(data.get("is_valid")) or bool(cufe)

    if not valido:
        error_msg = str(data.get("message") or data.get("errors") or data)
        logger.error(f"MATIAS API rechazó factura venta {venta_id}: {error_msg}")
        # Guardar intento fallido para auditoría
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

    # ── 4. Guardar en PostgreSQL ──────────────────────────────────────────────
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
            """, (
                venta_id,
                numero,
                cufe,
                venta.get("cliente_nombre"),
                venta.get("total"),
            ))
        conn.commit()

    logger.info(f"✅ Factura {numero} emitida — CUFE: {cufe[:20]}...")
    return {"ok": True, "cufe": cufe, "numero": numero}
