# -- stdlib --
import os
import jwt
import logging

# -- terceros --
from fastapi import Header, HTTPException, Depends, Query

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


def get_current_user_optional(authorization: str = Header(None)):
    """
    Versión NO bloqueante de get_current_user — retorna el payload del JWT
    si viene válido, o None si falta o es inválido.

    Útil para endpoints que NO requieren auth pero que se benefician de saber
    quién hace la petición (ej: tracking de budget por vendedor en /chat).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        token = authorization.split(" ")[1]
        return jwt.decode(
            token,
            os.environ.get("SECRET_KEY", ""),
            algorithms=["HS256"],
        )
    except Exception:
        return None


def get_filtro_usuario(current_user=Depends(get_current_user)):
    """
    Siempre retorna None — todos los usuarios ven datos de todos los vendedores.
    Se mantiene para compatibilidad con los routers que lo usan.
    """
    return None


def get_filtro_efectivo(
    vendor_id: int | None = Query(None),
    current_user=Depends(get_current_user)
):
    """
    Admin con vendor_id seleccionado → filtra por ese vendedor
    Admin sin vendor_id → sin filtro (ve todos los vendedores)
    Vendedor → sin filtro (ve datos de todos los vendedores)
    """
    if vendor_id:
        return vendor_id
    return None  # todos ven todo
