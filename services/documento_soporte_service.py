"""
services/documento_soporte_service.py
Generación y transmisión del Documento Soporte en Adquisiciones
a No Obligados a Facturar (DS-NO) via MATIAS API.

Proveedor: Andrés Felipe Malo Hernández (CC 1043295412)
Adquirente: Ferretería Punto Rojo F.D. (NIT 1235046119-1)
Endpoint MATIAS: POST /ds/document
"""

from __future__ import annotations

# -- stdlib --
import asyncio
import json
import logging
import os
from datetime import datetime

# -- terceros --
import httpx

# -- propios --
import db as _db
import config
from config import COLOMBIA_TZ, HONORARIOS_VALOR
from services.facturacion_service import MATIAS_API_URL, _get_token

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

# Número inicial del rango DS si la tabla está vacía.
# Ajustar si ya existen documentos previos en el portal MATIAS (ej: DS1-DS4 creados manualmente).
MATIAS_DS_NUM_DESDE = int(os.getenv("MATIAS_DS_NUM_DESDE", "1"))

log = logging.getLogger("ferrebot.documento_soporte")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

# Andrés como proveedor (no obligado a facturar).
# identity_document_id="1" = CC en IDs internos MATIAS (REGLA DE ORO: POST usa IDs MATIAS, no códigos DIAN).
# Datos parametrizados por env (config.py); defaults = Andrés / Punto Rojo.
_PROVEEDOR = {
    "country_id":           config.MATIAS_COUNTRY_ID,
    # FIX DSAJ25a: En endpoint DS, identity_document_id="3" genera schemeName="31"
    # en el XML UBL del AccountingSupplierParty, que es lo que exige la DIAN para DS.
    # Aunque en /invoice "3" = NIT, en /ds/document "3" es el valor correcto para CC.
    # Confirmado por ejemplo oficial MATIAS API y error DSAJ25a en producción.
    "identity_document_id": "3",
    "type_organization_id": 2,                # Persona natural
    "tax_regime_id":        2,                # Régimen simplificado
    "tax_level_id":         5,                # No responsable de IVA
    "company_name":         config.HON_PROV_NOMBRE_DIAN,
    "dni":                  config.HON_PROV_DNI,
    "address":              config.HON_PROV_DIRECCION,
    "city_id":              config.MATIAS_CITY_ID,     # ID interno MATIAS (no DANE)
    "postal_code":          config.MATIAS_POSTAL_CODE,
    "mobile":               config.HON_PROV_MOBILE,    # Requerido por DIAN (DSAJ08a)
    "email":                config.HON_PROV_EMAIL,
}

_DESCRIPCION_SERVICIO = os.getenv(
    "HONORARIOS_DS_DESCRIPCION",
    "SERVICIOS DE DESARROLLO DE SOFTWARE, SOPORTE TECNICO Y MANTENIMIENTO "
    "DEL SISTEMA DE GESTION INTEGRAL PARA FERRETERIA PUNTO ROJO - "
    "CONTRATO PSV-001-2026",
)

_MAX_REINTENTOS = 3

# TipoAmb DIAN: 1=Producción  2=Habilitación/Pruebas
# Controlado por MATIAS_AMBIENTE=pruebas|produccion (default: produccion)
_TIPO_AMB: int = 2 if os.getenv("MATIAS_AMBIENTE", "produccion").lower() == "pruebas" else 1


# ─────────────────────────────────────────────────────────────────────────────
# API PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────

def _siguiente_num_ds() -> int:
    """
    Devuelve el siguiente número de documento DS, garantizando unicidad con lock de tabla.
    Similar a _siguiente_num_dian() en facturacion_service.py.
    Usa MATIAS_DS_NUM_DESDE como piso mínimo.
    """
    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("LOCK TABLE documentos_soporte IN SHARE ROW EXCLUSIVE MODE")
            cur.execute(
                """
                SELECT COALESCE(
                    MAX(CAST(NULLIF(regexp_replace(consecutivo, '[^0-9]', '', 'g'), '') AS INTEGER)),
                    %s - 1
                ) + 1 AS siguiente
                FROM documentos_soporte
                """,
                (MATIAS_DS_NUM_DESDE,),
            )
            siguiente = cur.fetchone()["siguiente"]
        conn.commit()
    return max(siguiente, MATIAS_DS_NUM_DESDE)


