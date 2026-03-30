"""
Router: Reportes — /kardex, /resultados, /proyeccion

Agrupa los endpoints de análisis y reporting:
  - Kárdex de movimientos de inventario
  - Estado de resultados (P&L del período)
  - Proyección de caja
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Union

import config
from memoria import cargar_memoria
from routers.shared import (
    _hoy, _hace_n_dias, _leer_excel_rango, _leer_excel_compras,
    _to_float, _cantidad_a_float, _stock_wayper,
)

logger = logging.getLogger("ferrebot.api")

router = APIRouter()

# ── Kárdex por producto ───────────────────────────────────────────────────────
@router.get("/kardex")
def kardex(q: str = Query(default="")):
    """
    Devuelve el kárdex de movimientos de inventario.
    - Entradas: hoja Compras del Excel + historial_compras de memoria.json
    - Salidas: calculadas como diferencia (entradas - stock actual)
    - Si q != "" filtra por nombre de producto.
    """
    try:
        compras_excel = _leer_excel_compras()

        mem        = cargar_memoria()
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



@router.get("/resultados")
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
        # ventas con detalle (para CMV): excluye "Venta Varia" y sin_detalle
        ventas     = _leer_excel_rango(dias=dias_rango, mes_actual=es_mes)

        # ── Total de ventas REAL desde historico_ventas (misma fuente que Histórico) ─
        # historico_ventas es la fuente de verdad: incluye días registrados
        # manualmente, Venta Varia y sin_detalle. Es exactamente lo que el
        # tab Histórico muestra.
        import db as _db
        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        hoy_str = ahora.strftime("%Y-%m-%d")

        if periodo == "semana":
            fecha_limite_v = (ahora - timedelta(days=7)).strftime("%Y-%m-%d")
            rows_hist = _db.query_all(
                "SELECT fecha::text AS fecha, ventas FROM historico_ventas WHERE fecha >= %s AND fecha <= %s ORDER BY fecha",
                [fecha_limite_v, hoy_str],
            )
        else:
            primer_dia_v = ahora.replace(day=1).strftime("%Y-%m-%d")
            rows_hist = _db.query_all(
                "SELECT fecha::text AS fecha, ventas FROM historico_ventas WHERE fecha >= %s AND fecha <= %s ORDER BY fecha",
                [primer_dia_v, hoy_str],
            )

        ventas_por_dia: dict[str, float] = {str(r["fecha"])[:10]: float(r["ventas"] or 0) for r in rows_hist}

        # Inyectar el total de hoy en vivo desde la tabla ventas
        # (historico_ventas solo se actualiza al cierre del día)
        total_hoy_vivo = float((_db.query_one(
            "SELECT COALESCE(SUM(total), 0)::float AS t FROM ventas WHERE fecha = %s",
            [hoy_str],
        ) or {}).get("t", 0))
        if total_hoy_vivo > 0:
            ventas_por_dia[hoy_str] = total_hoy_vivo

        total_ventas = sum(ventas_por_dia.values())

        # ── 2. CMV ───────────────────────────────────────────────────────────
        # Costo de lo vendido = unidades vendidas × costo_promedio del producto
        mem        = cargar_memoria()
        inventario = mem.get("inventario", {})

        # Índice de inventario por nombre normalizado
        inv_idx: dict[str, dict] = {}
        for clave, datos in inventario.items():
            if isinstance(datos, dict):
                nombre_n = datos.get("nombre_original", "").lower().strip()
                inv_idx[nombre_n] = datos
                inv_idx[clave.replace("_", " ")] = datos

        # Agrupar ventas por producto
        # Excluir "Venta Varia": es un ajuste de caja por excedente de dinero
        # no registrado, no es un producto real del catálogo.
        _EXCLUIR_PRODUCTOS = {"venta varia", "ventas varia", "venta general"}
        ventas_prod: dict[str, dict] = defaultdict(lambda: {"cantidad": 0.0, "ingresos": 0.0})
        for v in ventas:
            nombre = str(v.get("producto", "")).strip()
            if not nombre or nombre.lower() in _EXCLUIR_PRODUCTOS:
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
@router.get("/proyeccion")
def proyeccion():
    """
    Proyecta el cierre del mes basándose en promedios de los últimos 14 días.
    Proyección = efectivo_actual + (ingreso_diario_prom - gasto_diario_prom) × días_restantes
    """
    try:
        ahora     = datetime.now(config.COLOMBIA_TZ)
        mem       = cargar_memoria()
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


class StockUpdate(BaseModel):
    stock: Union[float, int, None]

