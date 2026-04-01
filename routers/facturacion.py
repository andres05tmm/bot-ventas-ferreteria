"""
routers/facturacion.py — Facturación Electrónica DIAN vía MATIAS API

Endpoints:
  POST /facturacion/emitir        — emite la FE para una venta registrada
  GET  /facturacion/lista         — lista las últimas facturas emitidas
  GET  /facturacion/pdf/{cufe}    — descarga el PDF desde MATIAS API por CUFE
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
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
    """
    token    = os.getenv("MATIAS_API_TOKEN")
    url_base = os.getenv("MATIAS_API_URL", "https://api-v2.matias-api.com/api/ubl2.1")

    if not token:
        raise HTTPException(status_code=503, detail="MATIAS_API_TOKEN no configurado")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{url_base}/pdf/{cufe}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error contactando MATIAS API: {e}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail="No se pudo obtener el PDF desde MATIAS API",
        )

    return Response(content=resp.content, media_type="application/pdf")
