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
from ai.tools import tool_uses_a_tags, TOOLS, TOOL_REGISTRAR_VENTA


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
    assert TOOLS == [TOOL_REGISTRAR_VENTA]


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
