"""
tests/test_compresor_nocturno.py — Unit tests para services/compresor_nocturno.py.

Patching strategy:
- config stub con claude_client configurable por test.
- db stub con DB_DISPONIBLE = False por default; cada test que necesita DB
  patchea query_all.
- memoria_entidad_service.guardar_nota y purgar_antiguas se patchean con MagicMocks
  para aislar del service real.
"""

# -- stdlib --
import sys
import types
from datetime import date, datetime

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
from unittest.mock import patch, MagicMock

# -- propios --
from services import compresor_nocturno as cn


# ─────────────────────────────────────────────
# _fecha_objetivo
# ─────────────────────────────────────────────

def test_fecha_objetivo_es_dia_anterior():
    """La fecha objetivo debe ser un día menos que hoy."""
    import config as _c
    hoy_col = datetime.now(_c.COLOMBIA_TZ).date()
    f = cn._fecha_objetivo()
    diff = (hoy_col - f).days
    assert diff == 1


# ─────────────────────────────────────────────
# _cargar_conversaciones_del_dia
# ─────────────────────────────────────────────

def test_cargar_conversaciones_ok():
    filas = [
        {"chat_id": 100, "vendedor_id": 1, "role": "user",
         "content": "hola", "creado": datetime(2026, 4, 17, 10)},
        {"chat_id": 100, "vendedor_id": 1, "role": "assistant",
         "content": "buenas", "creado": datetime(2026, 4, 17, 10, 1)},
    ]
    with patch("db.query_all", return_value=filas):
        out = cn._cargar_conversaciones_del_dia(date(2026, 4, 17))
    assert len(out) == 2
    assert out[0]["chat_id"] == 100


def test_cargar_conversaciones_db_falla():
    def _boom(*a, **kw):
        raise RuntimeError("pg down")
    with patch("db.query_all", side_effect=_boom):
        assert cn._cargar_conversaciones_del_dia(date(2026, 4, 17)) == []


# ─────────────────────────────────────────────
# _cargar_productos_vendidos
# ─────────────────────────────────────────────

def test_cargar_productos_vendidos_ok():
    filas = [{"producto_nombre": "drywall 6mm"}, {"producto_nombre": "tornillos"}]
    with patch("db.query_all", return_value=filas):
        out = cn._cargar_productos_vendidos(date(2026, 4, 17))
    assert out == ["drywall 6mm", "tornillos"]


def test_cargar_productos_vendidos_filtra_nulos():
    filas = [{"producto_nombre": "drywall"}, {"producto_nombre": None}]
    with patch("db.query_all", return_value=filas):
        out = cn._cargar_productos_vendidos(date(2026, 4, 17))
    assert out == ["drywall"]


def test_cargar_productos_vendidos_db_falla():
    def _boom(*a, **kw):
        raise RuntimeError("x")
    with patch("db.query_all", side_effect=_boom):
        assert cn._cargar_productos_vendidos(date(2026, 4, 17)) == []


# ─────────────────────────────────────────────
# _cargar_vendedores_activos
# ─────────────────────────────────────────────

def test_cargar_vendedores_activos_ok():
    filas = [{"vendedor": "andres"}, {"vendedor": "maria"}]
    with patch("db.query_all", return_value=filas):
        out = cn._cargar_vendedores_activos(date(2026, 4, 17))
    assert out == ["andres", "maria"]


def test_cargar_vendedores_activos_db_falla():
    def _boom(*a, **kw):
        raise RuntimeError("x")
    with patch("db.query_all", side_effect=_boom):
        assert cn._cargar_vendedores_activos(date(2026, 4, 17)) == []


# ─────────────────────────────────────────────
# _serializar_conversaciones
# ─────────────────────────────────────────────

def test_serializar_conversaciones_agrupa_por_chat():
    filas = [
        {"chat_id": 100, "role": "user", "content": "hola"},
        {"chat_id": 100, "role": "assistant", "content": "buenas"},
        {"chat_id": 200, "role": "user", "content": "precio drywall"},
    ]
    texto = cn._serializar_conversaciones(filas)
    assert "[chat 100]" in texto
    assert "[chat 200]" in texto
    assert "USER: hola" in texto
    assert "ASSISTANT: buenas" in texto


def test_serializar_conversaciones_trunca():
    """Si el texto total excede _MAX_CONV_CHARS, se trunca."""
    filas = [
        {"chat_id": 1, "role": "user", "content": "x" * 100}
        for _ in range(500)
    ]
    texto = cn._serializar_conversaciones(filas)
    assert "[...truncado...]" in texto
    assert len(texto) <= cn._MAX_CONV_CHARS + len("\n[...truncado...]") + 10


def test_serializar_conversaciones_aplana_saltos():
    filas = [{"chat_id": 1, "role": "user", "content": "linea1\nlinea2"}]
    texto = cn._serializar_conversaciones(filas)
    assert "linea1 linea2" in texto


# ─────────────────────────────────────────────
# _construir_prompt
# ─────────────────────────────────────────────

def test_construir_prompt_incluye_productos_y_vendedores():
    p = cn._construir_prompt(
        date(2026, 4, 17),
        ["drywall", "tornillos"],
        ["andres"],
        "[chat 1]\n  USER: hola",
    )
    assert "2026-04-17" in p
    assert "drywall" in p
    assert "tornillos" in p
    assert "andres" in p
    assert "FORMATO DE RESPUESTA" in p
    assert '"productos"' in p
    assert '"aliases"' in p
    assert '"vendedores"' in p


def test_construir_prompt_sin_vendedores():
    p = cn._construir_prompt(date(2026, 4, 17), ["drywall"], [], "x")
    assert "(ninguno)" in p


