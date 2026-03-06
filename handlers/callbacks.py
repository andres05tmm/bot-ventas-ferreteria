"""
Manejo de botones (callbacks) de Telegram y flujos interactivos de creación de clientes.

CORRECCIONES v2:
  - _parsear_precio local eliminada — se usa parsear_precio de utils (era duplicado)
  - manejar_texto_cliente eliminada — era código muerto (nunca se llamaba desde ningún handler)
  - Docstring ANTES del import logging

CORRECCIONES v4 — FIX standby async:
  _procesar_siguiente_standby usaba procesar_acciones (síncrona), bloqueando
  el event loop completo mientras escribe en Excel/Drive. Cambiado a
  procesar_acciones_async para no congelar otros chats.
  Antes: el loop procesaba TODOS los mensajes del standby de golpe.
    Mensaje 1 → dejaba venta nueva en ventas_pendientes
    Mensaje 2 → veía ventas_pendientes ocupado → [VENTA] ignorado → pérdida silenciosa
  Ahora: _procesar_siguiente_standby toma SOLO el primero, muestra botones si genera venta,
    y guarda el resto de vuelta en mensajes_standby. El siguiente mensaje se procesa cuando
    el usuario confirme el pago de ese, garantizando la cadena completa.
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from excel import borrar_venta_excel, guardar_cliente_nuevo
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, parsear_precio
from ventas_state import (
    ventas_pendientes, borrados_pendientes, _estado_lock,
    registrar_ventas_con_metodo, clientes_en_proceso,
    ventas_esperando_cliente, mensajes_standby,
    agregar_a_standby,
)


# ─────────────────────────────────────────────
# HELPER: procesar el siguiente mensaje del standby (uno por vez)
# ─────────────────────────────────────────────

async def _procesar_siguiente_standby(bot, message, chat_id: int, pendientes: list, vendedor: str):
    """
    Toma el PRIMER mensaje del standby, lo procesa, y para.

    - Si genera una venta → muestra los botones de pago y termina.
      El siguiente mensaje del standby se procesará cuando el usuario confirme ese pago.
    - Si NO genera venta (consulta, saludo, etc.) → continúa con el siguiente del standby.
    - El resto de los mensajes se guarda de vuelta en mensajes_standby antes de procesar,
      para que no se pierdan si hay un error.
    """
    from ai import procesar_con_claude, procesar_acciones_async
    from ventas_state import agregar_al_historial, get_historial

    if not pendientes:
        return

    msg_text = pendientes[0]
    resto    = pendientes[1:]

    # Guardar el resto de vuelta ANTES de procesar (seguridad ante errores)
    if resto:
        with _estado_lock:
            mensajes_standby[chat_id] = resto

    historial     = get_historial(chat_id)
    agregar_al_historial(chat_id, "user", f"{vendedor}: {msg_text}")
    respuesta_raw            = await procesar_con_claude(f"{vendedor}: {msg_text}", vendedor, historial)
    texto_resp, acciones2, _ = await procesar_acciones_async(respuesta_raw, vendedor, chat_id)
    agregar_al_historial(chat_id, "assistant", texto_resp)

    confirmacion_accion = next((a for a in acciones2 if a.startswith("PEDIR_CONFIRMACION:")), None)
    pedir_metodo        = "PEDIR_METODO_PAGO" in acciones2
    genera_venta        = confirmacion_accion or pedir_metodo

    if texto_resp and "PAGO_PENDIENTE_AVISO" not in acciones2:
        await bot.send_message(chat_id=chat_id, text=texto_resp)

    if confirmacion_accion:
        metodo_conocido = confirmacion_accion.split(":", 1)[1]
        with _estado_lock:
            ventas2 = list(ventas_pendientes.get(chat_id, []))
        if ventas2:
            await _enviar_confirmacion_con_metodo(message, chat_id, ventas2, metodo_conocido)
    elif pedir_metodo:
        with _estado_lock:
            ventas2 = list(ventas_pendientes.get(chat_id, []))
        if ventas2:
            await _enviar_botones_pago(message, chat_id, ventas2)
        else:
            # No quedó venta (raro), seguir con el siguiente
            genera_venta = False

    if not genera_venta and resto:
        # Sin venta pendiente — el siguiente del standby puede procesarse ya
        with _estado_lock:
            siguiente_resto = mensajes_standby.pop(chat_id, [])
        if siguiente_resto:
            await _procesar_siguiente_standby(bot, message, chat_id, siguiente_resto, vendedor)


# ─────────────────────────────────────────────
# MANEJO DE BOTONES (CALLBACKS)
# ─────────────────────────────────────────────

async def manejar_metodo_pago(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    data    = query.data
    chat_id = query.message.chat_id
    await query.answer()

    # ── Modificar venta ──
    if data.startswith("pago_modificar_"):
        from ventas_state import esperando_correccion
        with _estado_lock:
            ventas_actuales = list(ventas_pendientes.get(chat_id, []))

        if not ventas_actuales:
            await query.edit_message_text("No hay venta activa para modificar.")
            return

        items = "\n".join(
            "  - " + str(v.get("producto", "?")) + " x" + str(v.get("cantidad", 1))
            + " - $" + f"{v.get('total', 0):,}"
            for v in ventas_actuales
        )

        with _estado_lock:
            esperando_correccion[chat_id] = "modificar"

        await query.edit_message_text(
            "Venta actual:\n" + items + "\n\n"
            "Dime qué quieres cambiar, por ejemplo:\n"
            "  - el precio del sellador era 25000\n"
            "  - quita los aerosoles\n"
            "  - los tornillos eran 3 docenas no 5\n"
            "  - agrega 1 brocha 5000"
        )
        return

    # ── Cancelar venta ──
    if data.startswith("pago_cancelar_"):
        from ventas_state import esperando_correccion
        with _estado_lock:
            ventas_canceladas             = ventas_pendientes.pop(chat_id, [])
            standby_pendiente             = mensajes_standby.pop(chat_id, [])
            esperando_correccion[chat_id] = True

        if ventas_canceladas:
            items           = "\n".join(f"  • {v.get('producto', '?')} — ${v.get('total', 0):,}" for v in ventas_canceladas)
            texto_cancelado = f"Venta cancelada:\n{items}\n\n"
        else:
            texto_cancelado = ""

        await query.edit_message_text(
            f"✏️ {texto_cancelado}"
            "Reescribe la venta como quieras y la registro de nuevo."
        )

        if standby_pendiente:
            await _procesar_siguiente_standby(
                context.bot, query.message, chat_id,
                standby_pendiente, update.effective_user.first_name,
            )
        return

    # ── Confirmar venta con método ya conocido ──
    if data.startswith("pago_confirmar_"):
        sin_prefijo  = data[len("pago_confirmar_"):]
        ultimo_guion = sin_prefijo.rfind("_")
        metodo       = sin_prefijo[:ultimo_guion]
        chat_id      = int(sin_prefijo[ultimo_guion + 1:])
        vendedor     = update.effective_user.first_name

        with _estado_lock:
            ventas = ventas_pendientes.get(chat_id)

        if not ventas:
            await query.edit_message_text("Esta sesión ya fue procesada.")
            return

        await query.edit_message_text("⏳ Registrando venta...")

        conf  = await asyncio.to_thread(registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id)
        emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
        await query.edit_message_text(
            f"✅ Venta confirmada — {emoji} {metodo.capitalize()}\n\n" + "\n".join(conf)
        )

        with _estado_lock:
            pendientes = mensajes_standby.pop(chat_id, [])
        if pendientes:
            await _procesar_siguiente_standby(
                context.bot, query.message, chat_id, pendientes, vendedor
            )
        return

    # ── Métodos de pago (botones 💵📱💳) ──
    if data.startswith("pago_"):
        partes   = data.split("_")
        metodo   = partes[1]
        chat_id  = int(partes[2])
        vendedor = update.effective_user.first_name

        with _estado_lock:
            ventas = ventas_pendientes.get(chat_id)

        if not ventas:
            await query.edit_message_text("Esta sesión de pago expiró o ya fue procesada.")
            return

        await query.edit_message_text("⏳ Registrando venta...")

        conf  = await asyncio.to_thread(registrar_ventas_con_metodo, ventas, metodo, vendedor, chat_id)
        emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
        await query.edit_message_text(
            f"✅ Venta registrada — {emoji} {metodo.capitalize()}\n\n" + "\n".join(conf)
        )

        with _estado_lock:
            pendientes = mensajes_standby.pop(chat_id, [])
        if pendientes:
            await _procesar_siguiente_standby(
                context.bot, query.message, chat_id, pendientes, vendedor
            )

    # ── Confirmación de borrado ──
    elif data.startswith("borrar_"):
        partes  = data.split("_")
        confirm = partes[1]
        chat_id = int(partes[2])

        with _estado_lock:
            numero = borrados_pendientes.pop(chat_id, None)

        if confirm == "si" and numero:
            # Borrar de Sheets primero (si está disponible)
            sheets_borradas = 0
            if config.SHEETS_ID and config.SHEETS_DISPONIBLE:
                from sheets import sheets_borrar_consecutivo
                sheets_borradas, _ = await asyncio.to_thread(sheets_borrar_consecutivo, numero)
            
            # También borrar del Excel local
            exito, msg = await asyncio.to_thread(borrar_venta_excel, numero)
            
            # Mensaje de confirmación
            if sheets_borradas > 0:
                await query.edit_message_text(f"✅ Consecutivo #{numero} eliminado ({sheets_borradas} productos borrados de Sheets).")
            elif exito:
                await query.edit_message_text(msg)
            else:
                await query.edit_message_text(f"✅ Consecutivo #{numero} eliminado.")
        else:
            await query.edit_message_text("Borrado cancelado.")

    # ── Gráficas ──
    elif data.startswith("grafica_"):
        from handlers.comandos import manejar_callback_grafica
        await manejar_callback_grafica(update, context)


# ─────────────────────────────────────────────
# ENVÍO DE BOTONES DE PAGO
# ─────────────────────────────────────────────

async def _enviar_confirmacion_con_metodo(message, chat_id: int, ventas: list, metodo: str, nota: str = ""):
    """
    Cuando el usuario ya dijo el método de pago, muestra la venta con
    botones de Confirmar o Modificar.
    nota: texto opcional que se muestra encima del resumen (ej: confirmación del cambio realizado).
    """
    emoji_metodo = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
    lineas = []
    cliente = None
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        producto     = v.get("producto", "")
        total        = parsear_precio(v.get("total", 0))
        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        lineas.append(f"• {cantidad_leg} {producto} ${total:,.0f}")
        if not cliente and v.get("cliente"):
            cliente = v.get("cliente")

    total_general = sum(parsear_precio(v.get("total", 0)) for v in ventas)
    encabezado = f"✓ Venta — {emoji_metodo} {metodo.capitalize()}"
    if cliente:
        encabezado += f" | 👤 {cliente}"
    encabezado += "\n\n"
    if nota:
        encabezado = nota.split("\n")[0] + "\n\n" + encabezado

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar",       callback_data=f"pago_confirmar_{metodo}_{chat_id}"),
        InlineKeyboardButton("✏️ Modificar venta", callback_data=f"pago_modificar_{chat_id}"),
    ]])
    await message.reply_text(
        encabezado + "\n".join(lineas) + f"\n\nTotal: ${total_general:,.0f}",
        reply_markup=keyboard,
    )


async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Muestra botones de método de pago con opción de modificar.
    Si todas las ventas ya tienen metodo_pago, usa confirmación directa."""

    # Si Claude ya detectó el método, pre-seleccionarlo
    metodos = {v.get("metodo_pago", "").lower() for v in ventas if v.get("metodo_pago")}
    if len(metodos) == 1:
        metodo = metodos.pop()
        if metodo in ("efectivo", "transferencia", "datafono"):
            with _estado_lock:
                ventas_pendientes[chat_id] = ventas
            await _enviar_confirmacion_con_metodo(message, chat_id, ventas, metodo)
            return

    lineas = []
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        producto     = v.get("producto", "")
        total        = parsear_precio(v.get("total", 0))
        p_unitario   = parsear_precio(v.get("precio_unitario", 0))
        valor_final  = total if total > 0 else round(p_unitario * cantidad_dec)
        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        lineas.append(f"• {cantidad_leg} {producto} ${valor_final:,.0f}")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Efectivo",        callback_data=f"pago_efectivo_{chat_id}"),
            InlineKeyboardButton("📱 Transf.",          callback_data=f"pago_transferencia_{chat_id}"),
            InlineKeyboardButton("💳 Datáfono",         callback_data=f"pago_datafono_{chat_id}"),
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
# HANDLER: botones de creación de cliente
# ─────────────────────────────────────────────

