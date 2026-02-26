"""
Manejo de botones (callbacks) de Telegram y flujos de texto interactivos (como crear clientes).
"""

import logging

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from excel import borrar_venta_excel, guardar_cliente_nuevo
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible
from ventas_state import (
    ventas_pendientes, borrados_pendientes, _estado_lock,
    registrar_ventas_con_metodo, clientes_en_proceso,
    ventas_esperando_cliente, mensajes_standby,
)


# ─────────────────────────────────────────────
# MANEJO DE BOTONES (CALLBACKS)
# ─────────────────────────────────────────────

async def manejar_metodo_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    data     = query.data
    chat_id  = query.message.chat_id
    await query.answer()

    # ── Modificar venta ──
    if data.startswith("pago_modificar_"):
        from ventas_state import esperando_correccion
        with _estado_lock:
            ventas_actuales = list(ventas_pendientes.get(chat_id, []))

        if not ventas_actuales:
            await query.edit_message_text("No hay venta activa para modificar.")
            return

        # Construir resumen de la venta actual
        items = "\n".join(
            "  - " + str(v.get("producto","?")) + " x" + str(v.get("cantidad",1)) + " - $" + f"{v.get('total',0):,}"
            for v in ventas_actuales
        )

        # Marcar que el proximo mensaje es una modificacion (no reescritura completa)
        with _estado_lock:
            esperando_correccion[chat_id] = "modificar"

        texto_modificar = (
            "Venta actual:\n" + items + "\n\n"
            "Dime que quieres cambiar, por ejemplo:\n"
            "  - el precio del sellador era 25000\n"
            "  - quita los aerosoles\n"
            "  - los tornillos eran 3 docenas no 5\n"
            "  - agrega 1 brocha 5000"
        )
        await query.edit_message_text(texto_modificar)
        return

    # ── Cancelar venta ──
    if data.startswith("pago_cancelar_"):
        from ventas_state import esperando_correccion
        with _estado_lock:
            ventas_canceladas = ventas_pendientes.pop(chat_id, [])
            standby_pendiente = mensajes_standby.pop(chat_id, [])

        # Marcar que el proximo mensaje es una correccion/reescritura
        with _estado_lock:
            esperando_correccion[chat_id] = True

        # Construir resumen de lo que se cancela
        if ventas_canceladas:
            items = "\n".join(f"  • {v.get('producto','?')} — ${v.get('total',0):,}" for v in ventas_canceladas)
            texto_cancelado = f"Venta cancelada:\n{items}\n\n"
        else:
            texto_cancelado = ""

        await query.edit_message_text(
            f"✏️ {texto_cancelado}"
            "Reescribe la venta como quieras y la registro de nuevo."
        )

        # Si habia standby, procesarlo ahora
        if standby_pendiente:
            for msg_text in standby_pendiente:
                from ai import procesar_con_claude, procesar_acciones
                from ventas_state import agregar_al_historial, get_historial
                vendedor = update.effective_user.first_name
                historial = get_historial(chat_id)
                agregar_al_historial(chat_id, "user", f"{vendedor}: {msg_text}")
                respuesta_raw = await procesar_con_claude(f"{vendedor}: {msg_text}", vendedor, historial)
                texto_resp, acciones2, _ = procesar_acciones(respuesta_raw, vendedor, chat_id)
                agregar_al_historial(chat_id, "assistant", texto_resp)
                if texto_resp:
                    await context.bot.send_message(chat_id=chat_id, text=f"📋 {msg_text}\n{texto_resp}")
                if "PEDIR_METODO_PAGO" in acciones2:
                    with _estado_lock:
                        ventas2 = list(ventas_pendientes.get(chat_id, []))
                    if ventas2:
                        await _enviar_botones_pago_por_chat(context.bot, chat_id, ventas2)
        return

    # ── Confirmar venta con metodo ya conocido ──
    if data.startswith("pago_confirmar_"):
        # formato: pago_confirmar_{metodo}_{chat_id}
        # chat_id siempre es el último segmento; metodo puede contener "_"
        sin_prefijo = data[len("pago_confirmar_"):]        # "transferencia_12345"
        ultimo_guion = sin_prefijo.rfind("_")
        metodo  = sin_prefijo[:ultimo_guion]               # "transferencia"
        chat_id = int(sin_prefijo[ultimo_guion + 1:])      # 12345
        vendedor = update.effective_user.first_name

        with _estado_lock:
            ventas = ventas_pendientes.get(chat_id)

        if not ventas:
            await query.edit_message_text("Esta sesion ya fue procesada.")
            return

        # Responder inmediatamente para evitar que Telegram expire el query
        await query.edit_message_text("⏳ Registrando venta...")

        conf  = await asyncio.to_thread(registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id)
        emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
        await query.edit_message_text(f"✅ Venta confirmada — {emoji} {metodo.capitalize()}\n\n" + "\n".join(conf))

        with _estado_lock:
            pendientes = mensajes_standby.pop(chat_id, [])
        for msg_text in pendientes:
            from ai import procesar_con_claude, procesar_acciones
            from ventas_state import agregar_al_historial, get_historial
            historial = get_historial(chat_id)
            agregar_al_historial(chat_id, "user", f"{vendedor}: {msg_text}")
            respuesta_raw = await procesar_con_claude(f"{vendedor}: {msg_text}", vendedor, historial)
            texto_resp, acciones2, _ = procesar_acciones(respuesta_raw, vendedor, chat_id)
            agregar_al_historial(chat_id, "assistant", texto_resp)
            if texto_resp:
                await context.bot.send_message(chat_id=chat_id, text=texto_resp)
            if "PEDIR_METODO_PAGO" in acciones2:
                with _estado_lock:
                    ventas2 = ventas_pendientes.get(chat_id, [])
                await _enviar_botones_pago(query.message, chat_id, ventas2)
        return

    # ── Métodos de pago ──
    if data.startswith("pago_"):
        partes  = data.split("_")
        metodo  = partes[1]
        chat_id = int(partes[2])
        vendedor = update.effective_user.first_name

        with _estado_lock:
            ventas = ventas_pendientes.get(chat_id)

        if not ventas:
            await query.edit_message_text("Esta sesion de pago expiro o ya fue procesada.")
            return

        # Responder inmediatamente para evitar que Telegram expire el query
        await query.edit_message_text("⏳ Registrando venta...")

        conf  = await asyncio.to_thread(registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id)
        emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
        await query.edit_message_text(f"✅ Venta registrada — {emoji} {metodo.capitalize()}\n\n" + "\n".join(conf))

        # Procesar mensajes que quedaron en standby
        with _estado_lock:
            pendientes = mensajes_standby.pop(chat_id, [])
        if pendientes:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔄 Procesando venta en espera..."
            )
            for msg_text in pendientes:
                from ai import procesar_con_claude, procesar_acciones
                from ventas_state import agregar_al_historial, get_historial
                historial = get_historial(chat_id)
                agregar_al_historial(chat_id, "user", f"{vendedor}: {msg_text}")
                respuesta_raw = await procesar_con_claude(f"{vendedor}: {msg_text}", vendedor, historial)
                texto_resp, acciones2, _ = procesar_acciones(respuesta_raw, vendedor, chat_id)
                agregar_al_historial(chat_id, "assistant", texto_resp)
                if texto_resp and "PAGO_PENDIENTE_AVISO" not in acciones2:
                    await context.bot.send_message(chat_id=chat_id, text=texto_resp)
                # Mostrar botones si hay ventas pendientes, EXCEPTO si Claude está
                # haciendo una pregunta (texto termina en ? o contiene "¿")
                es_pregunta = texto_resp and ("?" in texto_resp or "¿" in texto_resp)
                if "PEDIR_METODO_PAGO" in acciones2 and not es_pregunta:
                    from handlers.mensajes import _enviar_botones_pago
                    with _estado_lock:
                        ventas2 = ventas_pendientes.get(chat_id, [])
                    await _enviar_botones_pago(query.message, chat_id, ventas2)

    # ── Confirmación de borrado ──
    elif data.startswith("borrar_"):
        partes  = data.split("_")
        confirm = partes[1]
        chat_id = int(partes[2])

        with _estado_lock:
            numero = borrados_pendientes.pop(chat_id, None)

        if confirm == "si" and numero:
            exito, msg = await asyncio.to_thread(borrar_venta_excel, numero)
            await query.edit_message_text(msg)
        else:
            await query.edit_message_text("Borrado cancelado.")

    # ── Gráficas ──
    elif data.startswith("grafica_"):
        from handlers.comandos import manejar_callback_grafica
        await manejar_callback_grafica(update, context)


