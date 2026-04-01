"""
Router: Caja — /caja/*, /gastos/*, /compras/*

MIGRACIÓN PG-ONLY:
  - Eliminado: from sheets import sheets_leer_ventas_del_dia
  - Eliminado: lectura memoria.json (todos los fallbacks JSON)
  - Eliminado: from routers.shared import _leer_excel_*, _to_float, etc.
  - caja_abrir / caja_cerrar / registrar_gasto → INSERT/UPDATE directos a PG
  - GET /caja, /gastos, /compras → PG únicamente, lanza 503 si DB no disponible
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, Union

import db as _db
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

import config
from memoria import registrar_compra   # complejo: actualiza inventario + kardex

logger = logging.getLogger("ferrebot.api")

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _require_db():
    """Lanza 503 si la BD no está disponible."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


def _hoy_str() -> str:
    return datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")


def _hora_str() -> str:
    return datetime.now(config.COLOMBIA_TZ).strftime("%H:%M")


# ─────────────────────────────────────────────────────────────────────────────
# GET /caja
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/caja")
def caja():
    try:
        _require_db()
        hoy = _hoy_str()
        caja_row = _db.query_one("SELECT * FROM caja WHERE fecha = %s", (hoy,))

        # Caja no creada hoy o cerrada
        if not caja_row or not caja_row.get("abierta"):
            return {
                "abierta":           False,
                "fecha":             str(caja_row["fecha"]) if caja_row else hoy,
                "monto_apertura":    0,
                "efectivo":          0,
                "transferencias":    0,
                "datafono":          0,
                "total_ventas":      0,
                "total_gastos_caja": 0,
                "total_gastos":      0,
                "efectivo_esperado": 0,
                "gastos":            [],
            }

        gastos_rows = _db.query_all(
            "SELECT concepto, monto, categoria, origen, hora "
            "FROM gastos WHERE fecha = %s",
            (hoy,)
        )
        gastos_hoy = [{
            "concepto":  g["concepto"],
            "monto":     int(g["monto"]),
            "categoria": g.get("categoria") or "General",
            "origen":    g.get("origen") or "caja",
            "hora":      str(g["hora"])[:5] if g.get("hora") else "",
        } for g in gastos_rows]

        total_gastos_caja = sum(g["monto"] for g in gastos_hoy if g.get("origen") == "caja")
        total_gastos      = sum(g["monto"] for g in gastos_hoy)
        efectivo          = int(caja_row.get("efectivo", 0))
        transferencias    = int(caja_row.get("transferencias", 0))
        datafono          = int(caja_row.get("datafono", 0))
        apertura          = int(caja_row.get("monto_apertura", 0))
        total_ventas      = efectivo + transferencias + datafono
        efectivo_esperado = apertura + efectivo - total_gastos_caja

        return {
            "abierta":           True,
            "fecha":             str(caja_row["fecha"]),
            "monto_apertura":    apertura,
            "efectivo":          efectivo,
            "transferencias":    transferencias,
            "datafono":          datafono,
            "total_ventas":      total_ventas,
            "total_gastos_caja": total_gastos_caja,
            "total_gastos":      total_gastos,
            "efectivo_esperado": efectivo_esperado,
            "gastos":            gastos_hoy,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /caja/abrir
# ─────────────────────────────────────────────────────────────────────────────

class CajaAbrirBody(BaseModel):
    monto_apertura: Union[float, int] = 0


@router.post("/caja/abrir")
def caja_abrir(body: CajaAbrirBody):
    """Abre la caja del día con un monto inicial."""
    try:
        _require_db()
        hoy      = _hoy_str()
        caja_row = _db.query_one("SELECT abierta FROM caja WHERE fecha = %s", (hoy,))

        if caja_row and caja_row.get("abierta"):
            raise HTTPException(status_code=400, detail="La caja ya está abierta")

        _db.execute(
            """INSERT INTO caja (fecha, abierta, monto_apertura, efectivo, transferencias, datafono)
               VALUES (%s, TRUE, %s, 0, 0, 0)
               ON CONFLICT (fecha) DO UPDATE
                 SET abierta        = TRUE,
                     monto_apertura = EXCLUDED.monto_apertura,
                     efectivo       = 0,
                     transferencias = 0,
                     datafono       = 0,
                     cerrada_at     = NULL""",
            (hoy, int(body.monto_apertura)),
        )

        caja_abierta = {
            "abierta":        True,
            "fecha":          hoy,
            "monto_apertura": int(body.monto_apertura),
            "efectivo":       0,
            "transferencias": 0,
            "datafono":       0,
        }
        return {
            "ok":      True,
            "mensaje": f"Caja abierta con ${int(body.monto_apertura):,}".replace(",", "."),
            "caja":    caja_abierta,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /caja/cerrar
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/caja/cerrar")
def caja_cerrar():
    """Cierra la caja del día y retorna el resumen."""
    try:
        _require_db()
        hoy      = _hoy_str()
        caja_row = _db.query_one("SELECT * FROM caja WHERE fecha = %s", (hoy,))

        if not caja_row or not caja_row.get("abierta"):
            raise HTTPException(status_code=400, detail="La caja ya está cerrada")

        _db.execute(
            "UPDATE caja SET abierta = FALSE, cerrada_at = NOW() WHERE fecha = %s",
            (hoy,),
        )

        # Resumen inline (sin depender de memoria.obtener_resumen_caja)
        ventas_row = _db.query_one(
            "SELECT COALESCE(SUM(total), 0) AS total, COUNT(*) AS num_ventas "
            "FROM ventas WHERE fecha = %s",
            (hoy,),
        )
        gastos_rows       = _db.query_all(
            "SELECT monto, origen FROM gastos WHERE fecha = %s", (hoy,)
        )
        total_gastos_caja = sum(int(g["monto"]) for g in gastos_rows if g.get("origen") == "caja")
        efectivo          = int(caja_row.get("efectivo", 0))
        transferencias    = int(caja_row.get("transferencias", 0))
        datafono          = int(caja_row.get("datafono", 0))
        apertura          = int(caja_row.get("monto_apertura", 0))
        total_ventas_pg   = int(ventas_row["total"]) if ventas_row else 0
        num_ventas        = int(ventas_row["num_ventas"]) if ventas_row else 0
        efectivo_esperado = apertura + efectivo - total_gastos_caja

        resumen = (
            f"RESUMEN DE CAJA\n"
            f"Apertura: ${apertura:,.0f}\n"
            f"Ventas efectivo: ${efectivo:,.0f}\n"
            f"Transferencias: ${transferencias:,.0f}\n"
            f"Datafono: ${datafono:,.0f}\n"
            f"Total ventas hoy ({num_ventas}): ${total_ventas_pg:,.0f}\n"
            f"Gastos de caja: ${total_gastos_caja:,.0f}\n"
            f"Efectivo esperado en caja: ${efectivo_esperado:,.0f}"
        ).replace(",", ".")

        return {"ok": True, "mensaje": "Caja cerrada", "resumen": resumen}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /gastos
# ─────────────────────────────────────────────────────────────────────────────

class NuevoGastoBody(BaseModel):
    concepto:  str
    monto:     Union[float, int]
    categoria: str = "General"
    origen:    str = "caja"   # "caja" | "externo"


@router.post("/gastos")
def registrar_gasto(body: NuevoGastoBody):
    """Registra un gasto del día directamente en PostgreSQL."""
    try:
        _require_db()

        if not body.concepto.strip():
            raise HTTPException(status_code=400, detail="El concepto es obligatorio")
        if body.monto <= 0:
            raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

        hoy  = _hoy_str()
        hora = _hora_str()

        _db.execute(
            """INSERT INTO gastos (fecha, hora, concepto, monto, categoria, origen, usuario_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (hoy, hora, body.concepto.strip(), int(body.monto),
             body.categoria.strip() or "General", body.origen, None),
        )

        gasto = {
            "concepto":  body.concepto.strip(),
            "monto":     int(body.monto),
            "categoria": body.categoria.strip() or "General",
            "origen":    body.origen,
            "hora":      hora,
        }
        return {
            "ok":      True,
            "gasto":   gasto,
            "mensaje": f"Gasto registrado: {body.concepto} ${int(body.monto):,}".replace(",", "."),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /gastos
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/gastos")
def gastos(dias: int = Query(default=7, ge=1, le=90)):
    try:
        _require_db()
        ahora        = datetime.now(config.COLOMBIA_TZ)
        fecha_fin    = ahora.strftime("%Y-%m-%d")
        fecha_inicio = (ahora - timedelta(days=dias - 1)).strftime("%Y-%m-%d")

        rows = _db.query_all(
            "SELECT fecha, hora, concepto, monto, categoria, origen FROM gastos "
            "WHERE fecha >= %s AND fecha <= %s ORDER BY fecha DESC, hora DESC",
            (fecha_inicio, fecha_fin),
        )

        resultado: list             = []
        por_categoria: dict[str, float] = defaultdict(float)
        por_dia: dict[str, float]       = defaultdict(float)

        for r in rows:
            m         = int(r["monto"])
            cat       = r.get("categoria") or "Sin categoria"
            fecha_str = str(r["fecha"])
            resultado.append({
                "concepto":  r["concepto"],
                "monto":     m,
                "categoria": cat,
                "origen":    r.get("origen") or "caja",
                "hora":      str(r["hora"])[:5] if r.get("hora") else "",
                "fecha":     fecha_str,
            })
            por_categoria[cat] += m
            por_dia[fecha_str] += m

        historico_list = [
            {"fecha": (ahora - timedelta(days=i)).strftime("%Y-%m-%d"),
             "total": por_dia.get((ahora - timedelta(days=i)).strftime("%Y-%m-%d"), 0)}
            for i in range(dias - 1, -1, -1)
        ]

        return {
            "gastos":        resultado,
            "total":         sum(g["monto"] for g in resultado),
            "por_categoria": dict(por_categoria),
            "historico":     historico_list,
            "dias":          dias,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /compras
# ─────────────────────────────────────────────────────────────────────────────

class NuevaCompraBody(BaseModel):
    producto:       str
    cantidad:       Union[float, int]
    costo_unitario: Union[float, int]
    proveedor:      str = ""


@router.post("/compras")
def crear_compra(body: NuevaCompraBody):
    """Registra una compra de mercancía (actualiza inventario + kárdex)."""
    try:
        if not body.producto.strip():
            raise HTTPException(status_code=400, detail="El producto es obligatorio")
        if body.cantidad <= 0:
            raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")
        if body.costo_unitario <= 0:
            raise HTTPException(status_code=400, detail="El costo unitario debe ser mayor a 0")

        ok, mensaje, datos_excel = registrar_compra(
            nombre_producto=body.producto.strip(),
            cantidad=float(body.cantidad),
            costo_unitario=float(body.costo_unitario),
            proveedor=body.proveedor.strip() or None,
        )

        if not ok:
            raise HTTPException(status_code=400, detail=mensaje)

        return {"ok": True, "mensaje": mensaje, "datos": datos_excel}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /compras
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/compras")
def compras(dias: int = Query(default=30, ge=1, le=365)):
    try:
        _require_db()
        ahora        = datetime.now(config.COLOMBIA_TZ)
        fecha_fin    = ahora.strftime("%Y-%m-%d")
        fecha_inicio = (ahora - timedelta(days=dias)).strftime("%Y-%m-%d")

        rows = _db.query_all(
            "SELECT fecha::text, hora::text, proveedor, producto_nombre, "
            "       cantidad, costo_unitario, costo_total "
            "FROM compras "
            "WHERE fecha >= %s AND fecha <= %s ORDER BY fecha DESC, hora DESC",
            (fecha_inicio, fecha_fin),
        )

        resultado: list                = []
        por_proveedor: dict[str, float] = defaultdict(float)
        por_producto: dict[str, float]  = defaultdict(float)

        for r in rows:
            prov = r.get("proveedor") or "Sin proveedor"
            prod = r.get("producto_nombre") or ""
            ct   = int(r.get("costo_total") or 0)
            resultado.append({
                "fecha":          str(r["fecha"])[:10],
                "hora":           str(r["hora"])[:5] if r.get("hora") else "",
                "proveedor":      prov,
                "producto":       prod,
                "cantidad":       float(r["cantidad"]),
                "costo_unitario": int(r.get("costo_unitario") or 0),
                "costo_total":    ct,
            })
            por_proveedor[prov] += ct
            por_producto[prod]  += ct

        return {
            "compras":         resultado,
            "total_invertido": sum(c["costo_total"] for c in resultado),
            "por_proveedor":   dict(por_proveedor),
            "por_producto":    dict(sorted(por_producto.items(), key=lambda x: -x[1])[:20]),
            "dias":            dias,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Modelos Ventas Rápidas (usados desde ventas.py vía este router)
# ─────────────────────────────────────────────────────────────────────────────

class VentaRapidaItem(BaseModel):
    nombre:        str
    cantidad:      Union[float, str] = 1
    total:         float
    unidad_medida: str = ""


class VentaRapidaPayload(BaseModel):
    productos:      list[VentaRapidaItem]
    metodo:         str = "efectivo"
    vendedor:       str = "Dashboard"
    cliente_nombre: str = ""
    cliente_id:     str = ""
