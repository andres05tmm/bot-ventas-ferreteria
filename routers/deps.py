# -- stdlib --
import os
import jwt
import logging

# -- terceros --
from fastapi import Header, HTTPException, Depends

logger = logging.getLogger("ferrebot.routers.deps")


def get_current_user(authorization: str = Header(None)):
    """
    Valida JWT token del header Authorization.
    Retorna payload dict con: usuario_id, telegram_id, nombre, rol
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")

    try:
        token = authorization.split(" ")[1]
    except IndexError:
        raise HTTPException(status_code=401, detail="Token inválido")

    try:
        payload = jwt.decode(
            token,
            os.environ.get("SECRET_KEY", ""),
            algorithms=["HS256"]
        )
        return payload  # has: usuario_id, telegram_id, nombre, rol
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except Exception as e:
        logger.warning(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Token inválido")


def get_filtro_usuario(current_user=Depends(get_current_user)):
    """
    Retorna usuario_id si rol es vendedor, None si rol es admin.
    Se usa para filtrar datos en WHERE clauses.
    """
    if current_user["rol"] == "vendedor":
        return current_user["usuario_id"]
    return None
