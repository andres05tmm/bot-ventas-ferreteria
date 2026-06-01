"""
tests/test_ai_tools.py — Tests del puente tool_use → tags (M-01, Fase 1).

ai/tools.py es un módulo puro (solo json), no necesita stubs.

Cubre la PARIDAD entre el tool-calling nativo y el formato de tags [VENTA]
que procesar_acciones() ya consume:
  - Venta simple (producto/cantidad/total).
  - Multi-producto (varios tool_use → varios tags concatenados).
  - metodo_pago incluido / omitido.
  - cliente incluido / omitido.
  - Venta varia (producto="Venta Varia") sin tratamiento especial.
  - Texto + tool_use (pregunta + registro).
  - Solo texto (Claude pregunta, sin registrar).
  - Bloques como objeto del SDK (atributos) y como dict.
  - El tag generado es re-parseable con el mismo regex de procesar_acciones.
"""

# -- stdlib --
import os
import json
import re

# Importar ai.tools dispara ai/__init__ → config, que aborta sin estas claves.
# setdefault: no pisa valores reales si el runner ya los puso.
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")

# -- terceros --
import pytest

# -- propios --
from ai.tools import (
    tool_uses_a_tags, ventas_con_producto_desconocido, ventas_conocidas,
    TOOLS, TOOL_REGISTRAR_VENTA, TOOL_REGISTRAR_GASTO,
    TOOL_REGISTRAR_FIADO, TOOL_ABONAR_FIADO,
)


# Regex idéntico al de ai/response_builder.procesar_acciones
_RE_VENTA = re.compile(r"\[VENTA\](.*?)\[/VENTA\]", re.DOTALL)


class _Block:
    """Imita un content block del SDK de Anthropic (acceso por atributo)."""
    def __init__(self, type, text=None, name=None, input=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input


def _ventas_parseadas(salida: str) -> list[dict]:
    """Extrae y parsea los [VENTA] del string puente, igual que procesar_acciones."""
    return [json.loads(m.strip()) for m in _RE_VENTA.findall(salida)]


# ─────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────

def test_schema_registrar_venta_bien_formado():
    assert TOOL_REGISTRAR_VENTA["name"] == "registrar_venta"
    props = TOOL_REGISTRAR_VENTA["input_schema"]["properties"]
    assert {"producto", "cantidad", "total"} <= set(props)
    assert TOOL_REGISTRAR_VENTA["input_schema"]["required"] == ["producto", "cantidad", "total"]
    # TOOLS cubre las 4 mutaciones de plata (venta, gasto, fiado, abono) desde
    # el tool-calling completo — clasificación de intención precisa.
    assert TOOLS == [
        TOOL_REGISTRAR_VENTA, TOOL_REGISTRAR_GASTO,
        TOOL_REGISTRAR_FIADO, TOOL_ABONAR_FIADO,
    ]


# ─────────────────────────────────────────────
# Venta simple
# ─────────────────────────────────────────────

def test_venta_simple():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Martillo", "cantidad": 2, "total": 30000})]
    salida = tool_uses_a_tags(content)
    ventas = _ventas_parseadas(salida)
    assert ventas == [{"producto": "Martillo", "cantidad": 2, "total": 30000}]


def test_venta_fraccion_va_en_cantidad():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Laca Miel Catalizada", "cantidad": 0.25, "total": 17000})]
    v = _ventas_parseadas(tool_uses_a_tags(content))[0]
    assert v["cantidad"] == 0.25
    assert "1/4" not in v["producto"]


# ─────────────────────────────────────────────
# Multi-producto
# ─────────────────────────────────────────────

def test_multi_producto_dos_tool_use():
    content = [
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Martillo", "cantidad": 1, "total": 15000}),
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Brocha 3", "cantidad": 2, "total": 8000}),
    ]
    salida = tool_uses_a_tags(content)
    ventas = _ventas_parseadas(salida)
    assert len(ventas) == 2
    assert ventas[0]["producto"] == "Martillo"
    assert ventas[1]["producto"] == "Brocha 3"


# ─────────────────────────────────────────────
# metodo_pago / cliente opcionales
# ─────────────────────────────────────────────

def test_metodo_pago_incluido():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Cemento", "cantidad": 1, "total": 28000,
                             "metodo_pago": "transferencia"})]
    v = _ventas_parseadas(tool_uses_a_tags(content))[0]
    assert v["metodo_pago"] == "transferencia"


def test_metodo_pago_omitido_no_aparece():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Cemento", "cantidad": 1, "total": 28000})]
    v = _ventas_parseadas(tool_uses_a_tags(content))[0]
    assert "metodo_pago" not in v


