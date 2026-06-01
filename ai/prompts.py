"""
ai/prompts.py — Construccion del system prompt de Claude.
Extraido de ai.py (Tarea G). Funciones puras de construccion de texto.
"""

# -- stdlib --
import re
import logging
import os
import json
import time as _time

# -- propios --
import config
import skill_loader
import alias_manager
import fuzzy_match
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, _normalizar

logger = logging.getLogger("ferrebot.ai.prompts")

# ─────────────────────────────────────────────
# TAG [BUSCAR_HISTORICO] — capacidad de búsqueda de Capa 3
# ─────────────────────────────────────────────
# Doc breve para que Claude aprenda cuándo y cómo invocar la búsqueda
# histórica. Se inyecta en la parte ESTÁTICA del prompt (cacheable).

_DOC_BUSCAR_HISTORICO = """\
BÚSQUEDA EN HISTÓRICO (FTS + fuzzy):
Cuando el vendedor te pregunte sobre VENTAS PASADAS o conversaciones viejas
("¿qué le vendí ayer a Pedro?", "¿cuándo pidieron drywall?", "¿qué hablamos
con Juan del fiado?"), USA el tag [BUSCAR_HISTORICO] en lugar de adivinar:

  [BUSCAR_HISTORICO]{"tipo":"ventas_producto","query":"drywall","dias":30,"limit":10}[/BUSCAR_HISTORICO]
  [BUSCAR_HISTORICO]{"tipo":"ventas_cliente","query":"pedro","dias":7}[/BUSCAR_HISTORICO]
  [BUSCAR_HISTORICO]{"tipo":"conversaciones","query":"fiado","dias":30}[/BUSCAR_HISTORICO]

REGLAS:
- "tipo" obligatorio: ventas_producto | ventas_cliente | conversaciones
- "query" obligatorio (puede tener typos — el sistema tolera "drwayll")
- "dias" opcional (default 30; usa 1-3 para "ayer/recién", 90+ para "hace meses")
- "limit" opcional (default 10, máx 50)
- Para ventas de un vendedor específico: agrega "vendedor":"andres"

El sistema REEMPLAZA el tag por una lista formateada — vos NO inventes
resultados, solo emití el tag con un texto introductorio breve. Ejemplo:
  Vendedor: "qué le vendí ayer a pedro?"
  Vos: "Mirá las ventas de Pedro de ayer:\\n[BUSCAR_HISTORICO]{...}[/BUSCAR_HISTORICO]"

NO uses [BUSCAR_HISTORICO] para registrar ventas nuevas — para eso usa [VENTA].
"""


# ─────────────────────────────────────────────
# CANAL DE VOZ — instrucciones para el asistente hablado (##VOZ##)
# ─────────────────────────────────────────────
# Se inyecta como bloque de system prompt SOLO cuando el mensaje viene del
# asistente de voz (app Android). Cambia el TEXTO hablado, no el formato de los
# tags de acción ([VENTA], [GASTO], etc.), que siguen funcionando igual.

VOZ_INSTRUCCIONES = """\
CANAL DE VOZ — TU RESPUESTA SE LEERÁ EN VOZ ALTA POR UN AUDÍFONO.
Optimiza cada palabra para el OÍDO, no para la pantalla. Hablás con un vendedor de ferretería.

ESTILO HABLADO (obligatorio):
- NADA de emojis, markdown, viñetas, asteriscos, almohadillas ni símbolos.
- NUNCA escribas el signo "$". Di los montos en palabras: "cuatro mil pesos", no "$4.000".
- Números en palabras naturales: "dos bultos", "dieciséis mil pesos".
- Frases CORTAS y naturales, una o dos oraciones por turno. No leas listas largas:
  si hay varios ítems, resumí hablando ("tres productos, veinte mil en total").

PRECISIÓN ANTE TODO (el audio se puede transcribir mal):
- Cuando registres una venta, CONFIRMÁ en voz alta lo que entendiste —producto, cantidad y total—
  y preguntá el método de pago en la misma frase. Igual emití el tag [VENTA] como siempre.
  Ejemplo: "Listo, dos bultos de cemento, dieciséis mil pesos. ¿En efectivo, transferencia o datáfono?"
- Si NO estás seguro del producto o la cantidad (variantes, ambigüedad, transcripción dudosa),
  PREGUNTÁ en voz alta en vez de adivinar. Ejemplo: "¿El wayper blanco o el gris?".
- El método de pago se entiende HABLADO: efectivo, transferencia o datáfono. Nunca menciones "botones".
"""


