"""
tests/test_audio_sales.py — Tests para handlers/audio_sales.py.

Módulo puro sin dependencias (solo re + unicodedata), por lo que no requiere
stubs. Probamos cada detector frente a ejemplos realistas de un vendedor
colombiano hablando al bot.
"""
import sys
import os

# Permitir importar desde el root del proyecto
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from handlers.audio_sales import (
    _normalizar,
    detectar_cierre,
    detectar_cancelacion,
    detectar_metodo_pago,
    detectar_cliente_implicito,
    detectar_fiado,
    detectar_quitar_ultimo,
    es_solo_meta,
)


# ─────────────────────────────────────────────────────────────────────────
# NORMALIZACIÓN
# ─────────────────────────────────────────────────────────────────────────

def test_normalizar_quita_tildes():
    assert _normalizar("Cóbralo porfavor") == "cobralo porfavor"

def test_normalizar_quita_puntuacion():
    assert _normalizar("¡Cobra, eso es todo!") == "cobra eso es todo"

def test_normalizar_texto_vacio():
    assert _normalizar("") == ""
    assert _normalizar(None) == ""


# ─────────────────────────────────────────────────────────────────────────
# CIERRE
# ─────────────────────────────────────────────────────────────────────────

def test_cierre_cobra():
    assert detectar_cierre("cobra")
    assert detectar_cierre("cóbralo")
    assert detectar_cierre("ya cóbrale")

def test_cierre_cierra():
    assert detectar_cierre("ciérralo")
    assert detectar_cierre("cierra la venta")

def test_cierre_eso_es_todo():
    assert detectar_cierre("listo eso es todo")
    assert detectar_cierre("ya está")
    assert detectar_cierre("eso sería todo")

def test_cierre_no_dispara_por_similar():
    # Contextos conversacionales típicos de una ferretería que NO son cierre
    assert not detectar_cierre("hola como estás")
    assert not detectar_cierre("tres clavos por favor")
    assert not detectar_cierre("un martillo y un destornillador")
    # Nota: "cobra" por sí sola es tan común como verbo de cierre que aceptamos
    # falsos positivos como "la cobra es un animal" — no es un texto que un
    # vendedor enviaría a mitad de una venta.


# ─────────────────────────────────────────────────────────────────────────
# CANCELACIÓN
# ─────────────────────────────────────────────────────────────────────────

def test_cancelacion_basica():
    assert detectar_cancelacion("cancela")
    assert detectar_cancelacion("cancélalo todo")
    assert detectar_cancelacion("olvídalo")
    assert detectar_cancelacion("borra todo")
    assert detectar_cancelacion("no nada")

def test_cancelacion_no_dispara_por_contexto_normal():
    assert not detectar_cancelacion("dame tres clavos")
    assert not detectar_cancelacion("el cliente canceló su pedido anterior")  # palabra rodeada


# ─────────────────────────────────────────────────────────────────────────
# MÉTODO DE PAGO
# ─────────────────────────────────────────────────────────────────────────

def test_metodo_efectivo():
    assert detectar_metodo_pago("en efectivo") == "efectivo"
    assert detectar_metodo_pago("de contado") == "efectivo"
    assert detectar_metodo_pago("cash") == "efectivo"

def test_metodo_transferencia():
    assert detectar_metodo_pago("transferencia bancolombia") == "transferencia"
    assert detectar_metodo_pago("por nequi") == "transferencia"
    assert detectar_metodo_pago("daviplata") == "transferencia"

def test_metodo_datafono():
    assert detectar_metodo_pago("con el datáfono") == "datafono"
    assert detectar_metodo_pago("tarjeta") == "datafono"

def test_metodo_ninguno():
    assert detectar_metodo_pago("dame tres martillos") is None
    assert detectar_metodo_pago("") is None


# ─────────────────────────────────────────────────────────────────────────
# CLIENTE IMPLÍCITO
# ─────────────────────────────────────────────────────────────────────────

def test_cliente_al_fiado_de():
    assert detectar_cliente_implicito("al fiado de Juan") == "juan"
    assert detectar_cliente_implicito("ponle al fiado de pedro perez") == "pedro perez"

def test_cliente_a_nombre_de():
    assert detectar_cliente_implicito("a nombre de maría gonzález") == "maria gonzalez"

def test_cliente_para_doña():
    assert detectar_cliente_implicito("para doña maría") == "maria"
    assert detectar_cliente_implicito("para don carlos") == "carlos"

def test_cliente_ponle_a():
    assert detectar_cliente_implicito("ponle a pedro") == "pedro"

def test_cliente_ausente():
    assert detectar_cliente_implicito("tres clavos y dos tornillos") is None


# ─────────────────────────────────────────────────────────────────────────
# FIADO
# ─────────────────────────────────────────────────────────────────────────

def test_fiado_detectado():
    assert detectar_fiado("al fiado")
    assert detectar_fiado("fíale a juan")
    assert detectar_fiado("fiados")

def test_fiado_ausente():
    assert not detectar_fiado("efectivo por favor")


# ─────────────────────────────────────────────────────────────────────────
# QUITAR ÚLTIMO
# ─────────────────────────────────────────────────────────────────────────

def test_quitar_ultimo():
    assert detectar_quitar_ultimo("quita el último")
    assert detectar_quitar_ultimo("borra el ultimo")
    assert detectar_quitar_ultimo("ese último no")


# ─────────────────────────────────────────────────────────────────────────
# ES SOLO META
# ─────────────────────────────────────────────────────────────────────────

def test_es_solo_meta_cierre_corto():
    assert es_solo_meta("cobra")
    assert es_solo_meta("eso es todo")

def test_es_solo_meta_metodo_corto():
    assert es_solo_meta("en efectivo")
    assert es_solo_meta("con nequi")

def test_no_es_solo_meta_con_productos():
    # Texto largo con productos → NO es solo meta aunque mencione "cobra"
    assert not es_solo_meta(
        "tres clavos dos martillos y un destornillador y ya cobra"
    )

def test_no_es_solo_meta_texto_vacio_de_intent():
    assert not es_solo_meta("hola como va todo")
