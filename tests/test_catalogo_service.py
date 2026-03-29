"""
tests/test_catalogo_service.py — Unit tests for services/catalogo_service.py.

Patching strategy:
- Inject stub modules for `config` and `memoria` into sys.modules before importing
  the service, so no real API keys or DB connections are needed.
- All functions call `from memoria import cargar_memoria` lazily inside function bodies,
  so we patch `memoria.cargar_memoria` to return a controlled MEMORIA_MOCK dict.

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

# Inject memoria stub — functions will be patched per-test
if "memoria" not in sys.modules:
    _memoria_stub = types.ModuleType("memoria")
    _memoria_stub.cargar_memoria = lambda: {}
    _memoria_stub.cargar_inventario = lambda: {}
    _memoria_stub._cache = None
    _memoria_stub._cache_lock = __import__("threading").Lock()
    sys.modules["memoria"] = _memoria_stub

# -- terceros --
import pytest
from unittest.mock import patch

# -- propios --
from services.catalogo_service import (
    buscar_producto_en_catalogo,
    buscar_multiples_en_catalogo,
    obtener_precio_para_cantidad,
    obtener_precios_como_texto,
)

# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

CATALOGO_MOCK = {
    "tornillo": {
        "nombre_lower": "tornillo",
        "nombre": "Tornillo",
        "precio_unidad": 500,
        "precios_fraccion": {"1/4": {"precio": 150, "decimal": 0.25}},
        "unidad": "unidades",
    },
    "lija": {
        "nombre_lower": "lija",
        "nombre": "Lija",
        "precio_unidad": 2000,
        "precios_fraccion": {},
        "unidad": "unidades",
    },
    "cemento gris": {
        "nombre_lower": "cemento gris",
        "nombre": "Cemento Gris",
        "precio_unidad": 35000,
        "precios_fraccion": {},
        "unidad": "bultos",
    },
}

MEMORIA_MOCK = {"catalogo": CATALOGO_MOCK, "inventario": {}}


# ─────────────────────────────────────────────
# TESTS — buscar_producto_en_catalogo
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_buscar_producto_exacto(mock_cm):
    """buscar_producto_en_catalogo debe retornar producto exacto por nombre_lower."""
    result = buscar_producto_en_catalogo("tornillo")
    assert result is not None
    assert result["nombre_lower"] == "tornillo"
    assert result["precio_unidad"] == 500


@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_buscar_producto_no_encontrado(mock_cm):
    """buscar_producto_en_catalogo debe retornar None para producto inexistente."""
    result = buscar_producto_en_catalogo("producto_inexistente_xyz")
    assert result is None


@patch("memoria.cargar_memoria", return_value={"catalogo": {}, "inventario": {}})
def test_buscar_producto_catalogo_vacio(mock_cm):
    """buscar_producto_en_catalogo debe retornar None con catálogo vacío."""
    result = buscar_producto_en_catalogo("tornillo")
    assert result is None


@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_buscar_producto_por_palabras(mock_cm):
    """buscar_producto_en_catalogo debe encontrar producto con múltiples palabras clave."""
    result = buscar_producto_en_catalogo("cemento gris")
    assert result is not None
    assert result["nombre_lower"] == "cemento gris"


# ─────────────────────────────────────────────
# TESTS — buscar_multiples_en_catalogo
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_buscar_multiples_retorna_lista(mock_cm):
    """buscar_multiples_en_catalogo debe retornar una lista con el match exacto."""
    results = buscar_multiples_en_catalogo("tornillo")
    assert isinstance(results, list)
    nombres = [r.get("nombre_lower", "") for r in results]
    assert "tornillo" in nombres


@patch("memoria.cargar_memoria", return_value={"catalogo": {}, "inventario": {}})
def test_buscar_multiples_catalogo_vacio(mock_cm):
    """buscar_multiples_en_catalogo debe retornar lista vacía con catálogo vacío."""
    results = buscar_multiples_en_catalogo("tornillo")
    assert isinstance(results, list)
    assert len(results) == 0


# ─────────────────────────────────────────────
# TESTS — obtener_precio_para_cantidad
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_obtener_precio_para_cantidad_retorna_tupla(mock_cm):
    """obtener_precio_para_cantidad debe retornar (int, numeric) para producto existente."""
    precio, precio_u = obtener_precio_para_cantidad("tornillo", 1.0)
    assert isinstance(precio, int)
    assert isinstance(precio_u, (int, float))
    assert precio > 0


@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_obtener_precio_para_cantidad_calculo_correcto(mock_cm):
    """obtener_precio_para_cantidad debe multiplicar precio_unidad por cantidad."""
    precio, _ = obtener_precio_para_cantidad("lija", 3.0)
    assert precio == 6000  # 2000 * 3


@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_obtener_precio_para_cantidad_producto_inexistente(mock_cm):
    """obtener_precio_para_cantidad debe retornar (int, numeric) incluso sin producto."""
    precio, precio_u = obtener_precio_para_cantidad("producto_xyz_99", 1.0)
    assert isinstance(precio, int)
    assert isinstance(precio_u, (int, float))


# ─────────────────────────────────────────────
# TESTS — obtener_precios_como_texto
# ─────────────────────────────────────────────

@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_obtener_precios_como_texto_retorna_str(mock_cm):
    """obtener_precios_como_texto debe retornar string no vacío."""
    resultado = obtener_precios_como_texto()
    assert isinstance(resultado, str)
    assert len(resultado) > 0


@patch("memoria.cargar_memoria", return_value=MEMORIA_MOCK)
def test_obtener_precios_como_texto_contiene_productos(mock_cm):
    """obtener_precios_como_texto debe incluir nombres de productos del catálogo."""
    resultado = obtener_precios_como_texto()
    assert "Tornillo" in resultado or "tornillo" in resultado.lower()


@patch("memoria.cargar_memoria", return_value={"catalogo": {}, "inventario": {}, "precios": {}})
def test_obtener_precios_como_texto_sin_datos(mock_cm):
    """obtener_precios_como_texto debe retornar mensaje útil cuando no hay datos."""
    resultado = obtener_precios_como_texto()
    assert isinstance(resultado, str)
    assert len(resultado) > 0
