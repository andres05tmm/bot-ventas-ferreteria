"""
scripts/seed_admin.py — Siembra el usuario administrador de una ferretería nueva.

Lee ADMIN_TELEGRAM_ID y ADMIN_NOMBRE del entorno e inserta (o actualiza) la fila
en `usuarios` con rol='admin'. Idempotente: correrlo dos veces no duplica ni rompe.

Uso (tras `alembic upgrade head` sobre la BD nueva):
    railway run python scripts/seed_admin.py
    # o local con .env:  python scripts/seed_admin.py

Variables de entorno requeridas:
    DATABASE_URL        — conexión Postgres (Railway la provee)
    ADMIN_TELEGRAM_ID   — Telegram ID del dueño (entero; obtener con @userinfobot)
    ADMIN_NOMBRE        — nombre del admin
"""

# -- stdlib --
import os
import sys

# Permitir `import db` al correr desde la raíz del repo o desde scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Consola en UTF-8 (los mensajes usan ✅/❌; evita crash en Windows cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# -- terceros --
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # en Railway las env vars ya están en el entorno

# -- propios --
import db as _db


def main() -> int:
    tg_raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    nombre = os.getenv("ADMIN_NOMBRE", "").strip()

    if not tg_raw or not nombre:
        print("❌ Falta ADMIN_TELEGRAM_ID y/o ADMIN_NOMBRE en el entorno.")
        print("   Ejemplo:  ADMIN_TELEGRAM_ID=123456789  ADMIN_NOMBRE='Pedro Pérez'")
        return 1
    try:
        telegram_id = int(tg_raw)
    except ValueError:
        print(f"❌ ADMIN_TELEGRAM_ID debe ser un entero, recibí: {tg_raw!r}")
        return 1

    if not _db.init_db():
        print("❌ No se pudo conectar a la BD. ¿DATABASE_URL configurada?")
        return 1

    # UPSERT idempotente — usuarios.telegram_id es UNIQUE.
    row = _db.execute_returning(
        """
        INSERT INTO usuarios (telegram_id, nombre, rol, activo)
        VALUES (%s, %s, 'admin', TRUE)
        ON CONFLICT (telegram_id) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            rol    = 'admin',
            activo = TRUE
        RETURNING id, telegram_id, nombre, rol
        """,
        [telegram_id, nombre],
    )
    if not row:
        print("❌ El INSERT no devolvió fila — revisar logs de db.")
        return 1

    print(f"✅ Admin sembrado: id={row['id']} telegram_id={row['telegram_id']} "
          f"nombre={row['nombre']!r} rol={row['rol']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
