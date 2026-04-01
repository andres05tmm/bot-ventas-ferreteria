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

    elif paso == "ciudad":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🏙️ Cartagena",    callback_data=f"cli_ciudad_149_{chat_id}"),
                InlineKeyboardButton("🏙️ Barranquilla", callback_data=f"cli_ciudad_8001_{chat_id}"),
            ],
            [
                InlineKeyboardButton("🏙️ Bogotá",       callback_data=f"cli_ciudad_11001_{chat_id}"),
                InlineKeyboardButton("🏙️ Medellín",     callback_data=f"cli_ciudad_5001_{chat_id}"),
            ],
            [
                InlineKeyboardButton("🏙️ Cali",         callback_data=f"cli_ciudad_76001_{chat_id}"),
                InlineKeyboardButton("🏙️ Bucaramanga",  callback_data=f"cli_ciudad_68001_{chat_id}"),
            ],
            [
                InlineKeyboardButton("📍 Otra ciudad",  callback_data=f"cli_ciudad_149_{chat_id}"),
            ],
        ])
        await message.reply_text(
            "¿De qué ciudad es el cliente?",
            reply_markup=keyboard,
        )

    elif paso == "direccion":
        await message.reply_text(
            "¿Cuál es la dirección de la empresa? (escribe 'no tiene' si no aplica)"
        )


async def guardar_cliente_y_continuar(update, chat_id: int, telefono: str, en_proceso: dict):
    """
    Inserta el cliente nuevo en PostgreSQL y, si hay venta pendiente,
    dispara la confirmación de pago.

    Mueve la lógica que estaba en _procesar_mensaje L219-L268.
    """
    import asyncio
    import logging

    logger = logging.getLogger("ferrebot.handlers.cliente_flujo")

    def _insertar_cliente_pg():
        import db as _db
        if not _db.DB_DISPONIBLE:
            return False
        try:
            _db.execute(
                """INSERT INTO clientes
                       (nombre, tipo_id, identificacion, tipo_persona, correo, telefono,
                        direccion, municipio_dian)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    en_proceso["nombre"].upper().strip(),
                    en_proceso["tipo_id"],
                    en_proceso["identificacion"].strip() or None,
                    en_proceso["tipo_persona"],
                    en_proceso.get("correo", "").strip() or None,
                    telefono.strip() or None,
                    en_proceso.get("direccion", "").strip() or None,
                    int(en_proceso.get("municipio_dian") or 149),
                ),
            )
            return True
        except Exception as _e:
            logger.error("Error INSERT cliente PG: %s", _e)
            return False

    from memoria import invalidar_cache_memoria
    ok = await asyncio.to_thread(_insertar_cliente_pg)
    invalidar_cache_memoria()
    if ok:
        tipo_map     = {"CC": "Cédula de ciudadanía", "NIT": "NIT", "CE": "Cédula de extranjería"}
        tipo_legible = tipo_map.get(en_proceso.get("tipo_id", ""), en_proceso.get("tipo_id", ""))
        _ciudades = {
            149: "Cartagena", 8001: "Barranquilla", 11001: "Bogotá",
            5001: "Medellín", 76001: "Cali", 68001: "Bucaramanga",
        }
        ciudad_nombre = _ciudades.get(int(en_proceso.get("municipio_dian") or 149), "Cartagena")
        await update.message.reply_text(
            f"✅ Cliente creado exitosamente:\n\n"
            f"👤 {en_proceso['nombre']}\n"
            f"📄 {tipo_legible}: {en_proceso['identificacion']}\n"
            f"🏷️ {en_proceso.get('tipo_persona', '')}\n"
            f"📧 {en_proceso.get('correo', '') or 'Sin correo'}\n"
            f"📞 {telefono or 'Sin teléfono'}\n"
            f"🏙️ {ciudad_nombre}"
        )
        # Continuar con la venta pendiente si existe
        from ventas_state import ventas_pendientes, ventas_esperando_cliente, _estado_lock
        with _estado_lock:
            datos_espera = ventas_esperando_cliente.pop(chat_id, None)
            ventas_pend  = list(ventas_pendientes.get(chat_id, []))
        if ventas_pend:
            # Importar lazy para no crear ciclo con mensajes.py
            from handlers.callbacks import (
                _enviar_botones_pago as _botones_central,
                _enviar_confirmacion_con_metodo,
            )
            metodo = ventas_pend[0].get("metodo_pago", "").lower()
            if metodo in ("efectivo", "transferencia", "datafono"):
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_pend, metodo)
            else:
                await _botones_central(update.message, chat_id, ventas_pend)
    else:
        await update.message.reply_text("⚠️ No pude guardar el cliente. Intenta de nuevo.")
