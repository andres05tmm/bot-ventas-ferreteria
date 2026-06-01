"""
ai/voz_filtros.py — Filtros del canal de voz (transcripción + texto hablado).

Dos utilidades puras (solo stdlib), testeables sin red:

1. es_transcripcion_silencio() — Whisper, sobre audio mudo o ruido, ALUCINA texto
   (peor aún con el prompt de vocabulario de ferretería: inventa "puntilla con
   cabeza", "caja de puntillas", etc.). Eso disparaba "ventas fantasma" cuando el
   VAD capturaba silencio/eco del TTS. Con `response_format="verbose_json"` Whisper
   devuelve por segmento `no_speech_prob` y `avg_logprob`; si el audio es silencio,
   `no_speech_prob` es alto → descartamos la transcripción (texto vacío).

2. limpiar_texto_voz() — la respuesta se LEE en voz alta: no debe llevar emojis
   (el marcador "⚠️ AMBIGUO" del contexto a veces se cuela), ni "$", ni markdown.
"""

# -- stdlib --
import re
import unicodedata


# ─────────────────────────────────────────────
# FILTRO DE SILENCIO / ALUCINACIÓN DE WHISPER
# ─────────────────────────────────────────────

# Frases que Whisper inventa sobre silencio/música y que NUNCA son un comando real
# de ferretería. Normalizadas (minúsculas, sin tildes ni puntuación).
_HALUCINACIONES = {
    "gracias por ver el video",
    "gracias por ver",
    "subtitulos realizados por la comunidad de amara org",
    "subtitulado por la comunidad de amara org",
    "amara org",
    "musica",
    "subscribete",
    "suscribete al canal",
}


def _norm(texto: str) -> str:
    """minúsculas, sin tildes ni puntuación, espacios colapsados."""
    t = unicodedata.normalize("NFD", str(texto).lower()).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def es_transcripcion_silencio(
    texto: str,
    segmentos: list[dict] | None = None,
    umbral_no_speech: float = 0.6,
) -> bool:
    """
    True si la transcripción es, casi con seguridad, silencio o ruido que Whisper
    alucinó como texto (→ NO mandarla al cerebro: evita ventas/acciones fantasma).

    `segmentos`: lista de dicts con 'no_speech_prob' y 'avg_logprob' (los segments
    de verbose_json). Sin segmentos no se puede juzgar por probabilidad → solo se
    filtra por la lista de alucinaciones conocidas (conservador: no descarta voz real).
    """
    t = (texto or "").strip()
    if not t:
        return True
    if _norm(t) in _HALUCINACIONES:
        return True

    if not segmentos:
        return False  # sin métricas → no arriesgar a descartar voz real

    nsp = [s["no_speech_prob"] for s in segmentos if s.get("no_speech_prob") is not None]
    if not nsp:
        return False
    prom_nsp = sum(nsp) / len(nsp)

    lps = [s["avg_logprob"] for s in segmentos if s.get("avg_logprob") is not None]
    prom_lp = (sum(lps) / len(lps)) if lps else 0.0

    # Silencio claro: probabilidad de "sin voz" alta.
    if prom_nsp >= umbral_no_speech:
        return True
    # Zona gris: algo de no-voz + confianza muy baja (texto improbable) → alucinación.
    if prom_nsp >= 0.4 and prom_lp <= -0.9:
        return True
    return False


# ─────────────────────────────────────────────
# LIMPIEZA DE TEXTO PARA LECTURA EN VOZ
# ─────────────────────────────────────────────

# Rango amplio de emojis/símbolos pictográficos + flechas + dingbats + ⚠ (U+26A0).
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF"   # pictogramas, emoticones, símbolos suplementarios
    "\U00002600-\U000027BF"    # misc symbols + dingbats (incluye ⚠ U+26A0)
    "\U00002190-\U000021FF"    # flechas
    "\U00002B00-\U00002BFF"    # flechas/símbolos misc
    "️‍]"            # variation selector + ZWJ
)


def limpiar_texto_voz(texto: str) -> str:
    """
    Quita de un texto lo que NO debe leerse en voz alta: emojis (incluido ⚠️),
    el signo '$' y marcas de markdown (* # ` _ ~). Colapsa espacios. Fail-safe:
    devuelve el texto tal cual si viene vacío/None.
    """
    if not texto:
        return texto
    t = _EMOJI_RE.sub("", texto)
    t = t.replace("$", "")
    t = re.sub(r"[*#`~]+", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    # limpiar espacios sobrantes que dejó la remoción (ej. " ,  " → ", ")
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return t.strip()
