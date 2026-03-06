"""
Handlers de mensajes: texto, audio (voz) y documentos Excel.

CORRECCIONES v2:
  - manejar_audio: ruta_audio se inicializa a None ANTES del try/finally para
    evitar NameError si download_to_drive falla antes de asignar la variable
  - mensajes_standby: se usa agregar_a_standby() de ventas_state que tiene cap MAX_STANDBY
  - Docstring ANTES del import logging
"""

import logging
import asyncio
import os
import tempfile
import traceback

import openpyxl
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from ai import procesar_con_claude, procesar_acciones, procesar_acciones_async, editar_excel_con_claude
from ventas_state import (
    agregar_al_historial, get_historial,
    ventas_pendientes, clientes_en_proceso, _estado_lock,
    get_chat_lock, registrar_ventas_con_metodo, mensajes_standby,
    esperando_correccion, ventas_esperando_cliente,
    agregar_a_standby,   # ← nueva función con cap de MAX_STANDBY
)
from excel import guardar_cliente_nuevo
from handlers.comandos import manejar_flujo_agregar_producto
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, corregir_texto_audio

logger = logging.getLogger("ferrebot.mensajes")


async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Delega a callbacks._enviar_botones_pago para mantener un solo teclado centralizado."""
    from handlers.callbacks import _enviar_botones_pago as _botones_central
    await _botones_central(message, chat_id, ventas)


async def _enviar_pregunta_cliente(message, chat_id: int):
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


async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje  = update.message.text
    chat_id  = update.message.chat_id
    vendedor = update.message.from_user.first_name or "Desconocido"

    if mensaje.startswith("/"):
        return

    async with get_chat_lock(chat_id):
        await _procesar_mensaje(update, context, mensaje, chat_id, vendedor)


async def _procesar_mensaje(update, context, mensaje, chat_id, vendedor):
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Flujo paso a paso de agregar producto ──
    if await manejar_flujo_agregar_producto(update, context):
        return

    # ── Flujo paso a paso de creación de cliente ──
    with _estado_lock:
        en_proceso = clientes_en_proceso.get(chat_id)
    if en_proceso:
        paso        = en_proceso.get("paso")
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
            correo               = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
            en_proceso["correo"] = correo
            en_proceso["paso"]   = "telefono"
            with _estado_lock:
                clientes_en_proceso[chat_id] = en_proceso
            await update.message.reply_text("¿Cuál es el teléfono? (escribe 'no tiene' si no aplica)")
            return

        elif paso == "telefono":
            telefono               = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
            en_proceso["telefono"] = telefono
            with _estado_lock:
                clientes_en_proceso.pop(chat_id, None)
            ok = await asyncio.to_thread(
                guardar_cliente_nuevo,
                en_proceso["nombre"],
                en_proceso["tipo_id"],
                en_proceso["identificacion"],
                en_proceso["tipo_persona"],
                en_proceso.get("correo", ""),
                telefono,
            )
            if ok:
                tipo_map     = {"CC": "Cédula de ciudadanía", "NIT": "NIT", "CE": "Cédula de extranjería"}
                tipo_legible = tipo_map.get(en_proceso.get("tipo_id", ""), en_proceso.get("tipo_id", ""))
                await update.message.reply_text(
                    f"✅ Cliente creado exitosamente:\n\n"
                    f"👤 {en_proceso['nombre']}\n"
                    f"📄 {tipo_legible}: {en_proceso['identificacion']}\n"
                    f"🏷️ {en_proceso.get('tipo_persona', '')}\n"
                    f"📧 {en_proceso.get('correo', '') or 'Sin correo'}\n"
                    f"📞 {telefono or 'Sin teléfono'}"
                )
                # Continuar con la venta pendiente si existe
                with _estado_lock:
                    datos_espera = ventas_esperando_cliente.pop(chat_id, None)
                    ventas_pend  = list(ventas_pendientes.get(chat_id, []))
                if ventas_pend:
                    metodo = ventas_pend[0].get("metodo_pago", "").lower()
                    if metodo in ("efectivo", "transferencia", "datafono"):
                        from handlers.callbacks import _enviar_confirmacion_con_metodo
                        await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_pend, metodo)
                    else:
                        await _enviar_botones_pago(update.message, chat_id, ventas_pend)
            else:
                await update.message.reply_text("⚠️ No pude guardar el cliente. Intenta de nuevo.")
            return

    # ── Excel cargado por el usuario ──
    excel_temp   = context.user_data.get("excel_temp")
    excel_nombre = context.user_data.get("excel_nombre")
    if excel_temp and os.path.exists(excel_temp):
        try:
            await update.message.reply_text("⚙️ Procesando tu Excel...")
            codigo = await editar_excel_con_claude(mensaje, excel_temp, excel_nombre, vendedor, chat_id)

            if codigo.strip() == "IMPOSIBLE":
                await update.message.reply_text("No pude hacer eso con el Excel. Intenta con otra instrucción.")
                return

            import re as _re
            rutas_sospechosas  = _re.findall(r'''load_workbook\s*\(\s*['"]([^'"]+)['"]''', codigo)
            rutas_sospechosas += _re.findall(r'''\.save\s*\(\s*['"]([^'"]+)['"]''', codigo)
            for ruta_en_codigo in rutas_sospechosas:
                if ruta_en_codigo != excel_temp and ruta_en_codigo not in (excel_nombre, f"modificado_{excel_nombre}"):
                    await update.message.reply_text("No puedo ejecutar esa operación por seguridad.")
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
                "json":     __import__("json"),
            }
            await asyncio.to_thread(exec, compile(codigo, "<string>", "exec"), namespace_seguro)

            await update.message.reply_text("✅ Excel modificado. Aquí está el resultado:")
            with open(excel_temp, "rb") as f:
                await update.message.reply_document(document=f, filename=f"modificado_{excel_nombre}")

            context.user_data.pop("excel_temp", None)
            context.user_data.pop("excel_nombre", None)
            if os.path.exists(excel_temp):
                os.remove(excel_temp)
            return
        except Exception:
            print(f"Error editando Excel: {traceback.format_exc()}")
            await update.message.reply_text("Tuve un problema editando el Excel. Intenta con una instrucción diferente.")
            return

    # ── Interceptar método de pago escrito como texto ──
    with _estado_lock:
        _ventas_pend = list(ventas_pendientes.get(chat_id, []))

    if _ventas_pend:
        _cancelar_palabras = {"olvida", "olvidala", "olvídala", "cancela", "cancelar",
                              "no registres", "borra", "descarta"}
        _msg_norm = mensaje.strip().lower()
        if any(p in _msg_norm for p in _cancelar_palabras):
            with _estado_lock:
                ventas_pendientes.pop(chat_id, None)
                standby_pendiente = mensajes_standby.pop(chat_id, [])
            await update.message.reply_text("🗑️ Venta cancelada.")

            # CORRECCIÓN punto 7: usar _procesar_siguiente_standby en lugar del loop directo
            # para garantizar la cadena correcta uno por uno
            if standby_pendiente:
                from handlers.callbacks import _procesar_siguiente_standby
                await _procesar_siguiente_standby(
                    context.bot, update.message, chat_id, standby_pendiente, vendedor
                )
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
            with _estado_lock:
                standby_list = mensajes_standby.pop(chat_id, [])

            # CORRECCIÓN punto 7: usar _procesar_siguiente_standby en lugar del loop directo
            if standby_list:
                from handlers.callbacks import _procesar_siguiente_standby
                await _procesar_siguiente_standby(
                    context.bot, update.message, chat_id, standby_list, vendedor
                )
            return

    # ── Modo modificación/corrección de venta ──
    with _estado_lock:
        en_correccion = esperando_correccion.pop(chat_id, False)

    if en_correccion == "modificar":
        with _estado_lock:
            ventas_actuales = list(ventas_pendientes.get(chat_id, []))

        metodo_original = None
        if ventas_actuales and ventas_actuales[0].get("metodo_pago"):
            metodo_original = ventas_actuales[0]["metodo_pago"]

        import json as _json
        resumen_venta = _json.dumps(ventas_actuales, ensure_ascii=False)

        prompt_modificacion = (
            "El vendedor tiene esta venta pendiente de confirmar:\n"
            + resumen_venta
            + "\n\nEl vendedor quiere modificarla con esta instrucción: "
            + mensaje
            + "\n\nAplica EXACTAMENTE los cambios pedidos a la venta (modifica cantidad, precio, "
            "quita o agrega productos según corresponda). "
            "Luego emite los [VENTA] actualizados con los datos correctos y confirma los cambios en texto. "
            "IMPORTANTE: emite [VENTA] para TODOS los productos que quedan en la venta (no solo el modificado). "
            + (f"IMPORTANTE: mantén metodo_pago={metodo_original} en todos los [VENTA]." if metodo_original else "")
        )
        historial = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", prompt_modificacion)

        with _estado_lock:
            ventas_pendientes.pop(chat_id, None)

        respuesta_raw                         = await procesar_con_claude(prompt_modificacion, vendedor, historial)
        texto_respuesta, acciones, archivos_excel = await procesar_acciones_async(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        with _estado_lock:
            ventas_nuevas = list(ventas_pendientes.get(chat_id, []))

        if ventas_nuevas:
            # Nota del cambio en una sola linea, sin el resumen completo
            nota = texto_respuesta.split("\n")[0] if texto_respuesta else ""
            if confirmacion_accion:
                metodo_conocido = confirmacion_accion.split(":", 1)[1]
                from handlers.callbacks import _enviar_confirmacion_con_metodo
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_conocido, nota=nota)
            elif metodo_original:
                with _estado_lock:
                    for v in ventas_pendientes.get(chat_id, []):
                        v["metodo_pago"] = metodo_original
                from handlers.callbacks import _enviar_confirmacion_con_metodo
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_original, nota=nota)
            else:
                if nota:
                    await update.message.reply_text(nota)
                await _enviar_botones_pago(update.message, chat_id, ventas_nuevas)
        elif texto_respuesta:
            await update.message.reply_text(texto_respuesta)
        return

    elif en_correccion:
        historial = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {mensaje}")
        respuesta_raw                         = await procesar_con_claude(f"{vendedor}: {mensaje}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = await procesar_acciones_async(respuesta_raw, vendedor, chat_id)
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

    # ── Respuesta "no" a la pregunta de crear cliente ──
    with _estado_lock:
        _esperando_cliente_yn = ventas_pendientes.get(chat_id) and not clientes_en_proceso.get(chat_id)

    if _esperando_cliente_yn:
        _msg_lower    = mensaje.strip().lower()
        _respuesta_no = {"no", "nop", "nope", "nel", "sin cliente", "registra sin cliente", "registra asi"}
        if _msg_lower in _respuesta_no or _msg_lower.startswith("no "):
            with _estado_lock:
                ventas_para_registrar = list(ventas_pendientes.get(chat_id, []))
            if ventas_para_registrar:
                await update.message.reply_text("👍 Registrando la venta sin crear el cliente...")
                metodo_conocido = ventas_para_registrar[0].get("metodo_pago", "").lower()
                if metodo_conocido:
                    from handlers.callbacks import _enviar_confirmacion_con_metodo
                    await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_para_registrar, metodo_conocido)
                else:
                    await _enviar_botones_pago(update.message, chat_id, ventas_para_registrar)
                return

    # ── Flujo normal con Claude ──
    try:
        historial     = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {mensaje}")
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {mensaje}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = await procesar_acciones_async(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        pedir_metodo        = "PEDIR_METODO_PAGO"    in acciones
        iniciar_cliente     = "INICIAR_FLUJO_CLIENTE" in acciones
        pago_pend_aviso     = "PAGO_PENDIENTE_AVISO"  in acciones
        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        cliente_desconocido = next((a for a in acciones if a.startswith("CLIENTE_DESCONOCIDO:")), None)
        logging.getLogger("ferrebot.mensajes").debug(f"[ACCIONES] acciones={acciones} | pedir_metodo={pedir_metodo}")

        _acciones_internas = ("PEDIR_METODO_PAGO", "INICIAR_FLUJO_CLIENTE", "PAGO_PENDIENTE_AVISO")

        if texto_respuesta and not pago_pend_aviso and not cliente_desconocido and not pedir_metodo and not confirmacion_accion:
            await update.message.reply_text(texto_respuesta)

        # Agrupar precios actualizados en un solo mensaje
        precios_act = [a for a in acciones if a.startswith("🧠 Precio")]
        otras_acciones = [a for a in acciones if not a.startswith("🧠 Precio")
                         and not a.startswith("PEDIR_CONFIRMACION:")
                         and not a.startswith("CLIENTE_DESCONOCIDO:")
                         and a not in _acciones_internas]
        if precios_act:
            await update.message.reply_text("\n".join(precios_act))
        for accion in otras_acciones:
            await update.message.reply_text(accion)

        # ── Cliente desconocido: preguntar si quiere crearlo ──
        if cliente_desconocido:
            nombre_cli = cliente_desconocido.split(":", 1)[1]
            keyboard   = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Sí, crear cliente", callback_data=f"cli_crear_si_{chat_id}"),
                InlineKeyboardButton("➡️ No, registrar así", callback_data=f"cli_crear_no_{chat_id}"),
            ]])
            await update.message.reply_text(
                f"👤 El cliente *{nombre_cli}* no está en la base de datos.\n"
                f"¿Quieres crearlo antes de registrar la venta?",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

        if pago_pend_aviso:
            agregar_a_standby(chat_id, mensaje)
            with _estado_lock:
                ventas = ventas_pendientes.get(chat_id, [])
            await update.message.reply_text("⚠️ Primero confirma el método de pago de la venta anterior:")
            await _enviar_botones_pago(update.message, chat_id, ventas)
        elif not cliente_desconocido:
            # Solo mostrar botones de pago/confirmar si ya se resolvio el cliente
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

        if iniciar_cliente:
            await _enviar_pregunta_cliente(update.message, chat_id)

        for archivo in archivos_excel:
            if os.path.exists(archivo):
                await update.message.reply_text("📊 Aquí está tu reporte:")
                with open(archivo, "rb") as f:
                    await update.message.reply_document(document=f, filename=archivo)
                os.remove(archivo)

    except Exception:
        logger.error("Error en mensaje: %s", traceback.format_exc())
        await update.message.reply_text("Tuve un problema. Intenta de nuevo.")


async def manejar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vendedor = update.message.from_user.first_name or "Desconocido"
    chat_id  = update.message.chat_id

    async with get_chat_lock(chat_id):
        await _procesar_audio(update, context, vendedor, chat_id)


async def _procesar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, vendedor: str, chat_id: int):

    # CORRECCIÓN: inicializar ruta_audio ANTES del try para que el finally
    # no tenga NameError si la descarga falla antes de asignar la variable
    ruta_audio = None

    try:
        # Reintentos ante timeout de red de Telegram (común en Railway con servidor frío)
        _MAX_REINTENTOS = 3
        _archivo_voz    = None
        for _intento in range(_MAX_REINTENTOS):
            try:
                _archivo_voz = await update.message.voice.get_file()
                break
            except Exception as _e:
                if _intento < _MAX_REINTENTOS - 1:
                    await asyncio.sleep(1.5 * (_intento + 1))
                else:
                    raise _e

        archivo_voz = _archivo_voz

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            ruta_audio = tmp.name  # asignamos aquí, ANTES de la descarga

        # Reintentos también en la descarga del archivo
        for _intento in range(_MAX_REINTENTOS):
            try:
                await archivo_voz.download_to_drive(ruta_audio)
                break
            except Exception as _e:
                if _intento < _MAX_REINTENTOS - 1:
                    await asyncio.sleep(1.5 * (_intento + 1))
                else:
                    raise _e

        def _transcribir():
            with open(ruta_audio, "rb") as audio_file:
                return config.openai_client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, language="es"
                )

        transcripcion = await asyncio.to_thread(_transcribir)
        texto         = corregir_texto_audio(transcripcion.text)
        await update.message.reply_text(f"📝 {texto}")
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # ── Verificar modo corrección/modificación (igual que en texto) ──
        with _estado_lock:
            en_correccion = esperando_correccion.pop(chat_id, False)

        if en_correccion == "modificar":
            # Usar la misma lógica que el handler de texto para modificaciones
            with _estado_lock:
                ventas_actuales = list(ventas_pendientes.get(chat_id, []))

            metodo_original = None
            if ventas_actuales and ventas_actuales[0].get("metodo_pago"):
                metodo_original = ventas_actuales[0]["metodo_pago"]

            import json as _json
            resumen_venta = _json.dumps(ventas_actuales, ensure_ascii=False)

            prompt_modificacion = (
                "El vendedor tiene esta venta pendiente de confirmar:\n"
                + resumen_venta
                + "\n\nEl vendedor quiere modificarla con esta instrucción: "
                + texto
                + "\n\nAplica EXACTAMENTE los cambios pedidos a la venta (modifica cantidad, precio, "
                "quita o agrega productos según corresponda). "
                "Luego emite los [VENTA] actualizados con los datos correctos y confirma los cambios en texto. "
                "IMPORTANTE: emite [VENTA] para TODOS los productos que quedan en la venta (no solo el modificado). "
                + (f"IMPORTANTE: mantén metodo_pago={metodo_original} en todos los [VENTA]." if metodo_original else "")
            )
            historial = get_historial(chat_id)
            agregar_al_historial(chat_id, "user", prompt_modificacion)

            with _estado_lock:
                ventas_pendientes.pop(chat_id, None)

            respuesta_raw = await procesar_con_claude(prompt_modificacion, vendedor, historial)
            texto_respuesta, acciones, archivos_excel = await procesar_acciones_async(respuesta_raw, vendedor, chat_id)
            agregar_al_historial(chat_id, "assistant", texto_respuesta)

            confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
            with _estado_lock:
                ventas_nuevas = list(ventas_pendientes.get(chat_id, []))

            if ventas_nuevas:
                nota = texto_respuesta.split("\n")[0] if texto_respuesta else ""
                if confirmacion_accion:
                    metodo_conocido = confirmacion_accion.split(":", 1)[1]
                    from handlers.callbacks import _enviar_confirmacion_con_metodo
                    await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_conocido, nota=nota)
                elif metodo_original:
                    with _estado_lock:
                        for v in ventas_pendientes.get(chat_id, []):
                            v["metodo_pago"] = metodo_original
                    from handlers.callbacks import _enviar_confirmacion_con_metodo
                    await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_original, nota=nota)
                else:
                    if nota:
                        await update.message.reply_text(nota)
                    await _enviar_botones_pago(update.message, chat_id, ventas_nuevas)
            elif texto_respuesta:
                await update.message.reply_text(texto_respuesta)
            return

        # ── Chequeo de pago pendiente: si hay venta esperando, el audio va al standby ──
        with _estado_lock:
            _ventas_pend = list(ventas_pendientes.get(chat_id, []))

        if _ventas_pend:
            agregar_a_standby(chat_id, texto)
            await update.message.reply_text("⚠️ Primero confirma el método de pago de la venta anterior:")
            await _enviar_botones_pago(update.message, chat_id, _ventas_pend)
            return

        historial     = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {texto}")
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {texto}", vendedor, historial)
        texto_respuesta, acciones, archivos_excel = await procesar_acciones_async(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        pedir_metodo        = "PEDIR_METODO_PAGO" in acciones
        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        cliente_desconocido = next((a for a in acciones if a.startswith("CLIENTE_DESCONOCIDO:")), None)
        pago_pend_aviso     = "PAGO_PENDIENTE_AVISO" in acciones
        _acciones_internas  = ("PEDIR_METODO_PAGO", "INICIAR_FLUJO_CLIENTE", "PAGO_PENDIENTE_AVISO")

        # En audio: mostrar texto de Claude solo si NO hay botones de venta (es una pregunta o error)
        hay_botones_venta = confirmacion_accion or pedir_metodo
        if texto_respuesta and (not hay_botones_venta or cliente_desconocido):
            await update.message.reply_text(texto_respuesta)

        precios_act2 = [a for a in acciones if a.startswith("🧠 Precio")]
        otras_acciones2 = [a for a in acciones if not a.startswith("🧠 Precio")
                          and not a.startswith("PEDIR_CONFIRMACION:")
                          and not a.startswith("CLIENTE_DESCONOCIDO:")
                          and a not in _acciones_internas]
        if precios_act2:
            await update.message.reply_text("\n".join(precios_act2))
        for accion in otras_acciones2:
            await update.message.reply_text(accion)

        if cliente_desconocido:
            nombre_cli = cliente_desconocido.split(":", 1)[1]
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Sí, crear cliente", callback_data=f"cli_crear_si_{chat_id}"),
                InlineKeyboardButton("➡️ No, registrar así", callback_data=f"cli_crear_no_{chat_id}"),
            ]])
            await update.message.reply_text(
                f"👤 *{nombre_cli}* no está en la base. ¿Lo agrego como cliente?",
                reply_markup=keyboard, parse_mode="Markdown",
            )

        if not cliente_desconocido:
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
                await update.message.reply_text("📊 Aquí está tu reporte:")
                with open(archivo, "rb") as f:
                    await update.message.reply_document(document=f, filename=archivo)
                os.remove(archivo)

    except Exception:
        logger.error("Error en audio: %s", traceback.format_exc())
        await update.message.reply_text("Problema con el audio. Intenta de nuevo.")
    finally:
        # CORRECCIÓN: verificar que ruta_audio fue asignada antes de intentar borrarla
        if ruta_audio and os.path.exists(ruta_audio):
            try:
                os.unlink(ruta_audio)
            except Exception:
                pass


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

    # ── Si es BASE_DE_DATOS_PRODUCTOS, importar catálogo automáticamente ──
    if "base_de_datos_productos" in nombre.lower() or "base de datos" in nombre.lower():
        await update.message.reply_text("📦 Detecté el catálogo de productos. Importando...")
        try:
            ruta_temp = f"temp_catalogo_{update.message.chat_id}.xlsx"
            archivo   = await doc.get_file()
            await archivo.download_to_drive(ruta_temp)

            from memoria import importar_catalogo_desde_excel
            resultado  = await asyncio.to_thread(importar_catalogo_desde_excel, ruta_temp)
            importados = resultado["importados"]
            omitidos   = resultado["omitidos"]
            errores    = resultado["errores"]

            texto = (
                f"✅ Catálogo actualizado exitosamente\n\n"
                f"📦 {importados} productos importados\n"
                f"⏭️ {omitidos} filas omitidas (sin nombre o precio)"
            )
            if errores:
                texto += f"\n⚠️ {len(errores)} errores:\n" + "\n".join(f"  • {e}" for e in errores[:5])
            await update.message.reply_text(texto)

            import os
            if os.path.exists(ruta_temp):
                os.remove(ruta_temp)
        except Exception as e:
            await update.message.reply_text(f"❌ Error importando catálogo: {e}")
        return

    await update.message.reply_text(f"📂 Recibí tu archivo '{nombre}'. Leyendo contenido...")
    chat_id = update.message.chat_id

    try:
        excel_temp_anterior = context.user_data.get("excel_temp")
        if excel_temp_anterior and os.path.exists(excel_temp_anterior):
            try:
                os.remove(excel_temp_anterior)
            except Exception:
                pass
        context.user_data.pop("excel_temp", None)
        context.user_data.pop("excel_nombre", None)

        archivo   = await doc.get_file()
        ruta_temp = f"temp_{chat_id}_{nombre}"
        await archivo.download_to_drive(ruta_temp)

        def _leer_excel():
            wb = openpyxl.load_workbook(ruta_temp, read_only=True)
            resumen_hojas = []
            for hoja_nombre in wb.sheetnames:
                ws  = wb[hoja_nombre]
                enc = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1) if ws.cell(row=1, column=c).value]
                resumen_hojas.append(f"Hoja '{hoja_nombre}': {ws.max_row - 1} filas, columnas: {', '.join(str(e) for e in enc)}")
            wb.close()
            return "\n".join(resumen_hojas)

        resumen = await asyncio.to_thread(_leer_excel)
        context.user_data["excel_temp"]   = ruta_temp
        context.user_data["excel_nombre"] = nombre

        await update.message.reply_text(
            f"✅ Excel cargado correctamente.\n\n{resumen}\n\n"
            f"Ahora dime qué quieres hacer con él. Por ejemplo:\n"
            f"- Agrega una columna de IVA del 19%\n"
            f"- Ordena de mayor a menor por total\n"
            f"- Cambia los encabezados a color rojo\n"
            f"- Calcula el total de todas las ventas"
        )
    except Exception:
        logger.error("Error leyendo Excel: %s", traceback.format_exc())
        await update.message.reply_text("Tuve un problema leyendo el archivo. Asegúrate de que sea un Excel válido.")
