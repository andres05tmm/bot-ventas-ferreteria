"""
Router: Catálogo — /catalogo/*, /productos, /inventario/*, /kardex
MIGRADO A SQL: PostgreSQL es la única fuente de verdad.
               Sin MEMORIA_FILE, sin Drive, sin Excel.

MIGRACIÓN PG-ONLY v2:
  - Eliminado: from precio_sync import _normalizar_unidad
  - Inlineado: _UNIDAD_MAP + _normalizar_unidad (8 líneas) directamente en este módulo
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

import db
from routers.shared import _hace_n_dias
from routers.deps import get_current_user, get_filtro_efectivo
from routers.events import notify_all

logger = logging.getLogger("ferrebot.api")

router = APIRouter()

# ── Fracciones estándar para pinturas/impermeabilizantes ─────────────────────
_FRACS_GALON = [
    ("3/4", 0.75), ("1/2", 0.5), ("1/4", 0.25),
    ("1/8", 0.125), ("1/16", 0.0625), ("1/10", 0.1),
]

# ── Normalización de unidades de medida (DIAN) ────────────────────────────────
_UNIDAD_MAP: dict[str, str] = {
    # galón
    "galon": "Galón", "galón": "Galón", "gal": "Galón",
    # kilogramo
    "kg": "Kg", "kgs": "Kg", "kilo": "Kg",
    "kilos": "Kg", "kilogramo": "Kg", "25 kg": "Kg",
    # metro
    "mts": "Mts", "mt": "Mts", "metro": "Mts",
    "metros": "Mts", "m": "Mts",
    # centímetro
    "cms": "Cms", "cm": "Cms", "centimetro": "Cms",
    # litro
    "lt": "Lt", "lts": "Lts", "litro": "Lt", "litros": "Lts",
    # mililitro — código DIAN: MLT
    "ml": "MLT", "mlt": "MLT", "mililitro": "MLT",
    "mililitros": "MLT", "cc": "MLT", "centimetro cubico": "MLT",
    # unidad (por defecto)
    "unidad": "Unidad", "und": "Unidad", "un": "Unidad",
    "unidades": "Unidad", "uni": "Unidad",
}


def _normalizar_unidad(raw: str) -> str:
    """Normaliza texto de unidad de medida → etiqueta canónica DIAN."""
    if not raw:
        return "Unidad"
    clave = raw.strip().lower().replace("á", "a").replace("é", "e").replace("ó", "o")
    return _UNIDAD_MAP.get(clave, raw.strip()) or "Unidad"


def _parse_fraccion_decimal(frac_str: str) -> float:
    """Convierte '1/4' → 0.25, '0.5' → 0.5. No lanza ValueError."""
    try:
        if "/" in frac_str:
            num, den = frac_str.split("/", 1)
            return int(num.strip()) / int(den.strip())
        return float(frac_str)
    except Exception:
        return 0.0


# =============================================================================
# GET /productos
# =============================================================================
@router.get("/productos")
def productos(current_user=Depends(get_current_user)):
    try:
        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        prods = db.query_all(
            """
            SELECT p.id, p.clave, p.nombre, p.categoria, p.precio_unidad,
                   p.codigo, p.unidad_medida,
                   i.cantidad AS stock,
                   p.precio_umbral AS umbral, p.precio_sobre_umbral
            FROM productos p
            LEFT JOIN inventario i ON i.producto_id = p.id
            WHERE p.activo = TRUE
            ORDER BY p.nombre
            """
        )

        fracs_all = db.query_all(
            "SELECT producto_id, fraccion, precio_total FROM productos_fracciones"
        )
        fracs_map: dict[int, dict] = {}
        for r in fracs_all:
            fracs_map.setdefault(r["producto_id"], {})[r["fraccion"]] = {
                "precio": r["precio_total"]
            }

        lista = []
        for v in prods:
            pid    = v["id"]
            precio = v["precio_unidad"] or 0
            fracs  = fracs_map.get(pid) or {}

            if not fracs and precio > 0:
                cat_lower = (v["categoria"] or "").lower()
                if "pintura" in cat_lower or "disolvente" in cat_lower or "impermeab" in cat_lower:
                    fracs = {
                        label: {"precio": round(precio * dec), "decimal": dec}
                        for label, dec in _FRACS_GALON
                    }

            mayorista = None
            if v["umbral"]:
                mayorista = {"umbral": v["umbral"], "precio": v["precio_sobre_umbral"] or 0}

            lista.append({
                "key":              v["clave"],
                "nombre":           v["nombre"],
                "categoria":        v["categoria"] or "Sin categoría",
                "precio":           precio,
                "codigo":           v["codigo"] or "",
                "stock":            float(v["stock"]) if v["stock"] is not None else None,
                "precios_fraccion": fracs or None,
                "unidad_medida":    v["unidad_medida"] or "Unidad",
                "mayorista":        mayorista,
            })
        return {"productos": lista, "total": len(lista)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /productos/frecuentes
# =============================================================================
@router.get("/productos/frecuentes")
def productos_frecuentes(
    limit: int = Query(default=12, ge=1, le=50),
    filtro: int | None = Depends(get_filtro_efectivo),
    current_user=Depends(get_current_user),
):
    """Retorna los N productos más vendidos en los últimos 30 días (por frecuencia de venta)."""
    try:
        params: list = []
        filtro_sql = ""
        if filtro is not None:
            filtro_sql = "AND v.usuario_id = %s"
            params.append(filtro)
        params.append(limit)

        rows = db.query_all(
            f"""
            SELECT p.clave AS key, p.nombre,
                   COUNT(*) AS frecuencia,
                   COALESCE(SUM(vd.cantidad), 0) AS total_unidades
            FROM ventas_detalle vd
            JOIN productos p ON p.id = vd.producto_id
            JOIN ventas v ON v.id = vd.venta_id
            WHERE v.fecha >= NOW() - INTERVAL '30 days'
              AND p.activo = TRUE
              AND p.precio_unidad > 0
              {filtro_sql}
            GROUP BY p.id, p.clave, p.nombre
            ORDER BY COUNT(*) DESC
            LIMIT %s
            """,
            params,
        )
        return {"frecuentes": [dict(r) for r in rows]}
    except Exception as e:
        logger.warning(f"productos_frecuentes: {e}")
        return {"frecuentes": []}


# =============================================================================
# GET /inventario/bajo
# =============================================================================
@router.get("/inventario/bajo")
def inventario_bajo(current_user=Depends(get_current_user)):
    try:
        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        rows = db.query_all(
            """
            SELECT p.clave AS key, p.nombre, p.categoria,
                   p.precio_unidad AS precio,
                   i.cantidad AS stock
            FROM productos p
            LEFT JOIN inventario i ON i.producto_id = p.id
            WHERE p.activo = TRUE
              AND (
                    p.precio_unidad IS NULL
                 OR p.precio_unidad = 0
                 OR i.cantidad = 0
                 OR i.cantidad IS NULL
              )
            ORDER BY p.nombre
            """
        )
        alertas = []
        for r in rows:
            sin_precio = not r["precio"]
            alertas.append({
                "key":       r["key"],
                "nombre":    r["nombre"],
                "categoria": r["categoria"] or "",
                "precio":    r["precio"] or 0,
                "stock":     float(r["stock"]) if r["stock"] is not None else None,
                "motivo":    "sin_precio" if sin_precio else "stock_cero",
            })
        return {"alertas": alertas, "total": len(alertas)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /catalogo/nav
# =============================================================================
@router.get("/catalogo/nav")
def catalogo_nav(q: str = Query(default=""), current_user=Depends(get_current_user)):
    try:
        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        q_lower = q.strip().lower()

        rows = db.query_all(
            """
            SELECT p.id, p.clave, p.nombre, p.categoria, p.precio_unidad,
                   p.codigo, p.unidad_medida,
                   i.cantidad AS stock, i.costo_promedio,
                   p.precio_umbral AS umbral, p.precio_sobre_umbral
            FROM productos p
            LEFT JOIN inventario i ON i.producto_id = p.id
            WHERE p.activo = TRUE
            ORDER BY p.nombre
            """
        )

        fracs_all = db.query_all(
            "SELECT producto_id, fraccion, precio_total FROM productos_fracciones"
        )
        fracs_map: dict[int, dict] = {}
        for r in fracs_all:
            fracs_map.setdefault(r["producto_id"], {})[r["fraccion"]] = r["precio_total"]

        _cat_canonical: dict[str, str] = {}
        categorias: dict[str, list]    = defaultdict(list)

        for v in rows:
            nombre = v["nombre"]
            if q_lower and q_lower not in nombre.lower() and q_lower not in (v["codigo"] or "").lower():
                continue

            cat_raw   = v["categoria"] or "Sin categoría"
            cat_lower = cat_raw.lower()
            if cat_lower not in _cat_canonical:
                _cat_canonical[cat_lower] = cat_raw
            categoria = _cat_canonical[cat_lower]

            mayorista = None
            if v["umbral"]:
                mayorista = {"umbral": v["umbral"], "precio": v["precio_sobre_umbral"] or 0}

            categorias[categoria].append({
                "key":           v["clave"],
                "nombre":        nombre,
                "codigo":        v["codigo"] or "",
                "precio":        v["precio_unidad"] or 0,
                "stock":         float(v["stock"]) if v["stock"] is not None else None,
                "costo":         float(v["costo_promedio"]) if v["costo_promedio"] else None,
                "fracciones":    fracs_map.get(v["id"], {}),
                "mayorista":     mayorista,
                "unidad_medida": v["unidad_medida"] or "Unidad",
            })

        result = {}
        for cat in sorted(
            categorias.keys(),
            key=lambda c: (int(c.split()[0]) if c and c[0].isdigit() else 999),
        ):
            result[cat] = sorted(categorias[cat], key=lambda p: p["nombre"].lower())

        total = sum(len(v) for v in result.values())
        return {"categorias": result, "total": total, "query": q}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GET /kardex
# =============================================================================
def _kardex_item(prod_id: int, prod_nombre: str, dias: int) -> dict:
    """Construye el dict de un producto para la respuesta /kardex."""
    fecha_inicio = _hace_n_dias(dias)

    compras = db.query_all(
        """
        SELECT fecha, proveedor, cantidad, costo_unitario, costo_total
        FROM compras
        WHERE producto_id = %s AND fecha >= %s
        ORDER BY fecha ASC, id ASC
        """,
        [prod_id, fecha_inicio],
    )
    ventas = db.query_all(
        """
        SELECT v.fecha, v.consecutivo, v.cliente_nombre,
               vd.cantidad, vd.precio_unitario, vd.total
        FROM ventas_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        WHERE vd.producto_id = %s AND v.fecha >= %s
        ORDER BY v.fecha ASC, v.id ASC
        """,
        [prod_id, fecha_inicio],
    )
    inv_row = db.query_one(
        "SELECT cantidad, costo_promedio FROM inventario WHERE producto_id = %s",
        [prod_id],
    )
    stock_actual    = float(inv_row["cantidad"])     if inv_row else 0.0
    costo_prom_act  = float(inv_row["costo_promedio"]) if inv_row else 0.0

    # Unificar movimientos (ascendente para calcular saldo corriente)
    movs_raw: list[dict] = []
    for c in compras:
        movs_raw.append({
            "tipo":          "entrada",
            "fecha_sort":    c["fecha"],
            "fecha":         str(c["fecha"])[:10] if c["fecha"] else "",
            "hora":          str(c["fecha"])[11:16] if c["fecha"] and len(str(c["fecha"])) > 10 else "",
            "concepto":      f"Compra — {c['proveedor'] or 'Proveedor'}",
            "entrada":       float(c["cantidad"] or 0),
            "salida":        0.0,
            "costo_unitario": float(c["costo_unitario"] or 0),
        })
    for v in ventas:
        movs_raw.append({
            "tipo":          "salida",
            "fecha_sort":    v["fecha"],
            "fecha":         str(v["fecha"])[:10] if v["fecha"] else "",
            "hora":          str(v["fecha"])[11:16] if v["fecha"] and len(str(v["fecha"])) > 10 else "",
            "concepto":      f"Venta #{v['consecutivo']} — {v['cliente_nombre'] or 'Cliente'}",
            "entrada":       0.0,
            "salida":        float(v["cantidad"] or 0),
            "costo_unitario": costo_prom_act,
        })

    movs_raw.sort(key=lambda x: (x["fecha_sort"] or "", x["tipo"]))

    # Calcular saldo corriente y costo promedio por movimiento (ascendente)
    saldo          = 0.0
    costo_prom_cur = costo_prom_act
    for m in movs_raw:
        if m["tipo"] == "entrada":
            nueva_cant   = saldo + m["entrada"]
            if nueva_cant > 0:
                costo_prom_cur = (
                    (saldo * costo_prom_cur + m["entrada"] * m["costo_unitario"]) / nueva_cant
                )
            saldo = nueva_cant
        else:
            saldo = max(0.0, saldo - m["salida"])
        m["saldo"]         = round(saldo, 4)
        m["costo_promedio"] = round(costo_prom_cur, 2)
        m["valor_total"]   = round(
            m["entrada"] * m["costo_unitario"] if m["tipo"] == "entrada"
            else m["salida"] * costo_prom_cur,
            2,
        )
        del m["fecha_sort"]

    total_entradas = sum(m["entrada"] for m in movs_raw)
    salidas_est    = max(0.0, round(total_entradas - stock_actual, 4))

    return {
        "producto":         prod_nombre,
        "movimientos":      list(reversed(movs_raw)),  # más reciente primero
        "total_entradas":   round(total_entradas, 4),
        "salidas_est":      salidas_est,
        "stock_actual":     round(stock_actual, 4),
        "costo_promedio":   round(costo_prom_act, 2),
        "valor_inventario": round(stock_actual * costo_prom_act, 2),
    }


@router.get("/kardex")
def kardex(
    producto: Optional[str] = Query(None, description="Nombre o key del producto (opcional)"),
    dias: int                = Query(30,   description="Días hacia atrás"),
    current_user             = Depends(get_current_user)
):
    """
    Kardex de inventario desde PostgreSQL.
    Sin parámetros → todos los productos activos con stock o historial de compras.
    Con ?producto=... → filtrado por ese producto.
    """
    try:
        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        if producto:
            # ── Modo filtrado ──────────────────────────────────────────────
            from memoria import buscar_producto_en_catalogo
            prod = buscar_producto_en_catalogo(producto)
            if not prod:
                raise HTTPException(status_code=404, detail=f"Producto '{producto}' no encontrado")
            prod_row = db.query_one(
                "SELECT id FROM productos WHERE nombre_lower = %s AND activo = TRUE",
                [prod["nombre_lower"]],
            )
            if not prod_row:
                raise HTTPException(status_code=404, detail="Producto no encontrado en BD")
            items = [_kardex_item(prod_row["id"], prod["nombre"], dias)]
        else:
            # ── Todos los productos con historial de compras ───────────────
            prods = db.query_all(
                """
                SELECT DISTINCT p.id, p.nombre
                FROM productos p
                JOIN compras c ON c.producto_id = p.id
                WHERE p.activo = TRUE
                ORDER BY p.nombre
                """,
                [],
            )
            items = [_kardex_item(r["id"], r["nombre"], dias) for r in prods]

        tiene_datos     = len(items) > 0
        valor_inv_total = sum(i["valor_inventario"] for i in items)

        return {
            "kardex":                items,
            "valor_inventario_total": round(valor_inv_total, 2),
            "tiene_datos":           tiene_datos,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Modelos Pydantic
# =============================================================================
class PrecioUpdate(BaseModel):
    precio: Union[float, int]

class FraccionesUpdate(BaseModel):
    fracciones: dict

class MayoristaUpdate(BaseModel):
    precio: Union[float, int]
    umbral: Optional[int] = None

class NuevoProducto(BaseModel):
    nombre:           str
    categoria:        str
    precio_unidad:    Union[float, int]
    unidad_medida:    str  = "Unidad"
    codigo:           str  = ""
    stock_inicial:    Union[float, int, None] = None
    codigo_dian:      str  = "94"
    inventariable:    bool = True
    visible_facturas: bool = True
    stock_minimo:     int  = 0

class StockUpdate(BaseModel):
    stock: Union[float, int, None]

class EditarProductoBody(BaseModel):
    nombre:        Union[str, None]   = None
    categoria:     Union[str, None]   = None
    precio_unidad: Union[float, None] = None
    unidad_medida: Union[str, None]   = None
    codigo:        Union[str, None]   = None


# =============================================================================
# POST /catalogo — crear producto
# =============================================================================
@router.post("/catalogo")
async def crear_producto(body: NuevoProducto):
    """Crea un producto nuevo directamente en PostgreSQL."""
    try:
        from utils import _normalizar
        from memoria import invalidar_cache_memoria

        if not body.nombre.strip():
            raise HTTPException(status_code=400, detail="El nombre es obligatorio")
        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        key_base = _normalizar(body.nombre.strip()).replace(" ", "_")
        key      = key_base
        sufijo   = 2
        while db.query_one("SELECT 1 FROM productos WHERE clave = %s", [key]):
            key    = f"{key_base}_{sufijo}"
            sufijo += 1

        unidad_norm = _normalizar_unidad(body.unidad_medida)

        row_pg = db.execute_returning(
            """
            INSERT INTO productos
                (clave, nombre, nombre_lower, codigo, categoria,
                 precio_unidad, unidad_medida)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (clave) DO UPDATE SET
                nombre        = EXCLUDED.nombre,
                nombre_lower  = EXCLUDED.nombre_lower,
                codigo        = EXCLUDED.codigo,
                categoria     = EXCLUDED.categoria,
                precio_unidad = EXCLUDED.precio_unidad,
                unidad_medida = EXCLUDED.unidad_medida,
                updated_at    = NOW()
            RETURNING id
            """,
            (
                key,
                body.nombre.strip(),
                _normalizar(body.nombre.strip()),
                body.codigo.strip() or None,
                body.categoria.strip(),
                int(body.precio_unidad),
                unidad_norm,
            ),
        )
        if not row_pg:
            raise HTTPException(status_code=500, detail="No se pudo insertar el producto")

        if body.stock_inicial is not None:
            db.execute(
                """
                INSERT INTO inventario (producto_id, cantidad, minimo, unidad)
                VALUES (%s, %s, %s, 'und')
                ON CONFLICT (producto_id) DO UPDATE
                    SET cantidad = EXCLUDED.cantidad
                """,
                (row_pg["id"], float(body.stock_inicial), body.stock_minimo or 0),
            )

        invalidar_cache_memoria()

        return {
            "ok":            True,
            "key":           key,
            "nombre":        body.nombre.strip(),
            "categoria":     body.categoria.strip(),
            "precio_unidad": int(body.precio_unidad),
            "unidad_medida": unidad_norm,
            "stock_inicial": body.stock_inicial,
            "pg_guardado":   True,
        }
        await notify_all("inventario_actualizado", {"accion": "producto_creado", "key": key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PATCH /catalogo/{key}/precio
# =============================================================================
@router.patch("/catalogo/{key:path}/precio")
async def actualizar_precio_endpoint(key: str, body: PrecioUpdate):
    """Actualiza precio_unidad directamente en PostgreSQL."""
    try:
        from memoria import invalidar_cache_memoria

        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        row = db.query_one(
            "SELECT id, nombre, precio_unidad FROM productos WHERE clave = %s AND activo = TRUE",
            [key],
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        nuevo_precio = int(body.precio)
        db.execute(
            "UPDATE productos SET precio_unidad = %s, updated_at = NOW() WHERE clave = %s",
            [nuevo_precio, key],
        )
        invalidar_cache_memoria()

        return {
            "ok":              True,
            "key":             key,
            "nombre":          row["nombre"],
            "precio_anterior": row["precio_unidad"],
            "precio_nuevo":    nuevo_precio,
            "pg_actualizado":  True,
        }
        await notify_all("inventario_actualizado", {"accion": "precio_actualizado", "key": key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PATCH /catalogo/{key}/fracciones
# =============================================================================
@router.patch("/catalogo/{key:path}/fracciones")
async def actualizar_fracciones(key: str, body: FraccionesUpdate):
    """Actualiza precios_fraccion en productos_fracciones (PostgreSQL)."""
    try:
        from memoria import invalidar_cache_memoria

        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        row_prod = db.query_one(
            "SELECT id, nombre FROM productos WHERE clave = %s AND activo = TRUE", [key]
        )
        if not row_prod:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        prod_id = row_prod["id"]

        fracs_norm: dict[str, dict] = {}
        for k, v in body.fracciones.items():
            fracs_norm[k] = v if isinstance(v, dict) else {"precio": int(v)}

        precio_unidad_nuevo = None
        if "1" in fracs_norm:
            val = fracs_norm["1"]
            precio_unidad_nuevo = val.get("precio") if isinstance(val, dict) else int(val)

        for frac_key, frac_val in fracs_norm.items():
            precio_frac = frac_val["precio"] if isinstance(frac_val, dict) else int(frac_val)
            decimal_val = _parse_fraccion_decimal(frac_key)
            precio_unit = round(precio_frac / decimal_val) if decimal_val else precio_frac

            db.execute(
                """
                INSERT INTO productos_fracciones
                    (producto_id, fraccion, precio_total, precio_unitario)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT uq_prod_fraccion DO UPDATE
                SET precio_total    = EXCLUDED.precio_total,
                    precio_unitario = EXCLUDED.precio_unitario
                """,
                (prod_id, frac_key, precio_frac, int(precio_unit)),
            )

        if precio_unidad_nuevo:
            db.execute(
                "UPDATE productos SET precio_unidad = %s, updated_at = NOW() WHERE id = %s",
                [precio_unidad_nuevo, prod_id],
            )

        invalidar_cache_memoria()

        return {
            "ok":             True,
            "key":            key,
            "nombre":         row_prod["nombre"],
            "fracciones":     fracs_norm,
            "pg_actualizado": True,
        }
        await notify_all("inventario_actualizado", {"accion": "fracciones_actualizadas", "key": key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PATCH /catalogo/{key}/mayorista
# =============================================================================
@router.patch("/catalogo/{key:path}/mayorista")
async def actualizar_mayorista(key: str, body: MayoristaUpdate):
    """Actualiza precio_por_cantidad directamente en PostgreSQL."""
    try:
        from memoria import invalidar_cache_memoria

        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        row_prod = db.query_one(
            "SELECT id, nombre, precio_unidad FROM productos WHERE clave = %s AND activo = TRUE",
            [key],
        )
        if not row_prod:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        # Leer valores actuales de columnas inline de productos
        prod_actual = db.query_one(
            "SELECT precio_umbral, precio_bajo_umbral FROM productos WHERE id = %s",
            [row_prod["id"]],
        )
        umbral      = body.umbral if body.umbral else (prod_actual["precio_umbral"] if prod_actual and prod_actual["precio_umbral"] else 50)
        precio_bajo = prod_actual["precio_bajo_umbral"] if prod_actual and prod_actual["precio_bajo_umbral"] else (row_prod["precio_unidad"] or 0)
        precio_sobre = int(body.precio)

        db.execute(
            """
            UPDATE productos
            SET precio_umbral       = %s,
                precio_bajo_umbral  = %s,
                precio_sobre_umbral = %s,
                updated_at          = NOW()
            WHERE id = %s
            """,
            (umbral, precio_bajo, precio_sobre, row_prod["id"]),
        )
        invalidar_cache_memoria()

        return {
            "ok":               True,
            "key":              key,
            "nombre":           row_prod["nombre"],
            "precio_mayorista": precio_sobre,
            "umbral":           umbral,
            "pg_actualizado":   True,
        }
        await notify_all("inventario_actualizado", {"accion": "mayorista_actualizado", "key": key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PATCH /inventario/{key}/stock
# =============================================================================
@router.patch("/inventario/{key:path}/stock")
async def actualizar_stock(key: str, body: StockUpdate):
    """Actualiza cantidad en inventario directamente en PostgreSQL."""
    try:
        from memoria import invalidar_cache_memoria

        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        row_prod = db.query_one(
            "SELECT id, nombre FROM productos WHERE clave = %s AND activo = TRUE", [key]
        )
        if not row_prod:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        inv_actual     = db.query_one(
            "SELECT cantidad, minimo FROM inventario WHERE producto_id = %s", [row_prod["id"]]
        )
        stock_anterior = float(inv_actual["cantidad"]) if inv_actual else None
        minimo_actual  = float(inv_actual["minimo"]) if inv_actual else 0.0

        if body.stock is None:
            db.execute("DELETE FROM inventario WHERE producto_id = %s", [row_prod["id"]])
        else:
            db.execute(
                """
                INSERT INTO inventario (producto_id, cantidad, minimo, unidad)
                VALUES (%s, %s, %s, 'und')
                ON CONFLICT (producto_id) DO UPDATE
                SET cantidad = EXCLUDED.cantidad, updated_at = NOW()
                """,
                (row_prod["id"], float(body.stock), minimo_actual),
            )

        invalidar_cache_memoria()

        return {
            "ok":             True,
            "key":            key,
            "nombre":         row_prod["nombre"],
            "stock_anterior": stock_anterior,
            "stock_nuevo":    body.stock,
            "pg_actualizado": True,
        }
        await notify_all("inventario_actualizado", {"accion": "stock_actualizado", "key": key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PATCH /catalogo/{key}
# =============================================================================
@router.patch("/catalogo/{key:path}")
async def editar_producto(key: str, body: EditarProductoBody):
    """Edita metadatos de un producto directamente en PostgreSQL."""
    try:
        from utils import _normalizar
        from memoria import invalidar_cache_memoria

        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        cambios = {k: v for k, v in body.dict().items() if v is not None}
        if not cambios:
            raise HTTPException(status_code=400, detail="Sin campos para actualizar")

        row = db.query_one(
            "SELECT id, nombre, nombre_lower, precio_unidad, categoria, codigo, unidad_medida "
            "FROM productos WHERE clave = %s AND activo = TRUE",
            [key],
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        pg_parts, pg_params = [], []
        nueva_clave = key

        if "nombre" in cambios:
            nombre_nuevo = cambios["nombre"].strip()
            lower_nuevo  = _normalizar(nombre_nuevo)
            nueva_clave  = lower_nuevo.replace(" ", "_")
            pg_parts += ["nombre = %s", "nombre_lower = %s", "clave = %s"]
            pg_params += [nombre_nuevo, lower_nuevo, nueva_clave]

        if "categoria"     in cambios:
            pg_parts.append("categoria = %s");     pg_params.append(cambios["categoria"].strip())
        if "precio_unidad" in cambios:
            pg_parts.append("precio_unidad = %s"); pg_params.append(int(cambios["precio_unidad"]))
        if "codigo"        in cambios:
            pg_parts.append("codigo = %s");        pg_params.append(cambios["codigo"].strip())
        if "unidad_medida" in cambios:
            pg_parts.append("unidad_medida = %s"); pg_params.append(_normalizar_unidad(cambios["unidad_medida"]))

        pg_parts.append("updated_at = NOW()")
        pg_params.append(key)
        db.execute(f"UPDATE productos SET {', '.join(pg_parts)} WHERE clave = %s", pg_params)
        invalidar_cache_memoria()

        prod_resultado = db.query_one(
            "SELECT clave, nombre, categoria, precio_unidad, codigo, unidad_medida "
            "FROM productos WHERE id = %s",
            [row["id"]],
        )

        return {
            "ok":             True,
            "key_nueva":      nueva_clave,
            "producto":       dict(prod_resultado or {}),
            "pg_actualizado": True,
        }
        await notify_all("inventario_actualizado", {"accion": "producto_editado", "key": key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# DELETE /catalogo/{key}
# =============================================================================
@router.delete("/catalogo/{key:path}")
async def eliminar_producto(key: str):
    """Elimina un producto. CASCADE borra inventario, fracciones, alias."""
    try:
        from memoria import invalidar_cache_memoria

        if not db.DB_DISPONIBLE:
            raise HTTPException(status_code=503, detail="Base de datos no disponible")

        row = db.query_one(
            "SELECT nombre FROM productos WHERE clave = %s AND activo = TRUE", [key]
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        nombre = row["nombre"]
        db.execute("DELETE FROM productos WHERE clave = %s", [key])
        invalidar_cache_memoria()

        return {
            "ok":         True,
            "nombre":     nombre,
            "mensaje":    f"'{nombre}' eliminado del catálogo",
            "pg_borrado": True,
        }
        await notify_all("inventario_actualizado", {"accion": "producto_eliminado", "key": key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Endpoints legados — deprecados, sin operación
# =============================================================================
@router.post("/catalogo/sync-desde-excel")
def sync_catalogo_desde_excel():
    """DEPRECADO — la fuente de verdad ahora es PostgreSQL."""
    return {"ok": True, "mensaje": "Migrado a PostgreSQL. Este endpoint ya no es necesario."}

@router.post("/catalogo/agregar-a-excel")
def agregar_producto_a_excel_endpoint():
    """DEPRECADO — la fuente de verdad ahora es PostgreSQL."""
    return {"ok": True, "mensaje": "Migrado a PostgreSQL. Este endpoint ya no es necesario."}

@router.post("/catalogo/{key:path}/agregar-a-excel")
def agregar_producto_especifico_a_excel(key: str):
    """DEPRECADO — la fuente de verdad ahora es PostgreSQL."""
    return {"ok": True, "mensaje": "Migrado a PostgreSQL. Este endpoint ya no es necesario."}
