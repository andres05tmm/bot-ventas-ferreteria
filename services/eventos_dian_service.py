"""
services/eventos_dian_service.py
Gestión de eventos RADIAN/DIAN para facturas electrónicas de proveedores.

Flujo completo:
  1. Factura llega por Gmail → gmail_webhook importa + envía 030 (automático)
  2. Admin revisa en dashboard → Aceptar  = 032 + 033
                               → Reclamar = 031
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
import httpx
import db as _db
from services.facturacion_service import _get_token, MATIAS_API_URL

logger = logging.getLogger("ferrebot.eventos_dian")

EVENTO_ACUSE   = "030"
EVENTO_RECLAMO = "031"
EVENTO_RECIBO  = "032"
EVENTO_ACEPTAR = "033"

_NOTAS = {
    EVENTO_ACUSE:   "Acuse de recibo de la factura electrónica.",
    EVENTO_RECLAMO: "Reclamo de la factura electrónica.",
    EVENTO_RECIBO:  "Recibo del bien y/o prestación del servicio.",
    EVENTO_ACEPTAR: "Aceptación expresa de la factura electrónica.",
}


async def _auth_headers() -> dict:
    import asyncio
    token = await asyncio.to_thread(_get_token)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


async def importar_factura_proveedor(cufe: str) -> dict:
    """POST /events/import-track-id — registra la FE del proveedor en MATIAS."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{MATIAS_API_URL}/events/import-track-id",
                json={"trackId": cufe},
                headers=await _auth_headers(),
            )
        data = resp.json()
        ok   = resp.status_code in (200, 201)
        if ok:
            logger.info("✅ Factura importada MATIAS — CUFE: %s…", cufe[:30])
        else:
            logger.warning("⚠️ Importar factura: %s — CUFE: %s",
                           data.get("message", ""), cufe[:30])
        # No fallar — la DIAN puede devolver error idempotente si ya estaba importada
        return {"ok": True, "data": data}
    except Exception as e:
        logger.error("Error importando CUFE %s: %s", cufe[:30], e)
        return {"ok": False, "error": str(e)}


async def enviar_evento(cufe: str, code: str, notas: str | None = None) -> dict:
    """POST /events/send/{trackId} — envía un evento DIAN."""
    body = {"code": code, "notes": notas or _NOTAS.get(code, "Evento DIAN.")}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{MATIAS_API_URL}/events/send/{cufe}",
                json=body,
                headers=await _auth_headers(),
            )
        data = resp.json()
        ok   = resp.status_code in (200, 201) and bool(data.get("success") or data.get("ok"))
        if ok:
            logger.info("✅ Evento %s enviado — CUFE: %s…", code, cufe[:30])
        else:
            logger.warning("⚠️ Evento %s falló: %s — CUFE: %s",
                           code, data.get("message", ""), cufe[:30])
        return {"ok": ok, "code": code, "data": data,
                "error": None if ok else (data.get("message") or str(data))}
    except Exception as e:
        logger.error("Error evento %s CUFE %s: %s", code, cufe[:30], e)
        return {"ok": False, "code": code, "error": str(e)}


async def procesar_factura_entrante(cufe: str, compra_fiscal_id: int) -> dict:
    """
    Llamado automáticamente desde gmail_webhook al registrar una FE de proveedor.
    Importa + envía acuse de recibo 030.
    """
    resultado = {"cufe": cufe, "importada": False, "evento_030": False, "error": None}

    imp = await importar_factura_proveedor(cufe)
    resultado["importada"] = imp.get("ok", False)

    ev = await enviar_evento(cufe, EVENTO_ACUSE)
    resultado["evento_030"] = ev.get("ok", False)

    ahora = datetime.now(timezone.utc)
    try:
        if ev.get("ok"):
            _db.execute(
                """UPDATE compras_fiscal
                   SET evento_030_at = %s, evento_estado = 'pendiente', evento_error = NULL
                   WHERE id = %s""",
                [ahora, compra_fiscal_id],
            )
        else:
            _db.execute(
                "UPDATE compras_fiscal SET evento_error = %s WHERE id = %s",
                [(ev.get("error") or "Error enviando 030")[:500], compra_fiscal_id],
            )
    except Exception as e:
        logger.error("Error DB evento 030: %s", e)
        resultado["error"] = str(e)

    return resultado


async def aceptar_factura(cufe: str, compra_fiscal_id: int) -> dict:
    """Envía eventos 032 + 033 (Aceptación de la factura)."""
    ahora = datetime.now(timezone.utc)
    ev032 = await enviar_evento(cufe, EVENTO_RECIBO)
    ev033 = await enviar_evento(cufe, EVENTO_ACEPTAR)
    ok    = ev032.get("ok") and ev033.get("ok")
    try:
        if ok:
            _db.execute(
                """UPDATE compras_fiscal
                   SET evento_032_at = %s, evento_033_at = %s,
                       evento_estado = 'aceptada', evento_error = NULL
                   WHERE id = %s""",
                [ahora, ahora, compra_fiscal_id],
            )
        else:
            err = ev032.get("error") or ev033.get("error") or "Error enviando eventos"
            _db.execute(
                "UPDATE compras_fiscal SET evento_error = %s WHERE id = %s",
                [err[:500], compra_fiscal_id],
            )
    except Exception as e:
        logger.error("Error DB aceptación: %s", e)
    return {
        "ok": ok,
        "evento_032": ev032.get("ok"),
        "evento_033": ev033.get("ok"),
        "error": None if ok else (ev032.get("error") or ev033.get("error")),
    }


async def reclamar_factura(cufe: str, compra_fiscal_id: int, motivo: str) -> dict:
    """Envía evento 031 (Reclamo)."""
    ahora = datetime.now(timezone.utc)
    ev    = await enviar_evento(cufe, EVENTO_RECLAMO, notas=motivo)
    try:
        if ev.get("ok"):
            _db.execute(
                """UPDATE compras_fiscal
                   SET evento_031_at = %s, evento_estado = 'reclamada', evento_error = NULL
                   WHERE id = %s""",
                [ahora, compra_fiscal_id],
            )
        else:
            _db.execute(
                "UPDATE compras_fiscal SET evento_error = %s WHERE id = %s",
                [(ev.get("error") or "Error enviando 031")[:500], compra_fiscal_id],
            )
    except Exception as e:
        logger.error("Error DB reclamo: %s", e)
    return {"ok": ev.get("ok"), "error": None if ev.get("ok") else ev.get("error")}


async def reintentar_acuse(cufe: str, compra_fiscal_id: int) -> dict:
    """Reintenta el evento 030 si falló al recibir el correo."""
    await importar_factura_proveedor(cufe)
    ev = await enviar_evento(cufe, EVENTO_ACUSE)
    if ev.get("ok"):
        _db.execute(
            "UPDATE compras_fiscal SET evento_030_at = %s, evento_error = NULL WHERE id = %s",
            [datetime.now(timezone.utc), compra_fiscal_id],
        )
    return ev
