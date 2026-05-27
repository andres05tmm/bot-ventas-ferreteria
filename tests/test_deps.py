"""
tests/test_deps.py — Tests del RBAC en routers/deps.py.

Cubre la lógica de get_filtro_efectivo:
  - admin sin vendor_id           → None (ve todo)
  - admin con vendor_id            → ese id (puede impersonar a cualquiera)
  - vendedor sin vendor_id         → None (ve total agregado)
  - vendedor con vendor_id propio  → su propio id (filtra por sí mismo)
  - vendedor con vendor_id ajeno   → HTTPException 403

No requiere DATABASE_URL ni SECRET_KEY.
"""

# -- stdlib --
import sys
import types

# ── Stubs (deben preceder a los imports de proyecto) ──────────────────────────
if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    sys.modules["config"] = _cfg

if "db" not in sys.modules:
    _db = types.ModuleType("db")
    _db.DB_DISPONIBLE = False
    _db.query_one = lambda *a, **kw: None
    _db.query_all = lambda *a, **kw: []
    sys.modules["db"] = _db

# -- terceros --
import pytest
from fastapi import HTTPException

# -- propios --
from routers.deps import get_filtro_efectivo, get_filtro_usuario


# ─────────────────────────────────────────────
# Fixtures auxiliares
# ─────────────────────────────────────────────

ADMIN = {"usuario_id": 1, "telegram_id": 1831034712, "nombre": "Andrés", "rol": "admin"}
ADMIN_NUEVO = {"usuario_id": 7, "telegram_id": 8782658345, "nombre": "Andrés (cel nuevo)", "rol": "admin"}
VENDEDOR_FARID = {"usuario_id": 2, "telegram_id": 1, "nombre": "Farid M", "rol": "vendedor"}
VENDEDOR_KAROLAY = {"usuario_id": 3, "telegram_id": 3, "nombre": "Karolay", "rol": "vendedor"}


# ─────────────────────────────────────────────
# Tests — get_filtro_efectivo
# ─────────────────────────────────────────────

def test_admin_sin_vendor_id_retorna_none():
    """Admin sin ?vendor_id → None (ve todo agregado)."""
    assert get_filtro_efectivo(vendor_id=None, current_user=ADMIN) is None


def test_admin_con_vendor_id_retorna_ese_id():
    """Admin puede impersonar a cualquier vendedor."""
    assert get_filtro_efectivo(vendor_id=42, current_user=ADMIN) == 42


def test_admin_puede_filtrar_por_si_mismo():
    """Admin pasando su propio id obtiene su id."""
    assert get_filtro_efectivo(vendor_id=1, current_user=ADMIN) == 1


def test_admin_nuevo_tambien_puede_impersonar():
    """El segundo admin (Andrés cel nuevo) tiene los mismos privilegios."""
    assert get_filtro_efectivo(vendor_id=5, current_user=ADMIN_NUEVO) == 5


def test_vendedor_sin_vendor_id_retorna_none():
    """Vendedor sin ?vendor_id → None (ve total agregado, sin filtro)."""
    assert get_filtro_efectivo(vendor_id=None, current_user=VENDEDOR_FARID) is None


def test_vendedor_con_su_propio_id_retorna_su_id():
    """Vendedor filtrando por sí mismo: OK."""
    assert get_filtro_efectivo(vendor_id=2, current_user=VENDEDOR_FARID) == 2


def test_vendedor_con_otro_id_lanza_403():
    """Vendedor intentando ver datos de otro vendedor: HTTP 403."""
    with pytest.raises(HTTPException) as exc:
        get_filtro_efectivo(vendor_id=3, current_user=VENDEDOR_FARID)
    assert exc.value.status_code == 403


def test_vendedor_con_id_admin_tambien_lanza_403():
    """Vendedor no puede pasar el id de un admin tampoco."""
    with pytest.raises(HTTPException) as exc:
        get_filtro_efectivo(vendor_id=1, current_user=VENDEDOR_FARID)
    assert exc.value.status_code == 403


def test_vendedor_con_id_inexistente_lanza_403():
    """Si el vendedor pasa cualquier id que no sea el suyo, se rechaza (no se valida que exista)."""
    with pytest.raises(HTTPException) as exc:
        get_filtro_efectivo(vendor_id=99999, current_user=VENDEDOR_FARID)
    assert exc.value.status_code == 403


# ─────────────────────────────────────────────
# Tests — get_filtro_usuario (compatibilidad)
# ─────────────────────────────────────────────

def test_get_filtro_usuario_siempre_none():
    """get_filtro_usuario se mantiene retornando None para compatibilidad con routers viejos.
    La regla 'vendedor solo ve los suyos' no aplica al modelo actual (ven total + filtro opt-in).
    """
    assert get_filtro_usuario(current_user=ADMIN) is None
    assert get_filtro_usuario(current_user=VENDEDOR_FARID) is None


# ─────────────────────────────────────────────
# Tests — rol ausente o malformado (defensa)
# ─────────────────────────────────────────────

def test_usuario_sin_rol_se_trata_como_vendedor():
    """Si el JWT no trae 'rol', se asume el escenario más restrictivo: vendedor."""
    sin_rol = {"usuario_id": 99, "telegram_id": 0, "nombre": "?"}
    # Sin vendor_id → None (como cualquier vendedor que ve agregado)
    assert get_filtro_efectivo(vendor_id=None, current_user=sin_rol) is None
    # Con vendor_id != suyo → 403
    with pytest.raises(HTTPException) as exc:
        get_filtro_efectivo(vendor_id=1, current_user=sin_rol)
    assert exc.value.status_code == 403
    # Con vendor_id == suyo → su id
    assert get_filtro_efectivo(vendor_id=99, current_user=sin_rol) == 99
