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
    ventas_con_precio_dudoso, confirmacion_mutaciones_voz,
    TOOLS, TOOLS_VOZ, TOOL_REGISTRAR_VENTA, TOOL_REGISTRAR_GASTO,
    TOOL_REGISTRAR_FIADO, TOOL_ABONAR_FIADO, TOOL_CREAR_CLIENTE,
)
from ai import es_afirmacion_voz, es_negacion_voz

_RE_CLIENTE = re.compile(r"\[CLIENTE_NUEVO\](.*?)\[/CLIENTE_NUEVO\]", re.DOTALL)


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
    # precio_declarado existe pero es OPCIONAL (riel R2-precio): solo lo marca
    # Claude cuando el vendedor dijo el precio; su ausencia activa la validación.
    assert props["precio_declarado"]["type"] == "boolean"
    assert "precio_declarado" not in TOOL_REGISTRAR_VENTA["input_schema"]["required"]
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
# Riel R2-precio (voz): total dicho vs catálogo
# ─────────────────────────────────────────────

# Precios de catálogo simulados (precio unitario por producto).
_PRECIOS_FAKE = {"martillo": 15000, "cemento gris": 28000, "lija 80": 2000}


def _precio_esperado(producto: str, cantidad: float):
    """Imita obtener_precio_para_cantidad: (total, precio_unidad) o None."""
    unidad = _PRECIOS_FAKE.get(producto.strip().lower())
    if unidad is None:
        return None
    return round(unidad * cantidad), unidad


def test_r2precio_total_cuadra_no_se_reporta():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Martillo", "cantidad": 2, "total": 30000})]
    assert ventas_con_precio_dudoso(content, _precio_esperado) == []


def test_r2precio_total_no_cuadra_se_reporta():
    # Catálogo: 2 × 15000 = 30000; Claude puso 25000 → alucinación de precio.
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Martillo", "cantidad": 2, "total": 25000})]
    dudosas = ventas_con_precio_dudoso(content, _precio_esperado)
    assert len(dudosas) == 1
    assert dudosas[0]["producto"] == "Martillo"
    assert dudosas[0]["total_dicho"] == 25000
    assert dudosas[0]["total_catalogo"] == 30000


def test_r2precio_declarado_no_se_valida():
    # El vendedor dijo el precio ('en 25000') → precio_declarado=true → se respeta.
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Martillo", "cantidad": 2, "total": 25000,
                             "precio_declarado": True})]
    assert ventas_con_precio_dudoso(content, _precio_esperado) == []


def test_r2precio_venta_varia_se_ignora():
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Venta Varia", "cantidad": 1, "total": 80000})]
    assert ventas_con_precio_dudoso(content, _precio_esperado) == []


def test_r2precio_sin_precio_de_catalogo_no_se_valida():
    # Producto conocido pero sin precio (callback None) → no se puede validar.
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Producto Sin Precio", "cantidad": 1, "total": 9999})]
    assert ventas_con_precio_dudoso(content, _precio_esperado) == []


def test_r2precio_tolerancia_absorbe_redondeo():
    # 0.25 × 2000 = 500; un total de 501 (1 peso) cae dentro de la tolerancia.
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Lija 80", "cantidad": 0.25, "total": 501})]
    assert ventas_con_precio_dudoso(content, _precio_esperado) == []


def test_r2precio_fraccion_divergente_se_reporta():
    # 0.5 × 2000 = 1000; Claude puso 1500 → diverge.
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Lija 80", "cantidad": 0.5, "total": 1500})]
    dudosas = ventas_con_precio_dudoso(content, _precio_esperado)
    assert dudosas[0]["total_catalogo"] == 1000
    assert dudosas[0]["cantidad"] == 0.5


def test_r2precio_multi_solo_reporta_divergente():
    content = [
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Cemento Gris", "cantidad": 1, "total": 28000}),  # ok
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Martillo", "cantidad": 1, "total": 9000}),       # diverge
    ]
    dudosas = ventas_con_precio_dudoso(content, _precio_esperado)
    assert len(dudosas) == 1
    assert dudosas[0]["producto"] == "Martillo"


def test_r2precio_ignora_texto_y_otras_tools():
    content = [
        _Block("text", text="¿En efectivo o transferencia?"),
        _Block("tool_use", name="registrar_gasto",
               input={"concepto": "refrigerio", "monto": 5000}),
    ]
    assert ventas_con_precio_dudoso(content, _precio_esperado) == []


def test_r2precio_content_vacio():
    assert ventas_con_precio_dudoso([], _precio_esperado) == []
    assert ventas_con_precio_dudoso(None, _precio_esperado) == []