# ─────────────────────────────────────────────
# REGLAS DE VOZ — reemplazan los skills del bot en el canal hablado
# ─────────────────────────────────────────────
# En voz NO se cargan los skills de texto del bot (core/precios_base/granel/…):
# son ~16k chars escritos para Telegram y restan fluidez. En su lugar va este
# bloque compacto. La precisión la dan las TOOLS + los rieles deterministas
# (detección de ambigüedad), no la prosa.

VOZ_REGLAS = """\
Sos el asistente de voz de la ferretería. Hablás por audio con un vendedor.
Tu trabajo: registrar ventas, gastos, fiados y abonos, y responder consultas —
rápido y SIN errores.

REGLAS DURAS (no las rompas):
1. NUNCA inventes un producto ni un precio. Si el producto NO está en el catálogo,
   decílo y preguntá; no lo registres.
2. Si el producto es AMBIGUO (varias variantes: color, número, medida) y el
   vendedor no aclaró cuál, PREGUNTÁ cuál antes de registrar. La marca "⚠️ AMBIGUO"
   en el contexto es la señal: nunca elijas vos la variante.
3. Antes de registrar, leé de vuelta lo que entendiste (producto, cantidad y, si
   hay varios productos, el total) y pedí el método de pago en la misma frase.
4. Una venta puede tener VARIOS productos: llamá la herramienta una vez por cada uno.
5. El método de pago (efectivo, transferencia o datáfono) SOLO si el vendedor lo dice.
6. Un GASTO es plata que SALE (refrigerio, transporte, servicios): usá registrar_gasto,
   NO lo confundas con una venta.
7. Si no entendiste o el audio quedó dudoso, preguntá; no adivines.

Para las acciones usá las herramientas (registrar_venta, registrar_gasto,
registrar_fiado, abonar_fiado). Para consultas, respondé hablando, en frases cortas."""


# ─────────────────────────────────────────────
# TAG [BUSCAR_MEMORIA] — capacidad de memoria de entidad (Capa 4)
# ─────────────────────────────────────────────
# Claude pide notas estables sobre un producto/vendedor/alias cuando las
# necesita y no están ya inyectadas en el prompt. Se inyecta en la parte
# ESTÁTICA del prompt (cacheable).

_DOC_BUSCAR_MEMORIA = """\
MEMORIA DE ENTIDAD (notas generadas por el compresor nocturno):
Cuando necesités notas estables sobre un PRODUCTO, un VENDEDOR o un ALIAS
(ej. "qué sabemos de drywall?", "andres suele vender thinner?", "es tiner
igual que thinner?"), USA el tag [BUSCAR_MEMORIA]:

  [BUSCAR_MEMORIA]{"tipo":"producto","entidad":"drywall 6mm"}[/BUSCAR_MEMORIA]
  [BUSCAR_MEMORIA]{"tipo":"vendedor","entidad":"andres"}[/BUSCAR_MEMORIA]
  [BUSCAR_MEMORIA]{"tipo":"alias","entidad":"tiner"}[/BUSCAR_MEMORIA]

REGLAS:
- "tipo" obligatorio: producto | vendedor | alias
- "entidad" obligatorio (nombre normalizado; se tolera case/tildes)
- "limit" opcional (default 3, máx 10)

El sistema REEMPLAZA el tag por la lista de notas vigentes. Si no hay notas,
devuelve un placeholder y deberías responder con lo que sepas por contexto
o decir que no tenés información adicional.

PRIORIDAD:
- Si el mensaje del vendedor MENCIONA un producto del catálogo, es probable
  que las notas ya estén inyectadas arriba (bloque "NOTAS DE MEMORIA — ...").
  Solo usá [BUSCAR_MEMORIA] para entidades NO inyectadas automáticamente.
- NO uses [BUSCAR_MEMORIA] para buscar en el histórico de ventas —
  para eso está [BUSCAR_HISTORICO].
"""