# ─────────────────────────────────────────────
# ENVÍO DE BOTONES DE PAGO
# ─────────────────────────────────────────────

async def _enviar_confirmacion_con_metodo(message, chat_id: int, ventas: list, metodo: str):
    """
    Cuando el usuario ya dijo el metodo de pago, muestra la venta confirmada
    con botones de Confirmar o Modificar (sin preguntar el metodo de nuevo).
    """
    emoji_metodo = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
    lineas = []
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        producto     = v.get("producto", "")
        total        = v.get("total", 0)
        try:
            total = float(str(total).replace("$","").replace(",",""))
        except Exception:
            total = 0
        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        lineas.append(f"• {cantidad_leg} {producto} ${total:,.0f}")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar",        callback_data=f"pago_confirmar_{metodo}_{chat_id}"),
            InlineKeyboardButton("✏️ Modificar venta",  callback_data=f"pago_modificar_{chat_id}"),
        ]
    ])
    await message.reply_text(
        f"✓ Venta registrada — {emoji_metodo} {metodo.capitalize()}\n\n" + "\n".join(lineas),
        reply_markup=keyboard,
    )


async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Muestra botones de metodo de pago con opcion de modificar/cancelar."""
    lineas = []
    logging.getLogger("ferrebot.callbacks").debug(f"[BOTONES] ventas recibidas: {ventas}")
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        producto     = v.get("producto", "")

        def _parsear_precio(clave):
            val = v.get(clave, 0)
            if isinstance(val, str):
                val = val.replace("$", "").strip()
                # Formato colombiano: punto como sep. de miles → "1.500" → 1500
                # Formato decimal real: "1500.50" → 1500.5
                if "," in val and "." in val:
                    if val.rfind(".") > val.rfind(","):
                        val = val.replace(",", "")           # "1,500.50" → "1500.50"
                    else:
                        val = val.replace(".", "").replace(",", ".")  # "1.500,50" → "1500.50"
                elif "." in val:
                    partes = val.split(".")
                    if len(partes) == 2 and len(partes[1]) == 3:
                        val = val.replace(".", "")           # "1.500" → "1500" (miles colombiano)
                    # else: decimal real "4000.5", dejar como está
                elif "," in val:
                    val = val.replace(",", "")               # "1,500" → "1500"
            try:
                return float(val)
            except Exception:
                return 0.0

        total      = _parsear_precio("total")
        p_unitario = _parsear_precio("precio_unitario")
        valor_final = total if total > 0 else round(p_unitario * cantidad_dec)

        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        lineas.append(f"• {cantidad_leg} {producto} ${valor_final:,.0f}")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Efectivo",      callback_data=f"pago_efectivo_{chat_id}"),
            InlineKeyboardButton("📱 Transf.",        callback_data=f"pago_transferencia_{chat_id}"),
            InlineKeyboardButton("💳 Datáfono",       callback_data=f"pago_datafono_{chat_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Modificar venta", callback_data=f"pago_modificar_{chat_id}"),
        ]
    ])
    await message.reply_text(
        "¿Cómo fue el pago?\n\n" + "\n".join(lineas),
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────
# FLUJO PASO A PASO: CLIENTE NUEVO
# ─────────────────────────────────────────────

async def manejar_texto_cliente(chat_id: int, texto: str, message, vendedor: str) -> bool:
    """
    Atrapa mensajes de texto normales si el usuario esta en medio de la creacion
    de un cliente nuevo. Retorna True si atrapo el mensaje.
    """
    with _estado_lock:
        if chat_id not in clientes_en_proceso:
            return False
        cliente = clientes_en_proceso[chat_id]

    texto = texto.strip()
    paso  = cliente["paso"]

    if paso == "nombre":
        cliente["nombre"] = texto
        cliente["paso"] = "tipo_id"
        await message.reply_text("👤 ¿Qué tipo de identificación tiene? (Ej: Cédula o NIT)")
        return True

    elif paso == "tipo_id":
        cliente["tipo_id"] = texto
        cliente["paso"] = "identificacion"
        await message.reply_text("👤 ¿Cuál es el número de identificación?")
        return True

    elif paso == "identificacion":
        cliente["identificacion"] = texto
        cliente["paso"] = "tipo_persona"
        await message.reply_text("👤 ¿Es persona Natural o Jurídica?")
        return True

    elif paso == "tipo_persona":
        cliente["tipo_persona"] = texto
        cliente["paso"] = "correo"
        await message.reply_text("👤 ¿Cuál es el correo electrónico? (o escribe 'no' si no tiene)")
        return True

    elif paso == "correo":
        cliente["correo"] = texto if texto.lower() != "no" else ""
        cliente["paso"] = "telefono"
        await message.reply_text("👤 ¿Cuál es el teléfono? (o escribe 'no' si no tiene)")
        return True

    elif paso == "telefono":
        cliente["telefono"] = texto if texto.lower() != "no" else ""
        nombre = cliente["nombre"]

        await message.reply_text("⏳ Guardando cliente en la base de datos...")

        ok = await asyncio.to_thread(
            guardar_cliente_nuevo,
            nombre, cliente["tipo_id"], cliente["identificacion"],
            cliente["tipo_persona"], cliente["correo"], cliente["telefono"]
        )

        if ok:
            await message.reply_text(f"✅ Cliente {nombre.upper()} guardado con éxito.")
        else:
            await message.reply_text(f"⚠️ Hubo un error guardando a {nombre}.")

        with _estado_lock:
            pendientes = ventas_esperando_cliente.pop(chat_id, None)
            del clientes_en_proceso[chat_id]

        if pendientes and pendientes.get("ventas"):
            ventas = pendientes["ventas"]
            for v in ventas:
                v["cliente"] = nombre
            with _estado_lock:
                ventas_pendientes[chat_id] = ventas
            await _enviar_botones_pago(message, chat_id, ventas)

        return True

    return False


# ─────────────────────────────────────────────
# HELPER: botones de pago sin objeto message (via bot directo)
# Reemplaza el patrón fake-object que generaba TypeError en async
# ─────────────────────────────────────────────

async def _enviar_botones_pago_por_chat(bot, chat_id: int, ventas: list):
    """
    Versión de _enviar_botones_pago que usa bot.send_message directamente.
    Úsala cuando no tienes un objeto message disponible (ej: desde callbacks).
    """
    from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible
    lineas = []
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        producto = v.get("producto", "")
        total = v.get("total", 0)
        try:
            total = float(str(total).replace("$", "").replace(",", ""))
        except Exception:
            total = 0
        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        lineas.append(f"• {cantidad_leg} {producto} ${total:,.0f}")

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Efectivo",       callback_data=f"pago_efectivo_{chat_id}"),
            InlineKeyboardButton("📱 Transf.",         callback_data=f"pago_transferencia_{chat_id}"),
            InlineKeyboardButton("💳 Datáfono",        callback_data=f"pago_datafono_{chat_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Modificar venta", callback_data=f"pago_modificar_{chat_id}"),
        ]
    ])
    await bot.send_message(
        chat_id=chat_id,
        text="¿Cómo fue el pago?\n\n" + "\n".join(lineas),
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────
# HANDLER: botones de creación de cliente (cli_tipoid_ y cli_persona_)
# Estos callbacks son emitidos por _enviar_pregunta_cliente en mensajes.py
# ─────────────────────────────────────────────

async def manejar_callback_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja los botones inline del flujo de creación de cliente:
      - cli_tipoid_CC_{chat_id}     → tipo de identificación CC / NIT / CE
      - cli_persona_Natural_{chat_id}  → tipo de persona Natural / Juridica
    """
    query   = update.callback_query
    data    = query.data
    chat_id = query.message.chat_id
    await query.answer()

    # ── Tipo de identificación ──
    if data.startswith("cli_tipoid_"):
        # formato: cli_tipoid_{TIPO}_{chat_id}
        sin_prefijo = data[len("cli_tipoid_"):]
        ultimo      = sin_prefijo.rfind("_")
        tipo_id     = sin_prefijo[:ultimo]   # "CC", "NIT", "CE"

        with _estado_lock:
            datos = clientes_en_proceso.get(chat_id)

        if not datos:
            await query.edit_message_text("El proceso de creación de cliente expiró. Inicia de nuevo.")
            return

        tipo_map_legible = {"CC": "Cédula de ciudadanía", "NIT": "NIT", "CE": "Cédula de extranjería"}
        datos["tipo_id"] = tipo_id
        datos["paso"]    = "identificacion"
        with _estado_lock:
            clientes_en_proceso[chat_id] = datos

        await query.edit_message_text(
            f"Tipo de documento: {tipo_map_legible.get(tipo_id, tipo_id)}\n"
            f"¿Cuál es el número de {tipo_map_legible.get(tipo_id, 'identificación')}?"
        )
        return

    # ── Tipo de persona ──
    if data.startswith("cli_persona_"):
        # formato: cli_persona_{TIPO}_{chat_id}
        sin_prefijo  = data[len("cli_persona_"):]
        ultimo       = sin_prefijo.rfind("_")
        tipo_persona = sin_prefijo[:ultimo]   # "Natural", "Juridica"

        with _estado_lock:
            datos = clientes_en_proceso.get(chat_id)

        if not datos:
            await query.edit_message_text("El proceso de creación de cliente expiró. Inicia de nuevo.")
            return

        datos["tipo_persona"] = tipo_persona
        datos["paso"]         = "correo"
        with _estado_lock:
            clientes_en_proceso[chat_id] = datos

        await query.edit_message_text(
            f"Tipo de persona: {tipo_persona}\n"
            f"¿Cuál es el correo electrónico de {datos.get('nombre', 'el cliente')}? "
            f"(escribe 'no tiene' si no aplica)"
        )
        return
