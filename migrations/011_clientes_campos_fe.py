#!/usr/bin/env python3
"""
migrations/011_clientes_campos_fe.py
Agrega campos de facturación electrónica a la tabla clientes:
  - pais_id:        ID interno MATIAS del país (45 = Colombia por defecto)
  - regimen_fiscal: 1 = Responsable IVA, 2 = No Responsable (default)
  - ciudad_nombre:  Nombre display de la ciudad para facturas y PDFs

Ejecutar UNA VEZ:
    railway run python migrations/011_clientes_campos_fe.py
"""
import logging, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] -- %(message)s", stream=sys.stdout)
logger = logging.getLogger("011_clientes_campos_fe")

import db as _db

def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # 1. País MATIAS (45 = Colombia)
            cur.execute("""
                ALTER TABLE clientes
                    ADD COLUMN IF NOT EXISTS pais_id INTEGER DEFAULT 45;
            """)
            logger.info("✓ clientes: columna pais_id agregada")

            # 2. Régimen fiscal (2 = No Responsable por defecto)
            cur.execute("""
                ALTER TABLE clientes
                    ADD COLUMN IF NOT EXISTS regimen_fiscal INTEGER DEFAULT 2;
            """)
            logger.info("✓ clientes: columna regimen_fiscal agregada")

            # 3. Nombre de ciudad para display en facturas y PDFs
            cur.execute("""
                ALTER TABLE clientes
                    ADD COLUMN IF NOT EXISTS ciudad_nombre VARCHAR(120) DEFAULT 'Cartagena';
            """)
            logger.info("✓ clientes: columna ciudad_nombre agregada")

            # 4. Normalizar filas existentes sin ciudad_nombre
            cur.execute("""
                UPDATE clientes
                SET ciudad_nombre = 'Cartagena'
                WHERE ciudad_nombre IS NULL OR ciudad_nombre = '';
            """)
            logger.info("✓ clientes: ciudad_nombre normalizada en filas existentes")

        conn.commit()
        logger.info("✅ Migración 011 aplicada correctamente")

if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