# ─────────────────────────────────────────────
# DIRECTIVA TOOL-CALLING DE VENTAS (M-01) — solo con IA_TOOL_CALLING
# ─────────────────────────────────────────────
# Se antepone a la parte estática cuando el flag está activo. Tiene prioridad
# sobre la sección ACCIONES de core.md para el registro de ventas.

_DOC_TOOL_VENTAS = """\
==================== REGISTRO DE VENTAS — REGLA PRIORITARIA ====================
Para REGISTRAR VENTAS usa la herramienta `registrar_venta` (una llamada por
producto distinto). NO escribas tags de texto [VENTA]{...}[/VENTA] para ventas.

>>> REGLA DE ORO — AMBIGÜEDAD DE VARIANTE (tiene prioridad sobre "silencio total"):
ANTES de llamar registrar_venta, mirá el MATCH. Si hay 2 o MÁS productos cuyo
nombre base es el mismo pero difieren en medida / número / grano / pulgadas /
color (ej: varias "Lija N°...", o "Disco de Corte Metal 4\"" y "...7\""), y el
vendedor NO dijo cuál variante quiere → NO llames la herramienta. En su lugar
RESPONDÉ CON TEXTO preguntando cuál, listando las opciones del MATCH. Ejemplos:
  "1 lija" + MATCH con N°60, N°80, N°100... → "¿Qué número de lija? Tengo 60, 80, 100, 120..."
  "1 disco de corte metal" + MATCH 4" y 7"  → "¿Disco de corte metal de 4\" o 7\"?"
CLAVE: aunque TODAS las variantes cuesten lo MISMO (ej: 8 lijas todas a $2.000),
el número/grano/medida es una diferencia FÍSICA que el cliente ya eligió — una lija
N°60 (gruesa) NO es lo mismo que una N°400 (fina). Que tengan igual precio NO las
hace intercambiables: IGUAL tenés que preguntar cuál.
Vale MÁS preguntar que adivinar. NUNCA elijas vos la variante (ni la más barata,
ni la más común, ni la primera del MATCH) cuando hay varias y el vendedor no la especificó.
SÍ registrá directo si: el vendedor YA dio la variante ("lija 80", "disco metal 7"),
o el MATCH trae una sola variante, o dio el total exacto con "=" o "$".

Resto de reglas (siguen vigentes, ver abajo):
- Precio declarado por el vendedor con $ o "=" → es el total de esa línea, úsalo tal cual.
- La fracción va en el parámetro `cantidad` (0.25=1/4), nunca en el nombre del producto.
- "Venta Varia" se registra con producto="Venta Varia".
- Silencio total en ventas SIN ambigüedad: solo llamá la herramienta, sin texto.
Las demás acciones (gasto, fiado, inventario, cliente, etc.) se SIGUEN emitiendo
como tags de texto, igual que siempre.
================================================================================

"""


# ─────────────────────────────────────────────
def aplicar_alias_ferreteria(mensaje: str) -> str:
    """
    Transforma alias comunes antes de enviar a Claude (M-06).

    Delega a alias_manager.aplicar_alias_completo(), que aplica en orden:
      1. aliases dinámicos (defaults + BD)
      2. _ALIAS_REGEX (regex con backreferences)
      3. _ALIAS_LAMBDA (cálculo Python: rodillo, pita, thinner/varsol por botella/litro)
    """
    return alias_manager.aplicar_alias_completo(mensaje)

# ─────────────────────────────────────────────
# PARTE ESTÁTICA DEL SYSTEM PROMPT (cacheable)
# ─────────────────────────────────────────────

