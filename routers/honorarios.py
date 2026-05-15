"""
routers/honorarios.py — API de Cuentas de Cobro

Endpoints:
  GET  /honorarios/lista           — historial de cuentas generadas
  GET  /honorarios/pdf/{nro}       — descarga el PDF del consecutivo N
  POST /honorarios/generar         — genera manualmente desde el dashboard (admin)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from routers.deps import get_current_user

log    = logging.getLogger("ferrebot.api.honorarios")
router = APIRouter()


@router.get("/honorarios/lista")
async def listar(
    limit: int = 20,
    current_user=Depends(get_current_user),
):
    """Lista las últimas N cuentas de cobro."""
    from services.honorarios_service import listar_cuentas
    return listar_cuentas(limit=limit)


@router.get("/honorarios/pdf/{consecutivo}")
async def descargar_pdf(
    consecutivo: int,
    current_user=Depends(get_current_user),
):
    """Descarga el PDF de una Cuenta de Cobro por su consecutivo."""
    from services.honorarios_service import obtener_pdf
    pdf_bytes = obtener_pdf(consecutivo)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF no encontrado")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CC-{consecutivo:03d}.pdf"'},
    )


@router.post("/honorarios/generar")
async def generar_manual(current_user=Depends(get_current_user)):
    """
    Genera la Cuenta de Cobro del mes actual desde el dashboard.
    Solo disponible para admin.
    """
    if current_user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")
    from services.honorarios_service import generar_cuenta_cobro
    resultado = await generar_cuenta_cobro(bot=None)
    resultado.pop("pdf_bytes", None)  # no serializar bytes en JSON
    return resultado
