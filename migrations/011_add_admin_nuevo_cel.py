#!/usr/bin/env python3
"""
Migración 011: Agrega el nuevo número de Telegram de Andrés como admin.
Idempotente — seguro para ejecutar múltiples veces (ON CONFLICT DO NOTHING).
Ejecutar con: railway run python migrations/011_add_admin_nuevo_cel.py
"""

# -- stdlib --
import os

# -- terceros --
import psycopg2


def run_migration() -> None:
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # Insertar nuevo admin (nuevo cel de Andrés)
            cur.execute("""
                INSERT INTO usuarios (telegram_id, nombre, rol)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id) DO UPDATE
                    SET rol = EXCLUDED.rol,
                        activo = TRUE
            """, (8782658345, "Andrés (cel nuevo)", "admin"))

            rows_affected = cur.rowcount
            print(f"✓ Usuario telegram_id=8782658345 insertado/actualizado (filas: {rows_affected})")

            # Verificar resultado
            cur.execute(
                "SELECT id, telegram_id, nombre, rol, activo FROM usuarios WHERE telegram_id = %s",
                (8782658345,)
            )
            row = cur.fetchone()
            if row:
                print(f"✓ Verificación: id={row[0]}, telegram_id={row[1]}, nombre={row[2]}, rol={row[3]}, activo={row[4]}")

        conn.commit()
        print("\n✓ Migración completada.")

    except Exception as e:
        conn.rollback()
        print(f"✗ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