async def generar_documento_soporte(
    valor: int | None = None,
    fecha: datetime | None = None,
    cuenta_cobro_id: int | None = None,
) -> dict:
    """
    Genera y transmite a DIAN el DS-NO via MATIAS API.

    Parámetros:
        valor           — monto; si None usa HONORARIOS_VALOR de config
        fecha           — datetime del documento; si None usa now(COLOMBIA_TZ)
        cuenta_cobro_id — consecutivo de cuentas_cobro para vincular (FK)

    Retorna:
        {"ok": True,  "cude": "...", "numero": "..."}
        {"ok": False, "error": "mensaje legible"}
    """
    resolucion = os.environ.get("MATIAS_RESOLUTION_DSNO")
    log.warning("DSNO resolución leída en tiempo de ejecución: MATIAS_RESOLUTION_DSNO=%r", resolucion)

    if not resolucion:
        return {"ok": False, "error": "MATIAS_RESOLUTION_DSNO no configurado en Railway"}

    valor_f = float(valor or HONORARIOS_VALOR)
    ahora   = fecha or datetime.now(COLOMBIA_TZ)

    fecha_str = ahora.strftime("%Y-%m-%d")
    hora_str  = ahora.strftime("%H:%M:%S")

    try:
        num_ds = await asyncio.to_thread(_siguiente_num_ds)
    except Exception as e:
        log.error("No se pudo obtener siguiente número DS: %s", e)
        return {"ok": False, "error": f"Error calculando número DS: {e}"}

    payload = _armar_payload(valor_f, fecha_str, hora_str, resolucion, num_ds)

    try:
        token = await asyncio.to_thread(_get_token)
    except Exception as e:
        log.error("Auth MATIAS API falló para DSNO: %s", e)
        return {"ok": False, "error": f"Auth MATIAS API falló: {e}"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    log.warning("DSNO payload → %s", json.dumps(payload, ensure_ascii=False, default=str))

    data, ultimo_error = {}, ""
    for intento in range(1, _MAX_REINTENTOS + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{MATIAS_API_URL}/ds/document",
                    json=payload,
                    headers=headers,
                )
            data = resp.json()
            log.warning("MATIAS DSNO HTTP %s → %s", resp.status_code, json.dumps(data, ensure_ascii=False, default=str)[:1000])
            break
        except Exception as e:
            ultimo_error = str(e)
            log.warning("DSNO intento %d/%d falló: %s", intento, _MAX_REINTENTOS, e)
            if intento < _MAX_REINTENTOS:
                await asyncio.sleep(2 ** intento)
    else:
        _guardar_en_db(None, fecha_str, valor_f, None, "error_conexion", cuenta_cobro_id)
        return {"ok": False, "error": f"Error de conexión tras {_MAX_REINTENTOS} intentos: {ultimo_error}"}

    # ── Detección de resultado ────────────────────────────────────────────────
    # La respuesta de /ds/document tiene estructura diferente a /invoice:
    #   - No tiene campo "success"
    #   - Tiene "XmlDocumentKey" (CUDE) si llegó a DIAN
    #   - Tiene "response.IsValid" con "true"/"false"
    #   - Errores MATIAS (validación) → data["errors"] (dict)
    #   - Errores DIAN → data["response"]["ErrorMessage"]["string"] (lista)
    cude   = (data.get("XmlDocumentKey") or data.get("document_key") or "").strip()
    numero = str(num_ds)

    # Error de validación MATIAS (no llegó a DIAN)
    if data.get("errors"):
        errors    = data["errors"]
        msg       = data.get("message") or "Error de validación MATIAS"
        error_msg = f"{msg} | " + " | ".join(f"{k}: {v}" for k, v in errors.items()) if isinstance(errors, dict) else str(errors)
        log.error("MATIAS rechazó DSNO (validación): %s", error_msg)
        _guardar_en_db(None, fecha_str, valor_f, None, "rechazado_matias", cuenta_cobro_id)
        return {"ok": False, "error": error_msg}

    # Llegó a DIAN: revisar IsValid
    dian_resp  = data.get("response") or {}
    is_valid   = str(dian_resp.get("IsValid") or "false").lower() == "true"
    dian_msgs  = (dian_resp.get("ErrorMessage") or {}).get("string") or []
    if isinstance(dian_msgs, str):
        dian_msgs = [dian_msgs]

    if not is_valid and dian_msgs:
        # Hay rechazos DIAN — loguear pero guardar con CUDE para auditoría
        rechazos = [m for m in dian_msgs if "Rechazo" in m]
        notifs   = [m for m in dian_msgs if "Notificación" in m]
        log.warning("DSNO rechazado por DIAN (%d rechazos, %d notif): %s",
                    len(rechazos), len(notifs), "; ".join(dian_msgs))
        _guardar_en_db(numero, fecha_str, valor_f, cude or None, "rechazado_dian", cuenta_cobro_id)
        error_msg = " | ".join(rechazos) or " | ".join(dian_msgs)
        return {"ok": False, "error": error_msg, "cude": cude, "numero": numero}

    # Notificaciones sin rechazo = aceptado
    if dian_msgs:
        log.info("DSNO aceptado con notificaciones DIAN: %s", "; ".join(dian_msgs))

    _guardar_en_db(numero, fecha_str, valor_f, cude or None, "transmitido", cuenta_cobro_id)
    log.info("✅ DSNO DS%s transmitido — CUDE: %s…", numero, cude[:20] if cude else "?")

    # ── Descargar PDF del DS desde MATIAS API ────────────────────────────────
    pdf_bytes: bytes | None = None
    if cude:
        try:
            from services.facturacion_service import obtener_pdf
            await asyncio.sleep(2)          # dar tiempo a MATIAS para generar el PDF
            pdf_bytes = await obtener_pdf(cude)
            log.info("✅ PDF del DS%s descargado: %s bytes", numero, len(pdf_bytes))
        except Exception as e:
            log.warning("No se pudo descargar PDF del DS%s: %s", numero, e)

    return {"ok": True, "cude": cude, "numero": numero, "pdf_bytes": pdf_bytes}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _armar_payload(
    valor: float, fecha_str: str, hora_str: str,
    resolucion: str, num_ds: int,
) -> dict:
    """
    Construye el JSON para POST /ds/document de MATIAS API.

    Cambios respecto a versión anterior:
    - document_number: OBLIGATORIO (causaba 'Error de validación de datos' si se omitía)
    - Tipos corregidos: invoiced_quantity, quantity_units_id, base_quantity → int/float, no strings
    - legal_monetary_totals: campos completos (allowance, charge, pre_paid agregados)
    - tax_totals: valores numéricos (0.0) — confirmado funcionando con prueba directa a API
    """
    año_mes        = fecha_str[:7]        # "YYYY-MM"
    inicio_periodo = f"{año_mes}-01"      # primer día del mes → period de servicio

    valor_f = round(float(valor), 2)

    return {
        "resolution_number":      resolucion,
        # document_number: requerido por MATIAS API — consecutivo del DS
        "document_number":        str(num_ds),
        # prefix: omitido — MATIAS lo toma de la resolución en su portal.
        # Enviarlo causaba error de resolución no encontrada.
        "date":                   fecha_str,
        "time":                   hora_str,
        # type_document_id=11 → Documento Soporte residente colombiano (CC/CE)
        # type_document_id=5  → No residente / extranjero
        "type_document_id":       11,
        # operation_type_id=9 → DS en adquisiciones a no obligados a facturar
        "operation_type_id":      9,
        "currency_id":            272,
        "notes":                  (
            f"Contrato PSV-001-2026 - Honorarios mensuales "
            f"{fecha_str[5:7]}/{fecha_str[:4]}"
        ),
        "graphic_representation": 1,
        "send_email":             0,
        # En /ds/document el proveedor no obligado va en "customer"
        "customer":               _PROVEEDOR,
        # tax_totals: DS no lleva IVA → percent=0, tax_amount=0
        # taxable_amount = valor total (DSAU04 exige que coincida con suma de líneas)
        "tax_totals": [{
            "tax_id":         "1",
            "tax_amount":     0.0,
            "taxable_amount": valor_f,
            "percent":        0.0,
        }],
        # legal_monetary_totals completo (campos faltantes causaban validación fallida)
        "legal_monetary_totals": {
            "line_extension_amount":  valor_f,
            "tax_exclusive_amount":   valor_f,
            "tax_inclusive_amount":   valor_f,
            "allowance_total_amount": 0.0,
            "charge_total_amount":    0.0,
            "pre_paid_amount":        0.0,
            "payable_amount":         valor_f,
        },
        "payments": [{
            "payment_method_id": 1,    # contado
            "means_payment_id":  42,   # transferencia bancaria
            "value_paid":        valor_f,
        }],
        "lines": [{
            # Tipos numéricos — confirmado con prueba directa (strings daban error)
            "invoiced_quantity":            1,
            # quantity_units_id=1093 correcto para DS
            # (70 es para FE estándar y causaría DSFC03 en DS)
            "quantity_units_id":            1093,
            "line_extension_amount":        valor_f,
            "free_of_charge_indicator":     False,
            "description":                  _DESCRIPCION_SERVICIO,
            "code":                         "SERV-001",
            "type_item_identifications_id": "4",
            "reference_price_id":           "1",
            "price_amount":                 valor_f,
            "base_quantity":                1,
            # invoice_period obligatorio en DS (DSFC01 si se omite)
            "invoice_period": {
                "start_date":       inicio_periodo,
                "description_code": 1,
            },
            "tax_totals": [{
                "tax_id":         "1",
                "tax_amount":     0.0,
                "taxable_amount": valor_f,
                "percent":        0.0,
            }],
        }],
    }


def _guardar_en_db(
    consecutivo: str | None,
    fecha: str,
    valor: float,
    cude: str | None,
    estado_dian: str,
    cuenta_cobro_id: int | None,
) -> None:
    # Verificar que la FK exista antes de usarla para evitar violación de constraint.
    # Si la CC fue borrada y regenerada, el consecutivo pasado puede no existir.
    fk_valida: int | None = None
    if cuenta_cobro_id is not None:
        row = _db.query_one(
            "SELECT id FROM cuentas_cobro WHERE consecutivo = %s",
            [cuenta_cobro_id],
        )
        fk_valida = row["id"] if row else None

    try:
        _db.execute(
            """
            INSERT INTO documentos_soporte
                (consecutivo, fecha, valor, cude, estado_dian, cuenta_cobro_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [consecutivo, fecha, valor, cude, estado_dian, fk_valida],
        )
    except Exception as e:
        log.warning("No se pudo guardar DSNO en DB: %s", e)
