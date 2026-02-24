"""
Handlers de comandos de Telegram.
Las operaciones de I/O bloqueantes (Excel, Drive) se ejecutan via asyncio.to_thread
para no bloquear el event loop.
"""

import asyncio
import json
import os
import traceback
from datetime import datetime

import openpyxl
from openpyxl.styles import PatternFill
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from excel import (
    inicializar_excel, obtener_nombre_hoja, obtener_o_crear_hoja,
    detectar_columnas, buscar_ventas, obtener_ventas_recientes,
    buscar_clientes_multiples, cargar_clientes,
)
from memoria import (
    cargar_memoria, obtener_resumen_caja, cargar_gastos_hoy,
    cargar_inventario, verificar_alertas_inventario,
)
from sheets import (
    sheets_leer_ventas_del_dia, sheets_detectar_ediciones_vs_excel,
    sheets_limpiar,
)
from drive import subir_a_drive
from utils import convertir_fraccion_a_decimal, obtener_nombre_hoja
from ventas_state import borrados_pendientes, _estado_lock


# ─────────────────────────────────────────────
# /start y /ayuda
# ─────────────────────────────────────────────

async def comando_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    estado_drive  = "✅ Drive conectado" if config.DRIVE_DISPONIBLE else "⚠️ Drive offline"
    estado_sheets = (
        "✅ Sheets conectado" if config.SHEETS_DISPONIBLE else
        ("⚠️ Sheets no configurado" if not config.SHEETS_ID else "⚠️ Sheets sin conexion")
    )
    await update.message.reply_text(
        "👋 Hola! Soy tu asistente de la ferreteria.\n\n"
        "Puedo ayudarte con cualquier cosa:\n\n"
        "🛍️ Registrar ventas — 'Vendi 1/4 de vinilo t1 azul'\n"
        "🧠 Recordar precios — ya tengo el catalogo completo\n"
        "📊 Reportes — 'Cuanto vendimos esta semana?'\n"
        "📎 Excel personalizado — 'Hazme un Excel con los productos mas vendidos'\n"
        "📈 Graficas — /grafica\n"
        "🔍 Buscar ventas — /buscar [termino]\n"
        "💬 Cualquier pregunta — Lo que necesites\n\n"
        "Comandos:\n"
        "/ventas — Ver ultimas ventas\n"
        "/buscar [termino] — Buscar ventas\n"
        "/borrar [numero] — Borrar una venta\n"
        "/precios — Ver precios guardados\n"
        "/excel — Descargar archivo acumulado\n"
        "/sheets — Ver estado del Sheet del dia\n"
        "/cerrar — Cierre del dia (genera Excel + limpia Sheets)\n"
        "/grafica — Ver graficas de ventas\n"
        "/caja — Estado de caja\n"
        "/gastos — Gastos de hoy\n"
        "/inventario — Ver inventario\n\n"
        f"{estado_drive} | {estado_sheets}"
    )


# ─────────────────────────────────────────────
# /excel
# ─────────────────────────────────────────────

async def comando_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(inicializar_excel)
    await update.message.reply_text("📎 Aqui esta tu archivo de ventas:")
    with open(config.EXCEL_FILE, "rb") as archivo:
        await update.message.reply_document(document=archivo, filename="ventas.xlsx")


# ─────────────────────────────────────────────
# /ventas
# ─────────────────────────────────────────────

async def comando_ventas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Leer del Sheets primero (siempre actualizado)
    if config.SHEETS_ID and config.SHEETS_DISPONIBLE:
        ventas_raw = await asyncio.to_thread(sheets_leer_ventas_del_dia)
        if ventas_raw:
            total_dia = 0
            texto = f"📋 Ventas de hoy ({len(ventas_raw)}):\n\n"
            for v in ventas_raw:
                num      = v.get("num", "?")
                producto = v.get("producto", "?")
                vendedor = v.get("vendedor", "?")
                total_raw = v.get("total")
                try:
                    t = float(total_raw) if total_raw else 0
                    total_dia += t
                    total_fmt = f"${t:,.0f}"
                except (ValueError, TypeError):
                    total_fmt = str(total_raw) if total_raw else "?"
                metodo = v.get("metodo", "")
                texto += f"#{num} — {producto} — {total_fmt} — {vendedor}"
                if metodo:
                    texto += f" ({metodo})"
                texto += "\n"
            texto += f"\n💰 Total del día: ${total_dia:,.0f}"
            texto += "\n\nUsa /borrar [numero] para eliminar una venta."
            await update.message.reply_text(texto)
            return

    # Sin ventas en el día
    await update.message.reply_text("No hay ventas registradas hoy.\nUsa el bot para registrar ventas durante el día.")


