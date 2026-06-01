"""
tests/test_voz_filtros.py — Filtros del canal de voz (módulo puro, sin red).

Cubre:
  - es_transcripcion_silencio(): descarta silencio/alucinación de Whisper por
    no_speech_prob / avg_logprob y por frases alucinadas conocidas; NO descarta
    voz real ni comandos cortos ("sí", "efectivo").
  - limpiar_texto_voz(): quita emojis (⚠️), '$' y markdown sin romper el texto.
"""

# -- stdlib --
import os

os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")

# -- terceros --
import pytest

# -- propios --
from ai.voz_filtros import es_transcripcion_silencio, limpiar_texto_voz


# ─────────────────────────────────────────────
# es_transcripcion_silencio
# ─────────────────────────────────────────────

def _seg(no_speech, logprob=-0.2):
    return {"no_speech_prob": no_speech, "avg_logprob": logprob}


def test_texto_vacio_es_silencio():
    assert es_transcripcion_silencio("") is True
    assert es_transcripcion_silencio("   ") is True
    assert es_transcripcion_silencio(None) is True


def test_alucinacion_conocida_se_descarta():
    assert es_transcripcion_silencio("Gracias por ver el video.") is True
    assert es_transcripcion_silencio("Subtítulos realizados por la comunidad de Amara.org") is True


def test_silencio_por_no_speech_alto():
    # Whisper alucinó "puntilla 2 1/2 con cabeza" pero el audio era silencio.
    segs = [_seg(0.85, -0.8)]
    assert es_transcripcion_silencio("puntilla dos y media con cabeza", segs) is True


def test_zona_gris_no_speech_medio_y_logprob_malo():
    assert es_transcripcion_silencio("caja de puntillas", [_seg(0.45, -1.1)]) is True


def test_voz_real_no_se_descarta():
    # Habla real: no_speech_prob bajo, logprob bueno → pasa.
    segs = [_seg(0.05, -0.15)]
    assert es_transcripcion_silencio("dame dos bultos de cemento", segs) is False


def test_comando_corto_real_no_se_descarta():
    assert es_transcripcion_silencio("sí", [_seg(0.1, -0.3)]) is False
    assert es_transcripcion_silencio("efectivo", [_seg(0.08, -0.25)]) is False


def test_sin_segmentos_solo_filtra_alucinaciones_conocidas():
    # Sin métricas no se arriesga a descartar voz real.
    assert es_transcripcion_silencio("medio galón de thinner", None) is False
    assert es_transcripcion_silencio("amara.org", None) is True


def test_umbral_configurable():
    segs = [_seg(0.5, -0.3)]
    assert es_transcripcion_silencio("algo", segs, umbral_no_speech=0.4) is True
    assert es_transcripcion_silencio("algo", segs, umbral_no_speech=0.7) is False


def test_promedio_de_varios_segmentos():
    # Mezcla: un segmento con voz y otro de silencio → promedio bajo el umbral.
    segs = [_seg(0.05, -0.2), _seg(0.55, -0.5)]   # promedio 0.30 < 0.6
    assert es_transcripcion_silencio("dos rollos de cinta", segs) is False


# ─────────────────────────────────────────────
# limpiar_texto_voz
# ─────────────────────────────────────────────

def test_quita_emoji_de_advertencia():
    assert "⚠" not in limpiar_texto_voz("⚠️ No encontré el producto")
    assert limpiar_texto_voz("⚠️ No encontré el producto").startswith("No encontré")


def test_quita_signo_pesos():
    assert "$" not in limpiar_texto_voz("son $4.000 pesos")


def test_quita_markdown():
    out = limpiar_texto_voz("*Listo* `venta` #registrada")
    assert "*" not in out and "`" not in out and "#" not in out
    assert "Listo" in out and "venta" in out


def test_texto_normal_intacto():
    t = "Dos bultos de cemento, dieciséis mil pesos. ¿Cómo pagás?"
    assert limpiar_texto_voz(t) == t


def test_varios_emojis_y_espacios():
    out = limpiar_texto_voz("Listo ✅ 🎉  registrado")
    assert "✅" not in out and "🎉" not in out
    assert out == "Listo registrado"


def test_fail_safe_vacio():
    assert limpiar_texto_voz("") == ""
    assert limpiar_texto_voz(None) is None
