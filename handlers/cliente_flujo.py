"""
handlers/cliente_flujo.py — Flujo paso a paso de creación de cliente.

Maneja las preguntas y botones del wizard de creación de cliente.
Depende de ventas_state para leer clientes_en_proceso.
"""

# -- terceros --
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# -- propios --
from ventas_state import clientes_en_proceso, _estado_lock


async def enviar_pregunta_cliente(message, chat_id: int):
    """
    Lee el paso actual del flujo de creación de cliente y envía
    la pregunta correspondiente, con botones cuando aplica.
    """
    with _estado_lock:
        datos = clientes_en_proceso.get(chat_id)
    if not datos:
        return

    paso = datos.get("paso")

    if paso == "nombre":
        await message.reply_text("👤 Vamos a crear el cliente. ¿Cuál es el nombre completo?")

    elif paso == "tipo_id":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🪪 CC",  callback_data=f"cli_tipoid_CC_{chat_id}"),
            InlineKeyboardButton("🏢 NIT", callback_data=f"cli_tipoid_NIT_{chat_id}"),
            InlineKeyboardButton("🌍 CE",  callback_data=f"cli_tipoid_CE_{chat_id}"),
        ]])
        await message.reply_text(
            f"Perfecto. ¿Qué tipo de documento tiene {datos.get('nombre', 'el cliente')}?",
            reply_markup=keyboard,
        )

    elif paso == "identificacion":
        await message.reply_text(f"¿Cuál es el número de {datos.get('tipo_id', 'identificación')}?")

    elif paso == "tipo_persona":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👤 Persona Natural",  callback_data=f"cli_persona_Natural_{chat_id}"),
            InlineKeyboardButton("🏢 Persona Jurídica", callback_data=f"cli_persona_Juridica_{chat_id}"),
        ]])
        await message.reply_text("¿Es Persona Natural o Persona Jurídica?", reply_markup=keyboard)

    elif paso == "correo":
        await message.reply_text("¿Cuál es el correo electrónico? (escribe 'no tiene' si no aplica)")
