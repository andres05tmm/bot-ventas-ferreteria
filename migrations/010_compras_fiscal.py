#!/usr/bin/env python3
"""
migrations/010_compras_fiscal.py
Crea la tabla compras_fiscal para contabilidad de doble entrada.

Propósito:
  - compras          → registro operativo (almacén / inventario)
  - compras_fiscal   → registro contable (Libro IVA / declaraciones)

Las dos tablas pueden sincronizarse mutuamente con un botón desde el
dashboard, pero son independientes: una compra operativa no siempre
lleva factura fiscal, y viceversa.

Columnas extra vs compras:
  - numero_factura   → número de factura del proveedor (obligatorio para FE)
  - notas_fiscales   → observaciones para el libro IVA
  - compra_origen_id → FK opcional a compras.id (si vino de sincronización)

Ejecutar UNA VEZ:
    railway run python migrations/010_compras_fiscal.py
"""
import logging, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] -- %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("010_compras_fiscal")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── 1. Tabla principal compras_fiscal ─────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS compras_fiscal (
                    id               SERIAL PRIMARY KEY,
                    fecha            DATE        NOT NULL,
                    hora             TIME,
                    proveedor        VARCHAR(200),
                    producto_id      INTEGER     REFERENCES productos(id),
                    producto_nombre  VARCHAR(300) NOT NULL,
                    cantidad         NUMERIC(10,3) NOT NULL,
                    costo_unitario   INTEGER,
                    costo_total      INTEGER,
                    incluye_iva      BOOLEAN     DEFAULT FALSE,
                    tarifa_iva       INTEGER     DEFAULT 0,
                    numero_factura   VARCHAR(100),
                    notas_fiscales   TEXT,
                    compra_origen_id INTEGER     REFERENCES compras(id) ON DELETE SET NULL,
                    usuario_id       INTEGER,
                    created_at       TIMESTAMP   DEFAULT NOW(),
                    updated_at       TIMESTAMP   DEFAULT NOW()
                );
            """)
            logger.info("✓ tabla compras_fiscal creada (o ya existía)")

            # ── 2. Índices de rendimiento ──────────────────────────────────
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_compras_fiscal_fecha
                    ON compras_fiscal(fecha);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_compras_fiscal_iva
                    ON compras_fiscal(incluye_iva, tarifa_iva)
                    WHERE incluye_iva = TRUE;
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_compras_fiscal_origen
                    ON compras_fiscal(compra_origen_id)
                    WHERE compra_origen_id IS NOT NULL;
            """)
            logger.info("✓ índices de compras_fiscal creados")

            # ── 3. Columna compra_fiscal_id en compras (referencia inversa) ─
            # Permite saber desde compras si ya tiene una entrada fiscal
            cur.execute("""
                ALTER TABLE compras
                    ADD COLUMN IF NOT EXISTS compra_fiscal_id INTEGER
                        REFERENCES compras_fiscal(id) ON DELETE SET NULL;
            """)
            logger.info("✓ compras: columna compra_fiscal_id agregada")

            # ── 4. Trigger updated_at automático ──────────────────────────
            cur.execute("""
                CREATE OR REPLACE FUNCTION set_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                DROP TRIGGER IF EXISTS trg_compras_fiscal_updated_at
                    ON compras_fiscal;
            """)
            cur.execute("""
                CREATE TRIGGER trg_compras_fiscal_updated_at
                    BEFORE UPDATE ON compras_fiscal
                    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """)
            logger.info("✓ trigger updated_at en compras_fiscal creado")

        conn.commit()
        logger.info("✅ Migración 010 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