def _construir_parte_estatica(memoria: dict, solo_voz: bool = False) -> str:
    """
    Construye la parte del system prompt que NO cambia entre mensajes.
    Al ser idéntica en todas las llamadas, Anthropic la cachea automáticamente.

    `solo_voz=True`: usa el bloque compacto VOZ_REGLAS en vez de los skills de
    texto del bot (más fluidez). El catálogo y la info de negocio se mantienen.
    """
    from memoria import obtener_precios_como_texto as _obtener_precios_como_texto

    catalogo = memoria.get("catalogo", {})

    def _linea_producto_simple(prod):
        # Solo nombre:precio_unidad — las fracciones llegan via MATCH en la parte dinámica
        # Ahorra ~1960 tokens cacheados vs incluir fracciones completas
        pxc = prod.get("precio_por_cantidad")
        if pxc:
            return f"{prod['nombre']}:{pxc['precio_bajo_umbral']}/{pxc['precio_sobre_umbral']}x{pxc['umbral']}"
        else:
            return f"{prod['nombre']}:{prod['precio_unidad']}"

    if catalogo:
        # Catálogo simplificado: precio_unidad solamente (sin fracciones)
        # Las fracciones completas se inyectan en la parte dinámica via MATCH
        # cuando el producto es mencionado en el mensaje
        categorias: dict = {}
        for prod in catalogo.values():
            cat = prod.get("categoria", "Otros")
            categorias.setdefault(cat, []).append(_linea_producto_simple(prod))
        lineas_cat = []
        for cat, items in sorted(categorias.items()):
            lineas_cat.append(f"{cat}:")
            lineas_cat.extend(items[:60])
        precios_texto = "\n".join(lineas_cat)
    else:
        precios_texto = _obtener_precios_como_texto()

    precios_fraccion_mem = memoria.get("precios_fraccion", {})
    if precios_fraccion_mem:
        lineas_frac = [
            f"{prod_key} {frac}:{precio}"
            for prod_key, fracs in precios_fraccion_mem.items()
            for frac, precio in fracs.items()
        ]
        precios_fraccion_texto = "FRACCIONES EXTRA:\n" + "\n".join(lineas_frac)
    else:
        precios_fraccion_texto = ""

    # En MODO_MATCH_ONLY: catálogo se omite del estático — llega dinámicamente via MATCH
    # o como fallback completo si MATCH no encuentra nada. Cache estable con ~1235 tokens (reglas).
    # En modo normal: catálogo simplificado (solo precio base, sin fracciones) → 26% menos tokens
    _match_only = os.getenv("MODO_MATCH_ONLY", "false").lower() == "true"

    if _match_only:
        # Solo fracciones extra si las hay — el catálogo llega en la parte dinámica
        catalogo_seccion = precios_fraccion_texto
    else:
        catalogo_seccion = (
            "CATALOGO(nombre:precio_galon_o_unidad. Fracciones exactas en MATCH):\n"
            + precios_texto
            + ("\n" + precios_fraccion_texto if precios_fraccion_texto else "")
        ) if precios_texto else precios_fraccion_texto

    negocio_json = json.dumps(memoria.get("negocio", {}), ensure_ascii=False)

    # Skills estáticos: core + precios_base (siempre necesarios, muy cacheables)
    skills_estaticos = skill_loader.obtener_skills_estaticos()

    # M-01: cuando el tool-calling está activo, anteponer una directiva que le
    # diga a Claude que registre ventas con la herramienta registrar_venta en
    # vez de emitir tags [VENTA] de texto. Estable mientras el flag no cambie →
    # no rompe el prompt caching. El resto de acciones siguen como tags.
    tool_dir = _DOC_TOOL_VENTAS if config.IA_TOOL_CALLING else ""

    # Voz: en vez de los skills de texto del bot, el bloque compacto VOZ_REGLAS.
    # (En voz el tool-calling siempre está activo, así que se incluye el directivo.)
    encabezado = f"{_DOC_TOOL_VENTAS}{VOZ_REGLAS}" if solo_voz else f"{tool_dir}{skills_estaticos}"

    return f"""{encabezado}

INFORMACION DEL NEGOCIO: {negocio_json}

{catalogo_seccion}

{_DOC_BUSCAR_HISTORICO}

{_DOC_BUSCAR_MEMORIA}"""

# ─────────────────────────────────────────────
# CATÁLOGO COMPLETO PARA FOTOS (Fix 2)
# ─────────────────────────────────────────────

