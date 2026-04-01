"""
routers/facturacion.py — Facturación Electrónica DIAN vía MATIAS API

Endpoints:
  POST /facturacion/emitir              — emite la FE para una venta registrada
  GET  /facturacion/lista               — lista las últimas facturas emitidas
  GET  /facturacion/pdf/{cufe}          — descarga el PDF desde MATIAS API por CUFE
  GET  /facturacion/ventas-pendientes   — ventas sin FE en una fecha dada (para el dashboard)
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

import db as _db

logger = logging.getLogger("ferrebot.api")
router = APIRouter()


# ── Modelos ───────────────────────────────────────────────────────────────────

class FacturarRequest(BaseModel):
    venta_id: int


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

    fecha_consulta = fecha or str(date.today())

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
            COALESCE(v.hora::text, '')                      AS hora,
            COALESCE(v.vendedor, '')                        AS vendedor
        FROM ventas v
        WHERE v.fecha::date = %s
          AND (v.factura_estado IS NULL OR v.factura_estado != 'emitida')
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
