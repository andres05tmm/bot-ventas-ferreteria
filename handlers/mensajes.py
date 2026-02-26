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
    ventas_pendientes, clientes_en_proceso, _estado_lock,
    get_chat_lock, registrar_ventas_con_metodo, mensajes_standby,
    esperando_correccion,
)
from excel import guardar_cliente_nuevo
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, corregir_texto_audio


async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Delega a callbacks._enviar_botones_pago para mantener un solo teclado centralizado."""
    from handlers.callbacks import _enviar_botones_pago as _botones_central
    await _botones_central(message, chat_id, ventas)


async def _enviar_pregunta_cliente(message, chat_id: int):
    """
    Lee el paso actual del flujo de creacion de cliente y envia
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
        await message.reply_text(
            f"¿Cuál es el número de {datos.get('tipo_id', 'identificación')}?"
        )

    elif paso == "tipo_persona":
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👤 Persona Natural",   callback_data=f"cli_persona_Natural_{chat_id}"),
            InlineKeyboardButton("🏢 Persona Jurídica",  callback_data=f"cli_persona_Juridica_{chat_id}"),
        ]])
        await message.reply_text("¿Es Persona Natural o Persona Jurídica?", reply_markup=keyboard)

    elif paso == "correo":
        await message.reply_text(
            "¿Cuál es el correo electrónico? (escribe 'no tiene' si no aplica)"
        )


async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje  = update.message.text
    chat_id  = update.message.chat_id
    vendedor = update.message.from_user.first_name or "Desconocido"

    if mensaje.startswith("/"):
        return

    # Serializar mensajes del mismo chat para evitar race conditions
    async with get_chat_lock(chat_id):
        await _procesar_mensaje(update, context, mensaje, chat_id, vendedor)


