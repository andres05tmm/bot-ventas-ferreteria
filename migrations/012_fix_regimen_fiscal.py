#!/usr/bin/env python3
"""
migrations/012_fix_regimen_fiscal.py

Corrige la columna `regimen_fiscal` de la tabla `clientes`:
  - La migración 008 la creó como VARCHAR(30) con default 'no_responsable_iva'.
  - La migración 011 intentó agregarla como INTEGER, pero fue un no-op porque
    ya existía → la columna siguió siendo VARCHAR con strings legados.
  - Esta migración convierte los valores y cambia el tipo a INTEGER:
      'responsable_iva' | '1' | 1  →  1  (Responsable de IVA)
      cualquier otro valor           →  2  (No Responsable — default seguro)

Ejecutar UNA VEZ en Railway:
    railway run python migrations/012_fix_regimen_fiscal.py
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
logger = logging.getLogger("012_fix_regimen_fiscal")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # 1. Verificar tipo actual de la columna
            cur.execute("""
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'clientes'
                  AND column_name = 'regimen_fiscal';
            """)
            row = cur.fetchone()
            if not row:
                logger.error("❌ Columna regimen_fiscal no existe en tabla clientes")
                return

            tipo_actual = (row.get("data_type") or row.get(0) or "character varying").lower()
            logger.info(f"Tipo actual de regimen_fiscal: {tipo_actual}")

            if tipo_actual in ("integer", "bigint", "smallint"):
                logger.info("✓ regimen_fiscal ya es INTEGER — solo normalizando valores fuera de rango")
                cur.execute("""
                    UPDATE clientes
                    SET regimen_fiscal = 2
                    WHERE regimen_fiscal NOT IN (1, 2) OR regimen_fiscal IS NULL;
                """)
                logger.info(f"  Filas normalizadas: {cur.rowcount}")
            else:
                # 2. Soltar el default VARCHAR antes de cambiar el tipo
                #    (PostgreSQL no puede castear 'no_responsable_iva' → INTEGER automáticamente)
                logger.info("Soltando default VARCHAR …")
                cur.execute("""
                    ALTER TABLE clientes
                    ALTER COLUMN regimen_fiscal DROP DEFAULT;
                """)
                logger.info("✓ Default soltado")

                # 3. Convertir strings a números usando USING clause
                logger.info("Convirtiendo columna VARCHAR → INTEGER …")
                cur.execute("""
                    ALTER TABLE clientes
                    ALTER COLUMN regimen_fiscal
                    TYPE INTEGER
                    USING (
                        CASE
                            WHEN LOWER(TRIM(regimen_fiscal)) IN ('responsable_iva', 'responsable', '1')
                                THEN 1
                            ELSE 2
                        END
                    );
                """)
                logger.info("✓ Columna convertida a INTEGER")

                # 4. Establecer default correcto (ya con tipo INTEGER)
                cur.execute("""
                    ALTER TABLE clientes
                    ALTER COLUMN regimen_fiscal SET DEFAULT 2;
                """)
                logger.info("✓ Default establecido a 2 (No Responsable de IVA)")

            # 4. Verificar resultado
            cur.execute("""
                SELECT regimen_fiscal, COUNT(*) AS total
                FROM clientes
                GROUP BY regimen_fiscal
                ORDER BY regimen_fiscal;
            """)
            rows = cur.fetchall()
            logger.info("Distribución final de regimen_fiscal:")
            for r in rows:
                val = r.get("regimen_fiscal") if isinstance(r, dict) else r[0]
                cnt = r.get("total") if isinstance(r, dict) else r[1]
                etiqueta = "Responsable IVA" if val == 1 else "No Responsable"
                logger.info(f"  {val} ({etiqueta}): {cnt} clientes")

        conn.commit()
        logger.info("✅ Migración 012 aplicada correctamente")


if __name__ == "__main__":
    if not _db.init_db():
        logger.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)
    run()
