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
        "- Si el vendedor declara un monto con $, con '=', o diciéndolo (ej. 'a cinco "
        "mil', 'en diez mil', 'el precio es ocho mil'), ese ES el total: úsalo tal "
        "cual y marca 'precio_declarado': true. Si solo nombra el producto y la "
        "cantidad (el precio sale del catálogo), NO pongas 'precio_declarado'.\n"
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
            "precio_declarado": {
                "type": "boolean",
                "description": (
                    "true SOLO si el vendedor dijo explícitamente un precio o monto "
                    "para este producto (con $, con '=', o en palabras: 'a cinco mil', "
                    "'en diez mil', 'vale ocho mil'). Omitir cuando el precio sale del "
                    "catálogo (el vendedor solo nombró producto y cantidad)."
                ),
            },
        },
        "required": ["producto", "cantidad", "total"],
    },
}

# Egreso de dinero (gasto). CLAVE para no confundir con una venta.
TOOL_REGISTRAR_GASTO = {
    "name": "registrar_gasto",
    "description": (
        "Registra un EGRESO de dinero del negocio (un gasto): plata que SALE. "
        "Ejemplos: refrigerio, almuerzo, transporte, domicilio, servicios públicos "
        "(luz, agua, internet), arriendo, papelería, herramienta para el local, "
        "propina, pago de mano de obra.\n"
        "NO es una venta (la venta es plata que ENTRA por vender un producto). "
        "Si el vendedor dice 'gasté', 'pagué', 'registra un gasto', 'compré para el "
        "local', 'saqué de la caja para…', es un GASTO, no una venta.\n"
        "- 'concepto': en qué se gastó (ej. 'refrigerio', 'transporte').\n"
        "- 'monto': pesos gastados, sin símbolos $ ni comas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "concepto": {"type": "string", "description": "En qué se gastó."},
            "monto": {"type": "number", "description": "Monto en pesos. Sin $ ni comas."},
            "categoria": {
                "type": "string",
                "description": "Categoría opcional (ej. transporte, servicios, varios).",
            },
        },
        "required": ["concepto", "monto"],
    },
}

# Venta a crédito (fiado): el cliente se lleva mercancía y queda debiendo.
TOOL_REGISTRAR_FIADO = {
    "name": "registrar_fiado",
    "description": (
        "Registra un FIADO: una venta a crédito donde el cliente queda DEBIENDO. "
        "Úsala cuando el vendedor dice 'fíale', 'a crédito', 'queda debiendo', "
        "'anótale a la cuenta de…'. Requiere SIEMPRE el nombre del cliente.\n"
        "- 'cliente': nombre de quien queda debiendo.\n"
        "- 'concepto': qué se llevó.\n"
        "- 'cargo': monto que queda debiendo, en pesos, sin $ ni comas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cliente": {"type": "string", "description": "Nombre del cliente que queda debiendo."},
            "concepto": {"type": "string", "description": "Qué se llevó fiado."},
            "cargo": {"type": "number", "description": "Monto que queda debiendo. Sin $ ni comas."},
        },
        "required": ["cliente", "cargo"],
    },
}

# Abono: el cliente paga (total o parcial) sobre una deuda de fiado existente.
TOOL_ABONAR_FIADO = {
    "name": "abonar_fiado",
    "description": (
        "Registra un ABONO de un cliente sobre su deuda de fiado: plata que el "
        "cliente PAGA para reducir lo que debe. Úsala cuando el vendedor dice "
        "'abonó', 'pagó parte de la deuda', 'me dio X de lo que debía'. "
        "Requiere el nombre del cliente.\n"
        "- 'cliente': quién abona.\n"
        "- 'monto': cuánto abonó, en pesos, sin $ ni comas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cliente": {"type": "string", "description": "Nombre del cliente que abona."},
            "monto": {"type": "number", "description": "Monto abonado. Sin $ ni comas."},
        },
        "required": ["cliente", "monto"],
    },
}

