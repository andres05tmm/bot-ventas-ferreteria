# Migrado desde migrate_memoria.py (raíz del proyecto)
# Este archivo es una copia exacta. El original se mantiene en raíz hasta que Phase 1 esté verde.
"""
migrate_memoria.py — Migra memoria.json a PostgreSQL.

Ejecutar UNA SOLA VEZ despues del primer deploy de Fase 1:
    railway run python migrate_memoria.py

Seguro de re-ejecutar: usa UPSERT (ON CONFLICT) en todas las operaciones (D-09).

CORRECCIONES vs script ejemplo de MIGRATION.md:
  - Agrega migracion de alias (CAT-02)
  - Agrega campos unidad_medida y codigo
  - UPSERT correcto para fracciones (usa uq_prod_fraccion unique index)
  - Log de conflictos de alias duplicados
"""

# -- stdlib --
import json
import logging
import sys
import os

# Configurar logging basico para ver output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("migrate_memoria")

# -- propios --
import db


def migrar():
    """Migra catalogo e inventario de memoria.json a las tablas PostgreSQL."""
    # Inicializar DB
    if not db.init_db():
        logger.error("No se pudo conectar a PostgreSQL. Verifica DATABASE_URL.")
        sys.exit(1)

    # Leer memoria.json
    memoria_file = os.getenv("MEMORIA_FILE", "memoria.json")
    if not os.path.exists(memoria_file):
        logger.error(f"No se encontro {memoria_file}")
        sys.exit(1)

    with open(memoria_file, encoding="utf-8") as f:
        mem = json.load(f)

    catalogo = mem.get("catalogo", {})
    inventario = mem.get("inventario", {})

    logger.info(f"Migrando {len(catalogo)} productos...")

    # Contadores
    productos_ok = 0
    fracciones_ok = 0
    pxc_ok = 0
    alias_ok = 0
    alias_conflictos = 0
    inventario_ok = 0

    for clave, prod in catalogo.items():
        # 1. Insertar/actualizar producto
        row = db.execute_returning("""
            INSERT INTO productos (clave, nombre, nombre_lower, codigo, categoria, precio_unidad, unidad_medida)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (clave) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                nombre_lower = EXCLUDED.nombre_lower,
                codigo = EXCLUDED.codigo,
                categoria = EXCLUDED.categoria,
                precio_unidad = EXCLUDED.precio_unidad,
                unidad_medida = EXCLUDED.unidad_medida,
                updated_at = NOW()
            RETURNING id
        """, (
            clave,
            prod.get("nombre", ""),
            prod.get("nombre_lower", prod.get("nombre", "").lower()),
            prod.get("codigo") or None,
            prod.get("categoria", ""),
            prod.get("precio_unidad", 0),
            prod.get("unidad_medida", "Unidad"),
        ))
        if not row:
            logger.warning(f"No se pudo insertar producto: {clave}")
            continue
        prod_id = row["id"]
        productos_ok += 1

        # 2. Fracciones — UPSERT usando unique index uq_prod_fraccion(producto_id, fraccion)
        for frac, datos in prod.get("precios_fraccion", {}).items():
            db.execute("""
                INSERT INTO productos_fracciones (producto_id, fraccion, precio_total, precio_unitario)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (producto_id, fraccion) DO UPDATE SET
                    precio_total = EXCLUDED.precio_total,
                    precio_unitario = EXCLUDED.precio_unitario
            """, (prod_id, frac, datos.get("precio", 0), datos.get("precio_unitario", 0)))
            fracciones_ok += 1

        # 3. Precio por cantidad
        pxc = prod.get("precio_por_cantidad", {})
        if pxc:
            db.execute("""
                INSERT INTO productos_precio_cantidad
                    (producto_id, umbral, precio_bajo_umbral, precio_sobre_umbral)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (producto_id) DO UPDATE SET
                    umbral = EXCLUDED.umbral,
                    precio_bajo_umbral = EXCLUDED.precio_bajo_umbral,
                    precio_sobre_umbral = EXCLUDED.precio_sobre_umbral
            """, (
                prod_id,
                pxc.get("umbral", 50),
                pxc.get("precio_bajo_umbral", prod.get("precio_unidad", 0)),
                pxc.get("precio_sobre_umbral", 0),
            ))
            pxc_ok += 1

        # 4. Alias (CAT-02) — ON CONFLICT DO NOTHING + log conflictos
        alias_list = prod.get("alias", [])
        # Normalizar: si es string en vez de lista, convertir
        if isinstance(alias_list, str):
            alias_list = [alias_list] if alias_list.strip() else []
        for alias_str in alias_list:
            if not alias_str or not isinstance(alias_str, str) or not alias_str.strip():
                continue
            result = db.execute("""
                INSERT INTO productos_alias (producto_id, alias)
                VALUES (%s, %s)
                ON CONFLICT (alias) DO NOTHING
            """, (prod_id, alias_str.strip()))
            if result == 0:
                # ON CONFLICT DO NOTHING — el alias ya existe para otro producto
                logger.warning(
                    f"Alias duplicado ignorado: '{alias_str.strip()}' "
                    f"(producto '{clave}' no pudo reclamar este alias)"
                )
                alias_conflictos += 1
            else:
                alias_ok += 1

    logger.info(f"Catalogo migrado: {productos_ok} productos, "
                f"{fracciones_ok} fracciones, {pxc_ok} precios por cantidad, "
                f"{alias_ok} alias ({alias_conflictos} conflictos)")

    # 5. Inventario (CAT-03)
    logger.info(f"Migrando {len(inventario)} items de inventario...")
    for clave, datos in inventario.items():
        prod_row = db.query_one("SELECT id FROM productos WHERE clave = %s", (clave,))
        if not prod_row:
            logger.warning(f"Inventario: producto '{clave}' no encontrado en tabla productos — saltando")
            continue
        db.execute("""
            INSERT INTO inventario (producto_id, cantidad, minimo, unidad, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (producto_id) DO UPDATE SET
                cantidad = EXCLUDED.cantidad,
                minimo = EXCLUDED.minimo,
                unidad = EXCLUDED.unidad,
                updated_at = NOW()
        """, (
            prod_row["id"],
            datos.get("cantidad", 0),
            datos.get("minimo", 0),
            datos.get("unidad", "Unidad"),
        ))
        inventario_ok += 1

    logger.info(f"Inventario migrado: {inventario_ok} items")

    # Resumen final
    logger.info("=" * 50)
    logger.info("MIGRACION COMPLETA")
    logger.info(f"  Productos:         {productos_ok}")
    logger.info(f"  Fracciones:        {fracciones_ok}")
    logger.info(f"  Precios x cant:    {pxc_ok}")
    logger.info(f"  Alias:             {alias_ok} (conflictos: {alias_conflictos})")
    logger.info(f"  Inventario:        {inventario_ok}")
    logger.info("=" * 50)


if __name__ == "__main__":
    migrar()
