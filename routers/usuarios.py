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
    Lista vendedores disponibles para el selector del dashboard.

    Reglas:
      - Admin: ve todos los vendedores activos.
      - Vendedor: ve solo su propio nombre (defensa en profundidad — el filtro
        por vendor_id ajeno ya está bloqueado en get_filtro_efectivo, pero
        ocultar los nombres en la lista evita exponer información innecesaria).
    """
    try:
        rol = (current_user or {}).get("rol")
        usuario_id = (current_user or {}).get("usuario_id")

        if rol == "admin":
            rows = db.query_all(
                "SELECT id, nombre FROM usuarios WHERE activo = TRUE ORDER BY nombre"
            )
        else:
            # Vendedor (o rol ausente) — solo se ve a sí mismo.
            if usuario_id is None:
                return []
            rows = db.query_all(
                "SELECT id, nombre FROM usuarios WHERE id = %s AND activo = TRUE",
                (usuario_id,),
            )

        if not rows:
            return []
        return [{"id": r["id"], "nombre": r["nombre"]} for r in rows]
    except Exception:
        return []
