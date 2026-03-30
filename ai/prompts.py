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
# ALIAS DE FERRETERÍA (pre-procesamiento)
# ─────────────────────────────────────────────

_ALIAS_FERRETERIA = [
    # (patrón regex, reemplazo)
    # PUNTILLAS: normalizar abreviaturas y quitar "caja de" → "puntilla X"
    (r'\bcaja[s]?\s+de\s+puntilla[s]?\b', r'puntilla'),   # "caja de puntilla" → "puntilla"
    (r'\bpuntilla[s]?\s+(.*?)\bs\.c\.?\b', r'puntilla \g<1> sin cabeza'),  # s.c → sin cabeza
    (r'\bpuntilla[s]?\s+(.*?)\bc\.c\.?\b', r'puntilla \g<1> con cabeza'),  # c.c → con cabeza
    (r'\bpuntilla[s]?\s+(.*?)\bsc\b',      r'puntilla \g<1> sin cabeza'),  # sc → sin cabeza (sin puntos)
    (r'\bpuntilla[s]?\s+(.*?)\bcc\b',      r'puntilla \g<1> con cabeza'),  # cc → con cabeza (sin puntos)
    (r'\bs\.c\.?\b', r'sin cabeza'),   # s.c genérico
    (r'\bc\.c\.?\b', r'con cabeza'),   # c.c genérico
    (r'\bsc\b(?=.*puntilla|\bpuntilla)', r'sin cabeza'),  # sc genérico cerca de puntilla
    # TORNILLOS DRYWALL: normalizar medidas para evitar confusión (6x3 vs 6x3/4)
    # Importante: estos patrones van PRIMERO para que se apliquen antes de otros
    (r'\btornillo[s]?\s*(?:de\s*)?drywall\s*(\d+)\s*[xX]\s*3\b(?!/)', r'tornillo drywall \g<1>x3'),
    (r'\bdrywall\s*(\d+)\s*[xX]\s*3\b(?!/)', r'drywall \g<1>x3'),
    (r'\b(\d+)\s*[xX]\s*3\b(?!/)\s*(?=.*(?:tornillo|drywall))', r'\g<1>x3'),
    # Rodillo sin medida → Rodillo Convencional
    # Evita que "3 rodillos" matchee "Rodillo de 1"", "Rodillo de 2"", etc.
    # Solo aplica cuando NO va seguido de una medida explícita (número o pulgadas)
    (r'\b(\d+)\s+rodillos?\b(?!\s*(?:de\s+)?\d)', lambda m: f"{m.group(1)} rodillo convencional"),
    # Pita sin color especificado → pita para carpa azul (la más vendida)
    # Solo aplica cuando NO va seguido de un color
    (r'\b(\d+)\s+(?:metros?\s+(?:de\s+)?)?pitas?\b(?!\s*(?:para\s+)?(?:carpa\s+)?(?:azul|rojo|negro|blanco|amarillo))',
        lambda m: f"{m.group(1)} pita para carpa azul"),
    # Pegaternit: normalizar variantes de escritura
    (r'\bpagaternit\b', r'pegaternit'),
    (r'\bpega\s*ternit\b', r'pegaternit'),
    (r'\bpegaeternit\b', r'pegaternit'),
    # Esmalte 3en1: normalizar variantes sin espacios
    (r'\b3en1\b', r'3 en 1'),
    (r'\b3-en-1\b', r'3 en 1'),
    # Thinner/Varsol: litro=1/4 galón (8000), botella/botellita=1/10 galón (4000).
    # Convertimos directo a precio total antes de llegar a Claude.
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellitas?\s+(?:de\s+)?thinner\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} thinner" if int(m.group(1) or 1) > 1 else "thinner 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellitas?\s+(?:de\s+)?varsol\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} varsol" if int(m.group(1) or 1) > 1 else "varsol 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellas?\s+(?:de\s+)?thinner\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} thinner" if int(m.group(1) or 1) > 1 else "thinner 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*botellas?\s+(?:de\s+)?varsol\b',
        lambda m: f"{int(m.group(1) or 1) * 4000} varsol" if int(m.group(1) or 1) > 1 else "varsol 4000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*litros?\s+(?:de\s+)?thinner\b',
        lambda m: f"{int(m.group(1) or 1) * 8000} thinner" if int(m.group(1) or 1) > 1 else "thinner 8000"),
    (r'\b(?:un[ao]?\s+)?(\d+)?\s*litros?\s+(?:de\s+)?varsol\b',
        lambda m: f"{int(m.group(1) or 1) * 8000} varsol" if int(m.group(1) or 1) > 1 else "varsol 8000"),
    # Thinner/Varsol por galones (cantidades >= 1/2 galón)
    # "1-1/2 galón de thinner", "1 y medio galón de thinner", "2-1/2 galones thinner"
    (r'\b(\d+)\s*-\s*1/2\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    (r'\b(\d+)\s+y\s+(?:medio|1/2)\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    (r'\b(\d+)\s+(?:galon(?:es)?)\s+y\s+(?:medio|1/2)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1>.5 galones \g<2>'),
    # "medio galón de thinner", "1/2 galón thinner"
    (r'\b(?:medio|1/2)\s*(?:galon)?\s*(?:de\s*)?(thinner|varsol)\b', r'0.5 galones \g<1>'),
    # "2 galones de thinner", "1 galón thinner"
    (r'\b(\d+)\s*(?:galon(?:es)?)\s*(?:de\s*)?(thinner|varsol)\b', r'\g<1> galones \g<2>'),
]

