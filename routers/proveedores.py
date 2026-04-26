"""
Router: Proveedores — /proveedores/*
Gestión de cuentas por pagar, facturas y abonos.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel

import config
from routers.shared import _hoy
from routers.deps import get_current_user

logger = logging.getLogger("ferrebot.api")
router = APIRouter()


# ── Cloudinary helper ─────────────────────────────────────────────────────────

async def _subir_cloudinary(file_bytes: bytes, nombre_archivo: str, proveedor: str) -> dict:
    """
    Sube bytes a Cloudinary bajo ferreteria/facturas/<proveedor>/<nombre_archivo>.
    Retorna {"ok": True, "url": "...", "nombre": "..."}
           {"ok": False, "error": "..."}

    Variables de entorno requeridas:
        CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
    """
    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(
            cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            api_key    = os.environ.get("CLOUDINARY_API_KEY",    ""),
            api_secret = os.environ.get("CLOUDINARY_API_SECRET", ""),
        )

        slug      = proveedor.lower().replace(" ", "_")
        public_id = f"ferreteria/facturas/{slug}/{nombre_archivo.rsplit('.', 1)[0]}"

        def _do_upload():
            return cloudinary.uploader.upload(
                io.BytesIO(file_bytes),
                public_id     = public_id,
                overwrite     = True,
                resource_type = "auto",      # acepta pdf e imagen
            )

        result = await asyncio.to_thread(_do_upload)
        url    = result.get("secure_url", "")
        logger.info(f"[Cloudinary] 📎 {nombre_archivo} → {proveedor} → {url}")
        return {"ok": True, "url": url, "nombre": nombre_archivo}

    except ImportError:
        return {"ok": False, "error": "cloudinary no instalado — pip install cloudinary"}
    except Exception as e:
        logger.error(f"[Cloudinary] ❌ Error subiendo {nombre_archivo}: {e}")
        return {"ok": False, "error": str(e)}


# ── Modelos ───────────────────────────────────────────────────────────────────

class FacturaBody(BaseModel):
    proveedor:   str
    descripcion: str
    total:       float
    fecha:       Optional[str] = None
    compras_ids: list[int] = []


class AbonoBody(BaseModel):
    fac_id: str
    monto:  float
    fecha:  Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/proveedores/compras-sin-factura")
def get_compras_sin_factura(
    proveedor: str = "",
    current_user=Depends(get_current_user),
):
    """Compras sin factura_proveedor_id para un proveedor dado (búsqueda parcial). Admin only."""
    import db as _db
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="DB no disponible")
    filtro_sql = "AND proveedor ILIKE %s" if proveedor.strip() else ""
    params: list = []
    if proveedor.strip():
        params.append(f"%{proveedor.strip()}%")
    rows = _db.query_all(
        f"""
        SELECT id, producto_nombre AS producto, cantidad, costo_unitario,
               costo_total, fecha::text AS fecha, proveedor
        FROM compras
        WHERE factura_proveedor_id IS NULL
          {filtro_sql}
        ORDER BY fecha DESC, id DESC
        LIMIT 100
        """,
        params or None,
    )
    return [dict(r) for r in rows]


@router.get("/proveedores/facturas")
def get_facturas(
    solo_pendientes: bool = False,
    current_user=Depends(get_current_user)
):
    """Lista todas las facturas (o solo las pendientes/parciales). Admin only."""
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
def crear_factura(
    body: FacturaBody,
    current_user=Depends(get_current_user)
):
    """Crea una nueva factura de proveedor (sin foto — la foto va por separado). Admin only."""
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
        if body.compras_ids:
            import db as _db
            _db.execute(
                "UPDATE compras SET factura_proveedor_id = %s, estado_fiscal = 'con_factura' WHERE id = ANY(%s)",
                (factura["id"], body.compras_ids),
            )
        return {"ok": True, "factura": factura}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proveedores/facturas/{fac_id}/foto")
async def subir_foto_factura(
    fac_id: str,
    foto: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    """Sube la foto de una factura a Cloudinary y actualiza la URL en PostgreSQL. Admin only."""
    try:
        import db as _db

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

        contenido  = await foto.read()
        resultado  = await _subir_cloudinary(contenido, nombre_archivo, factura["proveedor"])

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
def registrar_abono(
    body: AbonoBody,
    current_user=Depends(get_current_user)
):
    """Registra un abono a una factura (sin foto). Admin only."""
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
async def subir_foto_abono(
    fac_id: str,
    foto: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    """Sube la foto del comprobante de abono y la adjunta al último abono en PostgreSQL. Admin only."""
    try:
        import db as _db

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

        n_abono = _db.query_one(
            "SELECT COUNT(*) AS n FROM facturas_abonos WHERE factura_id = %s",
            (fac_id.upper(),),
        )["n"]
        nombre_archivo = f"{_hoy()}_{fac_id}_abono{n_abono}{ext}"

        contenido = await foto.read()
        resultado = await _subir_cloudinary(contenido, nombre_archivo, factura["proveedor"])

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



# ══════════════════════════════════════════════════════════════════════════════
# EVENTOS DIAN — Facturas electrónicas de proveedores (RADIAN)
# ══════════════════════════════════════════════════════════════════════════════

class EventoBody(BaseModel):
    cufe:             str
    compra_fiscal_id: int


class ReclamoBody(BaseModel):
    cufe:             str
    compra_fiscal_id: int
    motivo:           str


@router.get("/proveedores/facturas-electronicas")
def listar_facturas_electronicas(
    estado: Optional[str] = None,   # 'pendiente' | 'aceptada' | 'reclamada'
    limit:  int           = 50,
    current_user=Depends(get_current_user),
):
    """Lista FE de proveedores recibidas por Gmail con estado de eventos DIAN."""
    import db as _db
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="DB no disponible")

    filtro = "AND evento_estado = %s" if estado else ""
    params = ([estado, limit] if estado else [limit])
    rows = _db.query_all(
        f"""
        SELECT id, fecha::text AS fecha, proveedor, numero_factura, costo_total,
               cufe_proveedor, gmail_message_id,
               evento_030_at::text AS evento_030_at,
               evento_031_at::text AS evento_031_at,
               evento_032_at::text AS evento_032_at,
               evento_033_at::text AS evento_033_at,
               evento_estado, evento_error, created_at::text AS created_at
        FROM compras_fiscal
        WHERE cufe_proveedor IS NOT NULL
          {filtro}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        params,
    )
    return [dict(r) for r in rows]


