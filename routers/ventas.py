"""
Router: Ventas — /ventas/* y /venta-rapida
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
from routers.shared import (
    _hoy, _hace_n_dias, _leer_excel_rango, _leer_ventas_postgres, _leer_excel_compras,
    _to_float, _cantidad_a_float, _stock_wayper,
)
from routers.caja import VentaRapidaPayload, VentaRapidaItem

logger = logging.getLogger("ferrebot.api")

router = APIRouter()

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/ventas/hoy")
def ventas_hoy():
    try:
        hoy = _hoy()
        filtradas = []
        fuente = "postgres"

        # ── Fuente primaria: Postgres ─────────────────────────────────────────
        try:
            pg_ventas = _leer_ventas_postgres(dias=1)
            if pg_ventas is not None:
                filtradas = [v for v in pg_ventas if str(v.get("fecha", ""))[:10] == hoy]
        except Exception as e_pg:
            logger.warning(f"Postgres no disponible en /ventas/hoy: {e_pg}")

        # ── Fallback: Excel local ─────────────────────────────────────────────
        if not filtradas:
            try:
                ventas_xls = _leer_excel_rango(dias=1)
                filtradas = [v for v in ventas_xls if str(v.get("fecha", ""))[:10] == hoy]
                if filtradas:
                    fuente = "excel_fallback"
            except Exception:
                pass

        # ── Enriquecer con unidad_medida desde el catálogo (solo si falta) ────
        try:
            necesitan = [v for v in filtradas if not v.get("unidad_medida") or v["unidad_medida"] == "Unidad"]
            if necesitan and os.path.exists(config.MEMORIA_FILE):
                with open(config.MEMORIA_FILE, encoding="utf-8") as _f:
                    _mem = json.load(_f)
                catalogo = _mem.get("catalogo", {})

                def _unidad_para(nombre_prod: str) -> str:
                    if not nombre_prod:
                        return "Unidad"
                    n = nombre_prod.lower().strip()
                    for key, prod in catalogo.items():
                        if prod.get("nombre", "").lower().strip() == n or key == n.replace(" ", "_"):
                            return prod.get("unidad_medida", "Unidad") or "Unidad"
                    return "Unidad"

                for v in necesitan:
                    v["unidad_medida"] = _unidad_para(v.get("producto", ""))
        except Exception:
            pass

        return {"fecha": hoy, "ventas": filtradas, "total": len(filtradas), "fuente": fuente}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/semana")
def ventas_semana():
    try:
        ventas = _leer_ventas_postgres(dias=7)
        if ventas is None:
            ventas = _leer_excel_rango(dias=7)
        return {"ventas": ventas, "total": len(ventas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/top")
def ventas_top(periodo: str = Query(default="semana", pattern="^(semana|mes)$")):
    try:
        dias = 7 if periodo == "semana" else None
        mes = periodo == "mes"
        ventas = _leer_ventas_postgres(dias=dias, mes_actual=mes)
        if ventas is None:
            ventas = _leer_excel_rango(dias=dias, mes_actual=mes)

        # Leer catálogo para obtener unidad_medida canónica de cada producto
        cat_unidad: dict[str, str] = {}
        if os.path.exists(config.MEMORIA_FILE):
            with open(config.MEMORIA_FILE, encoding="utf-8") as _f:
                _mem = json.load(_f)
            for prod in _mem.get("catalogo", {}).values():
                nombre_lower = (prod.get("nombre_lower") or prod.get("nombre", "")).lower().strip()
                cat_unidad[nombre_lower] = prod.get("unidad_medida", "Unidad") or "Unidad"

        por_producto: dict[str, dict] = {}
        for v in ventas:
            nombre = str(v.get("producto", "")).strip()
            if not nombre:
                continue
            cantidad  = _cantidad_a_float(v.get("cantidad", 0))
            total     = _to_float(v.get("total", 0))
            unidad_v  = str(v.get("unidad_medida", "") or "").strip()

            if nombre not in por_producto:
                unidad_cat = cat_unidad.get(nombre.lower(), "")
                por_producto[nombre] = {
                    "unidades":      0.0,
                    "ingresos":      0.0,
                    "frecuencia":    0,
                    "unidad_medida": unidad_cat or unidad_v or "Unidad",
                }
            por_producto[nombre]["unidades"]   += cantidad
            por_producto[nombre]["ingresos"]   += total
            por_producto[nombre]["frecuencia"] += 1

        # Ordenar por INGRESOS (no por unidades — evita que gramos inflen el ranking)
        ranking = sorted(
            [{"producto": k, **v} for k, v in por_producto.items()],
            key=lambda x: x["ingresos"],
            reverse=True,
        )[:10]

        for i, item in enumerate(ranking, 1):
            item["posicion"] = i

        return {"periodo": periodo, "top": ranking}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/resumen")
def ventas_resumen():
    try:
        hoy = _hoy()

        # Postgres — fuente primaria para hoy; tolerante a fallo
        try:
            pg_hoy = _leer_ventas_postgres(dias=1)
            if pg_hoy is not None:
                ventas_hoy_list = [v for v in pg_hoy if str(v.get("fecha", ""))[:10] == hoy]
            else:
                ventas_hoy_list = _leer_excel_rango(dias=1)
                ventas_hoy_list = [v for v in ventas_hoy_list if str(v.get("fecha", ""))[:10] == hoy]
        except Exception:
            ventas_hoy_list = []

        total_hoy   = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list)
        pedidos_hoy = len({str(v.get("num", i)) for i, v in enumerate(ventas_hoy_list)})

        # Postgres semana (con fallback a Excel) — tolerante a fallo
        try:
            ventas_sem = _leer_ventas_postgres(dias=7)
            if ventas_sem is None:
                ventas_sem = _leer_excel_rango(dias=7)
        except Exception:
            ventas_sem = []
        total_sem   = sum(_to_float(v.get("total", 0)) for v in ventas_sem)
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

        # Postgres mes (con fallback a Excel) — tolerante a fallo
        try:
            ventas_mes = _leer_ventas_postgres(mes_actual=True)
            if ventas_mes is None:
                ventas_mes = _leer_excel_rango(mes_actual=True)
        except Exception:
            ventas_mes = []
        total_mes = sum(_to_float(v.get("total", 0)) for v in ventas_mes)

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


@router.post("/venta-rapida")
def venta_rapida(payload: VentaRapidaPayload):
    try:
        from excel import guardar_venta_excel, recalcular_caja_desde_excel, obtener_siguiente_consecutivo

        # Cargar catálogo una sola vez para resolver unidad_medida
        _catalogo_cache = {}
        try:
            if os.path.exists(config.MEMORIA_FILE):
                with open(config.MEMORIA_FILE, encoding="utf-8") as _f:
                    _mem = json.load(_f)
                _catalogo_cache = _mem.get("catalogo", {})
        except Exception:
            pass

        def _resolver_unidad(item: VentaRapidaItem) -> str:
            """Devuelve la unidad_medida del item: primero la del payload, si no la del catálogo."""
            if item.unidad_medida and item.unidad_medida not in ("", "Unidad"):
                return item.unidad_medida
            nombre_norm = item.nombre.lower().strip()
            for prod_key, prod_val in _catalogo_cache.items():
                if prod_val.get("nombre", "").lower().strip() == nombre_norm or prod_key == nombre_norm.replace(" ", "_"):
                    return prod_val.get("unidad_medida", "Unidad")
            return item.unidad_medida or "Unidad"

        # Un solo consecutivo para toda la venta
        consecutivo = obtener_siguiente_consecutivo()

        # Pre-calcular items una sola vez (se reusan en PG y en Excel)
        items_calc = []
        for item in payload.productos:
            try:
                from utils import convertir_fraccion_a_decimal
                cant_num = convertir_fraccion_a_decimal(item.cantidad)
            except (ValueError, TypeError):
                cant_num = 1.0
            # Bug fix: cant_num <= 0 causaba precio_unitario=total (incorrecto).
            if not cant_num or cant_num <= 0:
                cant_num = 1.0
            items_calc.append({
                "item":            item,
                "cant_num":        cant_num,
                "precio_unitario": round(item.total / cant_num, 2),
                "unidad":          _resolver_unidad(item),
            })

        # ── Fuente primaria: Postgres ─────────────────────────────────────────
        pg_ok = False
        try:
            from db import DB_DISPONIBLE, _get_conn
            import datetime as _dt
            if DB_DISPONIBLE:
                ahora = _dt.datetime.now()
                with _get_conn() as _conn:
                    with _conn.cursor() as _cur:
                        _cur.execute(
                            """
                            INSERT INTO ventas
                                (consecutivo, fecha, vendedor, metodo_pago,
                                 total, cliente_nombre, cliente_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (consecutivo, fecha) DO NOTHING
                            RETURNING id
                            """,
                            (
                                consecutivo,
                                ahora,
                                payload.vendedor,
                                payload.metodo,
                                sum(i["item"].total for i in items_calc),
                                payload.cliente_nombre or None,
                                payload.cliente_id     or None,
                            ),
                        )
                        row = _cur.fetchone()
                        if row:
                            venta_id = row["id"]
                            for ic in items_calc:
                                _cur.execute(
                                    """
                                    INSERT INTO ventas_detalle
                                        (venta_id, producto_nombre, cantidad,
                                         precio_unitario, total, unidad_medida)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    """,
                                    (
                                        venta_id,
                                        ic["item"].nombre,
                                        ic["cant_num"],
                                        ic["precio_unitario"],
                                        ic["item"].total,
                                        ic["unidad"],
                                    ),
                                )
                    _conn.commit()
                pg_ok = True
        except Exception as e_pg:
            logger.warning(f"Postgres write falló en /venta-rapida (usando Excel como backup): {e_pg}")

        # ── Backup: Excel ─────────────────────────────────────────────────────
        filas = []
        try:
            for ic in items_calc:
                fila = guardar_venta_excel(
                    producto        = ic["item"].nombre,
                    cantidad        = ic["cant_num"],
                    precio_unitario = ic["precio_unitario"],
                    total           = ic["item"].total,
                    vendedor        = payload.vendedor,
                    observaciones   = "venta-rapida",
                    metodo_pago     = payload.metodo,
                    consecutivo     = consecutivo,
                    unidad_medida   = ic["unidad"],
                    cliente_nombre  = payload.cliente_nombre or None,
                    cliente_id      = payload.cliente_id     or None,
                )
                filas.append(fila)
            recalcular_caja_desde_excel()
        except Exception as e_xl:
            logger.warning(f"Excel backup falló en /venta-rapida: {e_xl}")

        # Si ambas fuentes fallaron → error real
        if not pg_ok and not filas:
            raise Exception("No se pudo guardar la venta en Postgres ni en Excel")

        # Descontar inventario (igual que hace el bot por Telegram)
        for ic in items_calc:
            try:
                from memoria import descontar_inventario
                descontar_inventario(ic["item"].nombre, ic["cant_num"])
            except Exception:
                pass

        return {
            "ok":          True,
            "consecutivo": consecutivo,
            "productos":   len(items_calc),
            "total":       sum(ic["item"].total for ic in items_calc),
            "metodo":      payload.metodo,
            "fuente":      "postgres" if pg_ok else "excel_fallback",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/ventas/top2")
def ventas_top2(
    periodo:  str = Query(default="semana", pattern="^(semana|mes)$"),
    criterio: str = Query(default="ingresos", pattern="^(ingresos|frecuencia|categoria)$"),
):
    try:
        dias = 7 if periodo == "semana" else None
        mes  = periodo == "mes"
        ventas = _leer_ventas_postgres(dias=dias, mes_actual=mes)
        if ventas is None:
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
@router.delete("/ventas/{numero}")
def eliminar_venta(numero: int):
    """
    Elimina todas las filas de un consecutivo de venta.
    PG primero, Excel como backup.
    """
    try:
        from excel import borrar_venta_excel, recalcular_caja_desde_excel

        # ── Fuente primaria: Postgres ─────────────────────────────────────────
        pg_ok = False
        try:
            import db as _db
            if _db.DB_DISPONIBLE:
                borradas = _db.execute(
                    "DELETE FROM ventas WHERE consecutivo = %s", [numero]
                )
                pg_ok = borradas > 0
        except Exception as e_pg:
            logger.warning(f"Postgres delete falló en /ventas/{numero}: {e_pg}")

        # ── Backup: Excel ─────────────────────────────────────────────────────
        excel_ok = False
        excel_msg = ""
        try:
            excel_ok, excel_msg = borrar_venta_excel(numero)
            if excel_ok:
                recalcular_caja_desde_excel()
        except Exception as e_xl:
            logger.warning(f"Excel delete falló para consecutivo {numero}: {e_xl}")

        if not pg_ok and not excel_ok:
            raise HTTPException(status_code=404, detail=excel_msg or f"Consecutivo #{numero} no encontrado")

        return {"ok": True, "mensaje": excel_msg or f"Venta #{numero} eliminada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ventas/{numero}/linea")
def eliminar_linea_venta(numero: int, producto: str = Query(...)):
    """
    Elimina UNA sola línea (producto) de un consecutivo multi-producto.
    PG primero, Excel como backup.
    """
    try:
        import openpyxl
        from excel import inicializar_excel, obtener_nombre_hoja, detectar_columnas, recalcular_caja_desde_excel

        # ── Fuente primaria: Postgres ─────────────────────────────────────────
        pg_ok = False
        try:
            import db as _db
            if _db.DB_DISPONIBLE:
                borradas = _db.execute(
                    """
                    DELETE FROM ventas_detalle
                    WHERE venta_id = (SELECT id FROM ventas WHERE consecutivo = %s LIMIT 1)
                      AND LOWER(producto_nombre) = LOWER(%s)
                    """,
                    [numero, producto],
                )
                pg_ok = borradas > 0
        except Exception as e_pg:
            logger.warning(f"Postgres delete línea falló para #{numero} '{producto}': {e_pg}")

        # ── Backup: Excel ─────────────────────────────────────────────────────
        total_borradas = 0
        try:
            inicializar_excel()
            wb    = openpyxl.load_workbook(config.EXCEL_FILE)
            hojas = [obtener_nombre_hoja(), "Registro de Ventas-Acumulado"]

            for nombre_sh in hojas:
                if nombre_sh not in wb.sheetnames:
                    continue
                ws   = wb[nombre_sh]
                cols = detectar_columnas(ws)
                col_id   = cols.get("consecutivo de venta") or cols.get("consecutivo") or cols.get("alias")
                col_prod = cols.get("producto")
                if not col_id or not col_prod:
                    continue

                filas_borrar = []
                for fila in range(config.EXCEL_FILA_DATOS, ws.max_row + 1):
                    val_id   = ws.cell(row=fila, column=col_id).value
                    val_prod = str(ws.cell(row=fila, column=col_prod).value or "").strip()
                    try:
                        if val_id is not None and int(float(str(val_id))) == numero:
                            if val_prod.lower() == producto.lower():
                                filas_borrar.append(fila)
                    except (ValueError, TypeError):
                        pass

                for fila in reversed(filas_borrar):
                    ws.delete_rows(fila)
                total_borradas += len(filas_borrar)

            if total_borradas:
                wb.save(config.EXCEL_FILE)
                recalcular_caja_desde_excel()
        except Exception as e_xl:
            logger.warning(f"Excel delete línea falló para #{numero} '{producto}': {e_xl}")

        if not pg_ok and not total_borradas:
            raise HTTPException(status_code=404, detail=f"No se encontró '{producto}' en consecutivo #{numero}")

        return {"ok": True, "borradas": total_borradas or 1, "mensaje": f"'{producto}' eliminado del consecutivo #{numero}"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class EditarVentaBody(BaseModel):
    producto:          Union[str, None]   = None
    cantidad:          Union[float, None] = None
    precio_unitario:   Union[float, None] = None
    total:             Union[float, None] = None
    metodo_pago:       Union[str, None]   = None
    cliente:           Union[str, None]   = None
    id_cliente:        Union[str, None]   = None
    vendedor:          Union[str, None]   = None
    producto_original: Union[str, None]   = None  # para identificar fila en multi-producto

@router.patch("/ventas/{numero}")
def editar_venta(numero: int, body: EditarVentaBody):
    """
    Edita los campos de un consecutivo.
    PG primero, Excel como backup.
    Si producto_original viene, solo actualiza la fila con ese producto (multi-producto).
    """
    try:
        import openpyxl
        from excel import inicializar_excel, obtener_nombre_hoja, detectar_columnas, recalcular_caja_desde_excel

        cambios = {k: v for k, v in body.dict().items() if v is not None and k != "producto_original"}
        if not cambios:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar")

        filtro_producto = body.producto_original.strip().lower() if body.producto_original else None

        # ── Fuente primaria: Postgres ─────────────────────────────────────────
        pg_ok = False
        try:
            import db as _db
            if _db.DB_DISPONIBLE:
                campo_col_pg = {
                    "producto":        "producto_nombre",
                    "cantidad":        "cantidad",
                    "precio_unitario": "precio_unitario",
                    "total":           "total",
                }
                cabecera_col_pg = {
                    "metodo_pago": "metodo_pago",
                    "cliente":     "cliente_nombre",
                    "vendedor":    "vendedor",
                }
                # Actualizar ventas_detalle
                det_parts, det_params = [], []
                for campo, col in campo_col_pg.items():
                    if campo in cambios:
                        det_parts.append(f"{col} = %s")
                        det_params.append(cambios[campo])
                if det_parts:
                    where_det = "WHERE venta_id = (SELECT id FROM ventas WHERE consecutivo = %s LIMIT 1)"
                    if filtro_producto:
                        where_det += " AND LOWER(producto_nombre) = LOWER(%s)"
                        det_params.append(numero)
                        det_params.append(filtro_producto)
                    else:
                        det_params.append(numero)
                    _db.execute(f"UPDATE ventas_detalle SET {', '.join(det_parts)} {where_det}", det_params)
                # Actualizar ventas (cabecera)
                cab_parts, cab_params = [], []
                for campo, col in cabecera_col_pg.items():
                    if campo in cambios:
                        cab_parts.append(f"{col} = %s")
                        cab_params.append(cambios[campo])
                if cab_parts:
                    cab_params.append(numero)
                    _db.execute(f"UPDATE ventas SET {', '.join(cab_parts)} WHERE consecutivo = %s", cab_params)
                pg_ok = True
        except Exception as e_pg:
            logger.warning(f"Postgres update falló en /ventas/{numero}: {e_pg}")

        # ── Backup: Excel ─────────────────────────────────────────────────────
        CAMPO_COL = {
            "producto":        ["producto"],
            "cantidad":        ["cantidad"],
            "precio_unitario": ["valor unitario", "precio unitario"],
            "total":           ["total"],
            "metodo_pago":     ["metodo de pago", "metodo pago"],
            "cliente":         ["cliente"],
            "id_cliente":      ["id cliente"],
            "vendedor":        ["vendedor"],
        }
        actualizadas = 0
        try:
            inicializar_excel()
            wb    = openpyxl.load_workbook(config.EXCEL_FILE)
            hojas = [obtener_nombre_hoja(), "Registro de Ventas-Acumulado"]

            for nombre_sh in hojas:
                if nombre_sh not in wb.sheetnames:
                    continue
                ws     = wb[nombre_sh]
                cols   = detectar_columnas(ws)
                col_id = cols.get("consecutivo de venta") or cols.get("alias")
                col_prod = cols.get("producto")
                if not col_id:
                    continue

                for fila in range(config.EXCEL_FILA_DATOS, ws.max_row + 1):
                    val = ws.cell(row=fila, column=col_id).value
                    try:
                        if val is None or int(float(str(val))) != numero:
                            continue
                    except (ValueError, TypeError):
                        continue

                    if filtro_producto and col_prod:
                        prod_fila = str(ws.cell(row=fila, column=col_prod).value or "").strip().lower()
                        if prod_fila != filtro_producto:
                            continue

                    for campo, valor in cambios.items():
                        claves = CAMPO_COL.get(campo, [campo.replace("_", " ")])
                        col_destino = None
                        for clave in claves:
                            col_destino = cols.get(clave)
                            if col_destino:
                                break
                        if col_destino:
                            ws.cell(row=fila, column=col_destino).value = valor
                            actualizadas += 1

            if actualizadas:
                wb.save(config.EXCEL_FILE)
                recalcular_caja_desde_excel()
        except Exception as e_xl:
            logger.warning(f"Excel update falló en /ventas/{numero}: {e_xl}")

        if not pg_ok and not actualizadas:
            return {"ok": False, "mensaje": f"No se encontró el consecutivo #{numero}"}

        return {"ok": True, "actualizadas": actualizadas, "mensaje": f"Venta #{numero} actualizada"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Editar / Eliminar Productos ───────────────────────────────────────────────
# ── Venta Varia ───────────────────────────────────────────────────────────────

class VentaVariaRequest(BaseModel):
    monto: float
    metodo_pago: str          # "efectivo" | "transferencia" | "datafono"
    descripcion: str = "Venta Varia"
    vendedor: str = "Dashboard"


@router.post("/ventas/varia")
async def registrar_venta_varia(req: VentaVariaRequest):
    """
    Registra una venta no especificada para cuadrar caja.
    Usa el mismo mecanismo que el bot: guardar_venta_excel + actualizar caja.
    """
    from ventas_state import registrar_ventas_con_metodo_async

    metodo = req.metodo_pago.strip().lower()
    if metodo not in ("efectivo", "transferencia", "datafono"):
        raise HTTPException(status_code=400, detail=f"Método de pago inválido: {metodo}")

    if req.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    nombre_prod = req.descripcion.strip() or "Venta Varia"
    venta = {
        "producto":        nombre_prod,
        "cantidad":        1,
        "total":           round(req.monto),
        "precio_unitario": round(req.monto),
        "metodo_pago":     metodo,
    }

    try:
        # chat_id=-1 reservado para ventas varias del dashboard
        confirmaciones = await registrar_ventas_con_metodo_async(
            [venta], metodo, req.vendedor, -1
        )
        return {
            "ok": True,
            "mensaje": "Venta varia registrada",
            "detalle": confirmaciones,
        }
    except Exception as e:
        logging.getLogger("ferrebot.api").error(f"[/ventas/varia] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



# ── Transcripción de audio desde el Dashboard ─────────────────────────────────


# ── Export Excel on-demand ─────────────────────────────────────────────────────

@router.get("/export/ventas.xlsx")
def export_ventas_xlsx():
    """
    Genera y descarga un archivo Excel con todas las ventas desde Postgres.
    Una sola hoja plana 'Ventas'. Ordenado por fecha DESC, consecutivo DESC.
    Per D-10, D-11, D-12, D-13.
    """
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        sql = """
            SELECT
                v.consecutivo,
                v.fecha::text          AS fecha,
                COALESCE(v.hora::text, '')          AS hora,
                COALESCE(v.cliente_nombre, 'Consumidor Final') AS cliente,
                d.producto_nombre      AS producto,
                d.cantidad::text       AS cantidad,
                COALESCE(d.unidad_medida, 'Unidad') AS unidad_medida,
                COALESCE(d.precio_unitario, 0)::float AS precio_unitario,
                COALESCE(d.total, 0)::float           AS total,
                COALESCE(v.vendedor, '')    AS vendedor,
                COALESCE(v.metodo_pago, '') AS metodo_pago
            FROM ventas v
            JOIN ventas_detalle d ON d.venta_id = v.id
            ORDER BY v.fecha DESC, v.consecutivo DESC
        """
        rows = _db.query_all(sql, [])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generando export ventas.xlsx: {e}")
        raise HTTPException(status_code=503, detail=f"Error consultando base de datos: {e}")

    # ── Construir Excel en memoria ────────────────────────────────────────────
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"

    COLUMNAS = [
        "consecutivo", "fecha", "hora", "cliente", "producto",
        "cantidad", "unidad_medida", "precio_unitario", "total",
        "vendedor", "metodo_pago",
    ]

    # Encabezados con estilo
    header_font  = Font(bold=True, color="FFFFFF")
    header_fill  = PatternFill("solid", fgColor="1B56E1")
    header_align = Alignment(horizontal="center")
    for col_idx, nombre in enumerate(COLUMNAS, 1):
        celda = ws.cell(row=1, column=col_idx, value=nombre.upper().replace("_", " "))
        celda.font      = header_font
        celda.fill      = header_fill
        celda.alignment = header_align

    # Anchos de columna (aprox)
    anchos = [14, 12, 8, 25, 35, 10, 14, 16, 14, 18, 14]
    for col_idx, ancho in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = ancho

    # Filas de datos
    alt_fill = PatternFill("solid", fgColor="EFF6FF")
    for row_idx, row in enumerate(rows, 2):
        for col_idx, clave in enumerate(COLUMNAS, 1):
            valor = row.get(clave)
            celda = ws.cell(row=row_idx, column=col_idx, value=valor)
            celda.alignment = Alignment(horizontal="center")
            if row_idx % 2 == 0:
                celda.fill = alt_fill
            # Formato numérico para columnas de dinero
            if clave in ("precio_unitario", "total"):
                celda.number_format = "$#,##0.00"

    # ── Serializar a BytesIO ──────────────────────────────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ventas.xlsx"},
    )
