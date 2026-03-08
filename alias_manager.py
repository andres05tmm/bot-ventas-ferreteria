"""
alias_manager.py — Gestión dinámica de aliases de ferretería.

Separa los aliases SIMPLES (palabra → palabra/frase) del código Python.
Se guardan en aliases_dinamicos.json y se cargan en RAM al iniciar.

Los aliases COMPLEJOS (regex con lógica) siguen en _ALIAS_FERRETERIA de ai.py.

COMANDOS TELEGRAM:
  /alias pagaternit pegaternit        → agrega alias
  /alias ver                          → lista todos
  /alias borrar pagaternit            → elimina alias
  /alias test "2 esmaltes"            → prueba cómo queda el mensaje
"""

import json
import os
import re
import logging
import threading

logger = logging.getLogger("ferrebot.alias")

# Archivo de persistencia (Railway persiste el volumen entre deploys)
_RUTA_ALIASES = os.getenv("ALIASES_PATH", "aliases_dinamicos.json")

# Cache en RAM — cargado una vez al iniciar, actualizado en cada /alias
_aliases: dict[str, str] = {}  # {termino_lower: reemplazo}
_lock = threading.Lock()


# ─────────────────────────────────────────────
# CARGA / GUARDADO
# ─────────────────────────────────────────────

def cargar_aliases() -> dict:
    """Carga aliases desde JSON. Llama al iniciar el bot."""
    global _aliases
    try:
        if os.path.exists(_RUTA_ALIASES):
            with open(_RUTA_ALIASES, "r", encoding="utf-8") as f:
                data = json.load(f)
            with _lock:
                _aliases = {k.lower(): v for k, v in data.items()}
            logger.info(f"[ALIAS] {len(_aliases)} aliases cargados desde {_RUTA_ALIASES}")
        else:
            logger.info("[ALIAS] No hay aliases_dinamicos.json — empezando vacío")
    except Exception as e:
        logger.error(f"[ALIAS] Error cargando aliases: {e}")
    return dict(_aliases)


def _guardar_aliases():
    """Persiste el dict actual a JSON."""
    try:
        with _lock:
            data = dict(_aliases)
        with open(_RUTA_ALIASES, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[ALIAS] Error guardando aliases: {e}")


# ─────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────

def agregar_alias(termino: str, reemplazo: str) -> str:
    """
    Agrega o actualiza un alias.
    Retorna mensaje de confirmación.
    """
    termino_key = termino.strip().lower()
    reemplazo_val = reemplazo.strip().lower()

    if not termino_key or not reemplazo_val:
        return "❌ Necesito dos argumentos: /alias [termino] [reemplazo]"

    if len(termino_key) < 2:
        return "❌ El término debe tener al menos 2 caracteres."

    if termino_key == reemplazo_val:
        return "❌ El término y el reemplazo son iguales."

    with _lock:
        existia = termino_key in _aliases
        _aliases[termino_key] = reemplazo_val

    _guardar_aliases()

    if existia:
        return f"✅ Alias actualizado: '{termino_key}' → '{reemplazo_val}'"
    return f"✅ Alias guardado: '{termino_key}' → '{reemplazo_val}'"


def borrar_alias(termino: str) -> str:
    """Elimina un alias. Retorna mensaje de confirmación."""
    termino_key = termino.strip().lower()

    with _lock:
        if termino_key not in _aliases:
            return f"❌ No existe el alias '{termino_key}'"
        del _aliases[termino_key]

    _guardar_aliases()
    return f"🗑️ Alias eliminado: '{termino_key}'"


def listar_aliases() -> str:
    """Retorna string formateado con todos los aliases."""
    with _lock:
        copia = dict(_aliases)

    if not copia:
        return "📋 No hay aliases guardados.\n\nUsa /alias [termino] [reemplazo] para agregar uno."

    lineas = ["📋 *Aliases activos:*\n"]
    for termino, reemplazo in sorted(copia.items()):
        lineas.append(f"  `{termino}` → `{reemplazo}`")
    lineas.append(f"\nTotal: {len(copia)} aliases")
    return "\n".join(lineas)


# ─────────────────────────────────────────────
# APLICAR ALIASES AL MENSAJE
# ─────────────────────────────────────────────

def aplicar_aliases_dinamicos(mensaje: str) -> str:
    """
    Reemplaza términos simples del mensaje usando aliases en RAM.
    Se aplica ANTES que los aliases regex de ai.py.

    Solo reemplaza palabras completas (word boundary) para evitar
    que "lija" reemplace parte de "antihongolija".
    """
    with _lock:
        aliases_activos = dict(_aliases)

    if not aliases_activos:
        return mensaje

    resultado = mensaje
    for termino, reemplazo in aliases_activos.items():
        # Word boundary para evitar falsos positivos
        patron = r'\b' + re.escape(termino) + r'\b'
        resultado = re.sub(patron, reemplazo, resultado, flags=re.IGNORECASE)

    return resultado


def probar_alias(mensaje: str) -> str:
    """Para el comando /alias test — muestra cómo queda el mensaje."""
    original = mensaje
    resultado = aplicar_aliases_dinamicos(mensaje)
    if resultado == original:
        return f"🔍 Sin cambios:\n`{original}`"
    return f"🔍 Transformación:\n`{original}`\n→ `{resultado}`"
