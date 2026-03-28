"""
memoria.py (PG-FIRST, SIN FALLBACK)

Diseño:
- Postgres es la ÚNICA fuente de verdad
- Cache en RAM para performance
- Si PG falla → se lanza excepción (fail fast)
- Sin JSON, sin Excel como respaldo

Requisitos del módulo db:
- db.execute(query, params)
- db.fetchall(query, params=None)
"""

import threading
import time
from typing import Dict, Any, Optional

# ===== CONFIG =====
CACHE_TTL = 60  # segundos

# ===== CACHE GLOBAL =====
_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: float = 0
_lock = threading.Lock()

# ===== DB =====
import db

# ===== CORE =====

def _leer_catalogo_postgres() -> Dict[str, Dict]:
    rows = db.fetchall("""
        SELECT clave, nombre, nombre_lower, precio_unidad
        FROM productos
    """)

    if rows is None:
        raise RuntimeError("Error leyendo productos desde Postgres")

    catalogo = {}
    for r in rows:
        catalogo[r["clave"]] = {
            "nombre": r["nombre"],
            "nombre_lower": r["nombre_lower"],
            "precio": float(r["precio_unidad"])
        }

    return catalogo


def _construir_memoria() -> Dict[str, Any]:
    return {
        "catalogo": _leer_catalogo_postgres(),
        "ultima_actualizacion": time.time()
    }


def cargar_memoria(force_reload: bool = False) -> Dict[str, Any]:
    global _cache, _cache_timestamp

    with _lock:
        ahora = time.time()

        if (
            not force_reload
            and _cache is not None
            and (ahora - _cache_timestamp) < CACHE_TTL
        ):
            return _cache

        # 🔥 SI FALLA, QUE EXPLOTE
        memoria = _construir_memoria()

        _cache = memoria
        _cache_timestamp = ahora

        return _cache


# ===== QUERY HELPERS =====

def obtener_producto(clave: str) -> Dict:
    mem = cargar_memoria()

    if clave not in mem["catalogo"]:
        raise KeyError(f"Producto no encontrado: {clave}")

    return mem["catalogo"][clave]


def buscar_producto_por_nombre(nombre: str) -> Dict:
    nombre = nombre.lower()
    mem = cargar_memoria()

    for prod in mem["catalogo"].values():
        if nombre in prod["nombre_lower"]:
            return prod

    raise ValueError(f"Producto no encontrado por nombre: {nombre}")


# ===== WRITE OPERATIONS (SIEMPRE PG) =====

def actualizar_precio(clave: str, nuevo_precio: float):
    result = db.execute("""
        UPDATE productos
        SET precio_unidad = %s
        WHERE clave = %s
    """, (nuevo_precio, clave))

    if result is None:
        raise RuntimeError("Error actualizando precio en PG")

    # actualización optimista de cache
    global _cache
    if _cache and clave in _cache["catalogo"]:
        _cache["catalogo"][clave]["precio"] = float(nuevo_precio)


def upsert_producto(clave: str, nombre: str, precio: float):
    result = db.execute("""
        INSERT INTO productos (clave, nombre, nombre_lower, precio_unidad)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (clave) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            nombre_lower = EXCLUDED.nombre_lower,
            precio_unidad = EXCLUDED.precio_unidad
    """, (clave, nombre, nombre.lower(), precio))

    if result is None:
        raise RuntimeError("Error en upsert de producto")

    invalidar_cache()


def eliminar_producto(clave: str):
    result = db.execute("DELETE FROM productos WHERE clave = %s", (clave,))

    if result is None:
        raise RuntimeError("Error eliminando producto")

    invalidar_cache()


# ===== IMPORT DESDE EXCEL (INPUT ONLY) =====

def importar_catalogo_desde_excel(path: str, reader_func):
    data = reader_func(path)

    if not isinstance(data, list):
        raise ValueError("reader_func debe devolver lista de productos")

    for prod in data:
        if not all(k in prod for k in ("clave", "nombre", "precio")):
            raise ValueError(f"Producto inválido: {prod}")

        db.execute("""
            INSERT INTO productos (clave, nombre, nombre_lower, precio_unidad)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (clave) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                nombre_lower = EXCLUDED.nombre_lower,
                precio_unidad = EXCLUDED.precio_unidad
        """, (
            prod["clave"],
            prod["nombre"],
            prod["nombre"].lower(),
            float(prod["precio"])
        ))

    invalidar_cache()


# ===== CACHE CONTROL =====

def invalidar_cache():
    global _cache, _cache_timestamp
    with _lock:
        _cache = None
        _cache_timestamp = 0


# ===== DEBUG =====

def stats_cache():
    return {
        "cache_activo": _cache is not None,
        "edad_segundos": time.time() - _cache_timestamp if _cache else None,
        "ttl": CACHE_TTL
    }


# ===== INIT =====
if __name__ == "__main__":
    print("[memoria] cargando desde Postgres...")
    m = cargar_memoria()
    print(f"[memoria] productos cargados: {len(m['catalogo'])}")
