"""
Router: Caja — /caja/*, /gastos/*, /compras/*
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Union

import config
from sheets import sheets_leer_ventas_del_dia
from routers.shared import (
    _hoy, _hace_n_dias, _leer_excel_rango, _leer_excel_compras,
    _to_float, _cantidad_a_float, _stock_wayper,
)

logger = logging.getLogger("ferrebot.api")

router = APIRouter()

# ── Caja del día ─────────────────────────────────────────────────────────────
@router.get("/caja")
def caja():
    try:
        # Try Postgres first
        import db as _db
        if _db.DB_DISPONIBLE:
            ahora = datetime.now(config.COLOMBIA_TZ)
            hoy = ahora.strftime("%Y-%m-%d")
            caja_row = _db.query_one("SELECT * FROM caja WHERE fecha = %s", (hoy,))
            if caja_row and not caja_row.get("abierta"):
                return {
                    "abierta":           False,
                    "fecha":             str(caja_row["fecha"]),
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
            if caja_row and caja_row.get("abierta"):
                gastos_rows = _db.query_all(
                    "SELECT concepto, monto, categoria, origen, hora FROM gastos WHERE fecha = %s", (hoy,)
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
                efectivo       = int(caja_row.get("efectivo", 0))
                transferencias = int(caja_row.get("transferencias", 0))
                datafono       = int(caja_row.get("datafono", 0))
                apertura       = int(caja_row.get("monto_apertura", 0))
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
            # DB available but no caja row for today — return closed state
            if caja_row is None:
                return {
                    "abierta":           False,
                    "fecha":             hoy,
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

        # Fallback: JSON logic
        if not os.path.exists(config.MEMORIA_FILE):
            return {"caja": {}, "gastos": []}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)

        caja_data = mem.get("caja_actual", {
            "abierta": False, "fecha": None,
            "monto_apertura": 0, "efectivo": 0,
            "transferencias": 0, "datafono": 0,
        })

        ahora     = datetime.now(config.COLOMBIA_TZ)
        hoy       = ahora.strftime("%Y-%m-%d")
        gastos_hoy = mem.get("gastos", {}).get(hoy, [])

        total_gastos_caja = sum(
            g.get("monto", 0) for g in gastos_hoy
            if g.get("origen") == "caja"
        )
        total_gastos      = sum(g.get("monto", 0) for g in gastos_hoy)

        abierta = caja_data.get("abierta", False)

        # Si la caja está cerrada, mostrar ceros — los valores guardados
        # corresponden al último día activo y no deben mostrarse como "de hoy"
        if not abierta:
            return {
                "abierta":           False,
                "fecha":             caja_data.get("fecha"),
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

        efectivo       = _to_float(caja_data.get("efectivo", 0))
        transferencias = _to_float(caja_data.get("transferencias", 0))
        datafono       = _to_float(caja_data.get("datafono", 0))
        apertura       = _to_float(caja_data.get("monto_apertura", 0))
        total_ventas      = efectivo + transferencias + datafono
        efectivo_esperado = apertura + efectivo - total_gastos_caja

        return {
            "abierta":           True,
            "fecha":             caja_data.get("fecha"),
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Caja: abrir / cerrar desde Dashboard ─────────────────────────────────────

class CajaAbrirBody(BaseModel):
    monto_apertura: Union[float, int] = 0

# ── Caja: abrir / cerrar desde Dashboard ─────────────────────────────────────

class CajaAbrirBody(BaseModel):
    monto_apertura: Union[float, int] = 0

@router.post("/caja/abrir")
def caja_abrir(body: CajaAbrirBody):
    """Abre la caja del día con un monto inicial."""
    try:
        from memoria import cargar_caja, guardar_caja
        caja = cargar_caja()
        if caja.get("abierta"):
            raise HTTPException(status_code=400, detail="La caja ya está abierta")

        hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        caja = {
            "abierta": True,
            "fecha": hoy,
            "monto_apertura": int(body.monto_apertura),
            "efectivo": 0,
            "transferencias": 0,
            "datafono": 0,
        }
        guardar_caja(caja)
        return {"ok": True, "mensaje": f"Caja abierta con ${int(body.monto_apertura):,}", "caja": caja}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/caja/cerrar")
def caja_cerrar():
    """Cierra la caja del día."""
    try:
        from memoria import cargar_caja, guardar_caja, cargar_gastos_hoy, obtener_resumen_caja
        caja = cargar_caja()
        if not caja.get("abierta"):
            raise HTTPException(status_code=400, detail="La caja ya está cerrada")

        resumen = obtener_resumen_caja()
        caja["abierta"] = False
        guardar_caja(caja)
        return {"ok": True, "mensaje": "Caja cerrada", "resumen": resumen}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Gastos: registrar desde Dashboard ────────────────────────────────────────

class NuevoGastoBody(BaseModel):
    concepto:   str
    monto:      Union[float, int]
    categoria:  str = "General"
    origen:     str = "caja"       # "caja" | "externo"

@router.post("/gastos")
def registrar_gasto(body: NuevoGastoBody):
    """Registra un gasto del día."""
    try:
        from memoria import guardar_gasto

        if not body.concepto.strip():
            raise HTTPException(status_code=400, detail="El concepto es obligatorio")
        if body.monto <= 0:
            raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

        hora = datetime.now(config.COLOMBIA_TZ).strftime("%H:%M")
        gasto = {
            "concepto":  body.concepto.strip(),
            "monto":     int(body.monto),
            "categoria": body.categoria.strip() or "General",
            "origen":    body.origen,
            "hora":      hora,
        }
        guardar_gasto(gasto)
        return {"ok": True, "gasto": gasto, "mensaje": f"Gasto registrado: {body.concepto} ${int(body.monto):,}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Compras: registrar desde Dashboard ───────────────────────────────────────

class NuevaCompraBody(BaseModel):
    producto:       str
    cantidad:       Union[float, int]
    costo_unitario: Union[float, int]
    proveedor:      str = ""

@router.post("/compras")
def crear_compra(body: NuevaCompraBody):
    """Registra una compra de mercancía (actualiza inventario + kárdex)."""
    try:
        from memoria import registrar_compra

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


# ── Ventas Rápidas (desde el Dashboard) ──────────────────────────────────────
class VentaRapidaItem(BaseModel):
    nombre:        str
    cantidad:      Union[float, str] = 1
    total:         float
    unidad_medida: str = ""   # si viene vacío se busca en catálogo

class VentaRapidaPayload(BaseModel):
    productos:       list[VentaRapidaItem]
    metodo:          str = "efectivo"
    vendedor:        str = "Dashboard"
    cliente_nombre:  str = ""
    cliente_id:      str = ""

@router.get("/gastos")
def gastos(dias: int = Query(default=7, ge=1, le=90)):
    try:
        # Try Postgres first
        import db as _db
        if _db.DB_DISPONIBLE:
            ahora      = datetime.now(config.COLOMBIA_TZ)
            fecha_fin  = ahora.strftime("%Y-%m-%d")
            fecha_inicio = (ahora - timedelta(days=dias - 1)).strftime("%Y-%m-%d")
            rows = _db.query_all(
                "SELECT fecha, hora, concepto, monto, categoria, origen FROM gastos "
                "WHERE fecha >= %s AND fecha <= %s ORDER BY fecha DESC, hora DESC",
                (fecha_inicio, fecha_fin)
            )
            resultado: list = []
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
            historico_list = []
            for i in range(dias - 1, -1, -1):
                dia = (ahora - timedelta(days=i)).strftime("%Y-%m-%d")
                historico_list.append({"fecha": dia, "total": por_dia.get(dia, 0)})
            return {
                "gastos":        resultado,
                "total":         sum(g["monto"] for g in resultado),
                "por_categoria": dict(por_categoria),
                "historico":     historico_list,
                "dias":          dias,
            }

        # Fallback: JSON logic
        if not os.path.exists(config.MEMORIA_FILE):
            return {"gastos": [], "total": 0, "por_categoria": {}}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)

        todos_gastos = mem.get("gastos", {})
        ahora  = datetime.now(config.COLOMBIA_TZ)
        limite = (ahora - timedelta(days=dias - 1)).strftime("%Y-%m-%d")

        resultado = []
        por_categoria: dict[str, float] = defaultdict(float)
        por_dia: dict[str, float]       = defaultdict(float)

        for fecha, lista in todos_gastos.items():
            if fecha < limite:
                continue
            for g in lista:
                monto = _to_float(g.get("monto", 0))
                cat   = g.get("categoria", "Sin categoría")
                resultado.append({**g, "fecha": fecha, "monto": monto})
                por_categoria[cat]  += monto
                por_dia[fecha]      += monto

        resultado.sort(key=lambda x: (x["fecha"], x.get("hora", "")), reverse=True)

        # Historico por día para gráfica
        historico = []
        for i in range(dias - 1, -1, -1):
            dia = (ahora - timedelta(days=i)).strftime("%Y-%m-%d")
            historico.append({"fecha": dia, "total": por_dia.get(dia, 0)})

        return {
            "gastos":        resultado,
            "total":         sum(g["monto"] for g in resultado),
            "por_categoria": dict(por_categoria),
            "historico":     historico,
            "dias":          dias,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Historial de compras a proveedores ────────────────────────────────────────
@router.get("/compras")
def compras(dias: int = Query(default=30, ge=1, le=365)):
    try:
        if not os.path.exists(config.MEMORIA_FILE):
            return {"compras": [], "total_invertido": 0, "por_proveedor": {}}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)

        historial = mem.get("historial_compras", [])
        ahora  = datetime.now(config.COLOMBIA_TZ)
        limite = (ahora - timedelta(days=dias)).strftime("%Y-%m-%d")

        filtradas      = [c for c in historial if str(c.get("fecha", ""))[:10] >= limite]
        por_proveedor: dict[str, float] = defaultdict(float)
        por_producto:  dict[str, float] = defaultdict(float)

        for c in filtradas:
            prov = c.get("proveedor") or "Sin proveedor"
            por_proveedor[prov] += _to_float(c.get("costo_total", 0))
            por_producto[c.get("producto", "")] += _to_float(c.get("costo_total", 0))

        filtradas.sort(key=lambda x: x.get("fecha", ""), reverse=True)

        return {
            "compras":        filtradas,
            "total_invertido": sum(_to_float(c.get("costo_total", 0)) for c in filtradas),
            "por_proveedor":  dict(por_proveedor),
            "por_producto":   dict(sorted(por_producto.items(), key=lambda x: -x[1])[:20]),
            "dias":           dias,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Top ventas (v2 — por ingresos, frecuencia o categoría) ───────────────────
