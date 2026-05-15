"""
tests/test_inventario_service.py — Unit tests for services/inventario_service.py.

Patching strategy:
- Inject config stub to avoid SystemExit(1) from missing env vars.
- Inject memoria stub; patch `memoria.cargar_memoria` per-test to return INVENTARIO_MOCK.
- Patch `services.inventario_service.guardar_inventario` for tests that trigger writes,
  preventing real DB calls.
- Inject db stub with DB_DISPONIBLE = False for cargar_inventario DB path.

⚠️  CONTRATO CRÍTICO: descontar_inventario() DEBE retornar (bool, str|None, float|None).
    ventas_state.py línea 210 destructura esta tupla — se testea explícitamente.

No real database or Telegram credentials required.
"""

# -- stdlib --
import sys
import types

# Inject config stub to avoid SystemExit(1) from missing env vars
if "config" not in sys.modules:
    _config_stub = types.ModuleType("config")
    _config_stub.COLOMBIA_TZ = None
    _config_stub.claude_client = None
    _config_stub.openai_client = None
    sys.modules["config"] = _config_stub

# Inject db stub — DB_DISPONIBLE = False so no real PG calls happen
if "db" not in sys.modules:
    _db_stub = types.ModuleType("db")
    _db_stub.DB_DISPONIBLE = False
    _db_stub.query_one = lambda *a, **kw: None
    _db_stub.query_all = lambda *a, **kw: []
    _db_stub.execute = lambda *a, **kw: None
    sys.modules["db"] = _db_stub

# Inject memoria stub — functions patched per-test
if "memoria" not in sys.modules:
    _memoria_stub = types.ModuleType("memoria")
    _memoria_stub.cargar_memoria = lambda: {"inventario": {}}
    _memoria_stub.cargar_inventario = lambda: {}
    _memoria_stub.guardar_inventario = lambda *a, **kw: None
    _memoria_stub._cache = None
    _memoria_stub._cache_lock = __import__("threading").Lock()
    sys.modules["memoria"] = _memoria_stub

# -- terceros --
import pytest
from unittest.mock import patch, MagicMock

# -- propios --
from services.inventario_service import (
    descontar_inventario,
    verificar_alertas_inventario,
    buscar_clave_inventario,
    cargar_inventario,
)

# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

INVENTARIO_MOCK = {
    "tornillo": {
        "nombre_lower": "tornillo",
        "nombre_original": "Tornillo",
        "cantidad": 100.0,
        "minimo": 10.0,
        "unidad": "unidades",
    },
    "cemento": {
        "nombre_lower": "cemento",
        "nombre_original": "Cemento",
        "cantidad": 3.0,
        "minimo": 5.0,
        "unidad": "bultos",
    },
}

MEMORIA_CON_INVENTARIO = {"inventario": INVENTARIO_MOCK}


# ─────────────────────────────────────────────
# TESTS — descontar_inventario (contrato 3-tupla)
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value=MEMORIA_CON_INVENTARIO)
@patch("services.inventario_service.guardar_inventario")
def test_descontar_inventario_retorna_contrato(mock_gi, mock_cm):
    """descontar_inventario DEBE retornar exactamente (bool, str|None, float|None)."""
    result = descontar_inventario("tornillo", 5.0)
    assert isinstance(result, tuple), "Must return a tuple"
    assert len(result) == 3, "Must return exactly 3 elements"
    ok, msg, cant = result
    assert isinstance(ok, bool), "First element must be bool"
    assert msg is None or isinstance(msg, str), "Second element must be str or None"
    assert cant is None or isinstance(cant, float), "Third element must be float or None"


@patch("memoria.cargar_memoria", return_value={"inventario": {
    "tornillo": {"nombre_lower": "tornillo", "nombre_original": "Tornillo",
                 "cantidad": 50.0, "minimo": 5.0, "unidad": "unidades"}
}})
@patch("services.inventario_service.guardar_inventario")
def test_descontar_inventario_exito(mock_gi, mock_cm):
    """descontar_inventario debe retornar (True, ..., nueva_cantidad) en caso exitoso."""
    ok, msg, nueva_cant = descontar_inventario("tornillo", 10.0)
    assert ok is True
    assert nueva_cant is not None
    assert nueva_cant == pytest.approx(40.0, abs=0.1)


@patch("memoria.cargar_memoria", return_value={"inventario": {}})
def test_descontar_inventario_producto_no_encontrado(mock_cm):
    """descontar_inventario debe retornar (False, None, None) si el producto no existe."""
    ok, msg, cant = descontar_inventario("no_existe_xyz", 1.0)
    assert ok is False
    assert msg is None
    assert cant is None


@patch("memoria.cargar_memoria", return_value={"inventario": {
    "cemento": {"nombre_original": "Cemento", "cantidad": 3.0, "minimo": 5.0, "unidad": "bultos"}
}})
@patch("services.inventario_service.guardar_inventario")
def test_descontar_inventario_genera_alerta_stock_bajo(mock_gi, mock_cm):
    """descontar_inventario debe generar alerta cuando cantidad <= minimo."""
    ok, msg, cant = descontar_inventario("cemento", 1.0)
    assert ok is True
    # msg debe ser string de alerta ya que cantidad_nueva (2) < minimo (5)
    assert isinstance(msg, str)
    assert cant is not None


# ─────────────────────────────────────────────
# TESTS — verificar_alertas_inventario
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value=MEMORIA_CON_INVENTARIO)
def test_verificar_alertas_retorna_lista(mock_cm):
    """verificar_alertas_inventario debe retornar una lista."""
    alertas = verificar_alertas_inventario()
    assert isinstance(alertas, list)
    # cemento tiene cantidad=3 < minimo=5, debe aparecer en alertas
    assert any("cemento" in a.lower() for a in alertas)


@patch("memoria.cargar_memoria", return_value={"inventario": {
    "tornillo": {"nombre_lower": "tornillo", "cantidad": 100.0, "minimo": 10.0, "unidad": "unidades"}
}})
def test_verificar_alertas_vacia_cuando_ok(mock_cm):
    """verificar_alertas_inventario debe retornar lista vacía cuando todo está en orden."""
    alertas = verificar_alertas_inventario()
    assert isinstance(alertas, list)
    assert len(alertas) == 0


# ─────────────────────────────────────────────
# TESTS — buscar_clave_inventario
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value=MEMORIA_CON_INVENTARIO)
def test_buscar_clave_inventario_exacto(mock_cm):
    """buscar_clave_inventario debe encontrar clave por coincidencia exacta."""
    clave = buscar_clave_inventario("tornillo")
    assert clave == "tornillo"


@patch("memoria.cargar_memoria", return_value=MEMORIA_CON_INVENTARIO)
def test_buscar_clave_inventario_no_encontrado(mock_cm):
    """buscar_clave_inventario debe retornar None para término desconocido."""
    clave = buscar_clave_inventario("producto_xyz_inexistente_99")
    assert clave is None


# ─────────────────────────────────────────────
# TESTS — cargar_inventario
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value={"inventario": {}})
def test_cargar_inventario_sin_db(mock_cm):
    """cargar_inventario debe retornar dict (puede ser vacío) sin DATABASE_URL."""
    result = cargar_inventario()
    assert isinstance(result, dict)


@patch("memoria.cargar_memoria", return_value=MEMORIA_CON_INVENTARIO)
def test_cargar_inventario_retorna_datos(mock_cm):
    """cargar_inventario debe retornar los datos del inventario del mock."""
    result = cargar_inventario()
    assert isinstance(result, dict)
    assert "tornillo" in result
