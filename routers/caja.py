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
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends
from pydantic import BaseModel

import config
from memoria import registrar_compra   # complejo: actualiza inventario + kardex
from routers.deps import get_current_user, get_filtro_efectivo

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
def caja(current_user=Depends(get_current_user)):
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
def gastos(
    dias: int = Query(default=7, ge=1, le=90),
    filtro: int | None = Depends(get_filtro_efectivo)
):
    try:
        _require_db()
        ahora        = datetime.now(config.COLOMBIA_TZ)
        fecha_fin    = ahora.strftime("%Y-%m-%d")
        fecha_inicio = (ahora - timedelta(days=dias - 1)).strftime("%Y-%m-%d")

        # Filtrar por usuario_id si aplica
        where_usuario = "AND usuario_id = %s" if filtro is not None else ""
        params = (fecha_inicio, fecha_fin, filtro) if filtro is not None else (fecha_inicio, fecha_fin)

        rows = _db.query_all(
            f"SELECT fecha, hora, concepto, monto, categoria, origen FROM gastos "
            f"WHERE fecha >= %s AND fecha <= %s {where_usuario} ORDER BY fecha DESC, hora DESC",
            params,
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
    incluye_iva:    bool = False
    tarifa_iva:     int  = 0    # 0, 5, 19 — se auto-detecta del catálogo si no se envía


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
            incluye_iva=body.incluye_iva,
            tarifa_iva=body.tarifa_iva,
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
def compras(
    dias: int = Query(default=30, ge=1, le=365),
    filtro: int | None = Depends(get_filtro_efectivo)
):
    try:
        _require_db()
        ahora        = datetime.now(config.COLOMBIA_TZ)
        fecha_fin    = ahora.strftime("%Y-%m-%d")
        fecha_inicio = (ahora - timedelta(days=dias)).strftime("%Y-%m-%d")

        # Filtrar por usuario_id si aplica
        where_usuario = "AND usuario_id = %s" if filtro is not None else ""
        params = (fecha_inicio, fecha_fin, filtro) if filtro is not None else (fecha_inicio, fecha_fin)

        rows = _db.query_all(
            f"SELECT id, fecha::text, hora::text, proveedor, producto_nombre, "
            f"       cantidad, costo_unitario, costo_total, incluye_iva, tarifa_iva, "
            f"       compra_fiscal_id "
            f"FROM compras "
            f"WHERE fecha >= %s AND fecha <= %s {where_usuario} ORDER BY fecha DESC, hora DESC",
            params,
        )

        resultado: list                = []
        por_proveedor: dict[str, float] = defaultdict(float)
        por_producto: dict[str, float]  = defaultdict(float)

        for r in rows:
            prov = r.get("proveedor") or "Sin proveedor"
            prod = r.get("producto_nombre") or ""
            ct   = int(r.get("costo_total") or 0)
            resultado.append({
                "id":               r["id"],
                "fecha":            str(r["fecha"])[:10],
                "hora":             str(r["hora"])[:5] if r.get("hora") else "",
                "proveedor":        prov,
                "producto":         prod,
                "cantidad":         float(r["cantidad"]),
                "costo_unitario":   int(r.get("costo_unitario") or 0),
                "costo_total":      ct,
                "incluye_iva":      bool(r.get("incluye_iva") or False),
                "tarifa_iva":       int(r.get("tarifa_iva") or 0),
                "compra_fiscal_id": r.get("compra_fiscal_id"),
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
    cliente_id:     Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# PUT /compras/{id}  — editar compra normal
# ─────────────────────────────────────────────────────────────────────────────

class EditarCompraBody(BaseModel):
    producto:       Optional[str]              = None
    cantidad:       Optional[Union[float, int]] = None
    costo_unitario: Optional[Union[float, int]] = None
    proveedor:      Optional[str]              = None
    incluye_iva:    Optional[bool]             = None
    tarifa_iva:     Optional[int]              = None


@router.put("/compras/{compra_id}")
def editar_compra(
    compra_id: int,
    body: EditarCompraBody,
    current_user=Depends(get_current_user),
):
    """Edita los campos de una compra existente."""
    try:
        _require_db()
        existente = _db.query_one(
            "SELECT id FROM compras WHERE id = %s", (compra_id,)
        )
        if not existente:
            raise HTTPException(status_code=404, detail="Compra no encontrada")

        sets, params = [], []
        if body.producto is not None:
            sets.append("producto_nombre = %s"); params.append(body.producto.strip())
        if body.cantidad is not None:
            if body.cantidad <= 0:
                raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")
            sets.append("cantidad = %s"); params.append(float(body.cantidad))
        if body.costo_unitario is not None:
            if body.costo_unitario <= 0:
                raise HTTPException(status_code=400, detail="El costo unitario debe ser mayor a 0")
            sets.append("costo_unitario = %s"); params.append(int(body.costo_unitario))
            # Recalcular total si hay costo_unitario
            if body.cantidad is not None:
                sets.append("costo_total = %s")
                params.append(int(body.costo_unitario) * int(body.cantidad))
        if body.proveedor is not None:
            sets.append("proveedor = %s"); params.append(body.proveedor.strip() or None)
        if body.incluye_iva is not None:
            sets.append("incluye_iva = %s"); params.append(body.incluye_iva)
        if body.tarifa_iva is not None:
            sets.append("tarifa_iva = %s"); params.append(body.tarifa_iva)

        if not sets:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar")

        params.append(compra_id)
        _db.execute(
            f"UPDATE compras SET {', '.join(sets)} WHERE id = %s",
            params,
        )
        return {"ok": True, "mensaje": "Compra actualizada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /compras/{id}/to-fiscal  — duplicar compra normal → fiscal
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/compras/{compra_id}/to-fiscal")
def compra_to_fiscal(
    compra_id: int,
    current_user=Depends(get_current_user),
):
    """Crea una entrada en compras_fiscal a partir de una compra normal.
    Si ya existe una entrada fiscal vinculada devuelve el id existente."""
    try:
        _require_db()
        c = _db.query_one(
            "SELECT * FROM compras WHERE id = %s", (compra_id,)
        )
        if not c:
            raise HTTPException(status_code=404, detail="Compra no encontrada")

        # Evitar duplicados: si ya tiene fiscal_id vinculado
        if c.get("compra_fiscal_id"):
            return {
                "ok": True,
                "ya_existia": True,
                "fiscal_id": c["compra_fiscal_id"],
                "mensaje": "Esta compra ya tiene una entrada fiscal vinculada",
            }

        row = _db.query_one(
            """
            INSERT INTO compras_fiscal
                (fecha, hora, proveedor, producto_id, producto_nombre,
                 cantidad, costo_unitario, costo_total,
                 incluye_iva, tarifa_iva, compra_origen_id, usuario_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                c["fecha"], c.get("hora"), c.get("proveedor"),
                c.get("producto_id"), c["producto_nombre"],
                c["cantidad"], c.get("costo_unitario"), c.get("costo_total"),
                bool(c.get("incluye_iva") or False),
                int(c.get("tarifa_iva") or 0),
                compra_id,
                c.get("usuario_id"),
            ),
        )
        fiscal_id = row["id"]

        # Marcar en compras que ya tiene entrada fiscal
        _db.execute(
            "UPDATE compras SET compra_fiscal_id = %s WHERE id = %s",
            (fiscal_id, compra_id),
        )

        return {
            "ok": True,
            "ya_existia": False,
            "fiscal_id": fiscal_id,
            "mensaje": "Compra enviada a Contabilidad Fiscal",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /compras-fiscal
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/compras-fiscal")
def compras_fiscal(
    dias: int = Query(default=30, ge=1, le=365),
    filtro: int | None = Depends(get_filtro_efectivo),
):
    try:
        _require_db()
        ahora        = datetime.now(config.COLOMBIA_TZ)
        fecha_fin    = ahora.strftime("%Y-%m-%d")
        fecha_inicio = (ahora - timedelta(days=dias)).strftime("%Y-%m-%d")

        where_usuario = "AND usuario_id = %s" if filtro is not None else ""
        params = (fecha_inicio, fecha_fin, filtro) if filtro is not None else (fecha_inicio, fecha_fin)

        rows = _db.query_all(
            f"""
            SELECT id, fecha::text, hora::text, proveedor, producto_nombre,
                   cantidad, costo_unitario, costo_total,
                   incluye_iva, tarifa_iva,
                   numero_factura, notas_fiscales, compra_origen_id
            FROM compras_fiscal
            WHERE fecha >= %s AND fecha <= %s {where_usuario}
            ORDER BY fecha DESC, hora DESC
            """,
            params,
        )

        resultado: list                 = []
        por_proveedor: dict[str, float] = defaultdict(float)
        por_producto: dict[str, float]  = defaultdict(float)

        for r in rows:
            prov = r.get("proveedor") or "Sin proveedor"
            prod = r.get("producto_nombre") or ""
            ct   = int(r.get("costo_total") or 0)
            resultado.append({
                "id":               r["id"],
                "fecha":            str(r["fecha"])[:10],
                "hora":             str(r["hora"])[:5] if r.get("hora") else "",
                "proveedor":        prov,
                "producto":         prod,
                "cantidad":         float(r["cantidad"]),
                "costo_unitario":   int(r.get("costo_unitario") or 0),
                "costo_total":      ct,
                "incluye_iva":      bool(r.get("incluye_iva") or False),
                "tarifa_iva":       int(r.get("tarifa_iva") or 0),
                "numero_factura":   r.get("numero_factura") or "",
                "notas_fiscales":   r.get("notas_fiscales") or "",
                "compra_origen_id": r.get("compra_origen_id"),
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
# POST /compras-fiscal  — crear compra fiscal directamente
# ─────────────────────────────────────────────────────────────────────────────

class NuevaCompraFiscalBody(BaseModel):
    producto:        str
    cantidad:        Union[float, int]
    costo_unitario:  Union[float, int]
    proveedor:       str  = ""
    incluye_iva:     bool = False
    tarifa_iva:      int  = 0
    numero_factura:  str  = ""
    notas_fiscales:  str  = ""


@router.post("/compras-fiscal")
def crear_compra_fiscal(
    body: NuevaCompraFiscalBody,
    current_user=Depends(get_current_user),
):
    """Registra una compra directamente en el libro fiscal (sin afectar inventario)."""
    try:
        _require_db()
        if not body.producto.strip():
            raise HTTPException(status_code=400, detail="El producto es obligatorio")
        if body.cantidad <= 0:
            raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")
        if body.costo_unitario <= 0:
            raise HTTPException(status_code=400, detail="El costo unitario debe ser mayor a 0")

        hoy   = _hoy_str()
        hora  = _hora_str()
        total = int(body.cantidad * body.costo_unitario)

        row = _db.query_one(
            """
            INSERT INTO compras_fiscal
                (fecha, hora, proveedor, producto_nombre,
                 cantidad, costo_unitario, costo_total,
                 incluye_iva, tarifa_iva, numero_factura, notas_fiscales)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                hoy, hora,
                body.proveedor.strip() or None,
                body.producto.strip(),
                float(body.cantidad),
                int(body.costo_unitario),
                total,
                body.incluye_iva,
                body.tarifa_iva if body.incluye_iva else 0,
                body.numero_factura.strip() or None,
                body.notas_fiscales.strip() or None,
            ),
        )

        return {
            "ok":      True,
            "id":      row["id"],
            "mensaje": f"Compra fiscal registrada: {body.producto} — ${total:,}".replace(",", "."),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# PUT /compras-fiscal/{id}  — editar compra fiscal
# ─────────────────────────────────────────────────────────────────────────────

class EditarCompraFiscalBody(BaseModel):
    producto:       Optional[str]               = None
    cantidad:       Optional[Union[float, int]]  = None
    costo_unitario: Optional[Union[float, int]]  = None
    proveedor:      Optional[str]               = None
    incluye_iva:    Optional[bool]              = None
    tarifa_iva:     Optional[int]               = None
    numero_factura: Optional[str]               = None
    notas_fiscales: Optional[str]               = None


@router.put("/compras-fiscal/{fiscal_id}")
def editar_compra_fiscal(
    fiscal_id: int,
    body: EditarCompraFiscalBody,
    current_user=Depends(get_current_user),
):
    """Edita los campos de una compra fiscal (incluidos nro. factura y notas)."""
    try:
        _require_db()
        existente = _db.query_one(
            "SELECT id FROM compras_fiscal WHERE id = %s", (fiscal_id,)
        )
        if not existente:
            raise HTTPException(status_code=404, detail="Compra fiscal no encontrada")

        sets, params = [], []
        if body.producto is not None:
            sets.append("producto_nombre = %s"); params.append(body.producto.strip())
        if body.cantidad is not None:
            if body.cantidad <= 0:
                raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0")
            sets.append("cantidad = %s"); params.append(float(body.cantidad))
        if body.costo_unitario is not None:
            if body.costo_unitario <= 0:
                raise HTTPException(status_code=400, detail="El costo unitario debe ser mayor a 0")
            sets.append("costo_unitario = %s"); params.append(int(body.costo_unitario))
            if body.cantidad is not None:
                sets.append("costo_total = %s")
                params.append(int(body.costo_unitario) * int(body.cantidad))
        if body.proveedor is not None:
            sets.append("proveedor = %s"); params.append(body.proveedor.strip() or None)
        if body.incluye_iva is not None:
            sets.append("incluye_iva = %s"); params.append(body.incluye_iva)
        if body.tarifa_iva is not None:
            sets.append("tarifa_iva = %s"); params.append(body.tarifa_iva)
        if body.numero_factura is not None:
            sets.append("numero_factura = %s"); params.append(body.numero_factura.strip() or None)
        if body.notas_fiscales is not None:
            sets.append("notas_fiscales = %s"); params.append(body.notas_fiscales.strip() or None)

        if not sets:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar")

        params.append(fiscal_id)
        _db.execute(
            f"UPDATE compras_fiscal SET {', '.join(sets)} WHERE id = %s",
            params,
        )
        return {"ok": True, "mensaje": "Compra fiscal actualizada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /compras-fiscal/{id}/to-compras  — duplicar fiscal → compra normal
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/compras-fiscal/{fiscal_id}/to-compras")
def fiscal_to_compra(
    fiscal_id: int,
    current_user=Depends(get_current_user),
):
    """Crea una compra normal (con actualización de inventario) a partir de
    una entrada fiscal. Devuelve el id de la compra creada."""
    try:
        _require_db()
        cf = _db.query_one(
            "SELECT * FROM compras_fiscal WHERE id = %s", (fiscal_id,)
        )
        if not cf:
            raise HTTPException(status_code=404, detail="Compra fiscal no encontrada")

        # Si ya hay una compra de origen, devolvemos esa
        if cf.get("compra_origen_id"):
            return {
                "ok": True,
                "ya_existia": True,
                "compra_id": cf["compra_origen_id"],
                "mensaje": "Esta compra fiscal ya está vinculada a una compra de almacén",
            }

        # Insertar en compras como registro operativo (sin tocar inventario ni kárdex)
        # compras_fiscal = contabilidad · compras = control de almacén
        nueva = _db.query_one(
            """
            INSERT INTO compras
                (fecha, hora, proveedor, producto_id, producto_nombre,
                 cantidad, costo_unitario, costo_total,
                 incluye_iva, tarifa_iva)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                cf["fecha"], cf.get("hora"),
                cf.get("proveedor"),
                cf.get("producto_id"),
                cf["producto_nombre"],
                cf["cantidad"],
                cf.get("costo_unitario"),
                cf.get("costo_total"),
                bool(cf.get("incluye_iva") or False),
                int(cf.get("tarifa_iva") or 0),
            ),
        )
        compra_id = nueva["id"] if nueva else None

        # Vincular ambos registros entre sí
        if compra_id:
            _db.execute(
                "UPDATE compras_fiscal SET compra_origen_id = %s WHERE id = %s",
                (compra_id, fiscal_id),
            )
            _db.execute(
                "UPDATE compras SET compra_fiscal_id = %s WHERE id = %s",
                (fiscal_id, compra_id),
            )

        return {
            "ok":         True,
            "ya_existia": False,
            "compra_id":  compra_id,
            "mensaje":    "Compra enviada a Almacén",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
