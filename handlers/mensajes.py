"""
Handlers de mensajes: texto, audio (voz) y documentos Excel.
"""

import asyncio
import os
import tempfile
import traceback

import openpyxl
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from ai import procesar_con_claude, procesar_acciones, editar_excel_con_claude
from ventas_state import (
    agregar_al_historial, get_historial,
    ventas_pendientes, _estado_lock,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible


async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Muestra los botones de metodo de pago con un resumen de las ventas."""
    lineas = []
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        precio       = float(v.get("precio_unitario", 0))
        total_mostrar = precio * cantidad_dec if cantidad_dec >= 1 else precio
        cantidad_legible = (
            decimal_a_fraccion_legible(cantidad_dec)
            if isinstance(cantidad_dec, float) else v.get("cantidad", 1)
        )
        lineas.append(f"• {v.get('producto')} x{cantidad_legible} = ${total_mostrar:,.0f}")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 Efectivo",      callback_data=f"pago_efectivo_{chat_id}"),
        InlineKeyboardButton("📱 Transferencia", callback_data=f"pago_transferencia_{chat_id}"),
        InlineKeyboardButton("💳 Datafono",      callback_data=f"pago_datafono_{chat_id}"),
    ]])
    await message.reply_text(f"¿Cómo fue el pago?\n\n" + "\n".join(lineas), reply_markup=keyboard)


async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje  = update.message.text
    chat_id  = update.message.chat_id
    vendedor = update.message.from_user.first_name or "Desconocido"

    if mensaje.startswith("/"):
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Si el usuario tiene un Excel cargado, procesarlo
    excel_temp   = context.user_data.get("excel_temp")
    excel_nombre = context.user_data.get("excel_nombre")
    if excel_temp and os.path.exists(excel_temp):
        try:
            await update.message.reply_text("⚙️ Procesando tu Excel...")
            codigo = await editar_excel_con_claude(mensaje, excel_temp, excel_nombre, vendedor, chat_id)

            if codigo.strip() == "IMPOSIBLE":
                await update.message.reply_text("No pude hacer eso con el Excel. Intenta con otra instruccion.")
                return

            # Sandbox restringido: solo expone openpyxl y json
            namespace_seguro = {
                "__builtins__": {
                    "range": range, "len": len, "enumerate": enumerate,
                    "int": int, "float": float, "str": str, "bool": bool,
                    "list": list, "dict": dict, "tuple": tuple, "set": set,
                    "min": min, "max": max, "sum": sum, "abs": abs,
                    "round": round, "sorted": sorted, "zip": zip,
                    "isinstance": isinstance, "print": print,
                    "Exception": Exception, "ValueError": ValueError,
                    "TypeError": TypeError, "KeyError": KeyError,
                },
                "openpyxl": openpyxl,
                "json": __import__("json"),
            }
            await asyncio.to_thread(exec, compile(codigo, "<string>", "exec"), namespace_seguro)

            await update.message.reply_text("✅ Excel modificado. Aqui esta el resultado:")
            with open(excel_temp, "rb") as f:
                await update.message.reply_document(document=f, filename=f"modificado_{excel_nombre}")

            context.user_data.pop("excel_temp", None)
            context.user_data.pop("excel_nombre", None)
            if os.path.exists(excel_temp):
                os.remove(excel_temp)
            return
        except Exception:
            print(f"Error editando Excel: {traceback.format_exc()}")
            await update.message.reply_text("Tuve un problema editando el Excel. Intenta con una instruccion diferente.")
            return

    try:
        historial    = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {mensaje}")
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {mensaje}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = procesar_acciones(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        if texto_respuesta:
            await update.message.reply_text(texto_respuesta)

        pedir_metodo = "PEDIR_METODO_PAGO" in acciones
        for accion in acciones:
            if accion != "PEDIR_METODO_PAGO":
                await update.message.reply_text(accion)

        if pedir_metodo:
            with _estado_lock:
                ventas = ventas_pendientes.get(chat_id, [])
            await _enviar_botones_pago(update.message, chat_id, ventas)

        for archivo in archivos_excel:
            if os.path.exists(archivo):
                await update.message.reply_text("📊 Aqui esta tu reporte:")
                with open(archivo, "rb") as f:
                    await update.message.reply_document(document=f, filename=archivo)
                os.remove(archivo)

    except Exception:
        print(f"Error completo: {traceback.format_exc()}")
        await update.message.reply_text("Tuve un problema. Intenta de nuevo.")


async def manejar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vendedor = update.message.from_user.first_name or "Desconocido"
    chat_id  = update.message.chat_id
    await update.message.reply_text("🎤 Escuchando...")
    try:
        archivo_voz = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await archivo_voz.download_to_drive(tmp.name)
            ruta_audio = tmp.name

        def _transcribir():
            with open(ruta_audio, "rb") as audio_file:
                return config.openai_client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, language="es"
                )

        transcripcion = await asyncio.to_thread(_transcribir)
        os.unlink(ruta_audio)
        texto = transcripcion.text
        await update.message.reply_text(f"📝 Escuche: {texto}")
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        historial     = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {texto}")
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {texto}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = procesar_acciones(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        if texto_respuesta:
            await update.message.reply_text(texto_respuesta)

        pedir_metodo = "PEDIR_METODO_PAGO" in acciones
        for accion in acciones:
            if accion != "PEDIR_METODO_PAGO":
                await update.message.reply_text(accion)

        if pedir_metodo:
            with _estado_lock:
                ventas = ventas_pendientes.get(chat_id, [])
            await _enviar_botones_pago(update.message, chat_id, ventas)

        for archivo in archivos_excel:
            if os.path.exists(archivo):
                await update.message.reply_text("📊 Aqui esta tu reporte:")
                with open(archivo, "rb") as f:
                    await update.message.reply_document(document=f, filename=archivo)
                os.remove(archivo)

    except Exception:
        print(f"Error audio: {traceback.format_exc()}")
        await update.message.reply_text("Problema con el audio. Intenta de nuevo.")


async def manejar_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja archivos Excel que le mandan al bot."""
    doc = update.message.document
    if not doc:
        return

    nombre    = doc.file_name or "archivo"
    extension = nombre.split(".")[-1].lower() if "." in nombre else ""

    if extension not in ["xlsx", "xls"]:
        await update.message.reply_text(
            f"Recibí '{nombre}'. Solo puedo procesar archivos Excel (.xlsx). ¿Necesitas algo más?"
        )
        return

    await update.message.reply_text(f"📂 Recibí tu archivo '{nombre}'. Leyendo contenido...")
    chat_id = update.message.chat_id

    try:
        archivo   = await doc.get_file()
        ruta_temp = f"temp_{chat_id}_{nombre}"
        await archivo.download_to_drive(ruta_temp)

        def _leer_excel():
            wb = openpyxl.load_workbook(ruta_temp)
            resumen_hojas = []
            for hoja_nombre in wb.sheetnames:
                ws  = wb[hoja_nombre]
                enc = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1) if ws.cell(row=1, column=c).value]
                resumen_hojas.append(f"Hoja '{hoja_nombre}': {ws.max_row - 1} filas, columnas: {', '.join(str(e) for e in enc)}")
            return "\n".join(resumen_hojas)

        resumen = await asyncio.to_thread(_leer_excel)
        context.user_data["excel_temp"]   = ruta_temp
        context.user_data["excel_nombre"] = nombre

        await update.message.reply_text(
            f"✅ Excel cargado correctamente.\n\n{resumen}\n\n"
            f"Ahora dime que quieres hacer con el. Por ejemplo:\n"
            f"- Agrega una columna de IVA del 19%\n"
            f"- Ordena de mayor a menor por total\n"
            f"- Cambia los encabezados a color rojo\n"
            f"- Calcula el total de todas las ventas"
        )
    except Exception:
        print(f"Error leyendo Excel: {traceback.format_exc()}")
        await update.message.reply_text("Tuve un problema leyendo el archivo. Asegurate de que sea un Excel valido.")
