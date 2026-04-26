"""
tests/test_memoria_entidad_service.py — Unit tests for services/memoria_entidad_service.py.

Patching strategy:
- Inject config stub para evitar SystemExit(1) por env vars faltantes.
- Inject db stub con DB_DISPONIBLE = False; por default query_all/execute retornan vacío.
- Tests que necesitan DB patchean db.query_all y db.execute con mocks.

No requiere PostgreSQL real.
"""

# -- stdlib --
import sys
import types
from datetime import date

# Inject config stub
if "config" not in sys.modules:
    _config_stub = types.ModuleType("config")
    import pytz
    _config_stub.COLOMBIA_TZ = pytz.timezone("America/Bogota")
    _config_stub.claude_client = None
    _config_stub.openai_client = None
    sys.modules["config"] = _config_stub

# Inject db stub
if "db" not in sys.modules:
    _db_stub = types.ModuleType("db")
    _db_stub.DB_DISPONIBLE = False
    _db_stub.query_one = lambda *a, **kw: None
    _db_stub.query_all = lambda *a, **kw: []
    _db_stub.execute = lambda *a, **kw: None
    sys.modules["db"] = _db_stub

# -- terceros --
import pytest
from unittest.mock import patch

# -- propios --
from services import memoria_entidad_service as me


# ─────────────────────────────────────────────
# _normalizar_key
# ─────────────────────────────────────────────

def test_normalizar_key_lowercase():
    assert me._normalizar_key("DRYWALL") == "drywall"


def test_normalizar_key_quita_tildes():
    assert me._normalizar_key("cañería") == "caneria"


def test_normalizar_key_colapsa_espacios():
    assert me._normalizar_key("  drywall   6mm  ") == "drywall 6mm"


def test_normalizar_key_vacio():
    assert me._normalizar_key("") == ""
    assert me._normalizar_key(None) == ""


# ─────────────────────────────────────────────
# _validar_tipo
# ─────────────────────────────────────────────

def test_validar_tipo_producto():
    assert me._validar_tipo("producto") == "producto"
    assert me._validar_tipo("PRODUCTO") == "producto"
    assert me._validar_tipo("  producto ") == "producto"


def test_validar_tipo_alias():
    assert me._validar_tipo("alias") == "alias"


def test_validar_tipo_vendedor():
    assert me._validar_tipo("vendedor") == "vendedor"


def test_validar_tipo_invalido():
    assert me._validar_tipo("cliente") is None
    assert me._validar_tipo("") is None
    assert me._validar_tipo(None) is None


# ─────────────────────────────────────────────
# obtener_notas
# ─────────────────────────────────────────────

def test_obtener_notas_tipo_invalido():
    """Tipo inválido → retorna [] sin tocar DB."""
    assert me.obtener_notas("cliente", "pedro") == []


def test_obtener_notas_entidad_vacia():
    """Entidad vacía → retorna [] sin tocar DB."""
    assert me.obtener_notas("producto", "") == []
    assert me.obtener_notas("producto", None) == []


def test_obtener_notas_db_falla_retorna_lista_vacia():
    """Si query_all lanza excepción, retorna [] (fail-silent)."""
    def _boom(*a, **kw):
        raise RuntimeError("DB down")
    with patch("db.query_all", side_effect=_boom):
        assert me.obtener_notas("producto", "drywall") == []


def test_obtener_notas_db_ok():
    """Query exitosa → retorna la lista tal cual."""
    filas = [
        {"id": 1, "nota": "se vende con tornillos", "confidence": 1.0, "fecha_generada": date(2026, 4, 15)},
        {"id": 2, "nota": "popular entre mayoristas", "confidence": 0.9, "fecha_generada": date(2026, 4, 10)},
    ]
    with patch("db.query_all", return_value=filas) as mock_q:
        result = me.obtener_notas("producto", "Drywall 6mm", limit=5)
    assert result == filas
    # Verificar que se normalizó la key al llamar
    args = mock_q.call_args[0][1]
    assert args[0] == "producto"
    assert args[1] == "drywall 6mm"
    assert args[2] == 5


def test_obtener_notas_limit_cap_10():
    """limit mayor a 10 se acota a 10."""
    with patch("db.query_all", return_value=[]) as mock_q:
        me.obtener_notas("producto", "x", limit=999)
    assert mock_q.call_args[0][1][2] == 10


def test_obtener_notas_limit_cero_usa_default():
    """limit 0 es falsy → usa _DEFAULT_LIMIT (3)."""
    with patch("db.query_all", return_value=[]) as mock_q:
        me.obtener_notas("producto", "x", limit=0)
    assert mock_q.call_args[0][1][2] == 3


def test_obtener_notas_limit_negativo_eleva_a_1():
    """limit negativo se acota a mínimo 1."""
    with patch("db.query_all", return_value=[]) as mock_q:
        me.obtener_notas("producto", "x", limit=-5)
    assert mock_q.call_args[0][1][2] == 1


# ─────────────────────────────────────────────
# Atajos obtener_notas_producto / obtener_notas_vendedor
# ─────────────────────────────────────────────

def test_obtener_notas_producto_atajo():
    with patch("services.memoria_entidad_service.obtener_notas", return_value=[]) as m:
        me.obtener_notas_producto("drywall")
    m.assert_called_once_with("producto", "drywall", 3)