def _construir_catalogo_imagen(memoria: dict) -> str:
    """
    Cuando hay una imagen del cuaderno de ventas, el MATCH dinámico no puede extraer
    candidatos del texto (que solo dice 'foto de ventas'). Este helper inyecta el
    catálogo COMPLETO con TODAS las fracciones para que Claude pueda identificar
    productos y calcular cantidades desde el precio anotado.
    Solo se llama cuando imagen_b64 is not None.
    """
    catalogo = memoria.get("catalogo", {})
    if not catalogo:
        return ""
    lineas = []
    for prod in sorted(catalogo.values(), key=lambda p: p.get("nombre", "")):
        nombre   = prod["nombre"]
        precio_u = prod.get("precio_unidad", 0)
        pxc      = prod.get("precio_por_cantidad")
        fracs    = prod.get("precios_fraccion", {})
        if pxc:
            umbral  = pxc.get("umbral", 50)
            p_bajo  = pxc.get("precio_bajo_umbral", precio_u)
            p_sobre = pxc.get("precio_sobre_umbral", precio_u)
            lineas.append(f"{nombre}: normal={p_bajo}/u | x{umbral}+={p_sobre}/u")
        elif fracs:
            partes_frac = []
            for fk, fd in fracs.items():
                if isinstance(fd, dict) and "precio" in fd:
                    partes_frac.append(f"{fk}=${fd['precio']:,}")
                elif isinstance(fd, (int, float)):
                    partes_frac.append(f"{fk}=${int(fd):,}")
            if partes_frac:
                lineas.append(f"{nombre}: " + " | ".join(partes_frac))
            else:
                lineas.append(f"{nombre}: unidad=${precio_u:,}")
        else:
            lineas.append(f"{nombre}: unidad=${precio_u:,}")
    return "CATÁLOGO COMPLETO CON FRACCIONES (para foto — usa esto para identificar productos y cantidades):\n" + "\n".join(lineas)


# ─────────────────────────────────────────────
# PARTE DINÁMICA DEL SYSTEM PROMPT (por mensaje)
# ─────────────────────────────────────────────

def _construir_parte_dinamica(mensaje_usuario: str, nombre_usuario: str, memoria: dict, dashboard_mode: bool = False, solo_voz: bool = False) -> str:
    """
    Orquesta la construcción de la parte dinámica del system prompt.
    Delega a ai.prompt_context (datos de negocio) y ai.prompt_products (productos).

    `solo_voz=True`: omite los skills dinámicos de texto del bot (granel,
    thinner_varsol, …) — conserva el MATCH de productos (con la señal ⚠️ AMBIGUO).
    """
    # Lazy imports — evita ciclos ai/__init__.py ↔ ai/prompts.py ↔ submodules
    from ai.prompt_context import (
        construir_seccion_ventas,
        construir_seccion_clientes,
        construir_seccion_operaciones,
        construir_seccion_memoria_entidades,
        construir_contexto_turno,
    )
    from ai.prompt_products import construir_seccion_match, construir_precalculos_especiales


    resumen_texto, datos_texto = construir_seccion_ventas(mensaje_usuario, dashboard_mode=dashboard_mode)
    match_texto       = construir_seccion_match(mensaje_usuario, nombre_usuario, memoria)
    especiales_texto  = construir_precalculos_especiales(mensaje_usuario, memoria)
    clientes_texto    = construir_seccion_clientes(mensaje_usuario)
    operaciones_texto = construir_seccion_operaciones(mensaje_usuario)
    # En voz no se cargan los skills dinámicos del bot (restan fluidez).
    skills_texto      = "" if solo_voz else skill_loader.obtener_skills_dinamicos(mensaje_usuario)
    turno_texto       = construir_contexto_turno()
    # Capa 4 — notas estables sobre productos/vendedor (compresor nocturno)
    memoria_ent_texto = construir_seccion_memoria_entidades(mensaje_usuario, nombre_usuario)

    partes = [
        p for p in [
            turno_texto,
            match_texto,
            especiales_texto,
            clientes_texto,
            resumen_texto,
            datos_texto,
            operaciones_texto,
            memoria_ent_texto,
            f"Vendedor:{nombre_usuario}",
            skills_texto,
        ] if p
    ]
    return "\n\n".join(partes)


