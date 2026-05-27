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
    Siempre retorna None — todos los usuarios ven datos de todos los vendedores
    por defecto. El filtrado opcional por vendedor vive en get_filtro_efectivo.

    Se mantiene este helper para compatibilidad con los routers que lo usan.
    """
    return None


def get_filtro_efectivo(
    vendor_id: int | None = Query(None),
    current_user=Depends(get_current_user)
):
    """
    Resuelve el filtro por vendedor aplicado a un endpoint.

    Reglas:
      - Admin sin vendor_id           → None (ve todo agregado).
      - Admin con vendor_id           → ese id (puede impersonar a cualquier vendedor).
      - Vendedor sin vendor_id        → None (ve total agregado).
      - Vendedor con vendor_id propio → su propio id (filtra por sí mismo).
      - Vendedor con vendor_id ajeno  → HTTPException 403.

    Nota: si el JWT no trae 'rol', se asume el escenario más restrictivo
    (vendedor) para fail-safe.
    """
    rol = (current_user or {}).get("rol")
    usuario_id = (current_user or {}).get("usuario_id")

    # Admin: puede pasar cualquier vendor_id o ninguno.
    if rol == "admin":
        return vendor_id

    # Vendedor (o rol ausente — fail-safe).
    # Sin filtro → ve agregado total. Es el comportamiento por defecto.
    if vendor_id is None:
        return None

    # Sólo se permite filtrar por uno mismo.
    if vendor_id == usuario_id:
        return vendor_id

    # Intento de impersonación: deniega.
    logger.warning(
        "Intento de filtrar por otro vendedor: usuario_id=%s rol=%s pidió vendor_id=%s",
        usuario_id, rol, vendor_id,
    )
    raise HTTPException(status_code=403, detail="No autorizado para ver datos de otro vendedor")
