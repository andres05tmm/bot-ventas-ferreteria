"""
services/inventario_service.py — Lógica de inventario extraída de memoria.py.

Funciones de lectura, descuento, ajuste y búsqueda de inventario.
Copias verbatim de memoria.py — sin cambios de firma ni lógica.

FASE 1 — este módulo NO está conectado a nada todavía.
Solo debe existir en disco e importar limpio.
La integración ocurre en Fase 2 (Tarea H).

⚠️  CONTRATO CRÍTICO — descontar_inventario() DEBE retornar exactamente:
    (bool, str | None, float | None)
    ventas_state.py línea 210 destructura esta tupla.
    Cualquier cambio rompe el flujo de ventas silenciosamente.

Imports permitidos: logging, db, config, utils.
cargar_inventario() y guardar_inventario() se importan lazy desde memoria
para evitar ciclos. NUNCA importar de ai, handlers, o memoria a nivel módulo.
"""

# -- stdlib --
import logging
from datetime import datetime

# -- terceros --
# (ninguno)

# -- propios --
# (ninguno a nivel módulo — imports lazy dentro de funciones)

logger = logging.getLogger("ferrebot.services.inventario")


# ─────────────────────────────────────────────
# PERSISTENCIA INTERNA
# ─────────────────────────────────────────────

def _upsert_inventario_producto_postgres(clave: str, datos: dict):
    """Upsert quirúrgico de un solo producto en inventario. Raises si PG falla."""
    import db as _db

    def _parse_ts(val):
        """Convierte string 'YYYY-MM-DD HH:MM' a datetime, o None si vacío."""
        if not val:
            return None
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return None

    prod_row = _db.query_one("SELECT id FROM productos WHERE clave = %s", (clave,))
    if not prod_row:
        raise ValueError(f"Producto con clave '{clave}' no existe en productos")
    _db.execute("""
        INSERT INTO inventario (
            producto_id, cantidad, minimo, unidad,
            nombre_original, costo_promedio, ultimo_costo, ultimo_proveedor,
            ultima_compra, ultima_venta, ultimo_ajuste, fecha_conteo,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (producto_id) DO UPDATE SET
            cantidad        = EXCLUDED.cantidad,
            minimo          = EXCLUDED.minimo,
            unidad          = EXCLUDED.unidad,
            nombre_original = EXCLUDED.nombre_original,
            costo_promedio  = EXCLUDED.costo_promedio,
            ultimo_costo    = EXCLUDED.ultimo_costo,
            ultimo_proveedor= EXCLUDED.ultimo_proveedor,
            ultima_compra   = EXCLUDED.ultima_compra,
            ultima_venta    = EXCLUDED.ultima_venta,
            ultimo_ajuste   = EXCLUDED.ultimo_ajuste,
            fecha_conteo    = EXCLUDED.fecha_conteo,
            updated_at      = NOW()
    """, (
        prod_row["id"],
        datos.get("cantidad", 0),
        datos.get("minimo", 0),
        datos.get("unidad", "Unidad"),
        datos.get("nombre_original") or None,
        datos.get("costo_promedio")  or None,
        datos.get("ultimo_costo")    or None,
        datos.get("ultimo_proveedor") or None,
        _parse_ts(datos.get("ultima_compra")),
        _parse_ts(datos.get("ultima_venta")),
        _parse_ts(datos.get("ultimo_ajuste")),
        _parse_ts(datos.get("fecha_conteo")),
    ))


# ─────────────────────────────────────────────
# LECTURA Y ESCRITURA DE INVENTARIO
# ─────────────────────────────────────────────

def cargar_inventario() -> dict:
    """Retorna el inventario completo desde el cache de memoria."""
    from memoria import cargar_memoria
    return cargar_memoria().get("inventario", {})


def guardar_inventario(clave: str, datos: dict):
    """Escribe un producto al inventario. PG es fuente de verdad.
    Actualiza el cache en memoria para que lecturas posteriores sean consistentes.
    Raises en caso de error — el caller debe manejar el fallo visiblemente.
    """
    from memoria import _cache, _cache_lock
    _upsert_inventario_producto_postgres(clave, datos)
    with _cache_lock:
        if _cache is not None:
            _cache.setdefault("inventario", {})[clave] = datos


def verificar_alertas_inventario() -> list[str]:
    """Retorna lista de alertas para productos con stock bajo o en mínimo."""
    alertas = []
    for producto, datos in cargar_inventario().items():
        if isinstance(datos, dict):
            cantidad = datos.get("cantidad", 0)
            minimo   = datos.get("minimo", 3)
            if cantidad <= minimo:
                alertas.append(f"⚠️ STOCK BAJO: {producto} — quedan {cantidad} unidades")
    return alertas


# ─────────────────────────────────────────────
# NORMALIZACIÓN Y BÚSQUEDA
# ─────────────────────────────────────────────

