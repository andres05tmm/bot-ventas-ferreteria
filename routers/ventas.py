"""
Router: Ventas — /ventas/* y /venta-rapida

MIGRACIÓN PG-ONLY:
  - Eliminado: _leer_excel_rango, _leer_excel_compras, _stock_wayper de shared
  - Eliminado: json / os / openpyxl / Path (ningún Excel ni memoria.json)
  - venta_rapida: consecutivo vía MAX()+1 PG; unidad_medida vía query PG; sin backup Excel
  - DELETE /ventas y /ventas/linea: PG únicamente; 404 si no existe
  - PATCH /ventas: PG únicamente; sin dual-write Excel
  - GET endpoints: _leer_ventas_postgres obligatorio; 503 si BD no disponible
  - cat_unidad / cat_map: query PG inline, sin memoria.json
"""
from __future__ import annotations

import io
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, Union

import db as _db
import openpyxl
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from pydantic import BaseModel

import config
from routers.shared import (
    _hoy, _hace_n_dias, _leer_ventas_postgres,
    _to_float, _cantidad_a_float,
)
from routers.caja import VentaRapidaPayload, VentaRapidaItem

logger = logging.getLogger("ferrebot.api")

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _require_db():
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")


def _ventas_o_503(dias: int | None = None, mes_actual: bool = False) -> list[dict]:
    """Llama _leer_ventas_postgres y lanza 503 si retorna None."""
    ventas = _leer_ventas_postgres(dias=dias, mes_actual=mes_actual)
    if ventas is None:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    return ventas


def _cat_unidad_map() -> dict[str, str]:
    """Dict nombre_lower → unidad_medida para todos los productos activos (1 query)."""
    rows = _db.query_all(
        "SELECT nombre_lower, unidad_medida FROM productos WHERE activo = TRUE"
    )
    return {r["nombre_lower"]: r["unidad_medida"] or "Unidad" for r in rows}