async def manejar_callback_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Maneja los botones inline del flujo de creación de cliente:
      - cli_crear_si_{chat_id}         → usuario quiere crear el cliente
      - cli_crear_no_{chat_id}         → usuario NO quiere crear cliente
      - cli_tipoid_CC_{chat_id}        → tipo de identificación
      - cli_persona_Natural_{chat_id}  → tipo de persona
    """
    query   = update.callback_query
    data    = query.data
    chat_id = query.message.chat_id
    await query.answer()

    # ── ¿Crear cliente? Sí ──
    if data.startswith("cli_crear_si_"):
        with _estado_lock:
            ventas = list(ventas_pendientes.get(chat_id, []))

        if not ventas:
            await query.edit_message_text("No hay venta pendiente. Registra la venta de nuevo.")
            return

        nombre_cliente = ""
        for v in ventas:
            nombre_cliente = v.get("cliente", "").strip()
            if nombre_cliente:
                break

        with _estado_lock:
            ventas_esperando_cliente[chat_id] = {
                "ventas":   ventas,
                "metodo":   None,
                "vendedor": update.effective_user.first_name,
            }
            clientes_en_proceso[chat_id] = {
                "nombre":         nombre_cliente.upper() if nombre_cliente else "",
                "tipo_id":        None,
                "identificacion": None,
                "tipo_persona":   None,
                "correo":         None,
                "telefono":       None,
                "paso":           "tipo_id" if nombre_cliente else "nombre",
                "vendedor":       update.effective_user.first_name,
            }

        if nombre_cliente:
            await query.edit_message_text(
                f"👤 Creando cliente: *{nombre_cliente.upper()}*\n¿Qué tipo de documento tiene?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🪪 CC",  callback_data=f"cli_tipoid_CC_{chat_id}"),
                    InlineKeyboardButton("🏢 NIT", callback_data=f"cli_tipoid_NIT_{chat_id}"),
                    InlineKeyboardButton("🌍 CE",  callback_data=f"cli_tipoid_CE_{chat_id}"),
                ]])
            )
        else:
            await query.edit_message_text("👤 Vamos a crear el cliente. ¿Cuál es el nombre completo?")
        return

    # ── ¿Crear cliente? No ──
    if data.startswith("cli_crear_no_"):
        with _estado_lock:
            ventas = list(ventas_pendientes.get(chat_id, []))

        if not ventas:
            await query.edit_message_text("No hay venta pendiente.")
            return

        await query.edit_message_text("➡️ De acuerdo. Procediendo sin crear el cliente...")
        await _enviar_botones_pago(query.message, chat_id, ventas)
        return

    # ── Tipo de identificación ──
    if data.startswith("cli_tipoid_"):
        sin_prefijo = data[len("cli_tipoid_"):]
        ultimo      = sin_prefijo.rfind("_")
        tipo_id     = sin_prefijo[:ultimo]

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
        sin_prefijo  = data[len("cli_persona_"):]
        ultimo       = sin_prefijo.rfind("_")
        tipo_persona = sin_prefijo[:ultimo]

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


# ─────────────────────────────────────────────
# HELPER: botones de pago sin objeto message (via bot directo)
# ─────────────────────────────────────────────

async def _enviar_botones_pago_por_chat(bot, chat_id: int, ventas: list):
    """
    Versión de _enviar_botones_pago que usa bot.send_message directamente.
    Úsala cuando no tienes un objeto message disponible.
    """
    lineas = []
    for v in ventas:
        cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
        producto     = v.get("producto", "")
        total        = parsear_precio(v.get("total", 0))
        cantidad_leg = decimal_a_fraccion_legible(cantidad_dec)
        lineas.append(f"• {cantidad_leg} {producto} ${total:,.0f}")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Efectivo",        callback_data=f"pago_efectivo_{chat_id}"),
            InlineKeyboardButton("📱 Transf.",          callback_data=f"pago_transferencia_{chat_id}"),
            InlineKeyboardButton("💳 Datáfono",         callback_data=f"pago_datafono_{chat_id}"),
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
