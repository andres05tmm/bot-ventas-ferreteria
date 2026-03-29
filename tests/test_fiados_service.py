"""
tests/test_fiados_service.py — Unit tests for services/fiados_service.py.

Patching strategy:
- Inject config stub to avoid SystemExit(1) from missing env vars.
- Inject db stub with DB_DISPONIBLE = False so no real PG calls happen by default.
- Inject memoria stub; patch `memoria.cargar_memoria` per-test to return controlled data.
- abonar_fiado calls guardar_fiado_movimiento internally (requires DB). For tuple-contract
  tests, patch guardar_fiado_movimiento to avoid RuntimeError from missing DB.

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
    _db_stub.execute_returning = lambda *a, **kw: None
    sys.modules["db"] = _db_stub

# Inject memoria stub — cargar_memoria patched per-test
if "memoria" not in sys.modules:
    _memoria_stub = types.ModuleType("memoria")
    _memoria_stub.cargar_memoria = lambda: {"fiados": {}}
    _memoria_stub._cache = None
    _memoria_stub._cache_lock = __import__("threading").Lock()
    sys.modules["memoria"] = _memoria_stub

# -- terceros --
import pytest
from unittest.mock import patch, MagicMock

# -- propios --
from services.fiados_service import (
    cargar_fiados,
    abonar_fiado,
    resumen_fiados,
    detalle_fiado_cliente,
    guardar_fiado_movimiento,
)


# ─────────────────────────────────────────────
# Fixture: datos de fiados de prueba
# ─────────────────────────────────────────────

FIADOS_MOCK = {
    "Pedro Lopez": {
        "saldo": 150000,
        "movimientos": [
            {"fecha": "2026-03-01", "concepto": "Compra", "cargo": 150000, "abono": 0, "saldo": 150000}
        ],
    },
    "Maria Garcia": {
        "saldo": 0,
        "movimientos": [],
    },
}


# ─────────────────────────────────────────────
# cargar_fiados
# ─────────────────────────────────────────────

def test_cargar_fiados_sin_db():
    """Sin DB, cargar_fiados debe retornar dict sin lanzar excepción."""
    with patch("db.DB_DISPONIBLE", False):
        result = cargar_fiados()
    assert isinstance(result, dict)


def test_cargar_fiados_desde_db():
    """cargar_fiados construye el dict correcto desde rows de DB."""
    rows_mock = [
        {"id": 1, "nombre": "Pedro Lopez", "deuda": 150000, "movimientos": []},
        {"id": 2, "nombre": "Maria Garcia", "deuda": 0, "movimientos": []},
    ]
    with patch("db.DB_DISPONIBLE", True), \
         patch("db.query_all", return_value=rows_mock):
        result = cargar_fiados()
    assert isinstance(result, dict)
    assert "Pedro Lopez" in result
    assert result["Pedro Lopez"]["saldo"] == 150000


def test_cargar_fiados_retorna_dict_vacios_sin_fiados():
    """cargar_fiados retorna dict vacío cuando memoria no tiene fiados."""
    with patch("db.DB_DISPONIBLE", False), \
         patch("memoria.cargar_memoria", return_value={"fiados": {}}):
        result = cargar_fiados()
    assert isinstance(result, dict)
    assert result == {}


# ─────────────────────────────────────────────
# abonar_fiado
# ─────────────────────────────────────────────

def test_abonar_fiado_retorna_tupla():
    """abonar_fiado debe retornar exactamente (bool, str) — contrato de retorno."""
    # El cliente no existe en fiados → retorna (False, str) sin llegar a guardar_fiado_movimiento
    with patch("db.DB_DISPONIBLE", False), \
         patch("memoria.cargar_memoria", return_value={"fiados": {}}):
        result = abonar_fiado("Pedro Lopez", 50000)
    assert isinstance(result, tuple)
    assert len(result) == 2
    ok, msg = result
    assert isinstance(ok, bool)
    assert isinstance(msg, str)


def test_abonar_fiado_cliente_no_encontrado():
    """Si el cliente no existe en fiados, abonar_fiado retorna (False, str)."""
    with patch("db.DB_DISPONIBLE", False), \
         patch("memoria.cargar_memoria", return_value={"fiados": {}}):
        ok, msg = abonar_fiado("Cliente_inexistente_xyz_99", 10000)
    assert ok is False
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_abonar_fiado_cliente_encontrado_retorna_true():
    """Si el cliente existe y guardar_fiado_movimiento tiene éxito, retorna (True, str)."""
    mem_con_fiado = {
        "fiados": {
            "Pedro Lopez": {"saldo": 150000, "movimientos": []}
        }
    }
    # Patch guardar_fiado_movimiento para evitar llamada real a DB
    with patch("db.DB_DISPONIBLE", False), \
         patch("memoria.cargar_memoria", return_value=mem_con_fiado), \
         patch("services.fiados_service.guardar_fiado_movimiento", return_value=100000):
        ok, msg = abonar_fiado("Pedro Lopez", 50000)
    assert ok is True
    assert isinstance(msg, str)
    assert len(msg) > 0


# ─────────────────────────────────────────────
# resumen_fiados
# ─────────────────────────────────────────────

def test_resumen_fiados_retorna_str():
    """resumen_fiados debe retornar string legible (con o sin DB)."""
    with patch("db.DB_DISPONIBLE", False), \
         patch("memoria.cargar_memoria", return_value={"fiados": {}}):
        result = resumen_fiados()
    assert isinstance(result, str)
    assert len(result) > 0


def test_resumen_fiados_con_pendientes():
    """resumen_fiados incluye a los clientes con saldo > 0."""
    with patch("services.fiados_service.cargar_fiados", return_value=FIADOS_MOCK):
        result = resumen_fiados()
    assert isinstance(result, str)
    assert "Pedro Lopez" in result


def test_resumen_fiados_sin_pendientes():
    """resumen_fiados retorna mensaje vacío cuando todos tienen saldo 0."""
    fiados_sin_deuda = {
        "Maria Garcia": {"saldo": 0, "movimientos": []},
    }
    with patch("services.fiados_service.cargar_fiados", return_value=fiados_sin_deuda):
        result = resumen_fiados()
    assert isinstance(result, str)
    assert len(result) > 0


# ─────────────────────────────────────────────
# detalle_fiado_cliente
# ─────────────────────────────────────────────

def test_detalle_fiado_cliente_retorna_str():
    """detalle_fiado_cliente retorna string (cliente no encontrado → mensaje de error)."""
    with patch("db.DB_DISPONIBLE", False), \
         patch("memoria.cargar_memoria", return_value={"fiados": {}}):
        result = detalle_fiado_cliente("Pedro Lopez")
    assert isinstance(result, str)


def test_detalle_fiado_cliente_encontrado():
    """detalle_fiado_cliente retorna detalle cuando cliente existe."""
    with patch("services.fiados_service.cargar_fiados", return_value=FIADOS_MOCK):
        result = detalle_fiado_cliente("Pedro Lopez")
    assert isinstance(result, str)
    assert "Pedro Lopez" in result


# ─────────────────────────────────────────────
# Thin wrapper smoke tests — memoria.py re-exports
# ─────────────────────────────────────────────

def test_thin_wrapper_memoria_exporta_simbolos_fiados():
    """
    memoria.py debe exportar los mismos símbolos de fiados que siempre exportó,
    ya sea como implementación directa o como thin wrapper que re-exporta desde services.

    Este test falla si alguien elimina los re-exports de memoria.py sin actualizarlo.
    """
    # Reset the stub so the real memoria.py is loaded
    _saved = sys.modules.pop("memoria", None)
    try:
        import memoria
        simbolos_requeridos = [
            "cargar_fiados",
            "abonar_fiado",
            "resumen_fiados",
            "guardar_fiado_movimiento",
            "detalle_fiado_cliente",
        ]
        faltantes = [s for s in simbolos_requeridos if not hasattr(memoria, s)]
        assert faltantes == [], f"memoria.py ya no exporta: {faltantes}"
    finally:
        if _saved is not None:
            sys.modules["memoria"] = _saved
        else:
            sys.modules.pop("memoria", None)


def test_thin_wrapper_memoria_exporta_simbolos_caja():
    """
    memoria.py debe seguir exportando los símbolos de caja que siempre exportó.
    """
    _saved = sys.modules.pop("memoria", None)
    try:
        import memoria
        simbolos_requeridos = [
            "cargar_caja",
            "guardar_caja",
            "cargar_gastos_hoy",
            "guardar_gasto",
            "obtener_resumen_caja",
        ]
        faltantes = [s for s in simbolos_requeridos if not hasattr(memoria, s)]
        assert faltantes == [], f"memoria.py ya no exporta: {faltantes}"
    finally:
        if _saved is not None:
            sys.modules["memoria"] = _saved
        else:
            sys.modules.pop("memoria", None)