def test_cliente_incluido_y_omitido():
    con = [_Block("tool_use", name="registrar_venta",
                  input={"producto": "Pintura", "cantidad": 1, "total": 50000, "cliente": "Pedro"})]
    sin = [_Block("tool_use", name="registrar_venta",
                  input={"producto": "Pintura", "cantidad": 1, "total": 50000})]
    assert _ventas_parseadas(tool_uses_a_tags(con))[0]["cliente"] == "Pedro"
    assert "cliente" not in _ventas_parseadas(tool_uses_a_tags(sin))[0]


# ─────────────────────────────────────────────
# Venta varia (sin tratamiento especial)
# ─────────────────────────────────────────────

def test_venta_varia():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Venta Varia", "cantidad": 1, "total": 80000,
                             "metodo_pago": "efectivo"})]
    v = _ventas_parseadas(tool_uses_a_tags(content))[0]
    assert v["producto"] == "Venta Varia"
    assert v["total"] == 80000
    assert v["metodo_pago"] == "efectivo"


# ─────────────────────────────────────────────
# Texto + tool_use / solo texto
# ─────────────────────────────────────────────

def test_texto_mas_tool_use():
    content = [
        _Block("text", text="⚠️ Sin registrar del mensaje anterior: lija N°?"),
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Martillo", "cantidad": 1, "total": 15000}),
    ]
    salida = tool_uses_a_tags(content)
    assert salida.startswith("⚠️ Sin registrar")
    assert len(_ventas_parseadas(salida)) == 1


def test_solo_texto_sin_tags():
    content = [_Block("text", text="¿Qué grano de lija? Tenemos 40, 80, 120.")]
    salida = tool_uses_a_tags(content)
    assert salida == "¿Qué grano de lija? Tenemos 40, 80, 120."
    assert _ventas_parseadas(salida) == []


def test_solo_tool_use_sin_texto_silencio():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Tornillo 6x1", "cantidad": 48, "total": 2000})]
    salida = tool_uses_a_tags(content)
    # SILENCIO TOTAL: sin texto antes ni después, solo el tag.
    assert salida.startswith("[VENTA]")
    assert salida.endswith("[/VENTA]")


# ─────────────────────────────────────────────
# Bloques como dict (no solo objeto del SDK)
# ─────────────────────────────────────────────

def test_bloques_como_dict():
    content = [
        {"type": "text", "text": "ok"},
        {"type": "tool_use", "name": "registrar_venta",
         "input": {"producto": "Lija 80", "cantidad": 3, "total": 6000}},
    ]
    salida = tool_uses_a_tags(content)
    assert "ok" in salida
    assert _ventas_parseadas(salida)[0]["producto"] == "Lija 80"


# ─────────────────────────────────────────────
# Robustez
# ─────────────────────────────────────────────

def test_content_vacio_o_none():
    assert tool_uses_a_tags([]) == ""
    assert tool_uses_a_tags(None) == ""


def test_tool_desconocido_se_ignora():
    content = [_Block("tool_use", name="herramienta_inexistente", input={"x": 1})]
    assert tool_uses_a_tags(content) == ""


# ─────────────────────────────────────────────
# Riel R2 (voz): producto fuera de catálogo
# ─────────────────────────────────────────────

# Catálogo simulado: solo estos productos "existen".
_CATALOGO_FAKE = {"martillo", "cemento gris", "lija 80"}


def _existe(nombre: str) -> bool:
    return nombre.strip().lower() in _CATALOGO_FAKE


def test_r2_producto_existente_no_se_reporta():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Martillo", "cantidad": 1, "total": 15000})]
    assert ventas_con_producto_desconocido(content, _existe) == []


def test_r2_producto_desconocido_se_reporta():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Acrilan", "cantidad": 1, "total": 9000})]
    assert ventas_con_producto_desconocido(content, _existe) == ["Acrilan"]


def test_r2_venta_varia_se_ignora():
    # "Venta Varia" es legítima sin entrada de catálogo → nunca se reporta.
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Venta Varia", "cantidad": 1, "total": 80000})]
    assert ventas_con_producto_desconocido(content, _existe) == []


def test_r2_multi_solo_reporta_desconocidos():
    content = [
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Cemento Gris", "cantidad": 2, "total": 56000}),
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Tornillo Fantasma", "cantidad": 5, "total": 5000}),
    ]
    assert ventas_con_producto_desconocido(content, _existe) == ["Tornillo Fantasma"]


