"""
fuzzy_match.py — Búsqueda difusa conservadora con rapidfuzz.

Se activa SOLO cuando buscar_producto_en_catalogo() devuelve None.
En vez de asumir, SUGIERE al empleado para que confirme.

UMBRALES (conservadores para ferretería):
  >= 92%  → Sugerencia automática con botón de confirmación
  80-91%  → No hace nada (demasiado ambiguo, mejor "no tengo")
  < 80%   → No hace nada

Por qué conservador:
  "laca caoba" y "laca catalizada caoba" tienen score ~85 — 
  son productos DIFERENTES con precio diferente. Mejor preguntar.

INSTALACIÓN:
  pip install rapidfuzz
  (agregar a requirements.txt)
"""

import logging
from typing import Optional

logger = logging.getLogger("ferrebot.fuzzy")

# Umbral mínimo para sugerir (no asumir)
UMBRAL_SUGERENCIA = 92  # % de similitud mínimo para mostrar sugerencia

# Cache del índice en RAM (construido una vez al cargar)
_indice_nombres: dict[str, dict] = {}  # {nombre_lower: producto}


def construir_indice(catalogo: dict):
    """
    Construye el índice de nombres normalizados.
    Llamar una vez al iniciar el bot después de cargar memoria.
    """
    global _indice_nombres
    _indice_nombres = {}
    for prod in catalogo.values():
        nl = prod.get("nombre_lower", prod.get("nombre", "")).lower()
        _indice_nombres[nl] = prod
    logger.info(f"[FUZZY] Índice construido: {len(_indice_nombres)} productos")


def buscar_fuzzy(fragmento: str, limite: int = 3) -> list[tuple[dict, float]]:
    """
    Busca productos similares al fragmento usando rapidfuzz.

    Retorna lista de (producto, score) ordenada por score desc.
    Solo incluye resultados con score >= UMBRAL_SUGERENCIA.

    Si rapidfuzz no está instalado, retorna lista vacía silenciosamente.
    """
    if not _indice_nombres:
        return []

    if not fragmento or len(fragmento) < 3:
        return []

    try:
        from rapidfuzz import process, fuzz

        # token_sort_ratio maneja palabras en diferente orden
        # "brocha 2 pulgadas" vs "brocha de 2\"" → score alto
        resultados = process.extract(
            fragmento.lower(),
            list(_indice_nombres.keys()),
            scorer=fuzz.token_sort_ratio,
            limit=limite,
            score_cutoff=UMBRAL_SUGERENCIA,
        )

        # Filtro adicional: el resultado no puede ser de una categoría
        # completamente diferente si hay palabras clave claras
        # Ej: "martillo" no puede sugerir "tornillo" aunque tengan score 85
        resultado_final = []
        palabras_fragmento = set(fragmento.lower().split())

        for nombre_match, score, _ in resultados:
            prod = _indice_nombres.get(nombre_match)
            if not prod:
                continue

            # Verificar que al menos 1 palabra clave coincide
            palabras_prod = set(nombre_match.split())
            palabras_alfab = {w for w in palabras_fragmento if len(w) > 3}
            palabras_alfab_prod = {w for w in palabras_prod if len(w) > 3}

            if palabras_alfab and palabras_alfab.isdisjoint(palabras_alfab_prod):
                # Cero palabras en común de más de 3 letras → demasiado diferente
                logger.debug(f"[FUZZY] '{fragmento}' → '{nombre_match}' ({score}%) descartado (sin palabras comunes)")
                continue

            resultado_final.append((prod, score))

        if resultado_final:
            logger.info(f"[FUZZY] '{fragmento}' → {[(p['nombre'], s) for p, s in resultado_final]}")

        return resultado_final

    except ImportError:
        # rapidfuzz no instalado — no es crítico, el bot sigue funcionando
        logger.debug("[FUZZY] rapidfuzz no instalado, búsqueda difusa desactivada")
        return []
    except Exception as e:
        logger.error(f"[FUZZY] Error en búsqueda difusa: {e}")
        return []


def generar_mensaje_sugerencia(fragmento: str, sugerencias: list[tuple[dict, float]]) -> str | None:
    """
    Genera el texto que el bot envía cuando encuentra sugerencias difusas.
    Retorna None si no hay sugerencias.

    El empleado ve algo como:
    "❓ No encontré 'lija 80'. ¿Quisiste decir:
     • Lija Esmeril N°80 (97% similar)
     • Lija al Agua N°80 (93% similar)"
    """
    if not sugerencias:
        return None

    lineas = [f"❓ No encontré *{fragmento}* exactamente. ¿Quisiste decir?\n"]
    for prod, score in sugerencias[:3]:
        precio = prod.get("precio_unidad", 0)
        precio_txt = f" — ${precio:,.0f}" if precio else ""
        lineas.append(f"• {prod['nombre']}{precio_txt} ({score:.0f}% similar)")

    lineas.append("\nEscribe el nombre exacto o usa /alias para agregar una variante.")
    return "\n".join(lineas)


def esta_disponible() -> bool:
    """Verifica si rapidfuzz está instalado."""
    try:
        import rapidfuzz
        return True
    except ImportError:
        return False
