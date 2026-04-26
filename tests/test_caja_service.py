"""
tests/test_caja_service.py — Unit tests for services/caja_service.py.

Patching strategy:
- Inject config stub to avoid SystemExit(1) from missing env vars.
- Inject db stub with DB_DISPONIBLE = False so no real PG calls happen by default.
- Tests that need DB success patch db.DB_DISPONIBLE = True and mock db.query_one/query_all.
- Tests that exercise no-DB fallback paths patch db.DB_DISPONIBLE = False (already default).

No real database or Telegram credentials required.
"""

# -- stdlib --
import sys
import types

# Inject config stub to avoid SystemExit(1) from missing env vars
if "config" not in sys.modules:
    _config_stub = types.ModuleType("config")
    import pytz
    _config_stub.COLOMBIA_TZ = pytz.timezone("America/Bogota")
    _config_stub.claude_client = None
    _config_stub.openai_client = None
    sys.modules["config"] = _config_stub

# Inject db stub — DB_DISPONIBLE = False so no real PG calls happen by default
if "db" not in sys.modules:
    _db_stub = types.ModuleType("db")
    _db_stub.DB_DISPONIBLE = False
    _db_stub.query_one = lambda *a, **kw: None
    _db_stub.query_all = lambda *a, **kw: []
    _db_stub.execute = lambda *a, **kw: None
    sys.modules["db"] = _db_stub

# -- terceros --
import pytest
from unittest.mock import patch, MagicMock

# -- propios --
from services.caja_service import (
    cargar_caja,
    obtener_resumen_caja,
    cargar_gastos_hoy,
    guardar_caja,
    guardar_gasto,
)


# ─────────────────────────────────────────────
# cargar_caja
# ─────────────────────────────────────────────

def test_cargar_caja_retorna_dict_sin_db():
    """cargar_caja debe retornar dict con claves abierta, fecha, monto_apertura cuando DB falla."""
    with patch("db.DB_DISPONIBLE", False):
        result = cargar_caja()
    assert isinstance(result, dict)
    assert "abierta" in result
    assert "monto_apertura" in result
    assert result["abierta"] is False


def test_cargar_caja_retorna_claves_completas_sin_db():
    """El dict de fallback debe contener todas las claves esperadas."""
    with patch("db.DB_DISPONIBLE", False):
        result = cargar_caja()
    claves_esperadas = {"abierta", "fecha", "monto_apertura", "efectivo", "transferencias", "datafono"}
    assert claves_esperadas.issubset(result.keys())


def test_cargar_caja_desde_postgres():
    """Cuando _leer_caja_postgres retorna datos, cargar_caja los devuelve."""
    caja_mock = {
        "abierta": True, "fecha": "2026-03-29",
        "monto_apertura": 50000, "efectivo": 120000,
        "transferencias": 30000, "datafono": 0,
    }
    with patch("services.caja_service._leer_caja_postgres", return_value=caja_mock):
        result = cargar_caja()
    assert result["abierta"] is True
    assert result["monto_apertura"] == 50000
    assert result["efectivo"] == 120000


# ─────────────────────────────────────────────
# obtener_resumen_caja
# ─────────────────────────────────────────────

def test_obtener_resumen_caja_cerrada():
    """Cuando la caja no está abierta, debe retornar mensaje de caja cerrada."""
    with patch("services.caja_service._leer_caja_postgres", return_value=None):
        result = obtener_resumen_caja()
    assert isinstance(result, str)
    assert len(result) > 0


def test_obtener_resumen_caja_sin_db():
    """Sin DB, obtener_resumen_caja debe retornar string (aviso o resumen parcial)."""
    caja_abierta = {
        "abierta": True, "fecha": "2026-03-29",
        "monto_apertura": 50000, "efectivo": 0,
        "transferencias": 0, "datafono": 0,
    }
    with patch("services.caja_service._leer_caja_postgres", return_value=caja_abierta), \
         patch("db.DB_DISPONIBLE", False):
        result = obtener_resumen_caja()
    assert isinstance(result, str)
    assert len(result) > 0


def test_obtener_resumen_caja_retorna_str_siempre():
    """obtener_resumen_caja siempre retorna str, nunca None."""
    with patch("services.caja_service._leer_caja_postgres", return_value=None):
        result = obtener_resumen_caja()
    assert result is not None
    assert isinstance(result, str)


# ─────────────────────────────────────────────
# cargar_gastos_hoy
# ─────────────────────────────────────────────

def test_cargar_gastos_hoy_sin_db():
    """Sin DB disponible, cargar_gastos_hoy retorna lista vacía sin lanzar excepción."""
    with patch("db.DB_DISPONIBLE", False):
        result = cargar_gastos_hoy()
    assert isinstance(result, list)
    assert result == []


def test_cargar_gastos_hoy_retorna_lista():
    """cargar_gastos_hoy siempre retorna lista (nunca None)."""
    with patch("db.DB_DISPONIBLE", False):
        result = cargar_gastos_hoy()
    assert result is not None
    assert isinstance(result, list)


# ─────────────────────────────────────────────
# guardar_caja — RuntimeError sin DB
# ─────────────────────────────────────────────

def test_guardar_caja_sin_db_lanza_error():
    """guardar_caja debe lanzar RuntimeError cuando DB no disponible (comportamiento documentado)."""
    with patch("db.DB_DISPONIBLE", False):
        with pytest.raises(RuntimeError):
            guardar_caja({
                "abierta": True, "fecha": "2026-03-29", "monto_apertura": 0,
                "efectivo": 0, "transferencias": 0, "datafono": 0,
            })


# ─────────────────────────────────────────────
# guardar_gasto — RuntimeError sin DB
# ─────────────────────────────────────────────

def test_guardar_gasto_sin_db_lanza_error():
    """guardar_gasto debe lanzar RuntimeError cuando DB no disponible."""
    with patch("db.DB_DISPONIBLE", False):
        with pytest.raises(RuntimeError):
            guardar_gasto({"concepto": "Varios", "monto": 5000, "categoria": "General"})
