"""
routers/shared.py
─────────────────
Helpers y utilidades compartidas por todos los routers de la API.
Ningún router debería reimplementar estas funciones — importarlas desde aquí.

Importar con:  from routers.shared import _hoy, _hace_n_dias, ...
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import HTTPException

import config

logger = logging.getLogger("ferrebot.api")

def _hoy() -> str:
    return datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")


def _hace_n_dias(n: int) -> datetime:
    return datetime.now(config.COLOMBIA_TZ) - timedelta(days=n)


# ── Helper: leer ventas históricas (100 % PostgreSQL) ─────────────────────────
def _leer_excel_rango(dias: int | None = None, mes_actual: bool = False) -> list[dict]:
    """
    Nombre mantenido por compatibilidad con los importadores existentes
    (historico.py, clientes.py, chat.py, reportes.py).
    Delega completamente a _leer_ventas_postgres(); sin fallback a Excel.
    """
    return _leer_ventas_postgres(dias=dias, mes_actual=mes_actual) or []


# ── Helper: leer ventas desde Postgres ────────────────────────────────────────
def _leer_ventas_postgres(dias: int | None = None, mes_actual: bool = False) -> list[dict] | None:
    """
    Lee ventas desde PostgreSQL (ventas + ventas_detalle) y devuelve el mismo
    formato de dicts que _leer_excel_rango().

    NOTA: Excluye filas marcadas como sin_detalle=TRUE O cuyo nombre sea
    "Venta Varia" / variantes. Esas son ajustes de caja por excedente de
    dinero no registrado, no son productos reales. Sus montos sí cuentan en
    el total de ventas del día (ventas_resumen los suma directamente desde la
    tabla ventas, sin pasar por aquí).
    """
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return None

        ahora = datetime.now(config.COLOMBIA_TZ)

        sql = """
            SELECT
                v.consecutivo AS num,
                v.fecha::text AS fecha,
                COALESCE(v.hora::text, '') AS hora,
                COALESCE(v.cliente_nombre, 'Consumidor Final') AS cliente,
                CASE WHEN v.cliente_id IS NULL THEN 'CF' ELSE v.cliente_id::text END AS id_cliente,
                d.producto_nombre AS producto,
                d.cantidad::text AS cantidad,
                COALESCE(d.unidad_medida, 'Unidad') AS unidad_medida,
                COALESCE(d.precio_unitario, 0)::float AS precio_unitario,
                COALESCE(d.total, 0)::float AS total,
                COALESCE(d.alias_usado, '') AS alias,
                COALESCE(v.vendedor, '') AS vendedor,
                COALESCE(v.metodo_pago, '') AS metodo
            FROM ventas v
            JOIN ventas_detalle d ON d.venta_id = v.id
            WHERE LOWER(d.producto_nombre) NOT IN (
                'venta varia', 'ventas varia', 'venta general'
            )
            AND (d.sin_detalle IS NULL OR d.sin_detalle = FALSE)
        """
        params: list = []

        if dias is not None:
            fecha_limite = (ahora - timedelta(days=dias)).strftime("%Y-%m-%d")
            sql += " AND v.fecha >= %s"
            params.append(fecha_limite)

        if mes_actual:
            primer_dia = ahora.replace(day=1).strftime("%Y-%m-%d")
            hoy_str    = ahora.strftime("%Y-%m-%d")
            sql += " AND v.fecha >= %s AND v.fecha <= %s"
            params.append(primer_dia)
            params.append(hoy_str)

        sql += " ORDER BY v.fecha, v.consecutivo, d.id"

        rows = _db.query_all(sql, params if params else None)

        result = []
        for r in rows:
            result.append({
                "num":             r["num"],
                "fecha":           str(r["fecha"])[:10],
                "hora":            str(r.get("hora", "")),
                "id_cliente":      str(r.get("id_cliente", "CF")),
                "cliente":         str(r.get("cliente", "Consumidor Final")),
                "codigo_producto": "",
                "producto":        str(r.get("producto", "")),
                "cantidad":        str(r.get("cantidad", "")),
                "unidad_medida":   str(r.get("unidad_medida", "Unidad")) or "Unidad",
                "precio_unitario": float(r.get("precio_unitario", 0)),
                "total":           float(r.get("total", 0)),
                "alias":           str(r.get("alias", "")),
                "vendedor":        str(r.get("vendedor", "")),
                "metodo":          str(r.get("metodo", "")),
            })
        return result

    except Exception as e:
        logger.warning(f"Postgres ventas read failed: {e}")
        return None


# ── Redirección de inventario: productos que se almacenan bajo otra clave ─────
# Formato: clave_producto → (clave_inventario_real, divisor_para_mostrar_stock)
#   Waypers: inventario en UNIDADES, se muestra en kg  (divisor = 12)
#   Carbonato x Kg: inventario en KG en la bolsa, se muestra tal cual (divisor = 1)
_WAYPER_KG_KEYS = {
    "wayper_blanco":   ("wayper_blanco_unidad",  12.0),
    "wayper_de_color": ("wayper_de_color_unidad", 12.0),
    # Carbonato por kilo → stock vive en la bolsa de 25 kg (en kg)
    "carbonato_x_kg":  ("carbonato_x_25_kg",       1.0),
}

def _stock_wayper(key: str, inventario: dict):
    """
    Para productos cuyo inventario vive bajo otra clave, aplica la conversión
    correspondiente y devuelve el stock en la unidad de venta.
    Para el resto devuelve el stock directo.
    """
    if key in _WAYPER_KG_KEYS:
        clave_inv, divisor = _WAYPER_KG_KEYS[key]
        inv_raw = inventario.get(clave_inv)
        if inv_raw is not None:
            cantidad = inv_raw.get("cantidad") if isinstance(inv_raw, dict) else inv_raw
            if cantidad is not None:
                return round(cantidad / divisor, 2)
        return None
    raw = inventario.get(key)
    if raw is None:
        return None
    return raw.get("cantidad") if isinstance(raw, dict) else raw


def _leer_compras(dias: int | None = None) -> list[dict]:
    """
    Lee compras recientes directamente desde PostgreSQL.

    Columnas devueltas (siempre presentes):
        fecha, hora, proveedor, producto, cantidad, costo_unitario, costo_total
    """
    import db as _db

    if not _db.DB_DISPONIBLE:
        return []

    try:
        desde = (
            (datetime.now(config.COLOMBIA_TZ) - timedelta(days=dias)).strftime("%Y-%m-%d")
            if dias
            else None
        )
        sql = """
            SELECT fecha::text,
                   COALESCE(hora::text, '')   AS hora,
                   COALESCE(proveedor, '—')   AS proveedor,
                   producto_nombre             AS producto,
                   cantidad,
                   COALESCE(costo_unitario, 0) AS costo_unitario,
                   COALESCE(costo_total,    0) AS costo_total
            FROM compras
            {where}
            ORDER BY fecha ASC, id ASC
        """.format(where="WHERE fecha >= %s" if desde else "")
        params = (desde,) if desde else None
        rows = _db.query_all(sql, params)
        return [dict(r) for r in rows]
    except Exception as _e:
        logger.warning("_leer_compras PG falló: %s", _e)
        return []


# Alias de compatibilidad — los routers la importan con este nombre.
_leer_excel_compras = _leer_compras


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
