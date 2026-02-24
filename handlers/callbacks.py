"""
Manejo de botones (callbacks) de Telegram.
"""

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from excel import borrar_venta_excel
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible
from ventas_state import (
    ventas_pendientes, borrados_pendientes, _estado_lock,
    registrar_ventas_con_metodo, clientes_en_proceso,
    ventas_esperando_cliente,
)

async def manejar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    # ── MÉTODOS DE PAGO ──
    if data.startswith("pago_"):
        partes  = data.split("_")
        metodo  = partes[1]
        chat_id = int(partes[2])
        vendedor = update.effective_user.first_name

        with _estado_lock:
            ventas = ventas_pendientes.get(chat_id)

        if not ventas:
            await query.edit_message_text("❌ Esta sesion de pago expiro o ya fue procesada.")
            return

        # Procesar la venta
        conf = await asyncio.to_thread(registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id)
        emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
        
        await query.edit_message_text(f"✅ Venta registrada — {emoji} {metodo.capitalize()}\n\n" + "\n".join(conf))

    # ── CONFIRMACIÓN DE BORRADO ──
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
            await query.edit_message_text("❌ Borrado cancelado.")

    # ── GRÁFICAS ──
    elif data.startswith("grafica_"):
        from handlers.comandos import manejar_callback_grafica
        await manejar_callback_grafica(update, context)

async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """
    Muestra los botones de pago con el resumen corregido:
    ORDEN: Cantidad + Producto + Valor Total.
    LÓGICA: Si es fracción (<1), el precio es el total.
    """
    lineas = []
    for v in ventas:
        producto     = v.get("producto", "")
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        precio       = float(v.get("precio_unitario", 0))
        
        # Lógica de precios: Fracción = Total | Entero = Unitario
        if cantidad_dec < 1 or (producto and "thinner" in producto.lower()):
            total = round(precio)
        else:
            total = round(precio * cantidad_dec)
            
        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        # ORDEN: Cantidad + Producto + Valor
        lineas.append(f"• {cantidad_leg} {producto} ${total:,.0f}")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 Efectivo",      callback_data=f"pago_efectivo_{chat_id}"),
        InlineKeyboardButton("📱 Transferencia", callback_data=f"pago_transferencia_{chat_id}"),
        InlineKeyboardButton("💳 Datafono",      callback_data=f"pago_datafono_{chat_id}"),
    ]])
    
    await message.reply_text(
        "¿Cómo fue el pago?\n\n" + "\n".join(lineas),
        reply_markup=keyboard,
    )