@router.post("/proveedores/aceptar")
async def aceptar_factura_proveedor(
    body: EventoBody,
    current_user=Depends(get_current_user),
):
    """Acepta una FE de proveedor: envía eventos 032 + 033 a la DIAN."""
    from services.eventos_dian_service import aceptar_factura
    resultado = await aceptar_factura(body.cufe, body.compra_fiscal_id)
    if not resultado["ok"]:
        raise HTTPException(
            status_code=400,
            detail=resultado.get("error") or "Error enviando eventos a DIAN",
        )
    return {"ok": True, "mensaje": "Factura aceptada (eventos 032 + 033 enviados)"}


@router.post("/proveedores/reclamar")
async def reclamar_factura_proveedor(
    body: ReclamoBody,
    current_user=Depends(get_current_user),
):
    """Envía reclamo (evento 031) sobre una FE de proveedor."""
    if not body.motivo.strip():
        raise HTTPException(status_code=400, detail="El motivo del reclamo es obligatorio")
    from services.eventos_dian_service import reclamar_factura
    resultado = await reclamar_factura(body.cufe, body.compra_fiscal_id, body.motivo.strip())
    if not resultado["ok"]:
        raise HTTPException(
            status_code=400,
            detail=resultado.get("error") or "Error enviando reclamo a DIAN",
        )
    return {"ok": True, "mensaje": "Reclamo enviado a la DIAN (evento 031)"}


@router.post("/proveedores/reintentar-030")
async def reintentar_acuse_recibo(
    body: EventoBody,
    current_user=Depends(get_current_user),
):
    """Reintenta el acuse de recibo (030) si falló al recibir el correo."""
    from services.eventos_dian_service import reintentar_acuse
    ev = await reintentar_acuse(body.cufe, body.compra_fiscal_id)
    if not ev.get("ok"):
        raise HTTPException(status_code=400, detail=ev.get("error") or "Error reenviando 030")
    return {"ok": True, "mensaje": "Acuse 030 reenviado correctamente"}

@router.get("/proveedores/resumen")
def resumen_proveedores(current_user=Depends(get_current_user)):
    """Resumen por proveedor: deuda total, facturas pendientes. Admin only."""
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
