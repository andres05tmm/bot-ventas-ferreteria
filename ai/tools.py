"""
ai/tools.py — Tool schemas para tool-calling nativo de Claude (M-01).

Reemplaza el patrón de tags de texto [VENTA]{...}[/VENTA] por tool use nativo:
Claude devuelve bloques tool_use con JSON garantizado válido (la API lo valida
contra el schema), eliminando el parsing frágil por regex.

PATRÓN PUENTE (Fase 1): para NO reescribir ai/response_builder.procesar_acciones
(700 líneas, 19 tags), los bloques tool_use se convierten de vuelta al formato de
tags que ese ejecutor ya entiende. Así el flujo de efectos no se toca y el rollback
es instantáneo vía el flag config.IA_TOOL_CALLING (default OFF).
"""

# -- stdlib --
import json

# ─────────────────────────────────────────────
# SCHEMAS DE HERRAMIENTAS
# ─────────────────────────────────────────────

# Herramienta de mayor volumen: registro de ventas.
# Claude la invoca UNA VEZ POR PRODUCTO (igual que emitía un [VENTA] por producto).
TOOL_REGISTRAR_VENTA = {
    "name": "registrar_venta",
    "description": (
        "Registra UNA línea de venta de un producto. Llámala una vez por cada "
        "producto distinto del mensaje del vendedor. NO la uses para consultas de "
        "precio, saludos ni preguntas: solo cuando el vendedor registra una venta real.\n"
        "REGLAS:\n"
        "- 'total' es el total en pesos de esa línea (lo que pagó el cliente por ese "
        "producto), NUNCA el precio unitario. Sin símbolos $ ni comas.\n"
        "- Si el vendedor declara un monto con $ o con '=', ese ES el total: úsalo tal "
        "cual, sin compararlo con el catálogo ni pedir confirmación.\n"
        "- 'producto' es el nombre limpio del catálogo SIN la fracción. La fracción va "
        "en 'cantidad' (ej. 0.25 para 1/4 — no escribas 'Laca 1/4').\n"
        "- 'metodo_pago' SOLO si el vendedor lo menciona explícitamente.\n"
        "- 'cliente' SOLO si el vendedor lo menciona."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "producto": {
                "type": "string",
                "description": "Nombre del producto del catálogo, sin fracción.",
            },
            "cantidad": {
                "type": "number",
                "description": "Cantidad vendida. Puede ser fracción decimal (0.25=1/4, 0.5=1/2, 1.5=1-1/2).",
            },
            "total": {
                "type": "number",
                "description": "Total en pesos de esta línea de venta. Sin $ ni comas.",
            },
            "metodo_pago": {
                "type": "string",
                "enum": ["efectivo", "transferencia", "datafono"],
                "description": "Método de pago. Omitir si el vendedor no lo menciona.",
            },
            "cliente": {
                "type": "string",
                "description": "Nombre del cliente. Omitir si no se menciona.",
            },
        },
        "required": ["producto", "cantidad", "total"],
    },
}

# Herramientas activas en Fase 1. El resto de acciones (gasto, fiado, inventario,
# etc.) siguen emitiéndose como tags de texto hasta fases posteriores.
TOOLS = [TOOL_REGISTRAR_VENTA]


# ─────────────────────────────────────────────
# PUENTE tool_use → tags de texto
# ─────────────────────────────────────────────

def _venta_a_tag(inp: dict) -> str:
    """Convierte el input de registrar_venta al tag [VENTA]{...}[/VENTA]."""
    venta: dict = {
        "producto": inp.get("producto", ""),
        "cantidad": inp.get("cantidad", 1),
        "total":    inp.get("total", 0),
    }
    if inp.get("metodo_pago"):
        venta["metodo_pago"] = inp["metodo_pago"]
    if inp.get("cliente"):
        venta["cliente"] = inp["cliente"]
    return f"[VENTA]{json.dumps(venta, ensure_ascii=False)}[/VENTA]"


# tool_name → builder del tag equivalente
_TAG_BUILDERS = {
    "registrar_venta": _venta_a_tag,
}


def _norm_block(block) -> dict:
    """Normaliza un content block (objeto del SDK o dict) a claves homogéneas."""
    if isinstance(block, dict):
        return {
            "type":  block.get("type"),
            "text":  block.get("text", "") or "",
            "name":  block.get("name"),
            "input": block.get("input") or {},
        }
    return {
        "type":  getattr(block, "type", None),
        "text":  getattr(block, "text", "") or "",
        "name":  getattr(block, "name", None),
        "input": getattr(block, "input", None) or {},
    }


def tool_uses_a_tags(content: list) -> str:
    """
    Convierte el `content` de una respuesta de Claude (lista de bloques text +
    tool_use) al string «texto + tags» que procesar_acciones() ya entiende.

    Mantiene el orden lógico: primero el texto libre que Claude haya emitido,
    luego los tags de las herramientas. Si Claude solo preguntó (sin tool_use),
    devuelve solo el texto.
    """
    textos: list[str] = []
    tags:   list[str] = []
    for raw in content or []:
        b = _norm_block(raw)
        if b["type"] == "text" and b["text"]:
            textos.append(b["text"])
        elif b["type"] == "tool_use":
            builder = _TAG_BUILDERS.get(b["name"])
            if builder:
                tags.append(builder(b["input"]))
    texto = "\n".join(textos).strip()
    if tags:
        return (texto + "\n" + "".join(tags)).strip() if texto else "".join(tags)
    return texto