def test_obtener_notas_vendedor_atajo():
    with patch("services.memoria_entidad_service.obtener_notas", return_value=[]) as m:
        me.obtener_notas_vendedor("andres")
    m.assert_called_once_with("vendedor", "andres", 3)


# ─────────────────────────────────────────────
# obtener_aliases_aprendidos
# ─────────────────────────────────────────────

def test_obtener_aliases_aprendidos_db_ok():
    filas = [{"entidad_key": "tiner", "nota": "thinner", "confidence": 1.0, "fecha_generada": date(2026, 4, 15)}]
    with patch("db.query_all", return_value=filas):
        result = me.obtener_aliases_aprendidos()
    assert result == filas


def test_obtener_aliases_aprendidos_db_falla():
    def _boom(*a, **kw):
        raise RuntimeError("x")
    with patch("db.query_all", side_effect=_boom):
        assert me.obtener_aliases_aprendidos() == []


# ─────────────────────────────────────────────
# guardar_nota
# ─────────────────────────────────────────────

def test_guardar_nota_tipo_invalido():
    assert me.guardar_nota("cliente", "x", "nota") is False


def test_guardar_nota_key_vacia():
    assert me.guardar_nota("producto", "", "nota") is False


def test_guardar_nota_texto_vacio():
    assert me.guardar_nota("producto", "x", "") is False
    assert me.guardar_nota("producto", "x", "   ") is False


def test_guardar_nota_ok():
    with patch("db.execute") as m:
        ok = me.guardar_nota("producto", "Drywall 6MM", "se vende con tornillos", fecha=date(2026, 4, 17))
    assert ok is True
    args = m.call_args[0][1]
    # [tipo, key_normalizada, nota, confidence, fecha]
    assert args[0] == "producto"
    assert args[1] == "drywall 6mm"
    assert args[2] == "se vende con tornillos"
    assert args[3] == 1.0
    assert args[4] == date(2026, 4, 17)


def test_guardar_nota_trunca_texto_largo():
    """Nota > 280 chars se trunca."""
    texto_largo = "x" * 500
    with patch("db.execute") as m:
        me.guardar_nota("producto", "drywall", texto_largo)
    guardado = m.call_args[0][1][2]
    assert len(guardado) <= 280
    assert guardado.endswith("…")


def test_guardar_nota_confidence_clamp():
    """Confidence fuera de [0,1] se normaliza."""
    with patch("db.execute") as m:
        me.guardar_nota("producto", "x", "nota", confidence=5.0)
    assert m.call_args[0][1][3] == 1.0
    with patch("db.execute") as m:
        me.guardar_nota("producto", "x", "nota", confidence=-1.0)
    assert m.call_args[0][1][3] == 0.0


def test_guardar_nota_db_falla():
    def _boom(*a, **kw):
        raise RuntimeError("pg down")
    with patch("db.execute", side_effect=_boom):
        assert me.guardar_nota("producto", "x", "y") is False


# ─────────────────────────────────────────────
# invalidar_nota
# ─────────────────────────────────────────────

def test_invalidar_nota_ok():
    with patch("db.execute", return_value=1):
        assert me.invalidar_nota(42) is True


def test_invalidar_nota_no_encontrada():
    with patch("db.execute", return_value=0):
        assert me.invalidar_nota(999) is False


def test_invalidar_nota_db_falla():
    def _boom(*a, **kw):
        raise RuntimeError("x")
    with patch("db.execute", side_effect=_boom):
        assert me.invalidar_nota(1) is False


# ─────────────────────────────────────────────
# purgar_antiguas
# ─────────────────────────────────────────────

def test_purgar_antiguas_ok():
    with patch("db.execute", return_value=5):
        assert me.purgar_antiguas(90) == 5


def test_purgar_antiguas_db_falla():
    def _boom(*a, **kw):
        raise RuntimeError("x")
    with patch("db.execute", side_effect=_boom):
        assert me.purgar_antiguas(90) == 0


def test_purgar_antiguas_minimo_7_dias():
    """Aunque se pida purgar con días < 7, se fuerza a 7 (safety)."""
    with patch("db.execute", return_value=0) as m:
        me.purgar_antiguas(1)
    # El INTERVAL se construye con string concat, así que revisamos la query
    query = m.call_args[0][0]
    assert "INTERVAL '7 days'" in query


# ─────────────────────────────────────────────
# formatear_para_prompt
# ─────────────────────────────────────────────

def test_formatear_para_prompt_vacio():
    assert me.formatear_para_prompt([], "drywall") == ""


def test_formatear_para_prompt_notas():
    notas = [
        {"nota": "se vende con tornillos", "fecha_generada": date(2026, 4, 15)},
        {"nota": "popular entre mayoristas", "fecha_generada": date(2026, 4, 10)},
    ]
    out = me.formatear_para_prompt(notas, "drywall 6mm")
    assert "NOTAS DE MEMORIA — drywall 6mm:" in out
    assert "[2026-04-15] se vende con tornillos" in out
    assert "[2026-04-10] popular entre mayoristas" in out


def test_formatear_para_prompt_ignora_notas_vacias():
    notas = [
        {"nota": "", "fecha_generada": date(2026, 4, 15)},
        {"nota": "   ", "fecha_generada": date(2026, 4, 14)},
    ]
    # Todas vacías → retorna ""
    assert me.formatear_para_prompt(notas, "x") == ""
