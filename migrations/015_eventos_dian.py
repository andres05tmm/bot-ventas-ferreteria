"""
migrations/015_eventos_dian.py
Agrega columnas de eventos RADIAN/DIAN a compras_fiscal.

Correr:
    railway run python migrations/015_eventos_dian.py
"""
import logging, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db as _db

logger = logging.getLogger("015_eventos_dian")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE compras_fiscal
                    ADD COLUMN IF NOT EXISTS cufe_proveedor VARCHAR(300),
                    ADD COLUMN IF NOT EXISTS evento_030_at  TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS evento_031_at  TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS evento_032_at  TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS evento_033_at  TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS evento_estado  VARCHAR(20) DEFAULT 'pendiente',
                    ADD COLUMN IF NOT EXISTS evento_error   TEXT;
            """)
            logger.info("✓ columnas de eventos DIAN agregadas a compras_fiscal")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_compras_fiscal_cufe
                    ON compras_fiscal(cufe_proveedor)
                    WHERE cufe_proveedor IS NOT NULL;
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_compras_fiscal_evento_estado
                    ON compras_fiscal(evento_estado);
            """)
            logger.info("✓ índices de eventos creados")
        conn.commit()
        logger.info("✅ Migración 015 aplicada correctamente")

if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB.")
        sys.exit(1)
    run()
