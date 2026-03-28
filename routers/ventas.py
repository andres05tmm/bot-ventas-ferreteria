"""
Router: Ventas — /ventas/* y /venta-rapida
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Union

import config
from memoria import cargar_memoria
from routers.shared import (
    _hoy, _hace_n_dias, _leer_ventas_postgres,
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

        try:
            pg_ventas = _leer_ventas_postgres(dias=1)
            filtradas = [v for v in pg_ventas if str(v.get("fecha", ""))[:10] == hoy]
        except Exception as e_pg:
            raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {e_pg}")

        # Enriquecer con unidad_medida desde el catálogo (solo si falta)
        try:
            necesitan = [v for v in filtradas if not v.get("unidad_medida") or v["unidad_medida"] == "Unidad"]
            if necesitan:
                catalogo = cargar_memoria().get("catalogo", {})

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

        return {"fecha": hoy, "ventas": filtradas, "total": len(filtradas), "fuente": "postgres"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/semana")
def ventas_semana():
    try:
        ventas = _leer_ventas_postgres(dias=7)
        if ventas is None:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")
        return {"ventas": ventas, "total": len(ventas)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ventas/top")
def ventas_top(periodo: str = Query(default="semana", pattern="^(semana|mes)$")):
    try:
        dias = 7 if periodo == "semana" else None
        mes = periodo == "mes"
        ventas = _leer_ventas_postgres(dias=dias, mes_actual=mes)
        if ventas is None:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        cat_unidad: dict[str, str] = {}
        for prod in cargar_memoria().get("catalogo", {}).values():
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


@router.get("/ventas/resumen")
def ventas_resumen():
    """
    Resumen para las tarjetas del dashboard. 100 % PostgreSQL, sin fallbacks.
    """
    import db as _db

    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    try:
        hoy         = _hoy()
        ahora_local = datetime.now(config.COLOMBIA_TZ)

        row_hoy = _db.query_one(
            """
            SELECT
                COALESCE(SUM(d.total), 0)          AS total_hoy,
                COUNT(DISTINCT v.id)               AS pedidos_hoy,
                COUNT(DISTINCT v.consecutivo)      AS n_transacciones
            FROM ventas v
            JOIN ventas_detalle d ON d.venta_id = v.id
            WHERE v.fecha = %s
            """,
            [hoy],
        )
        total_hoy   = _to_float(row_hoy["total_hoy"])   if row_hoy else 0.0
        pedidos_hoy = int(row_hoy["pedidos_hoy"])        if row_hoy else 0

        fecha_7d  = _hace_n_dias(7).strftime("%Y-%m-%d")
        rows_sem  = _db.query_all(
            "SELECT fecha::text AS fecha, ventas FROM historico_ventas WHERE fecha >= %s ORDER BY fecha",
            [fecha_7d],
        )
        ventas_por_dia = {str(r["fecha"])[:10]: _to_float(r["ventas"]) for r in rows_sem}
        total_sem = sum(ventas_por_dia.values())

        row_tick = _db.query_one(
            "SELECT COUNT(DISTINCT id) AS n FROM ventas WHERE fecha >= %s",
            [fecha_7d],
        )
        pedidos_sem = int(row_tick["n"]) if row_tick and row_tick["n"] else 1
        ticket_prom = round(total_sem / pedidos_sem, 0)

        historico = [
            {"fecha": _hace_n_dias(i).strftime("%Y-%m-%d"),
             "total": ventas_por_dia.get(_hace_n_dias(i).strftime("%Y-%m-%d"), 0)}
            for i in range(6, -1, -1)
        ]

        primer_dia_mes = ahora_local.replace(day=1).strftime("%Y-%m-%d")
        rows_mes = _db.query_all(
            "SELECT fecha::text AS fecha, ventas FROM historico_ventas WHERE fecha >= %s ORDER BY fecha",
            [primer_dia_mes],
        )
        ventas_mes_por_dia = {str(r["fecha"])[:10]: _to_float(r["ventas"]) for r in rows_mes}
        total_mes = sum(ventas_mes_por_dia.values())

        historico_mes = []
        current = ahora_local.replace(day=1)
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


@router.post("/venta-rapida")
def venta_rapida(payload: VentaRapidaPayload):
    try:
        import db as _db
        import datetime as _dt

        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        _catalogo_cache = {}
        try:
            _catalogo_cache = cargar_memoria().get("catalogo", {})
        except Exception:
            pass

        def _resolver_unidad(item: VentaRapidaItem) -> str:
            if item.unidad_medida and item.unidad_medida not in ("", "Unidad"):
                return item.unidad_medida
            nombre_norm = item.nombre.lower().strip()
            for prod_key, prod_val in _catalogo_cache.items():
                if prod_val.get("nombre", "").lower().strip() == nombre_norm or prod_key == nombre_norm.replace(" ", "_"):
                    return prod_val.get("unidad_medida", "Unidad")
            return item.unidad_medida or "Unidad"

        items_calc = []
        for item in payload.productos:
            try:
                from utils import convertir_fraccion_a_decimal
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

        ahora = _dt.datetime.now()

        with _db._get_conn() as conn:
            with conn.cursor() as cur:
                # Consecutivo atómico desde PG
                cur.execute("SELECT COALESCE(MAX(consecutivo), 0) + 1 AS siguiente FROM ventas")
                consecutivo = cur.fetchone()["siguiente"]

                cur.execute(
                    """
                    INSERT INTO ventas
                        (consecutivo, fecha, vendedor, metodo_pago,
                         total, cliente_nombre, cliente_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                venta_id = cur.fetchone()["id"]

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
            conn.commit()

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
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        cat_map: dict[str, str] = {}
        for v in cargar_memoria().get("catalogo", {}).values():
                nombre_lower = v.get("nombre_lower", "").strip()
                cat_map[nombre_lower] = v.get("categoria", "Sin categoría")

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


@router.delete("/ventas/{numero}")
def eliminar_venta(numero: int):
    """
    Elimina todas las filas de un consecutivo de venta.
    """
    try:
        import db as _db

        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

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


@router.delete("/ventas/{numero}/linea")
def eliminar_linea_venta(numero: int, producto: str = Query(...)):
    """
    Elimina UNA sola línea (producto) de un consecutivo multi-producto.
    """
    try:
        import db as _db

        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

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

        return {"ok": True, "borradas": borradas, "mensaje": f"'{producto}' eliminado del consecutivo #{numero}"}
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
    Edita los campos de un consecutivo. 100% Postgres.
    """
    try:
        import db as _db

        if not _db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        cambios = {k: v for k, v in body.dict().items() if v is not None and k != "producto_original"}
        if not cambios:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar")

        filtro_producto = body.producto_original.strip().lower() if body.producto_original else None

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
                det_params.extend([numero, filtro_producto])
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

        return {"ok": True, "mensaje": f"Venta #{numero} actualizada"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Venta Varia ───────────────────────────────────────────────────────────────

class VentaVariaRequest(BaseModel):
    monto: float
    metodo_pago: str
    descripcion: str = "Venta Varia"
    vendedor: str = "Dashboard"


@router.post("/ventas/varia")
async def registrar_venta_varia(req: VentaVariaRequest):
    """
    Registra una venta no especificada para cuadrar caja.
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


# ── Export Excel on-demand ─────────────────────────────────────────────────────

@router.get("/export/ventas.xlsx")
def export_ventas_xlsx():
    """
    Genera y descarga un archivo Excel con todas las ventas desde Postgres.
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

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"

    COLUMNAS = [
        "consecutivo", "fecha", "hora", "cliente", "producto",
        "cantidad", "unidad_medida", "precio_unitario", "total",
        "vendedor", "metodo_pago",
    ]

    header_font  = Font(bold=True, color="FFFFFF")
    header_fill  = PatternFill("solid", fgColor="1B56E1")
    header_align = Alignment(horizontal="center")
    for col_idx, nombre in enumerate(COLUMNAS, 1):
        celda = ws.cell(row=1, column=col_idx, value=nombre.upper().replace("_", " "))
        celda.font      = header_font
        celda.fill      = header_fill
        celda.alignment = header_align

    anchos = [14, 12, 8, 25, 35, 10, 14, 16, 14, 18, 14]
    for col_idx, ancho in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = ancho

    alt_fill = PatternFill("solid", fgColor="EFF6FF")
    for row_idx, row in enumerate(rows, 2):
        for col_idx, clave in enumerate(COLUMNAS, 1):
            valor = row.get(clave)
            celda = ws.cell(row=row_idx, column=col_idx, value=valor)
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