# ─────────────────────────────────────────────
# /buscar
# ─────────────────────────────────────────────

async def comando_buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Indica que quieres buscar.\nEjemplos:\n/buscar tornillos\n/buscar Juan\n/buscar 2025-06"
        )
        return
    termino    = " ".join(context.args)
    await update.message.reply_text(f"🔍 Buscando '{termino}'...")
    resultados = await asyncio.to_thread(buscar_ventas, termino)
    if not resultados:
        await update.message.reply_text(f"No encontre ventas que coincidan con '{termino}'.")
        return
    texto = f"🔍 {len(resultados)} resultado(s) para '{termino}':\n\n"
    for r in resultados[:15]:
        num    = r.get("#", "?")
        fecha  = r.get("fecha", "?")
        prod   = r.get("producto", "?")
        total  = r.get("total", "?")
        vend   = r.get("vendedor", "?")
        hoja   = r.get("hoja", "")
        try:
            total_fmt = f"${float(total):,.0f}" if total else "?"
        except Exception:
            total_fmt = str(total)
        texto += f"#{num} [{hoja}] {fecha} — {prod} — {total_fmt} — {vend}\n"
    if len(resultados) > 15:
        texto += f"\n... y {len(resultados) - 15} mas. Usa un termino mas especifico."
    await update.message.reply_text(texto)


# ─────────────────────────────────────────────
# /borrar
# ─────────────────────────────────────────────

async def comando_borrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Indica el numero de venta.\nEjemplo: /borrar 5")
        return
    arg = context.args[0].lstrip("#")
    try:
        numero = int(arg)
    except ValueError:
        await update.message.reply_text("El numero debe ser entero.\nEjemplo: /borrar 5")
        return

    chat_id = update.message.chat_id

    # Buscar en Sheets primero
    venta = None
    if config.SHEETS_ID and config.SHEETS_DISPONIBLE:
        ventas_sheets = await asyncio.to_thread(sheets_leer_ventas_del_dia)
        for v in ventas_sheets:
            try:
                if int(float(str(v.get("num", "")))) == numero:
                    venta = {
                        config.COL_PRODUCTO: v.get("producto", "?"),
                        config.COL_FECHA:    v.get("fecha", "?"),
                        config.COL_TOTAL:    v.get("total", "?"),
                        config.COL_VENDEDOR: v.get("vendedor", "?"),
                    }
                    break
            except (ValueError, TypeError):
                pass

    if not venta:
        from excel import obtener_venta_por_numero
        venta = await asyncio.to_thread(obtener_venta_por_numero, numero)

    if not venta:
        await update.message.reply_text(f"No encontre la venta #{numero}.")
        return

    with _estado_lock:
        borrados_pendientes[chat_id] = numero

    producto = venta.get(config.COL_PRODUCTO, "?")
    fecha    = venta.get(config.COL_FECHA, "?")
    total    = venta.get(config.COL_TOTAL, "?")
    vendedor = venta.get(config.COL_VENDEDOR, "?")
    try:
        total_fmt = f"${float(total):,.0f}"
    except Exception:
        total_fmt = str(total)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Sí, borrar", callback_data=f"borrar_si_{chat_id}"),
        InlineKeyboardButton("❌ Cancelar",   callback_data=f"borrar_no_{chat_id}"),
    ]])
    await update.message.reply_text(
        f"⚠️ ¿Confirmas que quieres borrar esta venta?\n\n"
        f"#{numero} — {producto}\nFecha: {fecha}\nTotal: {total_fmt}\nVendedor: {vendedor}",
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────
# /precios
# ─────────────────────────────────────────────

async def comando_precios(update: Update, context: ContextTypes.
