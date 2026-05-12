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
from config import COLOMBIA_TZ, HONORARIOS_VALOR
from services.facturacion_service import MATIAS_API_URL, MATIAS_RESOLUTION, _get_token

log = logging.getLogger("ferrebot.documento_soporte")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

# Andrés como proveedor (no obligado a facturar).
# identity_document_id="1" = CC en IDs internos MATIAS (REGLA DE ORO: POST usa IDs MATIAS, no códigos DIAN).
_PROVEEDOR = {
    "country_id":           "45",
    "identity_document_id": "1",              # CC → ID interno MATIAS (código DIAN 13 no aplica en POST)
    "type_organization_id": 2,                # Persona natural
    "tax_regime_id":        2,                # Régimen simplificado
    "tax_level_id":         5,                # No responsable de IVA
    "company_name":         "MALO HERNANDEZ ANDRES FELIPE",
    "dni":                  "1043295412",
    "address":              "CON EL REFUGIO BL 12 AP 2A",
    "city_id":              "149",            # Cartagena — ID interno MATIAS
    "city_name":            "Cartagena",
}

_DESCRIPCION_SERVICIO = (
    "SERVICIOS DE DESARROLLO DE SOFTWARE, SOPORTE TECNICO Y MANTENIMIENTO "
    "DEL SISTEMA DE GESTION INTEGRAL PARA FERRETERIA PUNTO ROJO - "
    "CONTRATO PSV-001-2026"
)

_MAX_REINTENTOS = 3

# TipoAmb DIAN: 1=Producción  2=Habilitación/Pruebas
# Controlado por MATIAS_AMBIENTE=pruebas|produccion (default: produccion)
_TIPO_AMB: int = 2 if os.getenv("MATIAS_AMBIENTE", "produccion").lower() == "pruebas" else 1


# ─────────────────────────────────────────────────────────────────────────────
# API PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────

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
    if not MATIAS_RESOLUTION:
        return {"ok": False, "error": "MATIAS_RESOLUTION no configurado en Railway"}

    valor_f = float(valor or HONORARIOS_VALOR)
    ahora   = fecha or datetime.now(COLOMBIA_TZ)

    fecha_str = ahora.strftime("%Y-%m-%d")
    hora_str  = ahora.strftime("%H:%M:%S")

    payload = _armar_payload(valor_f, fecha_str, hora_str)

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

    valido = bool(data.get("success"))
    cude   = (data.get("XmlDocumentKey") or data.get("document_key") or "").strip()
    numero = str(data.get("document_number") or data.get("number") or "")

    if not valido:
        msg    = data.get("message") or ""
        errors = data.get("errors") or {}
        if isinstance(errors, dict) and errors:
            error_msg = f"{msg} | " + " | ".join(f"{k}: {v}" for k, v in errors.items())
        else:
            error_msg = msg or str(data)[:300]
        log.error("MATIAS rechazó DSNO: %s", error_msg)
        _guardar_en_db(numero or None, fecha_str, valor_f, None, "rechazado", cuenta_cobro_id)
        return {"ok": False, "error": error_msg}

    _guardar_en_db(numero or "DS-001", fecha_str, valor_f, cude or None, "transmitido", cuenta_cobro_id)
    log.info("✅ DSNO transmitido — CUDE: %s…", cude[:20] if cude else "?")
    return {"ok": True, "cude": cude, "numero": numero}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _armar_payload(valor: float, fecha_str: str, hora_str: str) -> dict:
    return {
        "resolution_number":      MATIAS_RESOLUTION,
        "date":                   fecha_str,
        "time":                   hora_str,
        # El emisor ante DIAN es la ferretería (credenciales MATIAS); el supplier es Andrés.
        "type_document_id":       5,      # 5 = Documento Soporte (DS-NO) en MATIAS
        "type_environment_id":    _TIPO_AMB,  # 1=Producción  2=Pruebas/Habilitación
        "currency_id":            272,     # COP
        "notes":                  "Contrato PSV-001-2026 — Honorarios mensuales",
        "graphic_representation": 1,
        "send_email":             0,
        "supplier":               _PROVEEDOR,
        "tax_totals": [{
            "tax_id":         "1",
            "tax_amount":     0.0,
            "taxable_amount": valor,
            "percent":        0.0,    # No responsable de IVA
        }],
        "legal_monetary_totals": {
            "line_extension_amount":  valor,
            "tax_exclusive_amount":   valor,
            "tax_inclusive_amount":   valor,
            "allowance_total_amount": 0.0,
            "charge_total_amount":    0.0,
            "pre_paid_amount":        0.0,
            "payable_amount":         valor,
        },
        "payments": [{
            "payment_method_id": 1,   # contado
            "means_payment_id":  42,  # transferencia bancaria
            "value_paid":        valor,
        }],
        "lines": [{
            "invoiced_quantity":            1.0,
            "quantity_units_id":            70,   # Unidad
            "line_extension_amount":        valor,
            "free_of_charge_indicator":     False,
            "description":                  _DESCRIPCION_SERVICIO,
            "code":                         "SERV-001",
            "type_item_identifications_id": "4",
            "reference_price_id":           "1",
            "price_amount":                 valor,
            "base_quantity":                1.0,
            "tax_totals": [{
                "tax_id":         "1",
                "tax_amount":     0.0,
                "taxable_amount": valor,
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
            "SELECT consecutivo FROM cuentas_cobro WHERE consecutivo = %s",
            [cuenta_cobro_id],
        )
        fk_valida = row["consecutivo"] if row else None

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
