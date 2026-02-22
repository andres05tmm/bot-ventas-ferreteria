"""
Handlers de callbacks de botones inline:
- Confirmacion de metodo de pago
- Confirmacion de borrado
- Flujo de creacion de cliente (tipo de documento, tipo de persona)
"""

import asyncio

from telegram import Update
from telegram.ext import ContextTypes

import config
from excel import borrar_venta_excel
from sheets import sheets_borrar_fila
from ventas_state import (
    ventas_pendientes, borrados_pendientes, clientes_en_proceso,
    registrar_ventas_con_metodo, _estado_lock,
)


async def manejar_metodo_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja botones de metodo de pago Y confirmacion de borrado."""
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
        # formato: cli_tipoid_CC_<chat_id>
        partes  = data.split("_")
        tipo_id = partes[2]   # CC, NIT o CE
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

        # Preguntar el numero de identificacion
        await query.message.reply_text(f"¿Cuál es el número de {tipo_completo}?")
        return

    # ── Tipo de persona del cliente ──
    if data.startswith("cli_persona_"):
        # formato: cli_persona_Natural_<chat_id> o cli_persona_Juridica_<chat_id>
        partes       = data.split("_")
        tipo_persona = partes[2]   # Natural o Juridica
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

        # Preguntar correo
        await query.message.reply_text(
            "¿Cuál es el correo electrónico? (escribe 'no tiene' si no aplica)"
        )