# Alta de cliente. Solo se expone en VOZ (Fase 4.5): el bot de Telegram ya tiene
# su wizard paso a paso; en voz el cerebro junta los datos hablando y, cuando
# tiene nombre + cédula, llama esta herramienta. El puente la convierte al tag
# [CLIENTE_NUEVO] que response_builder ya inserta en PG.
TOOL_CREAR_CLIENTE = {
    "name": "crear_cliente",
    "description": (
        "Da de alta un CLIENTE NUEVO en la base. Úsala cuando el vendedor pide "
        "crear/registrar un cliente ('creá un cliente', 'guardá a este cliente', "
        "'anotá a don Pedro'). Necesita SIEMPRE nombre e identificación (cédula o "
        "NIT); si falta alguno, pedílo hablando antes de llamarla. El resto es "
        "opcional. NO la uses para fiar ni para registrar ventas a un cliente: "
        "para eso están registrar_fiado y registrar_venta.\n"
        "- 'nombre': nombre completo del cliente.\n"
        "- 'identificacion': número de cédula o NIT, solo dígitos, sin puntos."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre": {"type": "string", "description": "Nombre completo del cliente."},
            "identificacion": {
                "type": "string",
                "description": "Cédula o NIT, solo dígitos, sin puntos ni comas.",
            },
            "tipo_id": {
                "type": "string",
                "description": "Tipo de documento. Omitir si no se dice (default cédula).",
                "enum": ["Cedula de ciudadania", "NIT", "Cedula de extranjeria", "Pasaporte"],
            },
            "tipo_persona": {
                "type": "string",
                "enum": ["Natural", "Juridica"],
                "description": "Natural (persona) o Juridica (empresa). Omitir si no se dice.",
            },
            "telefono": {"type": "string", "description": "Teléfono. Omitir si no se menciona."},
            "correo": {"type": "string", "description": "Correo. Omitir si no se menciona."},
        },
        "required": ["nombre", "identificacion"],
    },
}

# Herramientas expuestas a Claude. Cubren las MUTACIONES de plata (venta, gasto,
# fiado, abono) — donde la clasificación de intención debe ser precisa. Las
# consultas y otras acciones siguen como tags de texto.
TOOLS = [
    TOOL_REGISTRAR_VENTA,
    TOOL_REGISTRAR_GASTO,
    TOOL_REGISTRAR_FIADO,
    TOOL_ABONAR_FIADO,
]

# Conjunto de herramientas para el canal de VOZ: las de plata + alta de cliente.
# El bot/dashboard siguen con TOOLS (el alta de cliente allá usa su propio wizard).
TOOLS_VOZ = TOOLS + [TOOL_CREAR_CLIENTE]


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


def _gasto_a_tag(inp: dict) -> str:
    """Convierte registrar_gasto al tag [GASTO]{...}[/GASTO]."""
    gasto: dict = {
        "concepto": inp.get("concepto", ""),
        "monto":    inp.get("monto", 0),
    }
    if inp.get("categoria"):
        gasto["categoria"] = inp["categoria"]
    return f"[GASTO]{json.dumps(gasto, ensure_ascii=False)}[/GASTO]"


def _fiado_a_tag(inp: dict) -> str:
    """Convierte registrar_fiado al tag [FIADO]{...}[/FIADO]."""
    fiado: dict = {
        "cliente":  inp.get("cliente", ""),
        "concepto": inp.get("concepto", ""),
        "cargo":    inp.get("cargo", 0),
    }
    return f"[FIADO]{json.dumps(fiado, ensure_ascii=False)}[/FIADO]"


def _abono_a_tag(inp: dict) -> str:
    """Convierte abonar_fiado al tag [ABONO_FIADO]{...}[/ABONO_FIADO]."""
    abono: dict = {
        "cliente": inp.get("cliente", ""),
        "monto":   inp.get("monto", 0),
    }
    return f"[ABONO_FIADO]{json.dumps(abono, ensure_ascii=False)}[/ABONO_FIADO]"


def _cliente_a_tag(inp: dict) -> str:
    """Convierte crear_cliente al tag [CLIENTE_NUEVO]{...}[/CLIENTE_NUEVO] que
    response_builder ya inserta en PG. Solo incluye los opcionales que vengan."""
    cli: dict = {
        "nombre":         inp.get("nombre", ""),
        "identificacion": str(inp.get("identificacion", "")),
    }
    for k in ("tipo_id", "tipo_persona", "telefono", "correo"):
        if inp.get(k):
            cli[k] = inp[k]
    return f"[CLIENTE_NUEVO]{json.dumps(cli, ensure_ascii=False)}[/CLIENTE_NUEVO]"


