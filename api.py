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


def _leer_excel_compras(dias: int | None = None) -> list[dict]:
    """Lee la hoja 'Compras' del Excel de ventas."""
    if not os.path.exists(config.EXCEL_FILE):
        return []
    try:
        wb = openpyxl.load_workbook(config.EXCEL_FILE, read_only=True, data_only=True)
    except Exception:
        return []
    if "Compras" not in wb.sheetnames:
        wb.close()
        return []
    ws     = wb["Compras"]
    ahora  = datetime.now(config.COLOMBIA_TZ)
    limite = (ahora - timedelta(days=dias)).strftime("%Y-%m-%d") if dias else None
    resultado = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        fecha = str(row[0])[:10] if row[0] else ""
        if limite and fecha < limite:
            continue
        resultado.append({
            "fecha":          fecha,
            "hora":           str(row[1] or ""),
            "proveedor":      str(row[2] or "—"),
            "producto":       str(row[3] or ""),
            "cantidad":       _to_float(row[4]),
            "costo_unitario": _to_float(row[5]),
            "costo_total":    _to_float(row[6]),
        })
    wb.close()
    return sorted(resultado, key=lambda x: x["fecha"])


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


# ── Kárdex por producto ───────────────────────────────────────────────────────
@app.get("/kardex")
def kardex(q: str = Query(default="")):
    """
    Devuelve el kárdex de movimientos de inventario.
    - Entradas: hoja Compras del Excel + historial_compras de memoria.json
    - Salidas: calculadas como diferencia (entradas - stock actual)
    - Si q != "" filtra por nombre de producto.
    """
    try:
        compras_excel = _leer_excel_compras()

        mem       = json.load(open(config.MEMORIA_FILE, encoding="utf-8")) if os.path.exists(config.MEMORIA_FILE) else {}
        inventario = mem.get("inventario", {})
        q_lower    = q.strip().lower()

        # Agrupar entradas por producto
        entradas_por_prod: dict[str, list] = defaultdict(list)
        for c in compras_excel:
            nombre = c["producto"].strip()
            if not nombre:
                continue
            if q_lower and q_lower not in nombre.lower():
                continue
            entradas_por_prod[nombre].append(c)

        kardex_items = []
        for nombre, entradas in entradas_por_prod.items():
            # Buscar stock actual en inventario
            stock_actual = 0.0
            costo_actual = 0.0
            for clave, datos in inventario.items():
                if isinstance(datos, dict):
                    n = datos.get("nombre_original", "").lower()
                    if n == nombre.lower() or clave.replace("_", " ") == nombre.lower():
                        stock_actual = _to_float(datos.get("cantidad", 0))
                        costo_actual = _to_float(datos.get("costo_promedio", 0))
                        break

            # Construir movimientos con saldo running
            movimientos = []
            saldo      = 0.0
            costo_prom = 0.0
            total_entradas = 0.0

            for e in sorted(entradas, key=lambda x: (x["fecha"], x["hora"])):
                cant  = e["cantidad"]
                costo = e["costo_unitario"]
                # Recalcular promedio ponderado
                if saldo + cant > 0:
                    costo_prom = round((saldo * costo_prom + cant * costo) / (saldo + cant))
                saldo         += cant
                total_entradas += cant
                movimientos.append({
                    "tipo":           "entrada",
                    "fecha":          e["fecha"],
                    "hora":           e["hora"],
                    "concepto":       f"Compra — {e['proveedor']}",
                    "entrada":        cant,
                    "salida":         0,
                    "saldo":          round(saldo, 3),
                    "costo_unitario": costo,
                    "costo_promedio": costo_prom,
                    "valor_total":    round(cant * costo),
                })

            # Salidas estimadas = total_entradas - stock_actual (si hay inventario registrado)
            salidas_est = round(max(0.0, total_entradas - stock_actual), 3)

            kardex_items.append({
                "producto":       nombre,
                "total_entradas": round(total_entradas, 3),
                "stock_actual":   stock_actual,
                "salidas_est":    salidas_est,
                "costo_promedio": costo_actual or costo_prom,
                "valor_inventario": round(stock_actual * (costo_actual or costo_prom)),
                "movimientos":    movimientos,
            })

        kardex_items.sort(key=lambda x: x["producto"].lower())
        total_valor_inv = sum(k["valor_inventario"] for k in kardex_items)

        return {
            "kardex":          kardex_items,
            "total_productos": len(kardex_items),
            "valor_inventario_total": total_valor_inv,
            "tiene_datos":     len(kardex_items) > 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Estado de Resultados ──────────────────────────────────────────────────────
@app.get("/resultados")
def resultados(periodo: str = Query(default="mes", pattern="^(semana|mes)$")):
    """
    Estado de Resultados:
      Ingresos (ventas)
    — CMV (costo de mercancía vendida = compras del período × promedio ponderado)
    = Utilidad Bruta
    — Gastos operativos
    = Utilidad Neta
    """
    try:
        ahora = datetime.now(config.COLOMBIA_TZ)

        # ── 1. INGRESOS ──────────────────────────────────────────────────────
        dias_rango = 7 if periodo == "semana" else None
        es_mes     = periodo == "mes"
        ventas     = _leer_excel_rango(dias=dias_rango, mes_actual=es_mes)

        total_ventas = sum(_to_float(v.get("total", 0)) for v in ventas)

        # Ventas por día para gráfica
        ventas_por_dia: dict[str, float] = defaultdict(float)
        for v in ventas:
            ventas_por_dia[v["fecha"]] += _to_float(v.get("total", 0))

        # ── 2. CMV ───────────────────────────────────────────────────────────
        # Costo de lo vendido = unidades vendidas × costo_promedio del producto
        mem        = json.load(open(config.MEMORIA_FILE, encoding="utf-8")) if os.path.exists(config.MEMORIA_FILE) else {}
        inventario = mem.get("inventario", {})

        # Índice de inventario por nombre normalizado
        inv_idx: dict[str, dict] = {}
        for clave, datos in inventario.items():
            if isinstance(datos, dict):
                nombre_n = datos.get("nombre_original", "").lower().strip()
                inv_idx[nombre_n] = datos
                inv_idx[clave.replace("_", " ")] = datos

        # Agrupar ventas por producto
        ventas_prod: dict[str, dict] = defaultdict(lambda: {"cantidad": 0.0, "ingresos": 0.0})
        for v in ventas:
            nombre = str(v.get("producto", "")).strip()
            if not nombre:
                continue
            cant = _to_float(v.get("cantidad", 1))
            ventas_prod[nombre]["cantidad"] += cant
            ventas_prod[nombre]["ingresos"] += _to_float(v.get("total", 0))

        cmv           = 0.0
        cmv_detalle   = []
        sin_costo     = []

        for nombre, datos_v in ventas_prod.items():
            datos_inv = inv_idx.get(nombre.lower().strip())
            costo_u   = _to_float(datos_inv.get("costo_promedio", 0)) if datos_inv else 0

            if costo_u > 0:
                costo_total_prod = costo_u * datos_v["cantidad"]
                cmv             += costo_total_prod
                margen = round(((datos_v["ingresos"] - costo_total_prod) / datos_v["ingresos"]) * 100, 1) if datos_v["ingresos"] else 0
                cmv_detalle.append({
                    "producto":    nombre,
                    "cantidad":    round(datos_v["cantidad"], 3),
                    "ingresos":    round(datos_v["ingresos"]),
                    "costo_unit":  costo_u,
                    "cmv":         round(costo_total_prod),
                    "margen_pct":  margen,
                })
            else:
                sin_costo.append(nombre)

        cmv_detalle.sort(key=lambda x: -x["cmv"])

        # ── 3. GASTOS ────────────────────────────────────────────────────────
        gastos_mem    = mem.get("gastos", {})
        if periodo == "semana":
            limite_g  = (ahora - timedelta(days=7)).strftime("%Y-%m-%d")
        else:
            limite_g  = f"{ahora.year}-{ahora.month:02d}-01"

        total_gastos      = 0.0
        gastos_por_cat: dict[str, float] = defaultdict(float)
        for fecha_g, lista_g in gastos_mem.items():
            if fecha_g < limite_g:
                continue
            for g in lista_g:
                monto = _to_float(g.get("monto", 0))
                total_gastos += monto
                gastos_por_cat[g.get("categoria", "Sin categoría")] += monto

        # ── 4. RESULTADOS ────────────────────────────────────────────────────
        utilidad_bruta = total_ventas - cmv
        utilidad_neta  = utilidad_bruta - total_gastos
        margen_bruto   = round((utilidad_bruta / total_ventas) * 100, 1) if total_ventas else 0
        margen_neto    = round((utilidad_neta  / total_ventas) * 100, 1) if total_ventas else 0

        # Histórico diario para gráfica
        dias_n = 7 if periodo == "semana" else ahora.day
        historico = []
        for i in range(dias_n - 1, -1, -1):
            dia = (ahora - timedelta(days=i)).strftime("%Y-%m-%d")
            gastos_dia = sum(_to_float(g.get("monto", 0))
                             for g in gastos_mem.get(dia, []))
            historico.append({
                "fecha":   dia,
                "ventas":  ventas_por_dia.get(dia, 0),
                "gastos":  gastos_dia,
            })

        return {
            "periodo":          periodo,
            "total_ventas":     round(total_ventas),
            "cmv":              round(cmv),
            "utilidad_bruta":   round(utilidad_bruta),
            "total_gastos":     round(total_gastos),
            "utilidad_neta":    round(utilidad_neta),
            "margen_bruto_pct": margen_bruto,
            "margen_neto_pct":  margen_neto,
            "cmv_detalle":      cmv_detalle,
            "sin_costo":        sin_costo[:20],
            "gastos_por_cat":   dict(gastos_por_cat),
            "historico":        historico,
            "tiene_cmv":        cmv > 0,
            "cobertura_cmv_pct": round((len(cmv_detalle) / max(len(ventas_prod), 1)) * 100, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Proyección de Caja ────────────────────────────────────────────────────────
@app.get("/proyeccion")
def proyeccion():
    """
    Proyecta el cierre del mes basándose en promedios de los últimos 14 días.
    Proyección = efectivo_actual + (ingreso_diario_prom - gasto_diario_prom) × días_restantes
    """
    try:
        ahora     = datetime.now(config.COLOMBIA_TZ)
        mem       = json.load(open(config.MEMORIA_FILE, encoding="utf-8")) if os.path.exists(config.MEMORIA_FILE) else {}
        caja_data = mem.get("caja_actual", {})

        # ── Base de caja actual ───────────────────────────────────────────
        efectivo_actual = (
            _to_float(caja_data.get("efectivo", 0)) +
            _to_float(caja_data.get("transferencias", 0)) +
            _to_float(caja_data.get("datafono", 0)) +
            _to_float(caja_data.get("monto_apertura", 0))
        )

        # ── Ventas últimos 14 días ────────────────────────────────────────
        ventas_14 = _leer_excel_rango(dias=14)
        ventas_por_dia14: dict[str, float] = defaultdict(float)
        for v in ventas_14:
            ventas_por_dia14[v["fecha"]] += _to_float(v.get("total", 0))

        dias_con_ventas = [d for d, t in ventas_por_dia14.items() if t > 0]
        prom_ventas_dia = (
            sum(ventas_por_dia14.values()) / len(dias_con_ventas)
            if dias_con_ventas else 0
        )

        # ── Gastos últimos 14 días ────────────────────────────────────────
        gastos_mem = mem.get("gastos", {})
        limite_14  = (ahora - timedelta(days=14)).strftime("%Y-%m-%d")
        total_gastos_14 = 0.0
        gastos_por_dia14: dict[str, float] = defaultdict(float)
        for fecha_g, lista_g in gastos_mem.items():
            if fecha_g < limite_14:
                continue
            for g in lista_g:
                m = _to_float(g.get("monto", 0))
                total_gastos_14         += m
                gastos_por_dia14[fecha_g] += m

        dias_con_gastos = max(len([d for d, t in gastos_por_dia14.items() if t > 0]), 1)
        prom_gastos_dia = total_gastos_14 / dias_con_gastos if total_gastos_14 else 0

        # ── Días restantes del mes ────────────────────────────────────────
        import calendar
        ultimo_dia   = calendar.monthrange(ahora.year, ahora.month)[1]
        dias_rest    = ultimo_dia - ahora.day
        dias_pasados = ahora.day

        # ── Proyecciones ──────────────────────────────────────────────────
        ventas_proy_rest  = prom_ventas_dia * dias_rest
        gastos_proy_rest  = prom_gastos_dia * dias_rest
        ventas_mes_total  = sum(v for d, v in ventas_por_dia14.items()
                                if d.startswith(f"{ahora.year}-{ahora.month:02d}"))
        gastos_mes_total  = sum(t for d, t in gastos_por_dia14.items()
                                if d >= f"{ahora.year}-{ahora.month:02d}-01")

        proy_ventas_mes   = ventas_mes_total  + ventas_proy_rest
        proy_gastos_mes   = gastos_mes_total  + gastos_proy_rest
        proy_caja_fin_mes = efectivo_actual   + ventas_proy_rest - gastos_proy_rest

        # Serie diaria para gráfica (real + proyectado)
        serie = []
        acum  = _to_float(caja_data.get("monto_apertura", 0))
        for i in range(1, ultimo_dia + 1):
            dia_str = f"{ahora.year}-{ahora.month:02d}-{i:02d}"
            if i < ahora.day:
                # Días pasados — datos reales
                v = ventas_por_dia14.get(dia_str, 0)
                g = sum(_to_float(x.get("monto", 0)) for x in gastos_mem.get(dia_str, []))
                acum += v - g
                serie.append({"dia": i, "valor": round(acum), "real": True})
            elif i == ahora.day:
                serie.append({"dia": i, "valor": round(efectivo_actual), "real": True, "hoy": True})
            else:
                acum_proy = efectivo_actual + (prom_ventas_dia - prom_gastos_dia) * (i - ahora.day)
                serie.append({"dia": i, "valor": round(acum_proy), "real": False})

        return {
            "hoy":                  ahora.strftime("%Y-%m-%d"),
            "dia_del_mes":          ahora.day,
            "dias_restantes":       dias_rest,
            "dias_pasados":         dias_pasados,
            "efectivo_actual":      round(efectivo_actual),
            "prom_ventas_dia":      round(prom_ventas_dia),
            "prom_gastos_dia":      round(prom_gastos_dia),
            "prom_neto_dia":        round(prom_ventas_dia - prom_gastos_dia),
            "ventas_mes_actual":    round(ventas_mes_total),
            "gastos_mes_actual":    round(gastos_mes_total),
            "proy_ventas_mes":      round(proy_ventas_mes),
            "proy_gastos_mes":      round(proy_gastos_mes),
            "proy_caja_fin_mes":    round(proy_caja_fin_mes),
            "serie_diaria":         serie,
            "tiene_datos":          prom_ventas_dia > 0,
        }
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
