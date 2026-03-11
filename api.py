"""
FerreBot Dashboard API — FastAPI
Expone datos de ventas (Google Sheets + Excel) y catálogo (memoria.json).
Corre en el mismo entorno que el bot; reutiliza config.py y sheets.py.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

import openpyxl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import config
from sheets import sheets_leer_ventas_del_dia

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FerreBot Dashboard API",
    description="API de ventas y catálogo para Ferretería Punto Rojo",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # restringe a tu dominio en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helpers de fecha ──────────────────────────────────────────────────────────
def _hoy() -> str:
    return datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")


def _hace_n_dias(n: int) -> datetime:
    return datetime.now(config.COLOMBIA_TZ) - timedelta(days=n)


# ── Helper: leer Excel histórico ──────────────────────────────────────────────
def _leer_excel_rango(dias: int | None = None, mes_actual: bool = False) -> list[dict]:
    """
    Lee filas del Excel (ventas.xlsx) para los últimos `dias` días
    o para todo el mes actual si mes_actual=True.
    Retorna lista de dicts con las mismas claves que sheets_leer_ventas_del_dia().
    """
    if not os.path.exists(config.EXCEL_FILE):
        return []

    try:
        wb = openpyxl.load_workbook(config.EXCEL_FILE, read_only=True, data_only=True)
    except Exception:
        return []

    ahora = datetime.now(config.COLOMBIA_TZ)
    # Hojas a revisar: mes actual y anterior (por si el rango cruza meses)
    hojas_candidatas = [
        f"{config.MESES[ahora.month]} {ahora.year}",
    ]
    if ahora.month > 1:
        hojas_candidatas.append(f"{config.MESES[ahora.month - 1]} {ahora.year}")
    else:
        hojas_candidatas.append(f"{config.MESES[12]} {ahora.year - 1}")

    # Límite inferior de fecha
    if dias is not None:
        limite = (_hace_n_dias(dias)).strftime("%Y-%m-%d")
    else:
        limite = None

    resultado = []
    for nombre_hoja in hojas_candidatas:
        if nombre_hoja not in wb.sheetnames:
            continue
        ws = wb[nombre_hoja]

        # Detectar columnas desde la fila de encabezados (fila 3)
        cols: dict[str, int] = {}
        for col in range(1, ws.max_column + 1):
            val = ws.cell(row=config.EXCEL_FILA_HEADERS, column=col).value
            if val:
                cols[str(val).lower().strip()] = col

        def _col(*claves) -> int | None:
            for k in claves:
                if k in cols:
                    return cols[k]
            return None

        c_fecha    = _col("fecha")
        c_hora     = _col("hora")
        c_producto = _col("producto")
        c_cantidad = _col("cantidad")
        c_precio   = _col("valor unitario", "precio unitario", "precio")
        c_total    = _col("total")
        c_alias    = _col("alias")
        c_vendedor = _col("vendedor")
        c_metodo   = _col("metodo de pago", "metodo pago", "método pago")
        c_num      = _col("#", "consecutivo", "num", "consecutivo de venta")

        for fila in ws.iter_rows(min_row=config.EXCEL_FILA_DATOS, values_only=True):
            if not any(fila):
                continue

            fecha_raw = fila[c_fecha - 1] if c_fecha else None
            if fecha_raw is None:
                continue

            # Normalizar fecha a string YYYY-MM-DD
            if isinstance(fecha_raw, datetime):
                fecha_str = fecha_raw.strftime("%Y-%m-%d")
            else:
                fecha_str = str(fecha_raw)[:10]

            # Filtro de rango
            if limite and fecha_str < limite:
                continue
            if mes_actual and not fecha_str.startswith(f"{ahora.year}-{ahora.month:02d}"):
                continue

            def _v(col_idx):
                if col_idx is None:
                    return ""
                v = fila[col_idx - 1]
                return v if v is not None else ""

            try:
                total = float(str(_v(c_total)).replace(",", ".") or 0)
            except (ValueError, TypeError):
                total = 0.0

            try:
                precio_unit = float(str(_v(c_precio)).replace(",", ".") or 0)
            except (ValueError, TypeError):
                precio_unit = 0.0

            resultado.append({
                "num":             _v(c_num),
                "fecha":           fecha_str,
                "hora":            str(_v(c_hora)),
                "id_cliente":      "CF",
                "cliente":         "Consumidor Final",
                "codigo_producto": "",
                "producto":        str(_v(c_producto)),
                "cantidad":        str(_v(c_cantidad)),
                "precio_unitario": precio_unit,
                "total":           total,
                "alias":           str(_v(c_alias)),
                "vendedor":        str(_v(c_vendedor)),
                "metodo":          str(_v(c_metodo)),
            })

    wb.close()
    return resultado


def _to_float(val) -> float:
    try:
        return float(str(val).replace(",", ".") or 0)
    except (ValueError, TypeError):
        return 0.0


def _cantidad_a_float(val) -> float:
    """Convierte cantidad (puede ser fracción '1 y 1/2' o decimal) a float."""
    if val is None:
        return 0.0
    s = str(val).strip()
    if not s:
        return 0.0
    # Ya es número
    try:
        return float(s)
    except ValueError:
        pass
    # Fracción simple: "1/2", "1/4", "3/4"
    if "/" in s and " " not in s:
        parts = s.split("/")
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return 0.0
    # "N y P/Q" → N + P/Q
    if " y " in s:
        partes = s.split(" y ")
        try:
            entero = float(partes[0])
            frac_parts = partes[1].split("/")
            frac = float(frac_parts[0]) / float(frac_parts[1])
            return entero + frac
        except (ValueError, IndexError, ZeroDivisionError):
            return 0.0
    return 0.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/ventas/hoy")
def ventas_hoy():
    """Ventas de hoy desde Google Sheets."""
    try:
        ventas = sheets_leer_ventas_del_dia()
        hoy = _hoy()
        # Filtrar solo las de hoy (por si el sheet acumula varios días)
        filtradas = [v for v in ventas if str(v.get("fecha", ""))[:10] == hoy]
        return {"fecha": hoy, "ventas": filtradas, "total": len(filtradas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventas/semana")
def ventas_semana():
    """Ventas de los últimos 7 días desde Excel."""
    try:
        ventas = _leer_excel_rango(dias=7)
        return {"ventas": ventas, "total": len(ventas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventas/top")
def ventas_top(periodo: str = Query(default="semana", pattern="^(semana|mes)$")):
    """Top 10 productos más vendidos por CANTIDAD en el período indicado."""
    try:
        dias = 7 if periodo == "semana" else None
        mes = periodo == "mes"
        ventas = _leer_excel_rango(dias=dias, mes_actual=mes)

        # Agrupar por producto
        por_producto: dict[str, dict] = defaultdict(lambda: {"unidades": 0.0, "ingresos": 0.0})
        for v in ventas:
            nombre = str(v.get("producto", "")).strip()
            if not nombre:
                continue
            cantidad = _cantidad_a_float(v.get("cantidad", 0))
            total    = _to_float(v.get("total", 0))
            por_producto[nombre]["unidades"] += cantidad
            por_producto[nombre]["ingresos"] += total

        # Ordenar por unidades desc, tomar top 10
        ranking = sorted(
            [{"producto": k, **v} for k, v in por_producto.items()],
            key=lambda x: x["unidades"],
            reverse=True,
        )[:10]

        # Agregar posición
        for i, item in enumerate(ranking, 1):
            item["posicion"] = i

        return {"periodo": periodo, "top": ranking}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventas/resumen")
def ventas_resumen():
    """Resumen: total hoy, total semana, número de pedidos, ticket promedio."""
    try:
        hoy = _hoy()

        # Datos de hoy (desde Sheets)
        ventas_hoy_list = sheets_leer_ventas_del_dia()
        ventas_hoy_list = [v for v in ventas_hoy_list if str(v.get("fecha", ""))[:10] == hoy]

        total_hoy   = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list)
        pedidos_hoy = len({str(v.get("num", i)) for i, v in enumerate(ventas_hoy_list)})

        # Datos de la semana (desde Excel)
        ventas_sem = _leer_excel_rango(dias=7)
        total_sem  = sum(_to_float(v.get("total", 0)) for v in ventas_sem)

        # Ticket promedio: total semana / número de ventas únicas de la semana
        pedidos_sem = len({str(v.get("num", i)) for i, v in enumerate(ventas_sem)}) or 1
        ticket_prom = round(total_sem / pedidos_sem, 0) if pedidos_sem else 0

        # Ventas diarias de la semana para gráfica de área
        ventas_por_dia: dict[str, float] = defaultdict(float)
        for v in ventas_sem:
            fecha = str(v.get("fecha", ""))[:10]
            ventas_por_dia[fecha] += _to_float(v.get("total", 0))

        # Rellenar días sin ventas (semana)
        historico = []
        for i in range(6, -1, -1):
            dia = (_hace_n_dias(i)).strftime("%Y-%m-%d")
            historico.append({"fecha": dia, "total": ventas_por_dia.get(dia, 0)})

        # Datos del mes actual para la gráfica mensual
        ventas_mes = _leer_excel_rango(mes_actual=True)
        total_mes  = sum(_to_float(v.get("total", 0)) for v in ventas_mes)

        ventas_mes_por_dia: dict[str, float] = defaultdict(float)
        for v in ventas_mes:
            fecha = str(v.get("fecha", ""))[:10]
            ventas_mes_por_dia[fecha] += _to_float(v.get("total", 0))

        ahora_local = datetime.now(config.COLOMBIA_TZ)
        primer_dia  = ahora_local.replace(day=1)
        historico_mes = []
        current = primer_dia
        while current.date() <= ahora_local.date():
            dia_str = current.strftime("%Y-%m-%d")
            historico_mes.append({"fecha": dia_str, "total": ventas_mes_por_dia.get(dia_str, 0)})
            current += timedelta(days=1)

        return {
            "total_hoy":    total_hoy,
            "pedidos_hoy":  pedidos_hoy,
            "total_semana": total_sem,
            "ticket_prom":  ticket_prom,
            "historico_7d": historico,
            "total_mes":    total_mes,
            "historico_mes": historico_mes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/productos")
def productos():
    """Todos los productos desde memoria.json."""
    try:
        if not os.path.exists(config.MEMORIA_FILE):
            return {"productos": []}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})
        lista = [
            {
                "key":      k,
                "nombre":   v.get("nombre", k),
                "categoria": v.get("categoria", "Sin categoría"),
                "precio":   v.get("precio_unidad", 0),
                "codigo":   v.get("codigo", ""),
                "stock":    inventario.get(k, None),
            }
            for k, v in catalogo.items()
        ]
        return {"productos": lista, "total": len(lista)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/inventario/bajo")
def inventario_bajo():
    """Productos con stock = 0 o sin precio definido."""
    try:
        if not os.path.exists(config.MEMORIA_FILE):
            return {"alertas": []}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)

        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})

        alertas = []
        for key, prod in catalogo.items():
            precio = prod.get("precio_unidad", None)
            stock  = inventario.get(key, None)

            sin_precio = precio is None or precio == 0
            sin_stock  = stock is not None and (stock == 0 or stock == "0")

            if sin_precio or sin_stock:
                alertas.append({
                    "key":       key,
                    "nombre":    prod.get("nombre", key),
                    "categoria": prod.get("categoria", ""),
                    "precio":    precio or 0,
                    "stock":     stock,
                    "motivo":    "sin_precio" if sin_precio else "stock_cero",
                })

        return {"alertas": alertas, "total": len(alertas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "servicio": "FerreBot Dashboard API",
        "estado":   "activo",
        "version":  "1.0.0",
        "docs":     "/docs",
    }