# tool_name → builder del tag equivalente
_TAG_BUILDERS = {
    "registrar_venta":  _venta_a_tag,
    "registrar_gasto":  _gasto_a_tag,
    "registrar_fiado":  _fiado_a_tag,
    "abonar_fiado":     _abono_a_tag,
    "crear_cliente":    _cliente_a_tag,
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


# Productos legítimos que NO tienen entrada en el catálogo (no se validan).
_PRODUCTOS_SIN_CATALOGO = {"venta varia", "ventas varia", "venta general"}


def ventas_con_producto_desconocido(content: list, existe_producto) -> list[str]:
    """
    Riel R2 (voz): revisa los bloques tool_use `registrar_venta` y devuelve los
    nombres de producto que NO existen en el catálogo, para NO registrarlos y
    pedir aclaración hablada en vez de inventar un producto/precio.

    `existe_producto(nombre: str) -> bool`: callback que resuelve si el producto
    está en el catálogo. Se inyecta para no acoplar este módulo a memoria/DB
    (lo mantiene puro y testeable). "Venta Varia" y similares se ignoran (son
    ventas legítimas sin entrada de catálogo).

    Devuelve la lista (preservando orden, sin duplicados) de nombres no hallados.
    Lista vacía = todos los productos existen (o no hubo ventas que validar).
    """
    desconocidos: list[str] = []
    for raw in content or []:
        b = _norm_block(raw)
        if b["type"] != "tool_use" or b["name"] != "registrar_venta":
            continue
        prod = (b["input"].get("producto") or "").strip()
        if not prod or prod.lower() in _PRODUCTOS_SIN_CATALOGO:
            continue
        if not existe_producto(prod) and prod not in desconocidos:
            desconocidos.append(prod)
    return desconocidos


def ventas_conocidas(content: list, existe_producto) -> list[dict]:
    """
    Complemento de ventas_con_producto_desconocido: devuelve los `input` de los
    `registrar_venta` cuyo producto SÍ está en el catálogo (o es "Venta Varia").

    Se usa para que, cuando un producto del pedido falle, la pregunta de
    aclaración recuerde lo que ya quedó entendido ("entendí un martillo, pero
    no encontré X..."). Así no se pierde el contexto de la venta completa: la
    parte buena queda explícita en el historial y el siguiente turno la retoma.
    """
    conocidas: list[dict] = []
    for raw in content or []:
        b = _norm_block(raw)
        if b["type"] != "tool_use" or b["name"] != "registrar_venta":
            continue
        prod = (b["input"].get("producto") or "").strip()
        if not prod:
            continue
        if prod.lower() in _PRODUCTOS_SIN_CATALOGO or existe_producto(prod):
            conocidas.append(b["input"])
    return conocidas


def ventas_con_precio_dudoso(content: list, precio_esperado) -> list[dict]:
    """
    Riel R2-precio (voz): revisa los `registrar_venta` de un producto CONOCIDO en
    los que el vendedor NO declaró precio (`precio_declarado` ausente/falso) y el
    `total` que puso Claude NO coincide con el del catálogo (precio × cantidad,
    respetando fracciones y precio por cantidad). Sin precio declarado, el catálogo
    es la fuente de verdad: un total divergente es una alucinación → NO se registra,
    se pide confirmación hablada con el precio real.

    A diferencia del riel de existencia, NO se auto-corrige el total: Claude ya
    dijo el monto en su prosa hablada, así que cambiar solo el tag dejaría la voz
    desincronizada del registro. Por eso se bloquea y se vuelve a preguntar.

    `precio_esperado(producto: str, cantidad: float) -> tuple[int, float] | int | None`:
    callback que devuelve el total de catálogo para esa cantidad (acepta la tupla
    (total, precio_unidad) de obtener_precio_para_cantidad o un int directo), o
    None / 0 si no se puede determinar. Se inyecta para no acoplar a memoria/DB.

    Devuelve la lista de divergencias (orden preservado):
        {"producto", "cantidad", "total_dicho", "total_catalogo"}
    Lista vacía = todos los totales cuadran (o no había nada que validar).
    """
    dudosas: list[dict] = []
    for raw in content or []:
        b = _norm_block(raw)
        if b["type"] != "tool_use" or b["name"] != "registrar_venta":
            continue
        inp = b["input"]
        prod = (inp.get("producto") or "").strip()
        if not prod or prod.lower() in _PRODUCTOS_SIN_CATALOGO:
            continue
        # El vendedor dijo un precio explícito → ese ES el total, no se valida.
        if inp.get("precio_declarado"):
            continue
        try:
            cantidad    = float(inp.get("cantidad", 1) or 1)
            total_dicho = float(inp.get("total", 0) or 0)
        except (TypeError, ValueError):
            continue

        esperado = precio_esperado(prod, cantidad)
        if isinstance(esperado, tuple):          # (total, precio_unidad) → tomar total
            esperado = esperado[0]
        if not esperado or esperado <= 0:        # sin precio de catálogo → no validar
            continue

        # Tolerancia: 1% del esperado (mín. 1 peso) absorbe redondeos; las
        # alucinaciones de precio divergen por miles, no por pesos.
        tolerancia = max(1.0, esperado * 0.01)
        if abs(total_dicho - esperado) > tolerancia:
            dudosas.append({
                "producto":       prod,
                "cantidad":       inp.get("cantidad", 1),
                "total_dicho":    round(total_dicho),
                "total_catalogo": int(esperado),
            })
    return dudosas


def _monto_int(val) -> int:
    """Monto a entero apto para leer en voz. Fail-safe a 0."""
    try:
        return int(round(float(val or 0)))
    except (TypeError, ValueError):
        return 0


def confirmacion_mutaciones_voz(content: list) -> str | None:
    """
    Riel de confirmación hablada (voz) para gasto / fiado / abono. Si Claude propone
    registrar uno de estos (y NINGUNA venta — las ventas ya tienen su flujo de método
    de pago de 2 pasos), devuelve una pregunta hablada para que el vendedor confirme
    ANTES de registrar. Devuelve None si no hay mutación de ese tipo, o si el turno
    también trae ventas (turno mixto → no se intercepta; raro en voz).

    El registro real ocurre en el turno SIGUIENTE: cuando el vendedor afirma, Claude
    vuelve a emitir la herramienta (la app manda el historial completo del loop) y el
    riel ya no retiene (ver es_afirmacion_voz en ai/__init__). Mismo patrón que los
    rieles de existencia/precio: se reemplaza la salida por la pregunta hablada.
    """
    tiene_venta = False
    propuestas: list[str] = []
    for raw in content or []:
        b = _norm_block(raw)
        if b["type"] != "tool_use":
            continue
        nombre = b["name"]
        inp    = b["input"]
        if nombre == "registrar_venta":
            tiene_venta = True
        elif nombre == "registrar_gasto":
            concepto = (inp.get("concepto") or "").strip() or "varios"
            propuestas.append(f"un gasto de {_monto_int(inp.get('monto'))} en {concepto}")
        elif nombre == "registrar_fiado":
            cliente = (inp.get("cliente") or "").strip() or "el cliente"
            propuestas.append(f"un fiado de {_monto_int(inp.get('cargo'))} a {cliente}")
        elif nombre == "abonar_fiado":
            cliente = (inp.get("cliente") or "").strip() or "el cliente"
            propuestas.append(f"un abono de {_monto_int(inp.get('monto'))} de {cliente}")
        elif nombre == "crear_cliente":
            nom   = (inp.get("nombre") or "").strip() or "el cliente"
            ident = str(inp.get("identificacion") or "").strip()
            propuestas.append(
                f"el cliente {nom} con cédula {ident}" if ident else f"el cliente {nom}"
            )

    if tiene_venta or not propuestas:
        return None
    return f"Voy a registrar {', '.join(propuestas)}. ¿Confirmás?"


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