def test_r2precio_acepta_int_directo_del_callback():
    # El callback puede devolver un int (no solo la tupla) → también funciona.
    def _precio_int(prod, cant):
        return 30000
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Martillo", "cantidad": 2, "total": 30000})]
    assert ventas_con_precio_dudoso(content, _precio_int) == []


# ─────────────────────────────────────────────
# Confirmar-antes-de-registrar gasto/fiado/abono (voz)
# ─────────────────────────────────────────────

def test_confirm_gasto_pide_confirmacion():
    content = [_Block("tool_use", name="registrar_gasto",
                      input={"concepto": "refrigerio", "monto": 5000})]
    msg = confirmacion_mutaciones_voz(content)
    assert msg is not None
    assert "gasto de 5000 en refrigerio" in msg
    assert "¿Confirmás?" in msg


def test_confirm_fiado_pide_confirmacion():
    content = [_Block("tool_use", name="registrar_fiado",
                      input={"cliente": "Pedro", "cargo": 20000})]
    msg = confirmacion_mutaciones_voz(content)
    assert msg is not None and "fiado de 20000 a Pedro" in msg


def test_confirm_abono_pide_confirmacion():
    content = [_Block("tool_use", name="abonar_fiado",
                      input={"cliente": "Pedro", "monto": 10000})]
    msg = confirmacion_mutaciones_voz(content)
    assert msg is not None and "abono de 10000 de Pedro" in msg


def test_confirm_gasto_sin_concepto_usa_varios():
    content = [_Block("tool_use", name="registrar_gasto", input={"monto": 3000})]
    assert "en varios" in confirmacion_mutaciones_voz(content)


def test_confirm_venta_no_se_intercepta():
    # Venta tiene su propio flujo de método de pago → no se confirma acá.
    content = [_Block("tool_use", name="registrar_venta",
                      input={"producto": "Martillo", "cantidad": 1, "total": 15000})]
    assert confirmacion_mutaciones_voz(content) is None


def test_confirm_turno_mixto_no_se_intercepta():
    # Si hay venta + gasto en el mismo turno, no se retiene (raro en voz).
    content = [
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Martillo", "cantidad": 1, "total": 15000}),
        _Block("tool_use", name="registrar_gasto",
               input={"concepto": "refrigerio", "monto": 5000}),
    ]
    assert confirmacion_mutaciones_voz(content) is None


def test_confirm_solo_texto_es_none():
    content = [_Block("text", text="¿En efectivo o transferencia?")]
    assert confirmacion_mutaciones_voz(content) is None


def test_confirm_multiples_mutaciones_se_juntan():
    content = [
        _Block("tool_use", name="registrar_gasto",
               input={"concepto": "refrigerio", "monto": 5000}),
        _Block("tool_use", name="registrar_gasto",
               input={"concepto": "transporte", "monto": 8000}),
    ]
    msg = confirmacion_mutaciones_voz(content)
    assert "refrigerio" in msg and "transporte" in msg


def test_confirm_content_vacio():
    assert confirmacion_mutaciones_voz([]) is None
    assert confirmacion_mutaciones_voz(None) is None


# ── es_afirmacion_voz ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "##VOZ## Andres: sí",
    "##VOZ## Andres: dale",
    "##VOZ## Andres: dale pues",
    "##VOZ## Andres: de una",
    "##VOZ## Andres: sí confirmo",
    "##VOZ## Andres: listo, hágale",
    "Andres: confirmo",
])
def test_es_afirmacion_voz_positivas(msg):
    assert es_afirmacion_voz(msg) is True


@pytest.mark.parametrize("msg", [
    "##VOZ## Andres: no",
    "##VOZ## Andres: gasté 5000 en refrigerio",
    "##VOZ## Andres: sí dame un martillo",   # 'sí' suelto en pedido sustantivo
    "##VOZ## Andres: ",
    "##VOZ## Andres: mejor no",
])
def test_es_afirmacion_voz_negativas(msg):
    assert es_afirmacion_voz(msg) is False


# ── es_negacion_voz ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "##VOZ## Andres: no",
    "##VOZ## Andres: mejor no",
    "##VOZ## Andres: espera, así no",
    "##VOZ## Andres: no, el correo está mal",
    "##VOZ## Andres: cambiá el teléfono",
])
def test_es_negacion_voz_positivas(msg):
    assert es_negacion_voz(msg) is True


@pytest.mark.parametrize("msg", [
    "##VOZ## Andres: sí confirmo",
    "##VOZ## Andres: dale regístralo",
    "##VOZ## Andres: el cliente es Pedro",
])
def test_es_negacion_voz_negativas(msg):
    assert es_negacion_voz(msg) is False


# ─────────────────────────────────────────────
# crear_cliente (Fase 4.5 — alta de cliente por voz)
# ─────────────────────────────────────────────