# ─────────────────────────────────────────────
# _parsear_respuesta
# ─────────────────────────────────────────────

def test_parsear_respuesta_json_puro():
    txt = '{"productos": {"drywall": "nota"}, "aliases": {}, "vendedores": {}}'
    out = cn._parsear_respuesta(txt)
    assert out["productos"] == {"drywall": "nota"}


def test_parsear_respuesta_vacio():
    assert cn._parsear_respuesta("") == {}
    assert cn._parsear_respuesta(None) == {}


def test_parsear_respuesta_con_markdown():
    """Haiku decora con ```json ... ``` — fallback debe extraer el JSON."""
    txt = "Aquí tienes:\n```json\n{\"productos\": {\"x\": \"y\"}}\n```\nFin."
    out = cn._parsear_respuesta(txt)
    assert out["productos"] == {"x": "y"}


def test_parsear_respuesta_malformado():
    """JSON inválido → dict vacío, sin excepción."""
    assert cn._parsear_respuesta("no es JSON en absoluto {{{") == {}


# ─────────────────────────────────────────────
# compresor_nocturno_job
# ─────────────────────────────────────────────

def test_compresor_job_sin_claude_client():
    """Si config.claude_client es None, aborta limpio."""
    import config as _c
    _c.claude_client = None
    res = cn.compresor_nocturno_job()
    assert res["ok"] is False
    assert "claude_client" in res["error"]


def test_compresor_job_sin_conversaciones():
    """Sin conversaciones del día: purga pero no llama a Haiku."""
    import config as _c
    _c.claude_client = MagicMock()

    with patch("services.compresor_nocturno._cargar_conversaciones_del_dia", return_value=[]), \
         patch("services.compresor_nocturno._cargar_productos_vendidos", return_value=[]), \
         patch("services.compresor_nocturno._cargar_vendedores_activos", return_value=[]), \
         patch("services.memoria_entidad_service.purgar_antiguas", return_value=3):
        res = cn.compresor_nocturno_job()

    assert res["ok"] is True
    assert res["convs"] == 0
    assert res["productos"] == 0
    assert res["purgadas"] == 3
    # Claude no fue llamado
    _c.claude_client.messages.create.assert_not_called()


def test_compresor_job_flujo_feliz():
    """Con datos, llama a Haiku y persiste notas."""
    import config as _c

    # Mock del cliente Claude: devuelve JSON válido
    respuesta_mock = MagicMock()
    bloque_text = MagicMock()
    bloque_text.text = (
        '{"productos": {"drywall": "popular con tornillos"}, '
        '"aliases": {"drwayll": "drywall"}, '
        '"vendedores": {"andres": "vende en tardes"}}'
    )
    respuesta_mock.content = [bloque_text]

    claude_mock = MagicMock()
    claude_mock.messages.create.return_value = respuesta_mock
    _c.claude_client = claude_mock

    convs = [{"chat_id": 100, "role": "user", "content": "hola drywall"}]

    with patch("services.compresor_nocturno._cargar_conversaciones_del_dia", return_value=convs), \
         patch("services.compresor_nocturno._cargar_productos_vendidos", return_value=["drywall"]), \
         patch("services.compresor_nocturno._cargar_vendedores_activos", return_value=["andres"]), \
         patch("services.memoria_entidad_service.guardar_nota", return_value=True) as mock_guardar, \
         patch("services.memoria_entidad_service.purgar_antiguas", return_value=2):
        res = cn.compresor_nocturno_job()

    assert res["ok"] is True
    assert res["convs"] == 1
    assert res["productos"] == 1
    assert res["notas_guardadas"] == 3  # producto + alias + vendedor
    assert res["purgadas"] == 2

    # Verificar que se llamó a Haiku con el modelo correcto
    kwargs = claude_mock.messages.create.call_args.kwargs
    assert kwargs["model"] == cn._HAIKU_MODEL
    assert kwargs["max_tokens"] == cn._MAX_TOKENS_OUT

    # guardar_nota se llamó 3 veces (1 producto + 1 alias + 1 vendedor)
    assert mock_guardar.call_count == 3


def test_compresor_job_respuesta_vacia_no_persiste():
    """Si Haiku devuelve JSON vacío/basura, no persiste nada."""
    import config as _c

    respuesta_mock = MagicMock()
    bloque_text = MagicMock()
    bloque_text.text = "no es JSON"
    respuesta_mock.content = [bloque_text]

    claude_mock = MagicMock()
    claude_mock.messages.create.return_value = respuesta_mock
    _c.claude_client = claude_mock

    with patch("services.compresor_nocturno._cargar_conversaciones_del_dia",
               return_value=[{"chat_id": 1, "role": "user", "content": "x"}]), \
         patch("services.compresor_nocturno._cargar_productos_vendidos", return_value=["drywall"]), \
         patch("services.compresor_nocturno._cargar_vendedores_activos", return_value=[]), \
         patch("services.memoria_entidad_service.guardar_nota") as mock_guardar:
        res = cn.compresor_nocturno_job()

    assert res["ok"] is False
    assert res["error"] is not None
    mock_guardar.assert_not_called()


def test_compresor_job_exception_captura():
    """Cualquier excepción dentro del job se loguea y retorna ok=False."""
    import config as _c
    _c.claude_client = MagicMock()

    def _boom(*a, **kw):
        raise RuntimeError("inesperado")

    with patch("services.compresor_nocturno._cargar_conversaciones_del_dia", side_effect=_boom):
        res = cn.compresor_nocturno_job()

    assert res["ok"] is False
    assert "inesperado" in res["error"]
