"""
tests/test_auth_usuarios.py — Unit tests for auth/usuarios.py.

Patching strategy:
- Inject stub modules for config and db into sys.modules before importing
- All functions use lazy imports of db inside their bodies
- Mock db functions (query_one, execute) to simulate database behavior

No real database or API keys required.
"""

# -- stdlib --
import sys
import types
import threading

# Inject config stub
if "config" not in sys.modules:
    _config_stub = types.ModuleType("config")
    _config_stub.COLOMBIA_TZ = None
    _config_stub.claude_client = None
    sys.modules["config"] = _config_stub

# Inject db stub with required functions
if "db" not in sys.modules:
    _db_stub = types.ModuleType("db")
    _db_stub.DB_DISPONIBLE = True
    _db_stub.query_one = lambda *a, **kw: None
    _db_stub.execute = lambda *a, **kw: 0
    sys.modules["db"] = _db_stub

# -- terceros --
import pytest
from unittest.mock import patch, MagicMock

# -- propios --
from auth.usuarios import (
    get_usuario,
    is_admin,
    registrar_telegram_id,
    crear_vendedor,
)


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

@pytest.fixture
def admin_user():
    """Admin Andrés con telegram_id=1831034712."""
    return {
        "id": 1,
        "telegram_id": 1831034712,
        "nombre": "Andrés",
        "rol": "admin",
        "activo": True,
    }


@pytest.fixture
def vendedor_user():
    """Vendedor placeholder con telegram_id=1."""
    return {
        "id": 2,
        "telegram_id": 1,
        "nombre": "Farid M",
        "rol": "vendedor",
        "activo": True,
    }


# ─────────────────────────────────────────────
# TESTS — get_usuario
# ─────────────────────────────────────────────

@patch("db.query_one")
@patch("db.DB_DISPONIBLE", True)
def test_get_usuario_not_found(mock_query_one):
    """get_usuario retorna None si el usuario no existe."""
    mock_query_one.return_value = None
    result = get_usuario(999999999)
    assert result is None
    mock_query_one.assert_called_once()


@patch("db.query_one")
@patch("db.DB_DISPONIBLE", True)
def test_get_usuario_found(mock_query_one, admin_user):
    """get_usuario retorna dict con claves id, telegram_id, nombre, rol, activo."""
    mock_query_one.return_value = admin_user
    result = get_usuario(1831034712)
    assert result is not None
    assert result["id"] == 1
    assert result["telegram_id"] == 1831034712
    assert result["nombre"] == "Andrés"
    assert result["rol"] == "admin"
    assert result["activo"] is True


@patch("db.query_one")
@patch("db.DB_DISPONIBLE", True)
def test_get_usuario_exception_returns_none(mock_query_one):
    """get_usuario retorna None si hay excepción en DB."""
    mock_query_one.side_effect = Exception("DB error")
    result = get_usuario(1831034712)
    assert result is None


# ─────────────────────────────────────────────
# TESTS — is_admin
# ─────────────────────────────────────────────

@patch("db.query_one")
@patch("db.DB_DISPONIBLE", True)
def test_is_admin_true(mock_query_one, admin_user):
    """is_admin retorna True para usuarios con rol='admin'."""
    mock_query_one.return_value = admin_user
    result = is_admin(1831034712)
    assert result is True


@patch("db.query_one")
@patch("db.DB_DISPONIBLE", True)
def test_is_admin_false(mock_query_one, vendedor_user):
    """is_admin retorna False para usuarios con rol='vendedor'."""
    mock_query_one.return_value = vendedor_user
    result = is_admin(1)
    assert result is False


@patch("db.query_one")
@patch("db.DB_DISPONIBLE", True)
def test_is_admin_user_not_found(mock_query_one):
    """is_admin retorna False si el usuario no existe."""
    mock_query_one.return_value = None
    result = is_admin(999999999)
    assert result is False


# ─────────────────────────────────────────────
# TESTS — registrar_telegram_id
# ─────────────────────────────────────────────