def _clientes_parseados(salida: str) -> list[dict]:
    return [json.loads(m.strip()) for m in _RE_CLIENTE.findall(salida)]


def test_schema_crear_cliente_bien_formado():
    assert TOOL_CREAR_CLIENTE["name"] == "crear_cliente"
    props = TOOL_CREAR_CLIENTE["input_schema"]["properties"]
    assert {"nombre", "identificacion"} <= set(props)
    assert TOOL_CREAR_CLIENTE["input_schema"]["required"] == ["nombre", "identificacion"]


def test_tools_voz_incluye_crear_cliente_y_las_de_plata():
    # TOOLS_VOZ = las 4 de plata + crear_cliente. TOOLS (bot/dashboard) NO lo trae.
    assert TOOLS_VOZ == TOOLS + [TOOL_CREAR_CLIENTE]
    assert TOOL_CREAR_CLIENTE not in TOOLS


def test_crear_cliente_genera_tag_parseable():
    content = [_Block("tool_use", name="crear_cliente",
                      input={"nombre": "Pedro Pérez", "identificacion": "123456",
                             "telefono": "3001234567"})]
    salida = tool_uses_a_tags(content)
    cli = _clientes_parseados(salida)[0]
    assert cli["nombre"] == "Pedro Pérez"
    assert cli["identificacion"] == "123456"
    assert cli["telefono"] == "3001234567"


def test_crear_cliente_omite_opcionales_ausentes():
    content = [_Block("tool_use", name="crear_cliente",
                      input={"nombre": "Ana", "identificacion": "999"})]
    cli = _clientes_parseados(tool_uses_a_tags(content))[0]
    assert set(cli) == {"nombre", "identificacion"}   # sin tipo_id/telefono/correo vacíos


def test_crear_cliente_identificacion_numerica_va_como_string():
    # Si Claude manda la cédula como número, el tag la serializa como string.
    content = [_Block("tool_use", name="crear_cliente",
                      input={"nombre": "Luis", "identificacion": 12345})]
    cli = _clientes_parseados(tool_uses_a_tags(content))[0]
    assert cli["identificacion"] == "12345"


def test_confirm_crear_cliente_pide_confirmacion():
    content = [_Block("tool_use", name="crear_cliente",
                      input={"nombre": "Pedro Pérez", "identificacion": "123456"})]
    msg = confirmacion_mutaciones_voz(content)
    assert msg is not None
    assert "cliente Pedro Pérez" in msg and "documento 123456" in msg
    assert "¿Confirmás?" in msg


def test_confirm_crear_cliente_incluye_correo_y_telefono():
    # La propuesta debe leer de vuelta TODOS los datos capturados (el bug era que
    # solo decía nombre+cédula y el vendedor no veía reflejado el correo).
    content = [_Block("tool_use", name="crear_cliente",
                      input={"nombre": "Doty", "identificacion": "123",
                             "correo": "andres@gmail.com", "telefono": "3001234567"})]
    msg = confirmacion_mutaciones_voz(content)
    assert "correo andres@gmail.com" in msg
    assert "teléfono 3001234567" in msg


def test_schema_crear_cliente_tipo_id_es_codigo():
    # tipo_id debe ser un CÓDIGO corto (cabe en varchar(10)), no el nombre largo.
    enum = TOOL_CREAR_CLIENTE["input_schema"]["properties"]["tipo_id"]["enum"]
    assert enum == ["CC", "NIT", "CE", "PAS"]
    assert all(len(c) <= 10 for c in enum)


def test_tipo_id_codigo_evita_overflow_varchar10():
    # El bug que rompía el alta: "Cedula de ciudadania" (20 chars) → varchar(10).
    from ai.response_builder import _tipo_id_codigo
    assert _tipo_id_codigo("Cedula de ciudadania") == "CC"
    assert _tipo_id_codigo("cédula") == "CC"
    assert _tipo_id_codigo("NIT") == "NIT"
    assert _tipo_id_codigo("Cedula de extranjeria") == "CE"
    assert _tipo_id_codigo(None) == "CC"          # default
    assert _tipo_id_codigo("") == "CC"
    assert all(len(_tipo_id_codigo(v)) <= 10
               for v in ["Cedula de ciudadania", "pasaporte", "CC", None, "xxxxxxxxxxxxxxx"])


def test_confirm_crear_cliente_con_venta_no_se_intercepta():
    content = [
        _Block("tool_use", name="registrar_venta",
               input={"producto": "Martillo", "cantidad": 1, "total": 15000}),
        _Block("tool_use", name="crear_cliente",
               input={"nombre": "Pedro", "identificacion": "123"}),
    ]
    assert confirmacion_mutaciones_voz(content) is None


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