def _cat_categoria_map() -> dict[str, str]:
    """Dict nombre_lower → categoria para todos los productos activos (1 query)."""
    rows = _db.query_all(
        "SELECT nombre_lower, categoria FROM productos WHERE activo = TRUE"
    )
    return {r["nombre_lower"]: r["categoria"] or "Sin categoría" for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# GET /ventas/hoy
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ventas/hoy")
def ventas_hoy():
    try:
        _require_db()
        hoy      = _hoy()
        ventas   = _ventas_o_503(dias=1)
        filtradas = [v for v in ventas if str(v.get("fecha", ""))[:10] == hoy]

        # Enriquecer unidad_medida faltante desde PG (1 query)
        necesitan = [v for v in filtradas if not v.get("unidad_medida") or v["unidad_medida"] == "Unidad"]
        if necesitan:
            cat_u = _cat_unidad_map()
            for v in necesitan:
                v["unidad_medida"] = cat_u.get(v.get("producto", "").lower().strip(), "Unidad")

        return {"fecha": hoy, "ventas": filtradas, "total": len(filtradas), "fuente": "postgres"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /ventas/semana
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ventas/semana")
def ventas_semana():
    try:
        _require_db()
        ventas = _ventas_o_503(dias=7)
        return {"ventas": ventas, "total": len(ventas)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /ventas/top
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ventas/top")
def ventas_top(periodo: str = Query(default="semana", pattern="^(semana|mes)$")):
    try:
        _require_db()
        dias     = 7 if periodo == "semana" else None
        mes      = periodo == "mes"
        ventas   = _ventas_o_503(dias=dias, mes_actual=mes)
        cat_u    = _cat_unidad_map()

        por_producto: dict[str, dict] = {}
        for v in ventas:
            nombre = str(v.get("producto", "")).strip()
            if not nombre:
                continue
            cantidad = _cantidad_a_float(v.get("cantidad", 0))
            total    = _to_float(v.get("total", 0))
            unidad_v = str(v.get("unidad_medida", "") or "").strip()

            if nombre not in por_producto:
                por_producto[nombre] = {
                    "unidades":      0.0,
                    "ingresos":      0.0,
                    "frecuencia":    0,
                    "unidad_medida": cat_u.get(nombre.lower(), "") or unidad_v or "Unidad",
                }
            por_producto[nombre]["unidades"]   += cantidad
            por_producto[nombre]["ingresos"]   += total
            por_producto[nombre]["frecuencia"] += 1

        ranking = sorted(
            [{"producto": k, **v} for k, v in por_producto.items()],
            key=lambda x: x["ingresos"],
            reverse=True,
        )[:10]
        for i, item in enumerate(ranking, 1):
            item["posicion"] = i

        return {"periodo": periodo, "top": ranking}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /ventas/resumen
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ventas/resumen")
def ventas_resumen():
    try:
        _require_db()
        hoy = _hoy()

        ventas_hoy_list = [v for v in _ventas_o_503(dias=1) if str(v.get("fecha", ""))[:10] == hoy]
        total_hoy   = sum(_to_float(v.get("total", 0)) for v in ventas_hoy_list)
        pedidos_hoy = len({str(v.get("num", i)) for i, v in enumerate(ventas_hoy_list)})

        ventas_sem  = _ventas_o_503(dias=7)
        total_sem   = sum(_to_float(v.get("total", 0)) for v in ventas_sem)
        pedidos_sem = len({str(v.get("num", i)) for i, v in enumerate(ventas_sem)}) or 1
        ticket_prom = round(total_sem / pedidos_sem, 0)

        ventas_por_dia: dict[str, float] = defaultdict(float)
        for v in ventas_sem:
            ventas_por_dia[str(v.get("fecha", ""))[:10]] += _to_float(v.get("total", 0))

        historico = [
            {"fecha": (_hace_n_dias(i)).strftime("%Y-%m-%d"),
             "total": ventas_por_dia.get((_hace_n_dias(i)).strftime("%Y-%m-%d"), 0)}
            for i in range(6, -1, -1)
        ]

        ventas_mes = _ventas_o_503(mes_actual=True)
        total_mes  = sum(_to_float(v.get("total", 0)) for v in ventas_mes)

        ventas_mes_por_dia: dict[str, float] = defaultdict(float)
        for v in ventas_mes:
            ventas_mes_por_dia[str(v.get("fecha", ""))[:10]] += _to_float(v.get("total", 0))

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /ventas/top2
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ventas/top2")
def ventas_top2(
    periodo:  str = Query(default="semana", pattern="^(semana|mes)$"),
    criterio: str = Query(default="ingresos", pattern="^(ingresos|frecuencia|categoria)$"),
):
    try:
        _require_db()
        dias   = 7 if periodo == "semana" else None
        mes    = periodo == "mes"
        ventas = _ventas_o_503(dias=dias, mes_actual=mes)
        cat_m  = _cat_categoria_map()

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
                acum[nombre]["categoria"] = cat_m.get(nombre.lower(), "Sin categoría")

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /venta-rapida
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/venta-rapida")
def venta_rapida(payload: VentaRapidaPayload):
    try:
        _require_db()
        from utils import convertir_fraccion_a_decimal

        # Consecutivo: MAX()+1 directo en PG — sin depender de excel.obtener_siguiente_consecutivo
        row_consec  = _db.query_one("SELECT COALESCE(MAX(consecutivo), 0) + 1 AS next FROM ventas")
        consecutivo = int(row_consec["next"]) if row_consec else 1

        # Unidades desde PG (1 query — sin memoria.json)
        cat_u = _cat_unidad_map()

        def _resolver_unidad(item: VentaRapidaItem) -> str:
            if item.unidad_medida and item.unidad_medida not in ("", "Unidad"):
                return item.unidad_medida
            return cat_u.get(item.nombre.lower().strip(), "Unidad")

        # Pre-calcular items
        items_calc = []
        for item in payload.productos:
            try:
                cant_num = convertir_fraccion_a_decimal(item.cantidad)
            except (ValueError, TypeError):
                cant_num = 1.0
            if not cant_num or cant_num <= 0:
                cant_num = 1.0
            items_calc.append({
                "item":            item,
                "cant_num":        cant_num,
                "precio_unitario": round(item.total / cant_num, 2),
                "unidad":          _resolver_unidad(item),
            })

        # INSERT en PG — fuente única (sin backup Excel)
        ahora = datetime.now(config.COLOMBIA_TZ)
        with _db._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ventas
                        (consecutivo, fecha, hora, vendedor, metodo_pago,
                         total, cliente_nombre, cliente_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (consecutivo, fecha) DO NOTHING
                    RETURNING id
                    """,
                    (
                        consecutivo,
                        ahora.date(),
                        ahora.strftime("%H:%M:%S"),
                        payload.vendedor,
                        payload.metodo,
                        sum(ic["item"].total for ic in items_calc),
                        payload.cliente_nombre or None,
                        int(payload.cliente_id) if payload.cliente_id else None,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=409, detail="Consecutivo duplicado, reintenta")
                venta_id = row["id"]
                for ic in items_calc:
                    cur.execute(
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

        # Descontar inventario (no-fatal)
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
            "fuente":      "postgres",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /ventas/{numero}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/ventas/{numero}")
def eliminar_venta(numero: int):
    """Elimina todas las líneas de un consecutivo directamente en PG."""
    try:
        _require_db()
        borradas = _db.execute(
            "DELETE FROM ventas WHERE consecutivo = %s", [numero]
        )
        if not borradas:
            raise HTTPException(status_code=404, detail=f"Consecutivo #{numero} no encontrado")
        return {"ok": True, "mensaje": f"Venta #{numero} eliminada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /ventas/{numero}/linea
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/ventas/{numero}/linea")
def eliminar_linea_venta(numero: int, producto: str = Query(...)):
    """Elimina UNA sola línea (producto) de un consecutivo multi-producto en PG."""
    try:
        _require_db()
        borradas = _db.execute(
            """
            DELETE FROM ventas_detalle
            WHERE venta_id = (SELECT id FROM ventas WHERE consecutivo = %s LIMIT 1)
              AND LOWER(producto_nombre) = LOWER(%s)
            """,
            [numero, producto],
        )
        if not borradas:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontró '{producto}' en consecutivo #{numero}",
            )
        return {
            "ok":      True,
            "borradas": borradas,
            "mensaje": f"'{producto}' eliminado del consecutivo #{numero}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /ventas/{numero}
# ─────────────────────────────────────────────────────────────────────────────

class EditarVentaBody(BaseModel):
    producto:          Union[str, None]   = None
    cantidad:          Union[float, None] = None
    precio_unitario:   Union[float, None] = None
    total:             Union[float, None] = None
    metodo_pago:       Union[str, None]   = None
    cliente:           Union[str, None]   = None
    id_cliente:        Union[str, None]   = None
    vendedor:          Union[str, None]   = None
    producto_original: Union[str, None]   = None  # filtro para multi-producto


@router.patch("/ventas/{numero}")
def editar_venta(numero: int, body: EditarVentaBody):
    """Edita campos de un consecutivo directamente en PG."""
    try:
        _require_db()
        cambios = {k: v for k, v in body.dict().items() if v is not None and k != "producto_original"}
        if not cambios:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar")

        filtro_producto = body.producto_original.strip().lower() if body.producto_original else None

        # ── ventas_detalle ───────────────────────────────────────────────────
        campo_col_det = {
            "producto":        "producto_nombre",
            "cantidad":        "cantidad",
            "precio_unitario": "precio_unitario",
            "total":           "total",
        }
        det_parts, det_params = [], []
        for campo, col in campo_col_det.items():
            if campo in cambios:
                det_parts.append(f"{col} = %s")
                det_params.append(cambios[campo])

        if det_parts:
            where = "WHERE venta_id = (SELECT id FROM ventas WHERE consecutivo = %s LIMIT 1)"
            if filtro_producto:
                where += " AND LOWER(producto_nombre) = LOWER(%s)"
                det_params += [numero, filtro_producto]
            else:
                det_params.append(numero)
            _db.execute(f"UPDATE ventas_detalle SET {', '.join(det_parts)} {where}", det_params)

        # ── ventas (cabecera) ────────────────────────────────────────────────
        campo_col_cab = {
            "metodo_pago": "metodo_pago",
            "cliente":     "cliente_nombre",
            "vendedor":    "vendedor",
        }
        cab_parts, cab_params = [], []
        for campo, col in campo_col_cab.items():
            if campo in cambios:
                cab_parts.append(f"{col} = %s")
                cab_params.append(cambios[campo])

        if cab_parts:
            cab_params.append(numero)
            _db.execute(
                f"UPDATE ventas SET {', '.join(cab_parts)} WHERE consecutivo = %s",
                cab_params,
            )

        if not det_parts and not cab_parts:
            return {"ok": False, "mensaje": f"No se encontró el consecutivo #{numero}"}

        return {"ok": True, "mensaje": f"Venta #{numero} actualizada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /ventas/varia
# ─────────────────────────────────────────────────────────────────────────────

class VentaVariaRequest(BaseModel):
    monto:       float
    metodo_pago: str
    descripcion: str = "Venta Varia"
    vendedor:    str = "Dashboard"


@router.post("/ventas/varia")
async def registrar_venta_varia(req: VentaVariaRequest):
    """Registra una venta no especificada para cuadrar caja."""
    from ventas_state import registrar_ventas_con_metodo_async

    metodo = req.metodo_pago.strip().lower()
    if metodo not in ("efectivo", "transferencia", "datafono"):
        raise HTTPException(status_code=400, detail=f"Método de pago inválido: {metodo}")
    if req.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    venta = {
        "producto":        req.descripcion.strip() or "Venta Varia",
        "cantidad":        1,
        "total":           round(req.monto),
        "precio_unitario": round(req.monto),
        "metodo_pago":     metodo,
    }
    try:
        confirmaciones = await registrar_ventas_con_metodo_async([venta], metodo, req.vendedor, -1)
        return {"ok": True, "mensaje": "Venta varia registrada", "detalle": confirmaciones}
    except Exception as e:
        logger.error(f"[/ventas/varia] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GET /export/ventas.xlsx
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/export/ventas.xlsx")
def export_ventas_xlsx():
    """Genera y descarga un Excel con todas las ventas desde PostgreSQL."""
    try:
        _require_db()
        rows = _db.query_all(
            """
            SELECT
                v.consecutivo,
                v.fecha::text                                       AS fecha,
                COALESCE(v.hora::text, '')                          AS hora,
                COALESCE(v.cliente_nombre, 'Consumidor Final')      AS cliente,
                d.producto_nombre                                   AS producto,
                d.cantidad::text                                    AS cantidad,
                COALESCE(d.unidad_medida, 'Unidad')                AS unidad_medida,
                COALESCE(d.precio_unitario, 0)::float              AS precio_unitario,
                COALESCE(d.total, 0)::float                        AS total,
                COALESCE(v.vendedor, '')                            AS vendedor,
                COALESCE(v.metodo_pago, '')                        AS metodo_pago
            FROM ventas v
            JOIN ventas_detalle d ON d.venta_id = v.id
            ORDER BY v.fecha DESC, v.consecutivo DESC
            """,
            [],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generando export ventas.xlsx: {e}")
        raise HTTPException(status_code=503, detail=f"Error consultando base de datos: {e}")

    COLUMNAS = [
        "consecutivo", "fecha", "hora", "cliente", "producto",
        "cantidad", "unidad_medida", "precio_unitario", "total",
        "vendedor", "metodo_pago",
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"

    header_font  = Font(bold=True, color="FFFFFF")
    header_fill  = PatternFill("solid", fgColor="1B56E1")
    header_align = Alignment(horizontal="center")
    for col_idx, nombre in enumerate(COLUMNAS, 1):
        celda           = ws.cell(row=1, column=col_idx, value=nombre.upper().replace("_", " "))
        celda.font      = header_font
        celda.fill      = header_fill
        celda.alignment = header_align

    anchos = [14, 12, 8, 25, 35, 10, 14, 16, 14, 18, 14]
    for col_idx, ancho in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = ancho

    alt_fill = PatternFill("solid", fgColor="EFF6FF")
    for row_idx, row in enumerate(rows, 2):
        for col_idx, clave in enumerate(COLUMNAS, 1):
            celda           = ws.cell(row=row_idx, column=col_idx, value=row.get(clave))
            celda.alignment = Alignment(horizontal="center")
            if row_idx % 2 == 0:
                celda.fill = alt_fill
            if clave in ("precio_unitario", "total"):
                celda.number_format = "$#,##0.00"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ventas.xlsx"},
    )