def _normalizar_clave_inventario(nombre: str) -> str:
    """Normaliza el nombre del producto para usar como clave en inventario."""
    from utils import _normalizar
    return _normalizar(nombre).strip().lower()


def buscar_clave_inventario(termino: str) -> str | None:
    """
    Busca un producto en inventario de forma flexible.
    Retorna la clave del inventario si encuentra coincidencia.
    """
    inventario = cargar_inventario()
    if not inventario:
        return None

    termino_lower = _normalizar_clave_inventario(termino)

    # 1. Coincidencia exacta con clave
    if termino_lower in inventario:
        return termino_lower

    # 2. Coincidencia exacta con nombre_original
    for clave, datos in inventario.items():
        if isinstance(datos, dict):
            nombre_orig = datos.get("nombre_original", "").lower()
            if nombre_orig == termino_lower:
                return clave

    # 3. Búsqueda por palabras
    palabras = [p for p in termino_lower.split() if len(p) > 2]
    if not palabras:
        return None

    mejores = []
    for clave, datos in inventario.items():
        if isinstance(datos, dict):
            nombre_orig = datos.get("nombre_original", clave).lower()
            texto_busqueda = f"{clave} {nombre_orig}"
            coincidencias = sum(1 for p in palabras if p in texto_busqueda)
            if coincidencias == len(palabras):
                mejores.append((3, coincidencias, len(clave), clave))
            elif coincidencias >= len(palabras) - 1 and len(palabras) > 1:
                mejores.append((2, coincidencias, len(clave), clave))
            elif coincidencias >= 1:
                mejores.append((1, coincidencias, len(clave), clave))

    if mejores:
        mejores.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return mejores[0][3]

    return None


# ─────────────────────────────────────────────
# CONTEO Y AJUSTE
# ─────────────────────────────────────────────

