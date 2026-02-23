"""
Handlers de callbacks de botones inline:
- Confirmacion de metodo de pago
- Confirmacion de borrado
- Flujo de creacion de cliente (tipo de documento, tipo de persona)
"""

import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from excel import borrar_venta_excel, guardar_cliente_nuevo
from sheets import sheets_borrar_fila
from ventas_state import (
    ventas_pendientes, borrados_pendientes, clientes_en_proceso,
    ventas_esperando_cliente, registrar_ventas_con_metodo, _estado_lock,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible


async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Muestra botones de metodo de pago con resumen de ventas."""
    lineas = []
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        precio       = float(v.get("precio_unitario", 0))
        total        = precio * cantidad_dec if cantidad_dec >= 1 else precio
        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        lineas.append(f"• {v.get('producto')} x{cantidad_leg} = ${total:,.0f}")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 Efectivo",      callback_data=f"pago_efectivo_{chat_id}"),
        InlineKeyboardButton("📱 Transferencia", callback_data=f"pago_transferencia_{chat_id}"),
        InlineKeyboardButton("💳 Datafono",      callback_data=f"pago_datafono_{chat_id}"),
    ]])
    await message.reply_text(
        "¿Cómo fue el pago?\n\n" + "\n".join(lineas),
        reply_markup=keyboard,
    )


async def manejar_metodo_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja botones de metodo de pago Y confirmacion de borrado Y flujo de cliente."""
    query    = update.callback_query
    await query.answer()
    data     = query.data
    vendedor = query.from_user.first_name or "Desconocido"

    # ── Confirmacion de borrado ──
    if data.startswith("borrar_si_") or data.startswith("borrar_no_"):
        partes  = data.split("_")
        accion  = partes[1]
        chat_id = int(partes[2])

        with _estado_lock:
            numero_venta = borrados_pendientes.pop(chat_id, None)

        if accion == "no" or numero_venta is None:
            await query.edit_message_text("❌ Borrado cancelado.")
            return

        sheets_ok = False
        if config.SHEETS_ID and config.SHEETS_DISPONIBLE:
            sheets_ok = await asyncio.to_thread(sheets_borrar_fila, numero_venta)

        exito, mensaje = await asyncio.to_thread(borrar_venta_excel, numero_venta)

        if sheets_ok and not exito:
            await query.edit_message_text(f"✅ Venta #{numero_venta} borrada del Sheets.")
        else:
            await query.edit_message_text(mensaje)
        return

    # ── Metodo de pago ──
    if data.startswith("pago_"):
        partes = data.split("_")
        if len(partes) < 3:
            return
        metodo  = partes[1]
        chat_id = int(partes[2])

        with _estado_lock:
            ventas = ventas_pendientes.pop(chat_id, [])

        if not ventas:
            await query.edit_message_text("Ya no hay ventas pendientes.")
            return

        confirmaciones = await asyncio.to_thread(
            registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id
        )
        emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
        texto = f"✅ Venta registrada — {emoji} {metodo.capitalize()}\n\n" + "\n".join(confirmaciones)
        await query.edit_message_text(texto)
        return

    # ── Tipo de documento del cliente ──
    if data.startswith("cli_tipoid_"):
        partes  = data.split("_")
        tipo_id = partes[2]
        chat_id = int(partes[3])

        tipo_map = {
            "CC":  "Cédula de ciudadanía",
            "NIT": "NIT",
            "CE":  "Cédula de extranjería",
        }
        tipo_completo = tipo_map.get(tipo_id, tipo_id)

        with _estado_lock:
            datos = clientes_en_proceso.get(chat_id)
        if not datos:
            await query.edit_message_text("⚠️ La sesion de creacion de cliente expiro. Empieza de nuevo.")
            return

        datos["tipo_id"] = tipo_completo
        datos["paso"]    = "identificacion"
        with _estado_lock:
            clientes_en_proceso[chat_id] = datos

        await query.edit_message_text(f"✅ Tipo de documento: {tipo_completo}")
        await query.message.reply_text(f"¿Cuál es el número de {tipo_completo}?")
        return

    # ── Tipo de persona del cliente ──
    if data.startswith("cli_persona_"):
        partes       = data.split("_")
        tipo_persona = partes[2]
        chat_id      = int(partes[3])

        with _estado_lock:
            datos = clientes_en_proceso.get(chat_id)
        if not datos:
            await query.edit_message_text("⚠️ La sesion de creacion de cliente expiro. Empieza de nuevo.")
            return

        datos["tipo_persona"] = tipo_persona
        datos["paso"]         = "correo"
        with _estado_lock:
            clientes_en_proceso[chat_id] = datos

        label = "Persona Natural" if tipo_persona == "Natural" else "Persona Jurídica"
        await query.edit_message_text(f"✅ Tipo de persona: {label}")
        await query.message.reply_text(
            "¿Cuál es el correo electrónico? (escribe 'no tiene' si no aplica)"
        )
        return


async def _finalizar_creacion_cliente(chat_id: int, datos: dict, message) -> str:
    """
    Guarda el cliente en el Excel y, si habia ventas esperando,
    las registra automaticamente con el cliente recien creado.
    Retorna el texto de confirmacion completo.
    """
    nombre       = datos["nombre"]
    tipo_id      = datos.get("tipo_id", "Cédula de ciudadanía")
    identificacion = datos.get("identificacion", "")
    tipo_persona = datos.get("tipo_persona", "Natural")
    correo       = datos.get("correo", "")

    ok = await asyncio.to_thread(
        guardar_cliente_nuevo,
        nombre, tipo_id, identificacion, tipo_persona, correo,
    )

    tipo_map = {
        "Cédula de ciudadanía": "CC",
        "NIT": "NIT",
        "Cédula de extranjería": "CE",
    }
    tipo_legible = tipo_map.get(tipo_id, tipo_id)

    if not ok:
        return "⚠️ No pude guardar el cliente. Intenta de nuevo."

    texto = (
        f"✅ Cliente creado:\n"
        f"👤 {nombre}\n"
        f"📄 {tipo_legible}: {identificacion}\n"
        f"🏷️ {tipo_persona}\n"
        f"📧 {correo or 'Sin correo'}"
    )

    # ── Verificar si habia ventas esperando este cliente ──
    with _estado_lock:
        pendiente = ventas_esperando_cliente.pop(chat_id, None)

    if pendiente:
        ventas  = pendiente.get("ventas", [])
        metodo  = pendiente.get("metodo")
        vendedor = pendiente.get("vendedor", "Desconocido")

        # Inyectar el nombre del cliente recien creado en cada venta
        for v in ventas:
            v["cliente"] = nombre

        if metodo:
            # Ya teniamos el metodo de pago — registrar directo
            confirmaciones = await asyncio.to_thread(
                registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id
            )
            emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
            texto += f"\n\n✅ Venta registrada — {emoji} {metodo.capitalize()}\n" + "\n".join(confirmaciones)
        else:
            # No teniamos metodo — guardar en pendientes y pedir con botones
            with _estado_lock:
                ventas_pendientes[chat_id] = ventas
            await _enviar_botones_pago(message, chat_id, ventas)

    return texto


async def manejar_texto_cliente(chat_id: int, mensaje: str, message, vendedor: str) -> bool:
    """
    Maneja los pasos de texto del flujo de creacion de cliente
    (nombre, identificacion, correo).
    Retorna True si el mensaje fue consumido por el flujo, False si no.
    """
    with _estado_lock:
        datos = clientes_en_proceso.get(chat_id)

    if not datos:
        return False

    paso        = datos.get("paso")
    texto_lower = mensaje.strip().lower()

    if paso == "nombre":
        datos["nombre"] = mensaje.strip().upper()
        datos["paso"]   = "tipo_id"
        with _estado_lock:
            clientes_en_proceso[chat_id] = datos

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🪪 CC",  callback_data=f"cli_tipoid_CC_{chat_id}"),
            InlineKeyboardButton("🏢 NIT", callback_data=f"cli_tipoid_NIT_{chat_id}"),
            InlineKeyboardButton("🌍 CE",  callback_data=f"cli_tipoid_CE_{chat_id}"),
        ]])
        await message.reply_text(
            f"¿Qué tipo de documento tiene {datos['nombre']}?",
            reply_markup=keyboard,
        )
        return True

    elif paso == "identificacion":
        datos["identificacion"] = mensaje.strip()
        datos["paso"]           = "tipo_persona"
        with _estado_lock:
            clientes_en_proceso[chat_id] = datos

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👤 Persona Natural",  callback_data=f"cli_persona_Natural_{chat_id}"),
            InlineKeyboardButton("🏢 Persona Jurídica", callback_data=f"cli_persona_Juridica_{chat_id}"),
        ]])
        await message.reply_text("¿Es Persona Natural o Persona Jurídica?", reply_markup=keyboard)
        return True

    elif paso == "correo":
        correo = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
        datos["correo"] = correo

        with _estado_lock:
            clientes_en_proceso.pop(chat_id, None)

        texto = await _finalizar_creacion_cliente(chat_id, datos, message)
        await message.reply_text(texto)
        return True

    return False