async def _procesar_mensaje(update, context, mensaje, chat_id, vendedor):
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Flujo paso a paso de creacion de cliente ──
    with _estado_lock:
        en_proceso = clientes_en_proceso.get(chat_id)
    if en_proceso:
        paso = en_proceso.get("paso")
        texto_lower = mensaje.strip().lower()

        if paso == "nombre":
            en_proceso["nombre"] = mensaje.strip().upper()
            en_proceso["paso"]   = "tipo_id"
            with _estado_lock:
                clientes_en_proceso[chat_id] = en_proceso
            await _enviar_pregunta_cliente(update.message, chat_id)
            return

        elif paso == "identificacion":
            en_proceso["identificacion"] = mensaje.strip()
            en_proceso["paso"]           = "tipo_persona"
            with _estado_lock:
                clientes_en_proceso[chat_id] = en_proceso
            await _enviar_pregunta_cliente(update.message, chat_id)
            return

        elif paso == "correo":
            correo = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
            en_proceso["correo"] = correo
            # ── Todos los datos recopilados — guardar cliente ──
            with _estado_lock:
                clientes_en_proceso.pop(chat_id, None)
            ok = await asyncio.to_thread(
                guardar_cliente_nuevo,
                en_proceso["nombre"],
                en_proceso["tipo_id"],
                en_proceso["identificacion"],
                en_proceso["tipo_persona"],
                correo,
            )
            if ok:
                tipo_map = {"CC": "Cédula de ciudadanía", "NIT": "NIT", "CE": "Cédula de extranjería"}
                tipo_legible = tipo_map.get(en_proceso["tipo_id"], en_proceso["tipo_id"])
                await update.message.reply_text(
                    f"✅ Cliente creado exitosamente:\n\n"
                    f"👤 {en_proceso['nombre']}\n"
                    f"📄 {tipo_legible}: {en_proceso['identificacion']}\n"
                    f"🏷️ {en_proceso['tipo_persona']}\n"
                    f"📧 {correo or 'Sin correo'}"
                )
            else:
                await update.message.reply_text("⚠️ No pude guardar el cliente. Intenta de nuevo.")
            return

    # Si el usuario esta en flujo de cliente pero llega aqui, continuar normal

    # ── Excel cargado por el usuario ──
    excel_temp   = context.user_data.get("excel_temp")
    excel_nombre = context.user_data.get("excel_nombre")
    if excel_temp and os.path.exists(excel_temp):
        try:
            await update.message.reply_text("⚙️ Procesando tu Excel...")
            codigo = await editar_excel_con_claude(mensaje, excel_temp, excel_nombre, vendedor, chat_id)

            if codigo.strip() == "IMPOSIBLE":
                await update.message.reply_text("No pude hacer eso con el Excel. Intenta con otra instruccion.")
                return

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

    # ── Interceptar metodo de pago escrito como texto ──
    with _estado_lock:
        _ventas_pend = list(ventas_pendientes.get(chat_id, []))

    if _ventas_pend:
        # Detectar si el usuario quiere cancelar/olvidar la venta pendiente
        _cancelar_palabras = {"olvida", "olvidala", "olvídala", "cancela", "cancelar",
                              "no registres", "borra", "descarta"}
        _msg_norm = mensaje.strip().lower()
        if any(p in _msg_norm for p in _cancelar_palabras):
            with _estado_lock:
                ventas_pendientes.pop(chat_id, None)
                standby_pendiente = mensajes_standby.pop(chat_id, [])
            await update.message.reply_text("🗑️ Venta cancelada.")

            # Si habia mensajes en standby, procesarlos ahora que se liberó el bloqueo
            for standby_msg in standby_pendiente:
                await update.message.reply_text(f"📋 Procesando venta pendiente: {standby_msg}")
                historial = get_historial(chat_id)
                agregar_al_historial(chat_id, "user", f"{vendedor}: {standby_msg}")
                respuesta_raw = await procesar_con_claude(f"{vendedor}: {standby_msg}", vendedor, historial)
                texto_resp, acciones2, _ = procesar_acciones(respuesta_raw, vendedor, chat_id)
                agregar_al_historial(chat_id, "assistant", texto_resp)
                if texto_resp:
                    await update.message.reply_text(texto_resp)
                for accion2 in acciones2:
                    if accion2 not in ("PEDIR_METODO_PAGO", "INICIAR_FLUJO_CLIENTE", "PAGO_PENDIENTE_AVISO"):
                        await update.message.reply_text(accion2)
                if "PEDIR_METODO_PAGO" in acciones2:
                    with _estado_lock:
                        ventas2 = list(ventas_pendientes.get(chat_id, []))
                    if ventas2:
                        from handlers.callbacks import _enviar_botones_pago as _botones_cb
                        await _botones_cb(update.message, chat_id, ventas2)
            return

        _metodos_texto = {
            "efectivo": "efectivo", "cash": "efectivo", "contado": "efectivo",
            "transferencia": "transferencia", "transfer": "transferencia",
            "nequi": "transferencia", "daviplata": "transferencia", "bancolombia": "transferencia",
            "datafono": "datafono", "datáfono": "datafono", "tarjeta": "datafono",
        }
        metodo_detectado = _metodos_texto.get(mensaje.strip().lower())
        if metodo_detectado:
            with _estado_lock:
                ventas = ventas_pendientes.pop(chat_id, [])
            if ventas:
                confirmaciones = await asyncio.to_thread(
                    registrar_ventas_con_metodo, ventas, metodo_detectado, vendedor, chat_id
                )
                emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo_detectado, "✅")
                await update.message.reply_text(
                    f"✅ Venta registrada — {emoji} {metodo_detectado.capitalize()}\n\n" + "\n".join(confirmaciones)
                )
            # Procesar mensaje en standby si hay uno esperando
            with _estado_lock:
                standby_list = mensajes_standby.pop(chat_id, [])
            for standby_msg in standby_list:
                await update.message.reply_text(f"📋 Procesando venta pendiente: {standby_msg}")
                historial = get_historial(chat_id)
                agregar_al_historial(chat_id, "user", f"{vendedor}: {standby_msg}")
                respuesta_raw = await procesar_con_claude(f"{vendedor}: {standby_msg}", vendedor, historial)
                texto_resp, acciones2, _ = procesar_acciones(respuesta_raw, vendedor, chat_id)
                agregar_al_historial(chat_id, "assistant", texto_resp)
                if texto_resp:
                    await update.message.reply_text(texto_resp)
                for accion2 in acciones2:
                    if accion2 not in ("PEDIR_METODO_PAGO", "INICIAR_FLUJO_CLIENTE", "PAGO_PENDIENTE_AVISO"):
                        await update.message.reply_text(accion2)
                if "PEDIR_METODO_PAGO" in acciones2:
                    with _estado_lock:
                        ventas2 = list(ventas_pendientes.get(chat_id, []))
                    if ventas2:
                        # Usar botones completos (con opcion cancelar) desde callbacks
                        from handlers.callbacks import _enviar_botones_pago as _botones_cb
                        await _botones_cb(update.message, chat_id, ventas2)
            return

    # ── Modo modificación/corrección de venta ──
    with _estado_lock:
        en_correccion = esperando_correccion.pop(chat_id, False)

    if en_correccion == "modificar":
        # El usuario quiere modificar la venta pendiente con instrucciones en texto libre.
        # Le pasamos a Claude la venta actual + la instrucción de cambio para que la edite.
        with _estado_lock:
            ventas_actuales = list(ventas_pendientes.get(chat_id, []))

        # Guardar el metodo original antes de limpiar ventas_pendientes
        metodo_original = None
        if ventas_actuales and ventas_actuales[0].get("metodo_pago"):
            metodo_original = ventas_actuales[0]["metodo_pago"]

        import json as _json
        resumen_venta = _json.dumps(ventas_actuales, ensure_ascii=False)

        prompt_modificacion = (
            "El vendedor tiene esta venta pendiente de confirmar:\n"
            + resumen_venta
            + "\n\nEl vendedor quiere modificarla con esta instruccion: "
            + mensaje
            + "\n\nAplica EXACTAMENTE los cambios pedidos a la venta (modifica cantidad, precio, "
            "quita o agrega productos segun corresponda). "
            "Luego emite los [VENTA] actualizados con los datos correctos y confirma los cambios en texto. "
            "IMPORTANTE: emite [VENTA] para TODOS los productos que quedan en la venta (no solo el modificado). "
            + (f"IMPORTANTE: mantén metodo_pago={metodo_original} en todos los [VENTA]." if metodo_original else "")
        )
        historial = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", prompt_modificacion)

        # Limpiar ventas anteriores para que las nuevas [VENTA] las reemplacen
        with _estado_lock:
            ventas_pendientes.pop(chat_id, None)

        respuesta_raw = await procesar_con_claude(prompt_modificacion, vendedor, historial)
        texto_respuesta, acciones, archivos_excel = procesar_acciones(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)
        if texto_respuesta:
            await update.message.reply_text(texto_respuesta)

        # Mostrar botones según si el método ya se conoce o no
        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        with _estado_lock:
            ventas_nuevas = list(ventas_pendientes.get(chat_id, []))

        if ventas_nuevas:
            if confirmacion_accion:
                metodo_conocido = confirmacion_accion.split(":", 1)[1]
                from handlers.callbacks import _enviar_confirmacion_con_metodo
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_conocido)
            elif metodo_original:
                # Las [VENTA] nuevas no traen metodo_pago — restaurar el original y mostrar confirmacion
                with _estado_lock:
                    for v in ventas_pendientes.get(chat_id, []):
                        v["metodo_pago"] = metodo_original
                from handlers.callbacks import _enviar_confirmacion_con_metodo
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_original)
            else:
                await _enviar_botones_pago(update.message, chat_id, ventas_nuevas)
        return

    elif en_correccion:
        # Modo reescritura completa (fallback)
        historial = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {mensaje}")
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {mensaje}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = procesar_acciones(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)
        if texto_respuesta:
            await update.message.reply_text(texto_respuesta)
        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        with _estado_lock:
            ventas = ventas_pendientes.get(chat_id, [])
        if confirmacion_accion:
            metodo_conocido = confirmacion_accion.split(":", 1)[1]
            from handlers.callbacks import _enviar_confirmacion_con_metodo
            await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas, metodo_conocido)
        elif "PEDIR_METODO_PAGO" in acciones:
            await _enviar_botones_pago(update.message, chat_id, ventas)
        return

    # ── Flujo normal con Claude ──
    try:
        historial    = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {mensaje}")
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {mensaje}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = procesar_acciones(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        pedir_metodo    = "PEDIR_METODO_PAGO"    in acciones
        iniciar_cliente = "INICIAR_FLUJO_CLIENTE" in acciones
        pago_pend_aviso = "PAGO_PENDIENTE_AVISO"  in acciones
        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        print(f"[ACCIONES DEBUG] acciones={acciones} | pedir_metodo={pedir_metodo}")

        _acciones_internas = ("PEDIR_METODO_PAGO", "INICIAR_FLUJO_CLIENTE",
                              "PAGO_PENDIENTE_AVISO")

        # No mostrar texto de Claude si hay pago pendiente y bloqueó la venta
        # (evita el "Registré la venta..." cuando en realidad no la registró)
        if texto_respuesta and not pago_pend_aviso:
            await update.message.reply_text(texto_respuesta)

        for accion in acciones:
            if not accion.startswith("PEDIR_CONFIRMACION:") and accion not in _acciones_internas:
                await update.message.reply_text(accion)

        if pago_pend_aviso:
            # Guardar este mensaje en standby para procesarlo tras confirmar pago
            with _estado_lock:
                if chat_id not in mensajes_standby:
                    mensajes_standby[chat_id] = []
                mensajes_standby[chat_id].append(mensaje)
            with _estado_lock:
                ventas = ventas_pendientes.get(chat_id, [])
            await update.message.reply_text("⚠️ Primero confirma el método de pago de la venta anterior:")
            await _enviar_botones_pago(update.message, chat_id, ventas)
        elif confirmacion_accion:
            metodo_conocido = confirmacion_accion.split(":", 1)[1]
            with _estado_lock:
                ventas = ventas_pendientes.get(chat_id, [])
            from handlers.callbacks import _enviar_confirmacion_con_metodo
            await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas, metodo_conocido)
        elif pedir_metodo:
            with _estado_lock:
                ventas = ventas_pendientes.get(chat_id, [])
            await _enviar_botones_pago(update.message, chat_id, ventas)

        if iniciar_cliente:
            await _enviar_pregunta_cliente(update.message, chat_id)

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
        texto = corregir_texto_audio(transcripcion.text)
        await update.message.reply_text(f"📝 Escuche: {texto}")
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        historial     = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {texto}")
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {texto}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = procesar_acciones(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        if texto_respuesta:
            await update.message.reply_text(texto_respuesta)

        pedir_metodo        = "PEDIR_METODO_PAGO" in acciones
        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        _acciones_internas  = ("PEDIR_METODO_PAGO", "INICIAR_FLUJO_CLIENTE", "PAGO_PENDIENTE_AVISO")

        for accion in acciones:
            if not accion.startswith("PEDIR_CONFIRMACION:") and accion not in _acciones_internas:
                await update.message.reply_text(accion)

        if confirmacion_accion:
            metodo_conocido = confirmacion_accion.split(":", 1)[1]
            with _estado_lock:
                ventas = ventas_pendientes.get(chat_id, [])
            from handlers.callbacks import _enviar_confirmacion_con_metodo
            await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas, metodo_conocido)
        elif pedir_metodo:
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
