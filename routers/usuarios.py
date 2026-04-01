# -- stdlib --
# -- terceros --
from fastapi import APIRouter, Depends

# -- propios --
from routers.deps import get_current_user
import db

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("/vendedores")
def listar_vendedores(current_user=Depends(get_current_user)):
    """
    Lista todos los vendedores activos (id, nombre).
    Cualquier usuario autenticado puede acceder.
    """
    try:
        rows = db.query_all(
            "SELECT id, nombre FROM usuarios WHERE activo = TRUE ORDER BY nombre"
        )
        if not rows:
            return []
        return [{"id": r["id"], "nombre": r["nombre"]} for r in rows]
    except Exception:
        return []