def test_r2_desconocidos_sin_duplicados():
    content = [
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Acrilan", "cantidad": 1, "total": 9000}),
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Acrilan", "cantidad": 2, "total": 18000}),
    ]
    assert ventas_con_producto_desconocido(content, _existe) == ["Acrilan"]


def test_r2_ignora_texto_y_otras_tools():
    content = [
        _Block("text", text="¿En efectivo o transferencia?"),
        _Block("tool_use", name="registrar_gasto",
               input={"concepto": "refrigerio", "monto": 5000}),
    ]
    # Sin registrar_venta → nada que validar.
    assert ventas_con_producto_desconocido(content, _existe) == []


def test_r2_producto_vacio_se_ignora():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"cantidad": 1, "total": 1000})]
    assert ventas_con_producto_desconocido(content, _existe) == []


def test_r2_content_vacio():
    assert ventas_con_producto_desconocido([], _existe) == []
    assert ventas_con_producto_desconocido(None, _existe) == []


# ── ventas_conocidas: contexto del pedido para la aclaración ──────────────────

def test_r2_conocidas_devuelve_inputs_existentes():
    content = [
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Martillo", "cantidad": 1, "total": 15000}),
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Tornillo Fantasma", "cantidad": 5, "total": 5000}),
    ]
    conocidas = ventas_conocidas(content, _existe)
    assert len(conocidas) == 1
    assert conocidas[0]["producto"] == "Martillo"


def test_r2_conocidas_incluye_venta_varia():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Venta Varia", "cantidad": 1, "total": 80000})]
    assert ventas_conocidas(content, _existe)[0]["producto"] == "Venta Varia"


def test_r2_conocidas_vacia_si_todo_desconocido():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Acrilan", "cantidad": 1, "total": 9000})]
    assert ventas_conocidas(content, _existe) == []


# ─────────────────────────────────────────────
# Wiring: tools llega (o no) a messages.create
# ─────────────────────────────────────────────

class _FakeMessages:
    def __init__(self):
        self.kwargs = None
    def create(self, **kwargs):
        self.kwargs = kwargs
        return object()  # _llamar_claude no toca .content/.usage en happy path sin métricas


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def test_llamar_claude_forwarda_tools():
    import asyncio
    from ai import _llamar_claude_con_reintentos
    cli = _FakeClient()
    asyncio.run(_llamar_claude_con_reintentos(
        cli, 100, [{"type": "text", "text": "x"}],
        [{"role": "user", "content": "hola"}],
        model=TOOL_REGISTRAR_VENTA and "claude-haiku-4-5-20251001",
        tools=TOOLS,
    ))
    assert cli.messages.kwargs.get("tools") == TOOLS


def test_llamar_claude_sin_tools_no_envia_param():
    import asyncio
    from ai import _llamar_claude_con_reintentos
    cli = _FakeClient()
    asyncio.run(_llamar_claude_con_reintentos(
        cli, 100, [{"type": "text", "text": "x"}],
        [{"role": "user", "content": "hola"}],
        model="claude-haiku-4-5-20251001",
        tools=None,
    ))
    assert "tools" not in cli.messages.kwargs


# ─────────────────────────────────────────────
# Streaming: done trae tags (con tools) / texto (sin tools)
# ─────────────────────────────────────────────

class _FakeStream:
    """Imita el context manager de config.claude_client.messages.stream(...)."""
    def __init__(self, texts, final):
        self._texts = texts
        self._final = final
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    @property
    def text_stream(self):
        for t in self._texts:
            yield t
    def get_final_message(self):
        return self._final


def _correr_stream(texts, final, tools):
    import asyncio
    import types
    import config
    from ai import _stream_claude_chunks
    orig = config.claude_client
    config.claude_client = types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=lambda **kw: _FakeStream(texts, final))
    )
    try:
        async def _collect():
            out = []
            async for k, d in _stream_claude_chunks(
                [{"type": "text", "text": "x"}],
                [{"role": "user", "content": "2 martillo"}],
                100, model="claude-haiku-4-5-20251001", tools=tools,
            ):
                out.append((k, d))
            return out
        return asyncio.run(_collect())
    finally:
        config.claude_client = orig


def test_stream_done_trae_tags_con_tools():
    import types
    final = types.SimpleNamespace(
        content=[_Block("tool_use", name="registrar_venta",
                        input={"producto": "Martillo", "cantidad": 1, "total": 15000})],
        usage=None,
    )
    eventos = _correr_stream(texts=[], final=final, tools=TOOLS)
    kinds = [k for k, _ in eventos]
    assert "done" in kinds
    done_payload = next(d for k, d in eventos if k == "done")
    assert _ventas_parseadas(done_payload) == [{"producto": "Martillo", "cantidad": 1, "total": 15000}]


