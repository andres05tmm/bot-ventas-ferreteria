"""
Router: Proveedores — /proveedores/*
Gestión de cuentas por pagar, facturas y abonos.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from routers.shared import _hoy

logger = logging.getLogger("ferrebot.api")
router = APIRouter()


# ── Modelos ───────────────────────────────────────────────────────────────────

class FacturaBody(BaseModel):
    proveedor:   str
    descripcion: str
    total:       float
    fecha:       Optional[str] = None


class AbonoBody(BaseModel):
    fac_id: str
    monto:  float
    fecha:  Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/proveedores/facturas")
def get_facturas(solo_pendientes: bool = False):
    """Lista todas las facturas (o solo las pendientes/parciales)."""
    try:
        from memoria import listar_facturas
        facturas = listar_facturas(solo_pendientes=solo_pendientes)

        # KPIs agregados
        total_deuda    = sum(f["pendiente"] for f in facturas if f["estado"] != "pagada")
        total_pagado   = sum(f["pagado"]    for f in facturas)
        n_pendientes   = sum(1 for f in facturas if f["estado"] == "pendiente")
        n_parciales    = sum(1 for f in facturas if f["estado"] == "parcial")

        return {
            "facturas":       facturas,
            "total_deuda":    total_deuda,
            "total_pagado":   total_pagado,
            "n_pendientes":   n_pendientes,
            "n_parciales":    n_parciales,
            "total_facturas": len(facturas),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proveedores/facturas")
def crear_factura(body: FacturaBody):
    """Crea una nueva factura de proveedor (sin foto — la foto va por separado)."""
    try:
        from memoria import registrar_factura_proveedor
        if not body.proveedor.strip():
            raise HTTPException(status_code=400, detail="El proveedor es obligatorio")
        if body.total <= 0:
            raise HTTPException(status_code=400, detail="El total debe ser mayor a 0")

        factura = registrar_factura_proveedor(
            proveedor   = body.proveedor,
            descripcion = body.descripcion,
            total       = body.total,
            fecha       = body.fecha,
        )
        return {"ok": True, "factura": factura}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proveedores/facturas/{fac_id}/foto")
async def subir_foto_factura(fac_id: str, foto: UploadFile = File(...)):
    """Sube la foto de una factura a Cloudinary y actualiza la URL en PostgreSQL."""
    try:
        import db as _db
        from drive import subir_foto_factura as _subir

        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        factura = _db.query_one(
            "SELECT id, proveedor, fecha::text AS fecha FROM facturas_proveedores WHERE id = %s",
            (fac_id.upper(),),
        )
        if not factura:
            raise HTTPException(status_code=404, detail=f"Factura {fac_id} no encontrada")

        ext = ".jpg"
        if foto.content_type == "image/png":
            ext = ".png"
        elif foto.content_type == "application/pdf":
            ext = ".pdf"

        fecha_factura  = factura.get("fecha") or _hoy()
        nombre_archivo = f"{fecha_factura}_{fac_id}{ext}"

        contenido = await foto.read()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(contenido)
            ruta_tmp = tmp.name

        resultado = _subir(ruta_tmp, nombre_archivo, factura["proveedor"])
        try:
            os.unlink(ruta_tmp)
        except Exception:
            pass

        if not resultado["ok"]:
            raise HTTPException(status_code=500, detail=resultado.get("error", "Error subiendo foto"))

        updated = _db.execute(
            "UPDATE facturas_proveedores SET foto_url=%s, foto_nombre=%s WHERE id=%s",
            (resultado["url"], nombre_archivo, fac_id.upper()),
        )
        if updated == 0:
            raise HTTPException(status_code=500, detail="No se pudo actualizar la foto en la base de datos")

        return {"ok": True, "url": resultado["url"], "nombre": nombre_archivo}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proveedores/abonos")
def registrar_abono(body: AbonoBody):
    """Registra un abono a una factura (sin foto)."""
    try:
        from memoria import registrar_abono_factura, listar_facturas
        if body.monto <= 0:
            raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

        # FIX: validar que el abono no supere el saldo pendiente
        facturas = listar_facturas()
        factura  = next((f for f in facturas if f["id"].upper() == body.fac_id.upper()), None)
        if not factura:
            raise HTTPException(status_code=404, detail=f"Factura {body.fac_id} no encontrada")
        if factura["estado"] == "pagada":
            raise HTTPException(status_code=400, detail="La factura ya está completamente pagada")
        pendiente = round(factura["pendiente"], 2)
        if body.monto > pendiente:
            raise HTTPException(
                status_code=400,
                detail=f"El abono ({body.monto:,.0f}) supera el saldo pendiente ({pendiente:,.0f}). "
                       f"Si deseas liquidar la factura, ingresa exactamente {pendiente:,.0f}."
            )

        result = registrar_abono_factura(
            fac_id = body.fac_id,
            monto  = body.monto,
            fecha  = body.fecha,
        )
        if not result["ok"]:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proveedores/abonos/{fac_id}/foto")
async def subir_foto_abono(fac_id: str, foto: UploadFile = File(...)):
    """Sube la foto del comprobante de abono y la adjunta al último abono en PostgreSQL."""
    try:
        import db as _db
        from drive import subir_foto_factura as _subir

        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        factura = _db.query_one(
            "SELECT id, proveedor FROM facturas_proveedores WHERE id = %s",
            (fac_id.upper(),),
        )
        if not factura:
            raise HTTPException(status_code=404, detail=f"Factura {fac_id} no encontrada")

        ultimo_abono = _db.query_one(
            "SELECT id FROM facturas_abonos WHERE factura_id = %s ORDER BY created_at DESC LIMIT 1",
            (fac_id.upper(),),
        )
        if not ultimo_abono:
            raise HTTPException(status_code=400, detail="Esta factura no tiene abonos registrados")

        ext = ".jpg"
        if foto.content_type == "image/png":
            ext = ".png"
        elif foto.content_type == "application/pdf":
            ext = ".pdf"

        n_abono        = _db.query_one(
            "SELECT COUNT(*) AS n FROM facturas_abonos WHERE factura_id = %s",
            (fac_id.upper(),),
        )["n"]
        hoy            = _hoy()
        nombre_archivo = f"{hoy}_{fac_id}_abono{n_abono}{ext}"

        contenido = await foto.read()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(contenido)
            ruta_tmp = tmp.name

        resultado = _subir(ruta_tmp, nombre_archivo, factura["proveedor"])
        try:
            os.unlink(ruta_tmp)
        except Exception:
            pass

        if not resultado["ok"]:
            raise HTTPException(status_code=500, detail=resultado.get("error", "Error subiendo foto"))

        updated = _db.execute(
            "UPDATE facturas_abonos SET foto_url=%s, foto_nombre=%s WHERE id=%s",
            (resultado["url"], nombre_archivo, ultimo_abono["id"]),
        )
        if updated == 0:
            raise HTTPException(status_code=500, detail="No se pudo actualizar la foto del abono")

        return {"ok": True, "url": resultado["url"], "nombre": nombre_archivo}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proveedores/resumen")
def resumen_proveedores():
    """Resumen por proveedor: deuda total, facturas pendientes."""
    try:
        from memoria import listar_facturas
        from collections import defaultdict

        facturas = listar_facturas()
        por_proveedor: dict = defaultdict(lambda: {
            "deuda": 0.0, "pagado": 0.0, "n_facturas": 0,
            "n_pendientes": 0, "ultima_factura": ""
        })

        for f in facturas:
            p = f["proveedor"]
            por_proveedor[p]["n_facturas"]  += 1
            por_proveedor[p]["pagado"]      += f["pagado"]
            if f["estado"] != "pagada":
                por_proveedor[p]["deuda"]       += f["pendiente"]
                por_proveedor[p]["n_pendientes"] += 1
            if f["fecha"] > por_proveedor[p]["ultima_factura"]:
                por_proveedor[p]["ultima_factura"] = f["fecha"]

        return {
            "por_proveedor": dict(por_proveedor),
            "total_deuda":   sum(v["deuda"] for v in por_proveedor.values()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