def aplicar_alias_ferreteria(mensaje: str) -> str:
    r"""
    Transforma alias comunes antes de enviar a Claude.

    re.sub maneja nativamente tanto callables (lambdas) como strings con
    backreferences \g<1>/\g<2>, por lo que no se necesita lógica especial.
    """
    resultado = alias_manager.aplicar_aliases_dinamicos(mensaje)
    for patron, reemplazo in _ALIAS_FERRETERIA:
        resultado = re.sub(patron, reemplazo, resultado, flags=re.IGNORECASE)
    return resultado

# ─────────────────────────────────────────────
# PARTE ESTÁTICA DEL SYSTEM PROMPT (cacheable)
# ─────────────────────────────────────────────

def _construir_parte_estatica(memoria: dict) -> str:
    """
    Construye la parte del system prompt que NO cambia entre mensajes.
    Al ser idéntica en todas las llamadas, Anthropic la cachea automáticamente.
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

    return f"""{skills_estaticos}

INFORMACION DEL NEGOCIO: {negocio_json}

{catalogo_seccion}"""

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

def _construir_parte_dinamica(mensaje_usuario: str, nombre_usuario: str, memoria: dict, dashboard_mode: bool = False) -> str:
    """
    Orquesta la construcción de la parte dinámica del system prompt.
    Delega a ai.prompt_context (datos de negocio) y ai.prompt_products (productos).
    """
    # Lazy imports — evita ciclos ai/__init__.py ↔ ai/prompts.py ↔ submodules
    from ai.prompt_context import (
        construir_seccion_ventas,
        construir_seccion_clientes,
        construir_seccion_operaciones,
    )
    from ai.prompt_products import construir_seccion_match, construir_precalculos_especiales


    resumen_texto, datos_texto = construir_seccion_ventas(mensaje_usuario, dashboard_mode=dashboard_mode)
    match_texto       = construir_seccion_match(mensaje_usuario, nombre_usuario, memoria)
    especiales_texto  = construir_precalculos_especiales(mensaje_usuario, memoria)
    clientes_texto    = construir_seccion_clientes(mensaje_usuario)
    operaciones_texto = construir_seccion_operaciones(mensaje_usuario)
    skills_texto      = skill_loader.obtener_skills_dinamicos(mensaje_usuario)

    partes = [
        p for p in [
            match_texto,
            especiales_texto,
            clientes_texto,
            resumen_texto,
            datos_texto,
            operaciones_texto,
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
