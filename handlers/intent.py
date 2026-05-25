"""
handlers/intent.py — Detección de intención del mensaje entrante.

Lee el estado global y retorna la intención activa para el chat_id,
o None si el mensaje debe procesarse normalmente por Claude.

Sin efectos secundarios: no envía mensajes, no modifica estado.
"""


def detectar_flujo_activo(chat_id: int) -> str | None:
    """
    Retorna la intención activa para este chat_id.

    Valores posibles:
      "cliente_en_proceso"  — wizard de creación de cliente activo
      "correccion_activa"   — venta en modo modificación/corrección
      None                  — mensaje normal, continuar al flujo Claude

    Nota: "excel_pendiente" y "pago_pendiente" se detectan dentro de
    manejar_flujo_excel y manejar_flujo_pago_texto respectivamente,
    porque leen context.user_data que no está disponible aquí.
    """
    # Lazy imports — patrón obligatorio del proyecto
    from ventas_state import clientes_en_proceso, esperando_correccion, _estado_lock

    with _estado_lock:
        if clientes_en_proceso.get(chat_id):
            return "cliente_en_proceso"
        if esperando_correccion.get(chat_id):
            return "correccion_activa"

    return None