def test_stream_done_es_texto_sin_tools():
    import types
    final = types.SimpleNamespace(content=[_Block("text", text="hola mundo")], usage=None)
    eventos = _correr_stream(texts=["hola ", "mundo"], final=final, tools=None)
    chunks = [d for k, d in eventos if k == "chunk"]
    done_payload = next(d for k, d in eventos if k == "done")
    assert chunks == ["hola ", "mundo"]          # los deltas se streamean igual
    assert done_payload == "hola mundo"          # sin tools, done = texto acumulado


# ─────────────────────────────────────────────
# Prompt: directiva de tool-calling solo con el flag activo
# ─────────────────────────────────────────────

def test_prompt_estatico_incluye_directiva_solo_con_flag():
    import config
    from ai.prompts import _construir_parte_estatica
    mem = {"negocio": {}, "catalogo": {}}
    orig = config.IA_TOOL_CALLING
    try:
        config.IA_TOOL_CALLING = True
        con = _construir_parte_estatica(mem)
        config.IA_TOOL_CALLING = False
        sin = _construir_parte_estatica(mem)
    finally:
        config.IA_TOOL_CALLING = orig
    assert "registrar_venta" in con and "REGLA PRIORITARIA" in con
    assert "REGLA PRIORITARIA" not in sin


# ─────────────────────────────────────────────
# Nudge de ambigüedad de variante (determinista)
# ─────────────────────────────────────────────

def _cands(*nombres):
    return [{"nombre": n, "nombre_lower": n.lower()} for n in nombres]


def test_ambiguo_lija_sin_grano():
    from ai.prompt_products import _detectar_ambiguedad_variante
    cands = _cands("Lija N°60", "Lija N°80", "Lija N°100", "Lija N°120")
    aviso = _detectar_ambiguedad_variante(cands, "1 lija")
    assert aviso and "AMBIGUO" in aviso and "Lija N°60" in aviso


def test_ambiguo_disco_metal_4_7():
    from ai.prompt_products import _detectar_ambiguedad_variante
    cands = _cands('Disco de Corte Metal 4"', 'Disco de Corte Metal 7"',
                   'Disco de Corte Madera 4"')
    aviso = _detectar_ambiguedad_variante(cands, "1 disco de corte metal")
    assert aviso and "AMBIGUO" in aviso


def test_no_ambiguo_si_especifica_grano():
    from ai.prompt_products import _detectar_ambiguedad_variante
    cands = _cands("Lija N°60", "Lija N°80", "Lija N°100")
    # "lija 80" menciona el token 80 → especificó → no ambiguo
    assert _detectar_ambiguedad_variante(cands, "lija 80") == ""


def test_no_ambiguo_si_especifica_medida_disco():
    from ai.prompt_products import _detectar_ambiguedad_variante
    cands = _cands('Disco de Corte Metal 4"', 'Disco de Corte Metal 7"')
    assert _detectar_ambiguedad_variante(cands, "1 disco de corte metal 7") == ""


def test_no_ambiguo_una_sola_variante():
    from ai.prompt_products import _detectar_ambiguedad_variante
    assert _detectar_ambiguedad_variante(_cands("Martillo"), "2 martillo") == ""


def test_no_ambiguo_distintos_productos_base():
    from ai.prompt_products import _detectar_ambiguedad_variante
    # Bases distintas (no son variantes del mismo producto) → no ambiguo
    cands = _cands("Martillo", "Brocha de 3", "Cemento Gris")
    assert _detectar_ambiguedad_variante(cands, "varios") == ""


def test_cantidad_inicial_no_cuenta_como_variante():
    from ai.prompt_products import _detectar_ambiguedad_variante
    # "4 lija" → el 4 es cantidad, no un grano; los granos son 60/80/100
    cands = _cands("Lija N°60", "Lija N°80", "Lija N°100")
    assert _detectar_ambiguedad_variante(cands, "4 lija") != ""


def test_no_ambiguo_en_mensaje_augmentado_multiturno():
    from ai.prompt_products import _detectar_ambiguedad_variante
    # Simula el mensaje augmentado que genera el multi-turno cuando el usuario
    # responde "80" después de "¿Lija de qué número? Tengo: ...":
    # _msg_para_match = "Test: 1 lija, Test: 80"
    # El "80" en el mensaje debe desactivar la ambigüedad aunque el prefijo "Test:" esté presente.
    cands = _cands("Lija N°60", "Lija N°80", "Lija N°100", "Lija N°120")
    assert _detectar_ambiguedad_variante(cands, "Test: 1 lija, Test: 80") == ""
