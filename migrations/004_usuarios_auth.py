#!/usr/bin/env python3
"""
Migración 004: Schema de autenticación de usuarios.
Idempotente — seguro para ejecutar múltiples veces.
Ejecutar con: railway run python migrations/004_usuarios_auth.py
"""

# -- stdlib --
import asyncio
import os

# -- terceros --
import asyncpg


async def run_migration():
    database_url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(database_url)
    try:
        # 1. Crear tabla usuarios
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                nombre      VARCHAR(100) NOT NULL,
                rol         VARCHAR(20) NOT NULL DEFAULT 'vendedor',
                activo      BOOLEAN NOT NULL DEFAULT TRUE,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        print("✓ Tabla 'usuarios' creada (o ya existía)")

        # 2. Agregar columna usuario_id a tablas de transacciones
        for tabla in ("ventas", "gastos", "compras", "facturas_proveedores"):
            await conn.execute(f"""
                ALTER TABLE {tabla}
                ADD COLUMN IF NOT EXISTS usuario_id INT REFERENCES usuarios(id)
            """)
            print(f"✓ Columna 'usuario_id' en '{tabla}' (o ya existía)")

        # 3. Crear índices
        indices = [
            ("idx_ventas_usuario_id",               "ventas",               "usuario_id"),
            ("idx_gastos_usuario_id",               "gastos",               "usuario_id"),
            ("idx_compras_usuario_id",              "compras",              "usuario_id"),
            ("idx_facturas_proveedores_usuario_id", "facturas_proveedores", "usuario_id"),
        ]
        for idx_name, tabla, col in indices:
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS {idx_name} ON {tabla} ({col})
            """)
            print(f"✓ Índice '{idx_name}' creado (o ya existía)")

        # 4. Seed usuarios
        seed_data = [
            (1831034712, "Andrés",  "admin"),
            (1,          "Farid M", "vendedor"),
            (2,          "Farid D", "vendedor"),
            (3,          "Karolay", "vendedor"),
            (4,          "Papá",    "vendedor"),
        ]
        for telegram_id, nombre, rol in seed_data:
            await conn.execute("""
                INSERT INTO usuarios (telegram_id, nombre, rol)
                VALUES ($1, $2, $3)
                ON CONFLICT (telegram_id) DO NOTHING
            """, telegram_id, nombre, rol)
        print(f"✓ Seed de {len(seed_data)} usuarios insertado (ON CONFLICT DO NOTHING)")

        # Conteo final
        count = await conn.fetchval("SELECT COUNT(*) FROM usuarios")
        print(f"\n✓ Migración completada. Total usuarios en tabla: {count}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
