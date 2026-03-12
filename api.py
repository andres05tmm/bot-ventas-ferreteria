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
from pathlib import Path

import openpyxl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
    allow_origins=["*"],
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
    if not os.path.exists(config.EXCEL_FILE):
        return []

    try:
        wb = openpyxl.load_workbook(config.EXCEL_FILE, read_only=True, data_only=True)
    except Exception:
        return []

    ahora = datetime.now(config.COLOMBIA_TZ)
    hojas_candidatas = [
        f"{config.MESES[ahora.month]} {ahora.year}",
    ]
    if ahora.month > 1:
        hojas_candidatas.append(f"{config.MESES[ahora.month - 1]} {ahora.year}")
    else:
        hojas_candidatas.append(f"{config.MESES[12]} {ahora.year - 1}")

    if dias is not None:
        limite = (_hace_n_dias(dias)).strftime("%Y-%m-%d")
    else:
        limite = None

    resultado = []
    for nombre_hoja in hojas_candidatas:
        if nombre_hoja not in wb.sheetnames:
            continue
        ws = wb[nombre_hoja]

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

            if isinstance(fecha_raw, datetime):
                fecha_str = fecha_raw.strftime("%Y-%m-%d")
            else:
                fecha_str = str(fecha_raw)[:10]

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
    if val is None:
        return 0.0
    s = str(val).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    if "/" in s and " " not in s:
        parts = s.split("/")
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return 0.0
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
    try:
        ventas = sheets_leer_ventas_del_dia()
        hoy = _hoy()
        filtradas = [v for v in ventas if str(v.get("fecha", ""))[:10] == hoy]
        return {"fecha": hoy, "ventas": filtradas, "total": len(filtradas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventas/semana")
def ventas_semana():
    try:
        ventas = _leer_excel_rango(dias=7)
        return {"ventas": ventas, "total": len(ventas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventas/top")
def ventas_top(periodo: str = Query(default="semana", pattern="^(semana|mes)$")):
    try:
        dias = 7 if periodo == "semana" else None
        mes = periodo == "mes"
        ventas = _leer_excel_rango(dias=dias, mes_actual=mes)

        por_producto: dict[str, dict] = defaultdict(lambda: {"unidades": 0.0, "ingresos": 0.0})
        for v in ventas:
            nombre = str(v.get("producto", "")).strip()
            if not nombre:
                continue
            cantidad = _cantidad_a_float(v.get("cantidad", 0))
            total    = _to_float(v.get("total", 0))
            por_producto[nombre]["unidades"] += cantidad
            por_producto[nombre]["ingresos"] += total

        ranking = sorted(
            [{"producto": k, **v} for k, v in por_producto.items()],
            key=lambda x: x["unidades"],
            reverse=True,
        )[:10]

        for i, item in enumerate(ranking, 1):
            item["posicion"] = i

        return {"periodo": periodo, "top": ranking}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ventas/resumen")
def ventas_resumen():
    try:
        hoy = _hoy()

        ventas_hoy_list = sheets_leer_ventas_del_dia()
        ventas_hoy_list = [v for v in ventas_hoy_list if str(v.get("fecha", ""))[:10] == hoy]

        total_hoy   = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list)
        pedidos_hoy = len({str(v.get("num", i)) for i, v in enumerate(ventas_hoy_list)})

        ventas_sem = _leer_excel_rango(dias=7)
        total_sem  = sum(_to_float(v.get("total", 0)) for v in ventas_sem)

        pedidos_sem = len({str(v.get("num", i)) for i, v in enumerate(ventas_sem)}) or 1
        ticket_prom = round(total_sem / pedidos_sem, 0) if pedidos_sem else 0

        ventas_por_dia: dict[str, float] = defaultdict(float)
        for v in ventas_sem:
            fecha = str(v.get("fecha", ""))[:10]
            ventas_por_dia[fecha] += _to_float(v.get("total", 0))

        historico = []
        for i in range(6, -1, -1):
            dia = (_hace_n_dias(i)).strftime("%Y-%m-%d")
            historico.append({"fecha": dia, "total": ventas_por_dia.get(dia, 0)})

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
            "total_hoy":     total_hoy,
            "pedidos_hoy":   pedidos_hoy,
            "total_semana":  total_sem,
            "ticket_prom":   ticket_prom,
            "historico_7d":  historico,
            "total_mes":     total_mes,
            "historico_mes": historico_mes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/productos")
def productos():
    try:
        if not os.path.exists(config.MEMORIA_FILE):
            return {"productos": []}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})
        lista = [
            {
                "key":       k,
                "nombre":    v.get("nombre", k),
                "categoria": v.get("categoria", "Sin categoría"),
                "precio":    v.get("precio_unidad", 0),
                "codigo":    v.get("codigo", ""),
                "stock":     inventario.get(k, None),
            }
            for k, v in catalogo.items()
        ]
        return {"productos": lista, "total": len(lista)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/inventario/bajo")
def inventario_bajo():
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


# ── Caja del día ─────────────────────────────────────────────────────────────
@app.get("/caja")
def caja():
    try:
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

        efectivo     = _to_float(caja_data.get("efectivo", 0))
        transferencias = _to_float(caja_data.get("transferencias", 0))
        datafono     = _to_float(caja_data.get("datafono", 0))
        apertura     = _to_float(caja_data.get("monto_apertura", 0))
        total_ventas = efectivo + transferencias + datafono
        efectivo_esperado = apertura + efectivo - total_gastos_caja

        return {
            "abierta":          caja_data.get("abierta", False),
            "fecha":            caja_data.get("fecha"),
            "monto_apertura":   apertura,
            "efectivo":         efectivo,
            "transferencias":   transferencias,
            "datafono":         datafono,
            "total_ventas":     total_ventas,
            "total_gastos_caja": total_gastos_caja,
            "total_gastos":     total_gastos,
            "efectivo_esperado": efectivo_esperado,
            "gastos":           gastos_hoy,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Gastos ────────────────────────────────────────────────────────────────────
@app.get("/gastos")
def gastos(dias: int = Query(default=7, ge=1, le=90)):
    try:
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
@app.get("/compras")
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
@app.get("/ventas/top2")
def ventas_top2(
    periodo:  str = Query(default="semana", pattern="^(semana|mes)$"),
    criterio: str = Query(default="ingresos", pattern="^(ingresos|frecuencia|categoria)$"),
):
    try:
        dias = 7 if periodo == "semana" else None
        mes  = periodo == "mes"
        ventas = _leer_excel_rango(dias=dias, mes_actual=mes)

        # Leer catálogo para saber la categoría de cada producto
        cat_map: dict[str, str] = {}
        if os.path.exists(config.MEMORIA_FILE):
            with open(config.MEMORIA_FILE, encoding="utf-8") as f:
                mem = json.load(f)
            for v in mem.get("catalogo", {}).values():
                nombre_lower = v.get("nombre_lower", "").strip()
                cat_map[nombre_lower] = v.get("categoria", "Sin categoría")

        # Acumular por producto
        acum: dict[str, dict] = defaultdict(lambda: {
            "ingresos": 0.0, "frecuencia": 0, "categoria": "Sin categoría"
        })
        for v in ventas:
            nombre = str(v.get("producto", "")).strip()
            if not nombre:
                continue
            total = _to_float(v.get("total", 0))
            acum[nombre]["ingresos"]   += total
            acum[nombre]["frecuencia"] += 1
            if acum[nombre]["categoria"] == "Sin categoría":
                acum[nombre]["categoria"] = cat_map.get(nombre.lower(), "Sin categoría")

        if criterio == "ingresos":
            ranking = sorted(acum.items(), key=lambda x: -x[1]["ingresos"])[:10]
            items = [{"producto": k, "valor": v["ingresos"], "frecuencia": v["frecuencia"],
                      "categoria": v["categoria"], "posicion": i+1}
                     for i, (k, v) in enumerate(ranking)]

        elif criterio == "frecuencia":
            ranking = sorted(acum.items(), key=lambda x: -x[1]["frecuencia"])[:10]
            items = [{"producto": k, "valor": v["frecuencia"], "ingresos": v["ingresos"],
                      "categoria": v["categoria"], "posicion": i+1}
                     for i, (k, v) in enumerate(ranking)]

        else:  # categoria
            # Top 5 por ingresos dentro de cada categoría
            por_cat: dict[str, list] = defaultdict(list)
            for nombre, datos in acum.items():
                por_cat[datos["categoria"]].append({"producto": nombre, **datos})
            result_cat = {}
            for cat, prods in por_cat.items():
                top = sorted(prods, key=lambda x: -x["ingresos"])[:5]
                result_cat[cat] = [{"producto": p["producto"], "valor": p["ingresos"],
                                    "frecuencia": p["frecuencia"], "posicion": i+1}
                                   for i, p in enumerate(top)]
            return {"periodo": periodo, "criterio": criterio, "por_categoria": result_cat}

        return {"periodo": periodo, "criterio": criterio, "top": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Catálogo navegable (para dashboard) ──────────────────────────────────────
@app.get("/catalogo/nav")
def catalogo_nav(q: str = Query(default="")):
    try:
        if not os.path.exists(config.MEMORIA_FILE):
            return {"categorias": {}, "total": 0}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)

        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})

        # Filtro de búsqueda
        q_lower = q.strip().lower()

        categorias: dict[str, list] = defaultdict(list)
        for key, prod in catalogo.items():
            nombre   = prod.get("nombre", key)
            categoria = prod.get("categoria", "Sin categoría")

            if q_lower and q_lower not in nombre.lower() and q_lower not in (prod.get("codigo","")).lower():
                continue

            # Stock info
            inv_data = inventario.get(key)
            if isinstance(inv_data, dict):
                stock = inv_data.get("cantidad")
                costo = inv_data.get("costo_promedio")
            else:
                stock = inv_data
                costo = None

            # Fracciones
            fracs = {}
            for frac_key, frac_val in (prod.get("precios_fraccion") or {}).items():
                if isinstance(frac_val, dict):
                    fracs[frac_key] = frac_val.get("precio", 0)
                else:
                    fracs[frac_key] = frac_val

            # Precio mayorista
            ppc = prod.get("precio_por_cantidad")
            mayorista = None
            if ppc:
                mayorista = {
                    "umbral":  ppc.get("umbral", 50),
                    "precio":  ppc.get("precio_sobre_umbral", 0),
                }

            categorias[categoria].append({
                "key":       key,
                "nombre":    nombre,
                "codigo":    prod.get("codigo", ""),
                "precio":    prod.get("precio_unidad", 0),
                "stock":     stock,
                "costo":     costo,
                "fracciones": fracs,
                "mayorista":  mayorista,
            })

        # Ordenar por prefijo numérico de categoría y productos por nombre
        result = {}
        for cat in sorted(categorias.keys(), key=lambda c: (int(c.split()[0]) if c[0].isdigit() else 999)):
            prods = sorted(categorias[cat], key=lambda p: p["nombre"].lower())
            result[cat] = prods

        total = sum(len(v) for v in result.values())
        return {"categorias": result, "total": total, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"estado": "activo", "version": "1.0.0"}


# ── Servir dashboard React (build estático) ───────────────────────────────────
# Los archivos del build quedan en dashboard/dist/ después de `npm run build`
_DIST = Path(__file__).parent / "dashboard" / "dist"

if _DIST.exists():
    # Archivos estáticos (JS, CSS, assets)
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    # Cualquier ruta que no sea /api/* → devolver index.html (SPA routing)
    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        index = _DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"error": "Dashboard no buildeado. Ejecuta: cd dashboard && npm run build"}
else:
    @app.get("/")
    def root():
        return {
            "servicio": "FerreBot Dashboard API",
            "estado":   "activo",
            "version":  "1.0.0",
            "nota":     "Dashboard no buildeado. Ejecuta: cd dashboard && npm run build",
            "docs":     "/docs",
        }