# ─────────────────────────────────────────────
# FUNCIÓN AUXILIAR: calcular historial adaptativo
# ─────────────────────────────────────────────

def _calcular_historial(mensaje: str) -> int:
    """
    Determina cuántos mensajes de historial enviar según el contexto.
    OPTIMIZACIÓN: ventas simples solo necesitan 1 mensaje, ahorrando ~100 tokens.
    """
    msg_l = mensaje.lower().strip()

    # Respuesta corta (1-2 palabras) = probablemente respuesta a pregunta anterior
    # Necesita contexto completo para no perder la venta original
    # Ej: "blanco", "rojo", "si", "no", "2 pulgadas"
    palabras = msg_l.split()
    if len(palabras) <= 2:
        return 4

    # Necesita contexto completo (cliente, correcciones, fiados)
    if any(k in msg_l for k in ("cliente", "fiado", "para ", "a nombre",
                                 "corrig", "modific", "error", "equivoque",
                                 "cambia", "quita", "agrega")):
        return 4

    # Análisis, reportes o consultas complejas
    _kw_contexto = {"cuanto", "vendimos", "reporte", "analiz", "resumen", "estadistica",
                    "inventario", "grafica", "top", "mas vendido", "caja", "gasto"}
    if any(k in msg_l for k in _kw_contexto):
        return 4

    # Multi-producto (comas o saltos de línea)
    if "," in mensaje or mensaje.count("\n") > 0:
        return 2

    # Venta simple: solo el mensaje actual basta
    return 1


# ─────────────────────────────────────────────
# MODELOS Y SELECTOR
# ─────────────────────────────────────────────

# Modelo híbrido: Haiku para tareas rápidas, Sonnet para complejas
MODELO_HAIKU  = "claude-haiku-4-5-20251001"
MODELO_SONNET = "claude-sonnet-4-6"

def _elegir_modelo(mensaje: str) -> str:
    """
    Clasifica el mensaje del usuario para elegir Haiku (rápido/barato)
    o Sonnet (inteligente/caro).

    Sonnet: análisis, reportes, comparaciones, explicaciones, ediciones
            complejas, fiados, correcciones, mensajes multi-línea largos.
    Haiku:  ventas simples, precios, stock, saludos, gastos simples.
    """
    ml = mensaje.lower()

    # ── Siempre Sonnet ──
    _kw_sonnet = {
        # Análisis y reportes
        "analiz", "analís", "compara", "explica", "por qué", "porqué",
        "reporte", "resumen", "estadistic", "rendimiento", "tendencia",
        "recomienda", "suger", "opina", "evalua", "evalúa",
        # Consultas complejas
        "cuánto vendimos", "cuanto vendimos", "qué se vendió", "que se vendio",
        "cuánto me", "cuanto me", "cuánto va", "cuanto va", "cuánto lleva", "cuanto lleva",
        "top producto", "más vendido", "mas vendido", "menos vendido",
        "ganancias", "utilidad", "margen", "rentabil",
        "histórico", "historico", "semana pasada", "mes pasado",
        "promedio", "proyección", "proyeccion",
        # Ediciones complejas
        "modifica", "corrig", "cambia el precio", "actualiza precio",
        "elimina", "borrar consecutivo",
        # Fiados / clientes
        "fiado", "debe", "abono", "deuda", "saldo",
        "cliente nuevo", "registrar cliente",
    }
    if any(kw in ml for kw in _kw_sonnet):
        return MODELO_SONNET

    # Multi-línea o mensajes largos con complejidad
    n_lineas = mensaje.count("\n") + 1
    n_comas  = mensaje.count(",")
    if n_lineas >= 3 or (len(mensaje) > 150 and n_comas >= 2):
        return MODELO_SONNET

    # Múltiples preguntas
    if mensaje.count("?") >= 2 or mensaje.count("¿") >= 2:
        return MODELO_SONNET

    # ── Todo lo demás → Haiku ──
    return MODELO_HAIKU
