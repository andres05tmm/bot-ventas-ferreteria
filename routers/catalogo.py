"""
Router: Catálogo — /catalogo/*, /productos, /inventario/*, /kardex
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

@router.get("/productos")
def productos():
    try:
        if not os.path.exists(config.MEMORIA_FILE):
            return {"productos": []}
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})
        lista = []
        # Fracciones estándar para productos de galón (pinturas/impermeabilizantes)
        _FRACS_GALON = [
            ("3/4", 0.75), ("1/2", 0.5), ("1/4", 0.25),
            ("1/8", 0.125), ("1/16", 0.0625), ("1/10", 0.1),
        ]

        for k, v in catalogo.items():
            ppc = v.get("precio_por_cantidad")
            mayorista = None
            if ppc:
                mayorista = {
                    "umbral": ppc.get("umbral", 50),
                    "precio": ppc.get("precio_sobre_umbral", 0),
                }

            fracs = v.get("precios_fraccion", None)
            precio = v.get("precio_unidad", 0)

            # Auto-generar fracciones para pinturas/impermeabilizantes sin precios_fraccion
            if not fracs and precio > 0:
                cat_lower = (v.get("categoria", "") or "").lower()
                es_galon = "pintura" in cat_lower or "disolvente" in cat_lower or "impermeab" in cat_lower
                if es_galon:
                    fracs = {}
                    for label, decimal in _FRACS_GALON:
                        fracs[label] = {"precio": round(precio * decimal), "decimal": decimal}

            lista.append({
                "key":              k,
                "nombre":           v.get("nombre", k),
                "categoria":        v.get("categoria", "Sin categoría"),
                "precio":           precio,
                "codigo":           v.get("codigo", ""),
                "stock":            _stock_wayper(k, inventario),
                "precios_fraccion": fracs,
                "unidad_medida":    v.get("unidad_medida", "Unidad"),
                "mayorista":        mayorista,
            })
        return {"productos": lista, "total": len(lista)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventario/bajo")
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
            raw_stock = inventario.get(key, None)
            stock = raw_stock.get("cantidad") if isinstance(raw_stock, dict) else raw_stock

            sin_precio = precio is None or precio == 0
            sin_stock  = stock is not None and (stock == 0 or stock == "0" or stock == 0.0)

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
@router.get("/catalogo/nav")
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

        # Mapa de normalización: agrupa categorías que difieren solo en mayúsculas
        _cat_canonical: dict[str, str] = {}  # lower → primera aparición original

        categorias: dict[str, list] = defaultdict(list)
        for key, prod in catalogo.items():
            nombre   = prod.get("nombre", key)
            cat_raw  = prod.get("categoria", "Sin categoría")

            # Normalizar: usar siempre la primera forma encontrada
            cat_lower = cat_raw.lower()
            if cat_lower not in _cat_canonical:
                _cat_canonical[cat_lower] = cat_raw
            categoria = _cat_canonical[cat_lower]

            if q_lower and q_lower not in nombre.lower() and q_lower not in (prod.get("codigo","")).lower():
                continue

            # Stock info (wayper por kg usa inventario de unidades)
            stock = _stock_wayper(key, inventario)
            if key in _WAYPER_KG_KEYS:
                costo = None
            else:
                inv_data = inventario.get(key)
                costo = inv_data.get("costo_promedio") if isinstance(inv_data, dict) else None

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
                "key":           key,
                "nombre":        nombre,
                "codigo":        prod.get("codigo", ""),
                "precio":        prod.get("precio_unidad", 0),
                "stock":         stock,
                "costo":         costo,
                "fracciones":    fracs,
                "mayorista":     mayorista,
                "unidad_medida": prod.get("unidad_medida", "Unidad"),
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


# ── Edición de precios desde el dashboard ────────────────────────────────────
class PrecioUpdate(BaseModel):
    precio: Union[float, int]

class FraccionesUpdate(BaseModel):
    fracciones: dict   # { "1/4": 8000, "1/2": 13000, ... }

class MayoristaUpdate(BaseModel):
    precio: Union[float, int]
    umbral: Optional[int] = None   # Si None, conserva el umbral existente

class NuevoProducto(BaseModel):
    nombre:          str
    categoria:       str
    precio_unidad:   Union[float, int]
    unidad_medida:   str  = "Unidad"
    codigo:          str  = ""
    stock_inicial:   Union[float, int, None] = None
    codigo_dian:     str  = "94"
    inventariable:   bool = True
    visible_facturas:bool = True
    stock_minimo:    int  = 0

@router.post("/catalogo")
def crear_producto(body: NuevoProducto):
    """
    Crea un producto nuevo en memoria.json y en BASE_DE_DATOS_PRODUCTOS.xlsx.
    """
    try:
        from utils import _normalizar
        from precio_sync import agregar_producto_a_excel, _normalizar_unidad

        if not body.nombre.strip():
            raise HTTPException(status_code=400, detail="El nombre es obligatorio")

        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)

        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})

        # Generar clave única
        key_base = _normalizar(body.nombre.strip()).replace(" ", "_")
        key = key_base
        sufijo = 2
        while key in catalogo:
            key = f"{key_base}_{sufijo}"
            sufijo += 1

        unidad_norm = _normalizar_unidad(body.unidad_medida)

        nuevo = {
            "nombre":        body.nombre.strip(),
            "nombre_lower":  _normalizar(body.nombre.strip()),
            "categoria":     body.categoria.strip(),
            "precio_unidad": int(body.precio_unidad),
            "unidad_medida": unidad_norm,
        }
        if body.codigo.strip():
            nuevo["codigo"] = body.codigo.strip()

        catalogo[key] = nuevo

        # Stock inicial — guardar en formato dict igual al que usa el bot
        # (float plano hace que descontar_inventario() retorne False silenciosamente)
        if body.stock_inicial is not None:
            from datetime import datetime as _dt
            inventario[key] = {
                "nombre_original": body.nombre.strip(),
                "cantidad":        float(body.stock_inicial),
                "minimo":          body.stock_minimo if hasattr(body, "stock_minimo") else 0,
                "unidad":          "und",
                "fecha_conteo":    _dt.now().strftime("%Y-%m-%d %H:%M"),
            }

        mem["catalogo"]   = catalogo
        mem["inventario"] = inventario

        # guardar_memoria sube a Drive automáticamente (urgente=True evita pérdida en reinicios)
        try:
            from memoria import guardar_memoria, invalidar_cache_memoria
            guardar_memoria(mem, urgente=True)
            invalidar_cache_memoria()
        except Exception:
            # Fallback: escritura directa si el módulo no está disponible
            with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)

        # Intentar escribir en el Excel de productos (no bloquea si falla)
        excel_resultado = {"ok": False, "error": "no intentado"}
        try:
            excel_resultado = agregar_producto_a_excel({
                "codigo":          body.codigo.strip() or key,
                "nombre":          body.nombre.strip(),
                "categoria":       body.categoria.strip(),
                "precio_unidad":   int(body.precio_unidad),
                "unidad_medida":   unidad_norm,
                "inventariable":   body.inventariable,
                "visible_facturas":body.visible_facturas,
                "stock_minimo":    body.stock_minimo,
                "codigo_dian":     body.codigo_dian,
            })
        except Exception as e_excel:
            excel_resultado = {"ok": False, "error": str(e_excel)}

        return {
            "ok":             True,
            "key":            key,
            "nombre":         nuevo["nombre"],
            "categoria":      nuevo["categoria"],
            "precio_unidad":  nuevo["precio_unidad"],
            "unidad_medida":  unidad_norm,
            "stock_inicial":  body.stock_inicial,
            "excel_guardado": excel_resultado.get("ok", False),
            "excel_detalle":  excel_resultado,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/catalogo/{key:path}/precio")
def actualizar_precio_endpoint(key: str, body: PrecioUpdate):
    """
    Actualiza precio_unidad de un producto.
    1. Guarda en memoria.json (inmediato).
    2. Encola actualización en BASE_DE_DATOS_PRODUCTOS.xlsx via precio_sync.
    """
    try:
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo = mem.get("catalogo", {})
        if key not in catalogo:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        nombre_prod     = catalogo[key].get("nombre", key)
        precio_anterior = catalogo[key].get("precio_unidad", 0)
        nuevo_precio    = int(body.precio)

        # 1 ── memoria.json + Drive (guardar_memoria sincroniza ambos)
        catalogo[key]["precio_unidad"] = nuevo_precio
        mem["catalogo"] = catalogo
        try:
            from memoria import guardar_memoria as _gm, invalidar_cache_memoria
            _gm(mem, urgente=True)
            invalidar_cache_memoria()
        except Exception:
            with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)

        # 2 ── Excel BASE_DE_DATOS_PRODUCTOS (via precio_sync, cola FIFO)
        try:
            from precio_sync import actualizar_precio as _sync_precio
            _sync_precio(nombre_prod, nuevo_precio, None)
        except Exception as e_sync:
            import logging
            logging.getLogger("ferrebot.api").warning(
                f"precio_sync falló para '{nombre_prod}': {e_sync}"
            )

        return {
            "ok":            True,
            "key":           key,
            "nombre":        nombre_prod,
            "precio_anterior": precio_anterior,
            "precio_nuevo":  nuevo_precio,
            "excel_encolado": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/catalogo/{key:path}/fracciones")
def actualizar_fracciones(key: str, body: FraccionesUpdate):
    """
    Actualiza precios_fraccion de un producto.
    1. Guarda en memoria.json (inmediato).
    2. Encola cada fracción en BASE_DE_DATOS_PRODUCTOS.xlsx via precio_sync.
    """
    try:
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo = mem.get("catalogo", {})
        if key not in catalogo:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        nombre_prod = catalogo[key].get("nombre", key)

        # Convertir a { frac: { "precio": X } } si llegan como { frac: precio }
        fracs_formateadas = {}
        for k, v in body.fracciones.items():
            if isinstance(v, dict):
                fracs_formateadas[k] = v
            else:
                fracs_formateadas[k] = {"precio": int(v)}

        # 1 ── memoria.json + Drive
        catalogo[key]["precios_fraccion"] = fracs_formateadas

        # Si fracción "1" (unidad completa) cambió, sincronizar precio_unidad para que la IA cotice bien
        if "1" in fracs_formateadas:
            precio_unidad_nuevo = fracs_formateadas["1"].get("precio") if isinstance(fracs_formateadas["1"], dict) else int(fracs_formateadas["1"])
            if precio_unidad_nuevo:
                catalogo[key]["precio_unidad"] = precio_unidad_nuevo

        mem["catalogo"] = catalogo
        try:
            from memoria import guardar_memoria as _gm, invalidar_cache_memoria
            _gm(mem, urgente=True)
            invalidar_cache_memoria()
        except Exception:
            with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)

        # 2 ── Excel: encolar cada fracción via precio_sync
        try:
            from precio_sync import actualizar_precio as _sync_precio
            for frac_key, frac_val in fracs_formateadas.items():
                precio_frac = frac_val["precio"] if isinstance(frac_val, dict) else int(frac_val)
                if precio_frac > 0:
                    _sync_precio(nombre_prod, precio_frac, frac_key)
        except Exception as e_sync:
            import logging
            logging.getLogger("ferrebot.api").warning(
                f"precio_sync fracciones falló para '{nombre_prod}': {e_sync}"
            )

        return {"ok": True, "key": key, "nombre": nombre_prod, "fracciones": fracs_formateadas}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Sync inverso: Excel → memoria.json ───────────────────────────────────────
@router.post("/catalogo/sync-desde-excel")
def sync_catalogo_desde_excel():
    """
    Descarga BASE_DE_DATOS_PRODUCTOS.xlsx desde Drive y reimporta
    todos los precios a memoria.json.
    Útil cuando el Excel se edita directamente (no desde el dashboard).
    """
    import tempfile, os
    try:
        from drive import descargar_de_drive
        from precio_sync import importar_catalogo_desde_excel

        # Descargar Excel fresco de Drive a un archivo temporal
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            ruta_tmp = tmp.name

        try:
            ok = descargar_de_drive("BASE_DE_DATOS_PRODUCTOS.xlsx", ruta_tmp)
            if not ok:
                raise HTTPException(status_code=502, detail="No se pudo descargar el Excel de Drive")

            resultado = importar_catalogo_desde_excel(ruta_tmp)
        finally:
            try:
                os.unlink(ruta_tmp)
            except Exception:
                pass

        if resultado.get("errores"):
            logging.getLogger("ferrebot.api").warning(
                f"sync-desde-excel errores parciales: {resultado['errores']}"
            )

        return {
            "ok":         True,
            "importados": resultado.get("importados", 0),
            "omitidos":   resultado.get("omitidos", 0),
            "errores":    resultado.get("errores", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# ── Estado de Resultados ──────────────────────────────────────────────────────
@router.patch("/catalogo/{key:path}/mayorista")
def actualizar_mayorista(key: str, body: MayoristaUpdate):
    """
    Actualiza el precio mayorista (precio_por_cantidad) de un producto.
    Guarda precio_sobre_umbral en memoria.json y sincroniza al Excel.
    """
    try:
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo = mem.get("catalogo", {})
        if key not in catalogo:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        prod = catalogo[key]
        nombre_prod = prod.get("nombre", key)
        ppc_actual  = prod.get("precio_por_cantidad")

        # Preservar umbral existente si no se manda uno nuevo
        umbral = body.umbral if body.umbral else (ppc_actual.get("umbral", 50) if ppc_actual else 50)

        prod["precio_por_cantidad"] = {
            "umbral":              umbral,
            "precio_bajo_umbral":  ppc_actual.get("precio_bajo_umbral", prod.get("precio_unidad", 0)) if ppc_actual else prod.get("precio_unidad", 0),
            "precio_sobre_umbral": int(body.precio),
        }
        catalogo[key] = prod
        mem["catalogo"] = catalogo

        # Usar guardar_memoria() para que también suba a Drive (antes solo hacía open+write)
        try:
            from memoria import guardar_memoria as _gm, invalidar_cache_memoria
            _gm(mem, urgente=True)
            invalidar_cache_memoria()
        except Exception:
            # Fallback: al menos guardar en disco si memoria.py falla
            with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)

        return {
            "ok": True, "key": key, "nombre": nombre_prod,
            "precio_mayorista": int(body.precio), "umbral": umbral,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/inventario/{key:path}/stock")
def actualizar_stock(key: str, body: StockUpdate):
    """
    Actualiza cantidad en inventario de un producto (memoria.json).
    Guarda en el mismo formato que usa el bot: {"cantidad": X, "nombre_original": ..., "minimo": N}
    para mantener sincronía completa bot <-> dashboard.
    """
    try:
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})
        if key not in catalogo:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        nombre_prod    = catalogo[key].get("nombre", key)
        entrada_actual = inventario.get(key)

        # Extraer stock_anterior independientemente del formato (dict o número)
        if isinstance(entrada_actual, dict):
            stock_anterior = entrada_actual.get("cantidad")
        elif entrada_actual is not None:
            stock_anterior = float(entrada_actual)
        else:
            stock_anterior = None

        if body.stock is None:
            inventario.pop(key, None)
        else:
            # Preservar minimo si ya existe, sino usar 0
            minimo_actual = 0
            if isinstance(entrada_actual, dict):
                minimo_actual = entrada_actual.get("minimo", 0)

            from datetime import datetime
            inventario[key] = {
                "nombre_original": nombre_prod,
                "cantidad":        float(body.stock),
                "minimo":          minimo_actual,
                "unidad":          "und",
                "fecha_conteo":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

        mem["inventario"] = inventario
        try:
            from memoria import guardar_memoria as _gm, invalidar_cache_memoria
            _gm(mem, urgente=True)
            invalidar_cache_memoria()
        except Exception:
            with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)

        return {
            "ok": True, "key": key,
            "nombre":         nombre_prod,
            "stock_anterior": stock_anterior,
            "stock_nuevo":    body.stock,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Health check ──────────────────────────────────────────────────────────────
# ── Editar / Eliminar Productos ───────────────────────────────────────────────
class EditarProductoBody(BaseModel):
    nombre:        Union[str, None]   = None
    categoria:     Union[str, None]   = None
    precio_unidad: Union[float, None] = None
    unidad_medida: Union[str, None]   = None
    codigo:        Union[str, None]   = None

@router.patch("/catalogo/{key:path}")
def editar_producto(key: str, body: EditarProductoBody):
    """Edita nombre, categoría, precio, unidad_medida o código de un producto."""
    try:
        from utils import _normalizar
        from precio_sync import actualizar_precio as _sync_precio, _normalizar_unidad
        from memoria import invalidar_cache_memoria

        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo = mem.get("catalogo", {})
        if key not in catalogo:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        prod    = catalogo[key]
        cambios = {k: v for k, v in body.dict().items() if v is not None}
        if not cambios:
            raise HTTPException(status_code=400, detail="Sin campos para actualizar")

        nueva_clave = key
        if "nombre" in cambios:
            prod["nombre"]       = cambios["nombre"].strip()
            prod["nombre_lower"] = _normalizar(cambios["nombre"].strip())
            nueva_clave          = prod["nombre_lower"].replace(" ", "_")

        if "categoria"     in cambios: prod["categoria"]     = cambios["categoria"].strip()
        if "precio_unidad" in cambios: prod["precio_unidad"] = int(cambios["precio_unidad"])
        if "codigo"        in cambios: prod["codigo"]        = cambios["codigo"].strip()
        if "unidad_medida" in cambios: prod["unidad_medida"] = _normalizar_unidad(cambios["unidad_medida"])

        # Si cambió el nombre → mover a nueva clave
        if nueva_clave != key:
            inv = mem.get("inventario", {})
            catalogo[nueva_clave] = prod
            del catalogo[key]
            if key in inv:
                inv[nueva_clave] = inv.pop(key)
            mem["inventario"] = inv
        else:
            catalogo[key] = prod

        mem["catalogo"] = catalogo
        try:
            from memoria import guardar_memoria as _gm, invalidar_cache_memoria
            _gm(mem, urgente=True)
            invalidar_cache_memoria()
        except Exception:
            with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)

        # Sync al Excel BASE_DE_DATOS_PRODUCTOS
        # — precio si cambió
        if "precio_unidad" in cambios:
            try:
                _sync_precio(prod["nombre"], int(cambios["precio_unidad"]), None)
            except Exception:
                pass

        # — nombre, categoría o unidad_medida: actualizar fila completa en el Excel
        if any(c in cambios for c in ("nombre", "categoria", "unidad_medida", "codigo")):
            try:
                from precio_sync import _actualizar_metadatos_en_excel
                _actualizar_metadatos_en_excel(
                    nombre_original = catalogo.get(key, prod).get("nombre", prod["nombre"]) if nueva_clave == key else key.replace("_", " "),
                    datos_nuevos    = {
                        "nombre":        prod.get("nombre", ""),
                        "categoria":     prod.get("categoria", ""),
                        "unidad_medida": prod.get("unidad_medida", "Unidad"),
                        "codigo":        prod.get("codigo", ""),
                    },
                )
            except Exception as e_meta:
                logging.getLogger("ferrebot.api").warning(
                    f"_actualizar_metadatos_en_excel falló para '{prod.get('nombre')}': {e_meta}"
                )

        return {"ok": True, "key_nueva": nueva_clave, "producto": prod}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/catalogo/{key:path}")
def eliminar_producto(key: str):
    """Elimina un producto del catálogo e inventario en memoria.json."""
    try:
        from memoria import invalidar_cache_memoria
        with open(config.MEMORIA_FILE, encoding="utf-8") as f:
            mem = json.load(f)
        catalogo   = mem.get("catalogo", {})
        inventario = mem.get("inventario", {})
        if key not in catalogo:
            raise HTTPException(status_code=404, detail=f"Producto '{key}' no encontrado")

        nombre = catalogo[key].get("nombre", key)
        del catalogo[key]
        inventario.pop(key, None)
        mem["catalogo"]   = catalogo
        mem["inventario"] = inventario

        try:
            from memoria import guardar_memoria as _gm, invalidar_cache_memoria
            _gm(mem, urgente=True)
            invalidar_cache_memoria()
        except Exception:
            with open(config.MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)

        # Eliminar también de BASE_DE_DATOS_PRODUCTOS.xlsx para evitar que
        # un sync-desde-excel resucite el producto eliminado
        excel_resultado = {"ok": False, "error": "no intentado"}
        try:
            from precio_sync import eliminar_producto_de_excel as _del_xls
            excel_resultado = _del_xls(nombre)
        except Exception as e_xls:
            logging.getLogger("ferrebot.api").warning(
                f"eliminar_producto_de_excel falló para '{nombre}': {e_xls}"
            )

        return {
            "ok":             True,
            "nombre":         nombre,
            "mensaje":        f"'{nombre}' eliminado del catálogo",
            "excel_borrado":  excel_resultado.get("ok", False),
            "excel_detalle":  excel_resultado,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


