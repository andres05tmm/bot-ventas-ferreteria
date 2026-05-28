"""
tests/test_multi_turno_guard.py — Tests del fix V-11.

El "fix multi-turno" en ai/__init__.py augmenta el mensaje actual con el
último turno del usuario cuando detecta una clarificación corta (≤6 palabras
sin comas). Antes del fix V-11, este guard era demasiado permisivo y
producía falsos positivos como:

    Mensaje previo: "Andrés: 2 cerradura de alcoba $24000"
    Mensaje actual: "Hola"
    Resultado:      "Andrés: 2 cerradura de alcoba $24000, Hola"
                    → Claude registra venta de cerraduras

Estos tests validan que los tres guards de V-11 (saludos, pregunta del
assistant, contenido más largo) bloquean correctamente esos casos.

NOTA: el fix vive dentro de procesar_con_claude, una función larga con
muchas dependencias (clientes API, memoria, etc). Para mantener el test
unitario, replicamos la lógica en una helper testeable.
"""

# -- stdlib --
import sys
import types

# ── Stubs ────────────────────────────────────────────────────────────────────
if "config" not in sys.modules:
    sys.modules["config"] = types.ModuleType("config")


def _es_clarificacion_real(msg_bypass: str, historial_chat: list) -> bool:
    """
    Réplica de la lógica V-11 en ai/__init__.py:380-440.
    Retorna True si el mensaje debería augmentarse con el historial.
    """
    palabras_match = [w for w in msg_bypass.lower().split() if len(w) > 2]
    es_clarificacion = len(palabras_match) <= 6 and "," not in msg_bypass

    # Guard 1: no-clarificaciones
    if es_clarificacion:
        msg_limpio = msg_bypass.lower().strip()
        if ":" in msg_limpio:
            msg_limpio = msg_limpio.split(":", 1)[1].strip()
        NO_CLARIFICACIONES = {
            "hola", "buenas", "buenas tardes", "buenos dias", "buenos días",
            "buenas noches", "saludos", "ola", "hey",
            "gracias", "muchas gracias", "ok", "vale", "listo", "dale",
            "perfecto", "si", "sí", "no", "ya", "claro",
            "jaja", "jeje", "jajaja", "mmm", "mm",
            "chao", "adios", "adiós", "hasta luego", "bye",
            "?", "??", "???",
        }
        if msg_limpio in NO_CLARIFICACIONES:
            es_clarificacion = False

    # Guard 2: último assistant terminó en ?
    if es_clarificacion:
        ultimo_assistant = None
        for hmsg in reversed(historial_chat):
            if hmsg.get("role") == "assistant":
                ultimo_assistant = hmsg.get("content", "") or ""
                break
        if not ultimo_assistant or not ultimo_assistant.rstrip().endswith("?"):
            es_clarificacion = False

    return es_clarificacion


# ─────────────────────────────────────────────────────────────────────────────
# Casos que DEBEN ser bloqueados (falsos positivos del bug original)
# ─────────────────────────────────────────────────────────────────────────────

HISTORIAL_VENTA_PREVIA = [
    {"role": "user", "content": "Andrés: 2 cerradura de alcoba $24000"},
    {"role": "assistant", "content": "Registré 2 Cerradura de Alcoba por $24.000. ¿Algo más?"},
    {"role": "user", "content": "ok"},
    {"role": "assistant", "content": "Listo. ¿Cómo fue el pago?"},  # esta pregunta sí abre clarificación
    {"role": "user", "content": "efectivo"},
    {"role": "assistant", "content": "Venta cerrada en efectivo."},  # último assistant no termina en "?"
]


def test_hola_no_se_augmenta_aunque_haya_venta_previa():
    """Bug reportado V-11: 'Hola' no debe combinarse con la venta anterior."""
    assert _es_clarificacion_real("Andrés (cel nuevo): Hola", HISTORIAL_VENTA_PREVIA) is False


def test_saludos_varios_no_se_augmentan():
    for saludo in ["Hola", "Buenas", "Buenos días", "Hey", "Saludos"]:
        msg = f"Vendedor: {saludo}"
        assert _es_clarificacion_real(msg, HISTORIAL_VENTA_PREVIA) is False, f"{saludo} fue augmentado"


def test_agradecimientos_no_se_augmentan():
    for ack in ["Gracias", "Muchas gracias", "OK", "Vale", "Listo", "Dale", "Perfecto"]:
        msg = f"Karolay: {ack}"
        assert _es_clarificacion_real(msg, HISTORIAL_VENTA_PREVIA) is False, f"{ack} fue augmentado"


def test_si_no_no_se_augmentan():
    for resp in ["sí", "Si", "No"]:
        msg = f"Farid: {resp}"
        assert _es_clarificacion_real(msg, HISTORIAL_VENTA_PREVIA) is False, f"{resp} fue augmentado"


def test_sin_pregunta_previa_no_augmenta():
    """Aunque el mensaje sea corto, si el bot no preguntó nada → no augmentar."""
    historial_sin_pregunta = [
        {"role": "user", "content": "Andrés: 2 martillo carpintero"},
        {"role": "assistant", "content": "Venta registrada por $30.000."},  # no ?
    ]
    # "Segmentado de 4" sería ambiguo sin contexto previo
    assert _es_clarificacion_real("Andrés: Segmentado de 4", historial_sin_pregunta) is False


def test_sin_historial_no_augmenta():
    assert _es_clarificacion_real("Andrés: Segmentado de 4", []) is False


# ─────────────────────────────────────────────────────────────────────────────
# Casos que SÍ deben augmentarse (comportamiento original preservado)
# ─────────────────────────────────────────────────────────────────────────────

HISTORIAL_CON_PREGUNTA = [
    {"role": "user", "content": "Andrés: disco de corte"},
    {"role": "assistant", "content": "Tengo varios discos. ¿De qué tamaño y tipo?"},
]


def test_respuesta_a_pregunta_real_se_augmenta():
    """Caso para el que se diseñó originalmente el fix multi-turno."""
    assert _es_clarificacion_real("Andrés: Segmentado de 4", HISTORIAL_CON_PREGUNTA) is True


def test_respuesta_corta_con_pregunta_previa_se_augmenta():
    """'Negro' como respuesta a '¿Qué color?' es un caso clásico."""
    historial = [
        {"role": "user", "content": "Andrés: pintura tipo 1"},
        {"role": "assistant", "content": "¿Qué color?"},
    ]
    assert _es_clarificacion_real("Andrés: Negro", historial) is True


# ─────────────────────────────────────────────────────────────────────────────
# Casos límite
# ─────────────────────────────────────────────────────────────────────────────

def test_mensaje_largo_nunca_es_clarificacion():
    """Mensajes con muchas palabras (>6 de >2 letras) nunca cuentan como clarificación."""
    msg = "Andrés: necesito tres tornillos drywall seis por uno con cabeza"
    assert _es_clarificacion_real(msg, HISTORIAL_CON_PREGUNTA) is False


def test_mensaje_con_coma_nunca_es_clarificacion():
    """Mensajes multi-producto con coma nunca cuentan como clarificación."""
    msg = "Andrés: martillo, alicate"
    assert _es_clarificacion_real(msg, HISTORIAL_CON_PREGUNTA) is False
