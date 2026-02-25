"""
Manejo de botones (callbacks) de Telegram y flujos de texto interactivos (como crear clientes).
"""

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

    # ── Cancelar / Modificar venta ──
    if data.startswith("pago_cancelar_"):
        with _estado_lock:
            ventas_pendientes.pop(chat_id, None)
            mensajes_standby.pop(chat_id, None)

        await query.edit_message_text(
            "🛑 Venta en pausa.\n\n"
            "El chat está desbloqueado. Dime qué quieres corregir:\n"
            "Ej: 'Era sin la brocha', 'Agrega un martillo a 15000', o 'Cancela todo'."
        )
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

        conf  = await asyncio.to_thread(registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id)
        emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
        await query.edit_message_text(f"✅ Venta registrada — {emoji} {metodo.capitalize()}\n\n" + "\n".join(conf))

        # Procesar mensajes que quedaron en standby
        with _estado_lock:
            pendientes = mensajes_standby.pop(chat_id, [])
        if pendientes:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔄 Procesando {len(pendientes)} mensaje(s) que estaban en espera..."
            )
            for msg_text in pendientes:
                from handlers.mensajes import _procesar_mensaje
                await _procesar_mensaje(update, context, msg_text, chat_id, update.effective_user.first_name)

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

async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Muestra botones de metodo de pago con opcion de modificar/cancelar."""
    lineas = []
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        producto     = v.get("producto", "")

        def _parsear_precio(clave):
            val = v.get(clave, 0)
            if isinstance(val, str):
                val = val.replace("$", "").replace(",", "").replace(".", "").strip()
            try:
                return float(val)
            except:
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
            InlineKeyboardButton("✏️ Modificar / Cancelar Venta", callback_data=f"pago_cancelar_{chat_id}"),
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
