"""
skill_loader.py — Cargador de skills para FerreBot.

Concepto inspirado en OpenFang/SKILL.md:
  - Las reglas de negocio viven en archivos .md separados (skills/)
  - Se cargan una vez al inicio (sin I/O por llamada)
  - Se inyectan selectivamente según el mensaje del usuario

Beneficios vs prompt hardcodeado en ai.py:
  1. MANTENIMIENTO: editar reglas sin tocar Python
  2. TOKENS: solo se envían las reglas relevantes al mensaje actual
  3. CACHE: la parte estática es más pequeña y estable → mejor hit rate
  4. CLARIDAD: cada regla en su propio archivo con nombre descriptivo
"""

import os
import re
import logging

_logger = logging.getLogger("ferrebot.skills")

# ─────────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────────
_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")

# ─────────────────────────────────────────────
# CACHE EN RAM — cargadas una sola vez al inicio
# ─────────────────────────────────────────────
_skills_cache: dict[str, str] = {}


def _cargar_skill(nombre: str) -> str:
    """Carga un skill desde disco (con cache en RAM)."""
    if nombre in _skills_cache:
        return _skills_cache[nombre]
    ruta = os.path.join(_SKILLS_DIR, f"{nombre}.md")
    if not os.path.exists(ruta):
        _logger.warning(f"[SKILLS] Skill no encontrado: {ruta}")
        return ""
    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read().strip()
    _skills_cache[nombre] = contenido
    _logger.info(f"[SKILLS] Cargado: {nombre} ({len(contenido)} chars)")
    return contenido


def precargar_todos():
    """Precarga todos los skills al inicio del bot para evitar I/O en runtime."""
    skills_disponibles = ["core", "precios_base", "clientes",
                          "tornillos", "thinner_varsol", "lija_esmeril",
                          "pinturas", "granel"]
    for nombre in skills_disponibles:
        _cargar_skill(nombre)
    _logger.info(f"[SKILLS] {len(_skills_cache)} skills precargados en RAM")


# ─────────────────────────────────────────────
# DETECCIÓN DE KEYWORDS
# ─────────────────────────────────────────────

_KEYWORDS_SKILLS: dict[str, list[str]] = {
    "tornillos": [
        "tornillo", "tornillos", "drywall", "chazo", "chazos",
        "puntilla", "puntillas", "arandela", "soldadura"
    ],
    "thinner_varsol": [
        "thinner", "tiner", "varsol", "cunete", "cunetes",
        "galon", "galones", "litro", "litros", "botella", "botellas"
    ],
    "lija_esmeril": [
        "lija", "lijar", "esmeril", "lija esmeril", "lija de agua",
        "lija al agua"
    ],
    "pinturas": [
        "vinilo", "esmalte", "laca", "poliuretano", "poliamida",
        "anticorrosivo", "brocha", "brochas", "rodillo", "rodillos",
        "pintura", "pintar", "davinci", "sherwin"
    ],
    "granel": [
        "cemento blanco", "yeso", "talco", "marmolina", "granito",
        "carbonato", "acronal", "kilo", "kilos"
    ],
    "clientes": [
        "cliente", "para ", "a nombre", "de parte", "factura",
        "facturar", "a crédito", "a credito", "fiado", "cuenta de"
    ],
}


def _normalizar_msg(msg: str) -> str:
    """Normaliza el mensaje para comparación (sin tildes, minúsculas)."""
    msg = msg.lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        msg = msg.replace(a, b)
    return msg


def detectar_skills_relevantes(mensaje: str) -> list[str]:
    """
    Detecta qué skills son relevantes para un mensaje dado.
    Retorna lista de nombres de skills a inyectar.
    """
    msg_norm = _normalizar_msg(mensaje)
    relevantes = []
    for skill_nombre, keywords in _KEYWORDS_SKILLS.items():
        for kw in keywords:
            if kw in msg_norm:
                relevantes.append(skill_nombre)
                break
    return relevantes


# ─────────────────────────────────────────────
# API PÚBLICA
# ─────────────────────────────────────────────

def obtener_skills_estaticos() -> str:
    """
    Retorna los skills que van en la parte ESTÁTICA (cacheada) del system prompt.
    Solo incluye reglas que NO cambian entre mensajes:
      - core (identidad + formato de respuesta + acciones)
      - precios_base (reglas de precio siempre necesarias)
    """
    partes = [
        _cargar_skill("core"),
        _cargar_skill("precios_base"),
    ]
    return "\n\n".join(p for p in partes if p)


def obtener_skills_dinamicos(mensaje: str) -> str:
    """
    Retorna los skills relevantes para inyectar en la parte DINÁMICA del prompt.
    Solo carga los skills que aplican al mensaje actual.

    Ejemplo:
      "2 tornillos drywall 6x1" → carga skill 'tornillos'
      "1/4 de laca miel"        → carga skills 'pinturas'
      "hola cuanto vendimos"    → no carga skills especiales
    """
    nombres = detectar_skills_relevantes(mensaje)
    if not nombres:
        return ""

    partes = []
    for nombre in nombres:
        contenido = _cargar_skill(nombre)
        if contenido:
            partes.append(contenido)

    if not partes:
        return ""

    resultado = "\n\n".join(partes)
    _logger.debug(f"[SKILLS] Inyectados para mensaje: {nombres} ({len(resultado)} chars)")
    return resultado


def obtener_skill(nombre: str) -> str:
    """Retorna el contenido de un skill específico por nombre."""
    return _cargar_skill(nombre)


def listar_skills() -> list[str]:
    """Lista los nombres de todos los skills disponibles."""
    if not os.path.exists(_SKILLS_DIR):
        return []
    return [
        f.replace(".md", "")
        for f in os.listdir(_SKILLS_DIR)
        if f.endswith(".md")
    ]
