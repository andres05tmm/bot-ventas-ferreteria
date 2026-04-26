"""
auth/usuarios.py — Gestión de usuarios y autenticación por Telegram ID.
Proporciona funciones para obtener usuarios, verificar admin, registrar telegram IDs y crear vendedores.

Usa lazy imports de db para evitar dependencias circulares con handlers.
"""

# -- stdlib --
import logging

logger = logging.getLogger("ferrebot.auth.usuarios")


def get_usuario(telegram_id: int) -> dict | None:
    """
    Obtiene un usuario por su telegram_id.

    Args:
        telegram_id: ID de Telegram del usuario

    Returns:
        Dict con keys {id, telegram_id, nombre, rol, activo} o None si no existe
    """
    import db as _db

    try:
        if not _db.DB_DISPONIBLE:
            return None

        row = _db.query_one(
            "SELECT id, telegram_id, nombre, rol, activo FROM usuarios WHERE telegram_id = %s AND activo = TRUE",
            [telegram_id]
        )
        if not row:
            return None

        return {
            "id": row["id"],
            "telegram_id": row["telegram_id"],
            "nombre": row["nombre"],
            "rol": row["rol"],
            "activo": row["activo"],
        }
    except Exception as e:
        logger.warning(f"Error obteniendo usuario con telegram_id {telegram_id}: {e}")
        return None


def is_admin(telegram_id: int) -> bool:
    """
    Verifica si un usuario es administrador.

    Args:
        telegram_id: ID de Telegram del usuario

    Returns:
        True si el usuario existe y es admin, False en caso contrario
    """
    usuario = get_usuario(telegram_id)
    if not usuario:
        return False
    return usuario.get("rol") == "admin"


def registrar_telegram_id(nombre_parcial: str, telegram_id: int) -> bool:
    """
    Registra un telegram_id a un usuario vendedor existente (placeholder).
    Busca un nombre que coincida parcialmente y tenga telegram_id placeholder (1,2,3,4).

    Args:
        nombre_parcial: Nombre parcial del vendedor (ej: "Farid M")
        telegram_id: ID de Telegram a registrar

    Returns:
        True si se actualizó exactamente 1 fila, False en caso contrario
    """
    import db as _db

    try:
        if not _db.DB_DISPONIBLE:
            return False

        # Buscar un vendedor placeholder cuyo nombre coincida (LIKE)
        pattern = f"%{nombre_parcial}%"
        rowcount = _db.execute(
            """UPDATE usuarios
               SET telegram_id = %s
               WHERE LOWER(nombre) LIKE LOWER(%s)
                 AND activo = TRUE
                 AND telegram_id IN (1,2,3,4)""",
            [telegram_id, pattern]
        )

        return rowcount == 1
    except Exception as e:
        logger.warning(f"Error registrando telegram_id para {nombre_parcial}: {e}")
        return False


def crear_vendedor(nombre: str) -> bool:
    """
    Crea un nuevo vendedor con un telegram_id placeholder.
    Obtiene el siguiente placeholder (basado en MAX(telegram_id) < 1000) e inserta.

    Args:
        nombre: Nombre completo del nuevo vendedor

    Returns:
        True si se insertó correctamente, False en caso de error
    """
    import db as _db

    try:
        if not _db.DB_DISPONIBLE:
            return False

        # Obtener el siguiente placeholder (1,2,3,4 o el siguiente disponible < 1000)
        row = _db.query_one(
            "SELECT COALESCE(MAX(telegram_id), 0)+1 as next_placeholder FROM usuarios WHERE telegram_id < 1000",
            []
        )

        if not row:
            next_placeholder = 1
        else:
            next_placeholder = row["next_placeholder"]

        # Insertar nuevo vendedor
        _db.execute(
            "INSERT INTO usuarios (nombre, rol, telegram_id) VALUES (%s, %s, %s)",
            [nombre, "vendedor", next_placeholder]
        )

        return True
    except Exception as e:
        logger.warning(f"Error creando vendedor {nombre}: {e}")
        return False