@patch("db.execute")
@patch("db.DB_DISPONIBLE", True)
def test_registrar_telegram_id_not_found(mock_execute):
    """registrar_telegram_id retorna False si no encuentra el nombre."""
    mock_execute.return_value = 0  # Sin filas actualizadas
    result = registrar_telegram_id("XYZNoExiste", 9999999)
    assert result is False


@patch("db.execute")
@patch("db.DB_DISPONIBLE", True)
def test_registrar_telegram_id_success(mock_execute):
    """registrar_telegram_id retorna True si actualiza exactamente 1 fila."""
    mock_execute.return_value = 1  # 1 fila actualizada
    result = registrar_telegram_id("Farid M", 9999991)
    assert result is True
    # Verificar que execute fue llamado con parámetros correctos
    mock_execute.assert_called_once()
    call_args = mock_execute.call_args
    assert "Farid M" in str(call_args[0]) or any("Farid M" in str(arg) for arg in call_args[0])
    assert 9999991 in call_args[0][1]


@patch("db.execute")
@patch("db.DB_DISPONIBLE", True)
def test_registrar_telegram_id_multiple_matches(mock_execute):
    """registrar_telegram_id retorna False si actualiza más de 1 fila."""
    mock_execute.return_value = 2  # 2 filas actualizadas (error)
    result = registrar_telegram_id("Farid", 9999991)
    assert result is False


@patch("db.execute")
@patch("db.DB_DISPONIBLE", True)
def test_registrar_telegram_id_exception(mock_execute):
    """registrar_telegram_id retorna False en caso de excepción."""
    mock_execute.side_effect = Exception("DB error")
    result = registrar_telegram_id("Farid M", 9999991)
    assert result is False


@patch("db.DB_DISPONIBLE", False)
def test_registrar_telegram_id_db_unavailable():
    """registrar_telegram_id retorna False si DB no está disponible."""
    result = registrar_telegram_id("Farid M", 9999991)
    assert result is False


# ─────────────────────────────────────────────
# TESTS — crear_vendedor
# ─────────────────────────────────────────────

@patch("db.query_one")
@patch("db.execute")
@patch("db.DB_DISPONIBLE", True)
def test_crear_vendedor_success(mock_execute, mock_query_one):
    """crear_vendedor retorna True si inserta correctamente."""
    # Mock para obtener el próximo placeholder
    mock_query_one.return_value = {"next_placeholder": 5}
    mock_execute.return_value = None  # INSERT sin RETURNING
    result = crear_vendedor("Test Vendedor")
    assert result is True
    # Verificar que execute fue llamado
    mock_execute.assert_called_once()


@patch("db.query_one")
@patch("db.execute")
@patch("db.DB_DISPONIBLE", True)
def test_crear_vendedor_no_max(mock_execute, mock_query_one):
    """crear_vendedor obtiene placeholder 1 si MAX es NULL."""
    mock_query_one.return_value = None
    mock_execute.return_value = None
    result = crear_vendedor("New Vendedor")
    assert result is True


@patch("db.query_one")
@patch("db.execute")
@patch("db.DB_DISPONIBLE", True)
def test_crear_vendedor_exception(mock_execute, mock_query_one):
    """crear_vendedor retorna False en caso de excepción."""
    mock_query_one.side_effect = Exception("DB error")
    result = crear_vendedor("Test Vendedor")
    assert result is False


@patch("db.DB_DISPONIBLE", False)
def test_crear_vendedor_db_unavailable():
    """crear_vendedor retorna False si DB no está disponible."""
    result = crear_vendedor("Test Vendedor")
    assert result is False


# ─────────────────────────────────────────────
# INTEGRATION-STYLE TESTS (still mocked DB)
# ─────────────────────────────────────────────

@patch("db.query_one")
@patch("db.DB_DISPONIBLE", True)
def test_get_usuario_workflow(mock_query_one, admin_user):
    """
    Workflow completo: get_usuario + is_admin.
    Simula que un usuario admin intenta verificarse.
    """
    mock_query_one.return_value = admin_user

    # Primero get_usuario
    usuario = get_usuario(1831034712)
    assert usuario is not None

    # Luego is_admin (hace su propio call a get_usuario)
    mock_query_one.reset_mock()
    mock_query_one.return_value = admin_user
    es_admin = is_admin(1831034712)
    assert es_admin is True