def registrar_conteo_inventario(nombre_producto: str, cantidad: float, minimo: float = 5, unidad: str = "unidades") -> tuple[bool, str]:
    """
    Registra o actualiza el conteo de un producto en inventario.
    Busca primero en el catálogo para usar el nombre correcto.
    Retorna (éxito, mensaje).
    """
    from services.catalogo_service import buscar_producto_en_catalogo
    inventario = cargar_inventario()

    # Buscar producto en catálogo para usar nombre oficial
    producto_catalogo = buscar_producto_en_catalogo(nombre_producto)
    if producto_catalogo:
        nombre_oficial = producto_catalogo.get("nombre", nombre_producto)
    else:
        nombre_oficial = nombre_producto.strip()

    clave = _normalizar_clave_inventario(nombre_oficial)

    # Verificar si ya existe con otra clave similar
    clave_existente = buscar_clave_inventario(nombre_producto)
    if clave_existente and clave_existente != clave:
        clave = clave_existente
        nombre_oficial = inventario[clave].get("nombre_original", nombre_oficial)

    datos_nuevos = {
        "nombre_original": nombre_oficial,
        "cantidad": round(cantidad, 4),
        "minimo": minimo,
        "unidad": unidad,
        "fecha_conteo": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    guardar_inventario(clave, datos_nuevos)

    return True, f"✅ Registrado: {nombre_oficial} — {cantidad} {unidad}"


def ajustar_inventario(nombre_producto: str, ajuste: float) -> tuple[bool, str]:
    """
    Ajusta el inventario sumando o restando cantidad.
    ajuste puede ser positivo (+10) o negativo (-5).
    Retorna (éxito, mensaje).
    """
    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return False, f"❌ Producto no encontrado en inventario: {nombre_producto}"

    inventario = cargar_inventario()
    datos = inventario.get(clave, {})

    cantidad_anterior = datos.get("cantidad", 0)
    cantidad_nueva = max(0, round(cantidad_anterior + ajuste, 4))
    datos["cantidad"] = cantidad_nueva
    datos["ultimo_ajuste"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    guardar_inventario(clave, datos)

    nombre = datos.get("nombre_original", clave)
    unidad = datos.get("unidad", "unidades")
    signo = "+" if ajuste > 0 else ""

    return True, f"✅ Ajustado: {nombre}\n   {cantidad_anterior} {signo}{ajuste} = {cantidad_nueva} {unidad}"


# ─────────────────────────────────────────────
# DESCUENTO DE INVENTARIO
# ─────────────────────────────────────────────

# Tabla de redirección para productos vendidos diferente a como se almacenan.
# Formato: nombre_producto_lower → (clave_inventario, factor)
#   factor = multiplicador sobre la cantidad vendida para obtener la cantidad a descontar.
#   Waypers: 1 kg vendido = 12 unidades descontadas (factor 12)
#   Carbonato: 1 kg vendido = 1 kg descontado de la bolsa (factor 1)
_KG_INVENTARIO_LINKS: dict[str, tuple[str, float]] = {
    "wayper blanco":   ("wayper_blanco_unidad",  12.0),
    "wayper de color": ("wayper_de_color_unidad", 12.0),
    # Carbonato x Kg descuenta de la bolsa de 25 kg (inventario en kg)
    "carbonato x kg":  ("carbonato_x_25_kg",       1.0),
}


def _resolver_wayper_inventario(nombre_producto: str, cantidad: float) -> tuple[str | None, float]:
    """
    Para productos vendidos de forma distinta a como se almacenan, redirige
    al inventario real y aplica el factor de conversión correspondiente.
    Retorna (clave_inventario, cantidad_a_descontar) o (None, cantidad) si no aplica.
    """
    nombre_lower = nombre_producto.lower().strip()
    for nombre_ref, (clave_inv, factor) in _KG_INVENTARIO_LINKS.items():
        if nombre_lower == nombre_ref or nombre_lower.startswith(nombre_ref):
            if "unidad" not in nombre_lower:
                return clave_inv, round(cantidad * factor, 4)
    return None, cantidad


def descontar_inventario(nombre_producto: str, cantidad: float) -> tuple[bool, str | None, float | None]:
    """
    Descuenta cantidad del inventario si el producto está registrado.
    Para waypers vendidos por kg, convierte automáticamente a unidades (1 kg = 12 und).

    ⚠️  CONTRATO: retorna exactamente (bool, str | None, float | None).
        ventas_state.py línea 210 destructura esta tupla — no cambiar la firma.

    Retorna:
        (True,  alerta_o_None, cantidad_restante)  — si el producto estaba en inventario
        (False, None, None)                        — si el producto no está en inventario
    """
    # Wayper por kg → convertir a unidades y buscar inventario de unidades
    clave_wayper, cantidad_real = _resolver_wayper_inventario(nombre_producto, cantidad)
    if clave_wayper:
        inventario = cargar_inventario()
        if clave_wayper in inventario:
            cantidad = cantidad_real
            datos = inventario.get(clave_wayper, {})
            if isinstance(datos, dict):
                cantidad_actual = datos.get("cantidad", 0)
                cantidad_nueva  = max(0, round(cantidad_actual - cantidad, 4))
                datos["cantidad"]     = cantidad_nueva
                datos["ultima_venta"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                guardar_inventario(clave_wayper, datos)
                minimo = datos.get("minimo", 5)
                nombre = datos.get("nombre_original", clave_wayper)
                unidad = datos.get("unidad", "unidades")
                alerta = None
                if cantidad_nueva <= minimo:
                    alerta = f"⚠️ Stock bajo: {nombre} — quedan {cantidad_nueva:.0f} {unidad}"
                return True, alerta, cantidad_nueva
        # No hay inventario de unidades registrado → intentar con la clave original

    clave = buscar_clave_inventario(nombre_producto)
    if not clave:
        return False, None, None

    inventario = cargar_inventario()
    datos = inventario.get(clave, {})

    if not isinstance(datos, dict):
        return False, None, None

    cantidad_actual = datos.get("cantidad", 0)
    cantidad_nueva = max(0, round(cantidad_actual - cantidad, 4))
    datos["cantidad"] = cantidad_nueva
    datos["ultima_venta"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    guardar_inventario(clave, datos)

    minimo = datos.get("minimo", 5)
    nombre = datos.get("nombre_original", clave)
    unidad = datos.get("unidad", "unidades")

    alerta = None
    if cantidad_nueva <= minimo:
        alerta = f"⚠️ Stock bajo: {nombre} — quedan {cantidad_nueva} {unidad}"

    return True, alerta, cantidad_nueva


# ─────────────────────────────────────────────
# BÚSQUEDA EN INVENTARIO
# ─────────────────────────────────────────────

def buscar_productos_inventario(termino: str = None, limite: int = 50) -> list[dict]:
    """
    Busca productos en inventario. Si no hay término, retorna todos.
    Retorna lista de dicts con info del producto.
    """
    inventario = cargar_inventario()
    resultados = []

    for clave, datos in inventario.items():
        if not isinstance(datos, dict):
            continue

        if termino:
            termino_lower = termino.lower()
            nombre_orig = datos.get("nombre_original", clave).lower()
            if termino_lower not in clave and termino_lower not in nombre_orig:
                # Verificar palabras individuales
                palabras = termino_lower.split()
                texto = f"{clave} {nombre_orig}"
                if not any(p in texto for p in palabras):
                    continue

        resultados.append({
            "clave": clave,
            "nombre": datos.get("nombre_original", clave),
            "cantidad": datos.get("cantidad", 0),
            "minimo": datos.get("minimo", 5),
            "unidad": datos.get("unidad", "unidades"),
            "fecha_conteo": datos.get("fecha_conteo", ""),
        })

    # Ordenar por nombre
    resultados.sort(key=lambda x: x["nombre"].lower())
    return resultados[:limite]
