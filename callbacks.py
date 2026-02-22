"""
Handlers de callbacks de botones inline:
- Confirmacion de metodo de pago
- Confirmacion de borrado
"""

import asyncio

from telegram import Update
from telegram.ext import ContextTypes

import config
from excel import borrar_venta_excel
from sheets import sheets_borrar_fila
from ventas_state import (
    ventas_pendientes, borrados_pendientes,
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

        # Borrar del Sheets y del Excel (ambos en thread para no bloquear)
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
