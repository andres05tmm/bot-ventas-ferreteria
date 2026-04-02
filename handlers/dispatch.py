"""
handlers/dispatch.py — Flujos especiales que no pasan por Claude.

Cada función maneja un caso específico y retorna:
  True  → mensaje manejado, _procesar_mensaje debe hacer return
  False → flujo no aplica, continuar con el siguiente check

TODOS los imports de ventas_state, memoria y ai son LAZY (dentro de función).
Esto es obligatorio — evita ciclos de importación con mensajes.py.
"""

# -- stdlib --
import asyncio
import json
import logging
import os
import re
import traceback

logger = logging.getLogger("ferrebot.handlers.dispatch")


async def manejar_flujo_cliente(update, chat_id: int, mensaje: str) -> bool:
    """
    Maneja los pasos del wizard de creación de cliente.
    Mover L182-L268 de _procesar_mensaje.
    Retorna True si el paso fue procesado.
    """
    from ventas_state import clientes_en_proceso, _estado_lock
    from handlers.cliente_flujo import enviar_pregunta_cliente, guardar_cliente_y_continuar

    with _estado_lock:
        en_proceso = clientes_en_proceso.get(chat_id)
    if not en_proceso:
        return False

    paso        = en_proceso.get("paso")
    texto_lower = mensaje.strip().lower()

    if paso == "nombre":
        en_proceso["nombre"] = mensaje.strip().upper()
        en_proceso["paso"]   = "tipo_id"
        with _estado_lock:
            clientes_en_proceso[chat_id] = en_proceso
        await enviar_pregunta_cliente(update.message, chat_id)
        return True

    elif paso == "identificacion":
        en_proceso["identificacion"] = mensaje.strip()
        en_proceso["paso"]           = "tipo_persona"
        with _estado_lock:
            clientes_en_proceso[chat_id] = en_proceso
        await enviar_pregunta_cliente(update.message, chat_id)
        return True

    elif paso == "correo":
        correo               = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
        en_proceso["correo"] = correo
        en_proceso["paso"]   = "telefono"
        with _estado_lock:
            clientes_en_proceso[chat_id] = en_proceso
        await update.message.reply_text("¿Cuál es el teléfono? (escribe 'no tiene' si no aplica)")
        return True

    elif paso == "telefono":
        telefono               = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
        en_proceso["telefono"] = telefono
        en_proceso["paso"]     = "ciudad"
        with _estado_lock:
            clientes_en_proceso[chat_id] = en_proceso
        await enviar_pregunta_cliente(update.message, chat_id)
        return True

    elif paso == "ciudad":
        # El callback cli_ciudad_XXX es el camino normal (botones inline).
        # Si el usuario escribe texto en este paso, recordarle que use los botones.
        await update.message.reply_text(
            "📍 Por favor selecciona la ciudad usando los botones de arriba."
        )
        await enviar_pregunta_cliente(update.message, chat_id)
        return True

    elif paso == "direccion":
        # Solo para NIT — persona natural salta este paso
        direccion               = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
        en_proceso["direccion"] = direccion
        with _estado_lock:
            clientes_en_proceso.pop(chat_id, None)
        await guardar_cliente_y_continuar(update, chat_id, en_proceso["telefono"], en_proceso)
        return True

    return False


async def manejar_flujo_excel(update, context, chat_id: int, mensaje: str) -> bool:
    """
    Maneja instrucciones sobre un Excel cargado previamente.
    Claude elige una operación predefinida y devuelve JSON con parámetros.
    ejecutar_operacion_excel() aplica la operación — nunca se ejecuta código arbitrario.
    Retorna True si el mensaje fue procesado como instrucción de Excel.
    """
    from ai.excel_gen import editar_excel_con_claude, ejecutar_operacion_excel

    excel_temp   = context.user_data.get("excel_temp")
    excel_nombre = context.user_data.get("excel_nombre")
    if not excel_temp or not os.path.exists(excel_temp):
        return False

    try:
        await update.message.reply_text("⚙️ Procesando tu Excel...")
        operacion_dict = await editar_excel_con_claude(
            mensaje, excel_temp, excel_nombre,
            update.message.from_user.first_name or "Desconocido", chat_id,
        )

        if operacion_dict.get("operacion") == "IMPOSIBLE":
            await update.message.reply_text("No pude hacer eso con el Excel. Intenta con otra instrucción.")
            return True

        resultado = await asyncio.to_thread(ejecutar_operacion_excel, excel_temp, operacion_dict)

        await update.message.reply_text(f"✅ {resultado}\n\nAquí está el Excel modificado:")
        with open(excel_temp, "rb") as f:
            await update.message.reply_document(document=f, filename=f"modificado_{excel_nombre}")

        context.user_data.pop("excel_temp", None)
        context.user_data.pop("excel_nombre", None)
        if os.path.exists(excel_temp):
            os.remove(excel_temp)
        return True
    except Exception:
        logger.error(f"Error editando Excel: {traceback.format_exc()}")
        await update.message.reply_text("Tuve un problema editando el Excel. Intenta con una instrucción diferente.")
        return True


async def manejar_flujo_pago_texto(update, context, chat_id: int, mensaje: str, vendedor: str) -> bool:
    """
    Detecta si hay una venta pendiente y el usuario canceló o escribió el método de pago como texto.
    Mover L319-L367 de _procesar_mensaje.
    Retorna True si el mensaje fue procesado.
    """
    from ventas_state import ventas_pendientes, mensajes_standby, registrar_ventas_con_metodo, _estado_lock
    from handlers.callbacks import _enviar_botones_pago as _botones_central, _procesar_siguiente_standby

    with _estado_lock:
        _ventas_pend = list(ventas_pendientes.get(chat_id, []))

    if not _ventas_pend:
        return False

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
            await _procesar_siguiente_standby(
                context.bot, update.message, chat_id, standby_pendiente, vendedor
            )
        return True

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
            usuario_id = context.user_data.get("usuario", {}).get("id")
            confirmaciones = await asyncio.to_thread(
                registrar_ventas_con_metodo, ventas, metodo_detectado, vendedor, chat_id, usuario_id
            )
            emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo_detectado, "✅")
            await update.message.reply_text(
                f"✅ Venta registrada — {emoji} {metodo_detectado.capitalize()}\n\n" + "\n".join(confirmaciones)
            )
        with _estado_lock:
            standby_list = mensajes_standby.pop(chat_id, [])

        # CORRECCIÓN punto 7: usar _procesar_siguiente_standby en lugar del loop directo
        if standby_list:
            await _procesar_siguiente_standby(
                context.bot, update.message, chat_id, standby_list, vendedor
            )
        return True

    return False


async def manejar_flujo_correccion(update, context, chat_id: int, mensaje: str, vendedor: str) -> bool:
    """
    Maneja el modo de modificación/corrección de una venta existente.
    Mover L369-L543 de _procesar_mensaje.
    Retorna True si el mensaje fue procesado como corrección.
    """
    from ventas_state import esperando_correccion, ventas_pendientes, _estado_lock
    from ventas_state import get_historial, agregar_al_historial

    with _estado_lock:
        en_correccion = esperando_correccion.pop(chat_id, False)

    if en_correccion == "modificar":
        from handlers.callbacks import _enviar_botones_pago as _botones_central, _enviar_confirmacion_con_metodo
        from ai import procesar_con_claude, procesar_acciones_async

        with _estado_lock:
            ventas_actuales = list(ventas_pendientes.get(chat_id, []))

        metodo_original = None
        if ventas_actuales and ventas_actuales[0].get("metodo_pago"):
            metodo_original = ventas_actuales[0]["metodo_pago"]

        # ── PARSER RÁPIDO: agregar productos no encontrados sin Claude ──────
        # Formato: "modificar = 2---Tornillo especial=5000, 1---Clavija=3000"
        # o línea por línea:
        #   2---Tornillo especial=5000
        #   1---Clavija=3000

        # ── Parser de acciones explícitas ─────────────────────────────────
        # Prefijo obligatorio para evitar confusión con correcciones normales:
        #   añadir/agregar N nombre = total  → agrega producto a la venta
        #   quitar/eliminar/borrar nombre    → elimina de la venta
        #   reemplazar nombre [por N nuevo=total] → quita y opcionalmente agrega
        # Sin prefijo → va a Claude (correcciones de precio, cantidad, etc.)

        # Patrón con cantidad obligatoria: "2 nombre = 5000"
        _PATRON_ITEM_MOD = re.compile(
            r'(\d+(?:[.,]\d+)?)\s+([a-zA-Z\xe1\xe9\xed\xf3\xfa\xf1\xc1\xc9\xcd\xd3\xda\xd1][^=]+?)\s*=\s*(\d+)',
            re.IGNORECASE
        )
        # Patrón sin cantidad (default=1): "nombre = 5000"
        _PATRON_ITEM_MOD_SIN_CANT = re.compile(
            r'([a-zA-Z\xe1\xe9\xed\xf3\xfa\xf1\xc1\xc9\xcd\xd3\xda\xd1][^=]+?)\s*=\s*(\d+)',
            re.IGNORECASE
        )

        def _parse_accion_mod(msg):
            ml = msg.strip().lower()
            _PREFIJOS_ANADIR = ('añadir ', 'anadir ', 'agregar ', 'añade ', 'añade:', 'anadir:', 'agrega ', 'agrega:')
            if ml.startswith(_PREFIJOS_ANADIR):
                resto = re.sub(r'^(a[nñ]ad[ei][r]?|agreg[ao][r]?)[:\s]+', '', msg.strip(), flags=re.IGNORECASE).strip()
                m = _PATRON_ITEM_MOD.match(resto)
                if m:
                    return {'accion': 'anadir',
                            'cantidad': float(m.group(1).replace(',', '.')),
                            'producto': m.group(2).strip(),
                            'total': int(m.group(3))}
                # Sin cantidad explícita → default 1
                m2 = _PATRON_ITEM_MOD_SIN_CANT.match(resto)
                if m2:
                    return {'accion': 'anadir',
                            'cantidad': 1,
                            'producto': m2.group(1).strip(),
                            'total': int(m2.group(2))}
            if ml.startswith(('quitar ', 'eliminar ', 'borrar ', 'sacar ', 'quita ', 'quita:', 'elimina ', 'borra ')):
                resto = re.sub(r'^(quitar|eliminar|borrar|sacar)\s+(los?\s+|las?\s+)?',
                                    '', msg.strip(), flags=re.IGNORECASE)
                return {'accion': 'quitar', 'termino': resto.strip()}
            if ml.startswith(('reemplazar ', 'cambiar ')):
                resto = re.sub(r'^(reemplazar|cambiar)\s+', '', msg.strip(), flags=re.IGNORECASE)
                if re.search(r'\s+por\s+', resto, flags=re.IGNORECASE):
                    partes = re.split(r'\s+por\s+', resto, maxsplit=1, flags=re.IGNORECASE)
                    m = _PATRON_ITEM_MOD.match(partes[1].strip())
                    if m:
                        return {'accion': 'reemplazar',
                                'termino': partes[0].strip(),
                                'cantidad': float(m.group(1).replace(',', '.')),
                                'producto': m.group(2).strip(),
                                'total': int(m.group(3))}
                return {'accion': 'quitar', 'termino': resto.strip()}
            return None

        _acciones_parsed = []
        for _linea in mensaje.strip().splitlines():
            _linea = _linea.strip()
            if not _linea:
                continue
            _a = _parse_accion_mod(_linea)
            if _a:
                _acciones_parsed.append(_a)
            else:
                _acciones_parsed = []
                break

        if _acciones_parsed:
            with _estado_lock:
                _venta_actual = list(ventas_pendientes.get(chat_id, []))
            _resumen_cambios = []
            for _ac in _acciones_parsed:
                if _ac['accion'] == 'anadir':
                    _venta_actual.append({
                        "producto":    _ac['producto'],
                        "cantidad":    _ac['cantidad'],
                        "total":       _ac['total'],
                        "metodo_pago": metodo_original or "",
                    })
                    _resumen_cambios.append(f"\u2795 {_ac['cantidad']:g} {_ac['producto']} ${_ac['total']:,}")
                elif _ac['accion'] == 'quitar':
                    _t = _ac['termino'].lower()
                    _antes = len(_venta_actual)
                    _venta_actual = [v for v in _venta_actual if _t not in v.get('producto','').lower()]
                    if len(_venta_actual) < _antes:
                        _resumen_cambios.append(f"\u2796 {_ac['termino']} (eliminado)")
                    else:
                        _resumen_cambios.append(f"\u26a0\ufe0f No encontr\xe9 '{_ac['termino']}' en la venta")
                elif _ac['accion'] == 'reemplazar':
                    _t = _ac['termino'].lower()
                    _venta_actual = [v for v in _venta_actual if _t not in v.get('producto','').lower()]
                    _venta_actual.append({
                        "producto":    _ac['producto'],
                        "cantidad":    _ac['cantidad'],
                        "total":       _ac['total'],
                        "metodo_pago": metodo_original or "",
                    })
                    _resumen_cambios.append(
                        f"\U0001f501 {_ac['termino']} \u2192 {_ac['cantidad']:g} {_ac['producto']} ${_ac['total']:,}"
                    )
            with _estado_lock:
                ventas_pendientes[chat_id] = _venta_actual
            _total_general = sum(v.get("total", 0) for v in _venta_actual)
            await update.message.reply_text(
                "\n".join(_resumen_cambios) + f"\nTotal venta: ${_total_general:,.0f}"
            )
            if metodo_original:
                await _enviar_confirmacion_con_metodo(update.message, chat_id, _venta_actual, metodo_original)
            else:
                await _botones_central(update.message, chat_id, _venta_actual)
            return True
        # ── Fin parser — sin prefijo reconocido, va a Claude normal ──────────

        resumen_venta = json.dumps(ventas_actuales, ensure_ascii=False)

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
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_conocido, nota=nota)
            elif metodo_original:
                with _estado_lock:
                    for v in ventas_pendientes.get(chat_id, []):
                        v["metodo_pago"] = metodo_original
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_original, nota=nota)
            else:
                if nota:
                    await update.message.reply_text(nota)
                await _botones_central(update.message, chat_id, ventas_nuevas)
        elif texto_respuesta:
            await update.message.reply_text(texto_respuesta)
        return True

    elif en_correccion:
        from handlers.callbacks import _enviar_botones_pago as _botones_central, _enviar_confirmacion_con_metodo
        from ai import procesar_con_claude, procesar_acciones_async

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
            await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas, metodo_conocido)
        elif "PEDIR_METODO_PAGO" in acciones:
            await _botones_central(update.message, chat_id, ventas)
        return True

    return False


async def manejar_rechazo_cliente(update, chat_id: int, mensaje: str) -> bool:
    """
    Usuario respondió "no" a la pregunta de crear cliente.
    Mover L563-L580 de _procesar_mensaje.
    Retorna True si el mensaje era un rechazo y fue procesado.
    """
    from ventas_state import ventas_pendientes, clientes_en_proceso, _estado_lock

    with _estado_lock:
        _esperando_cliente_yn = ventas_pendientes.get(chat_id) and not clientes_en_proceso.get(chat_id)

    if not _esperando_cliente_yn:
        return False

    _msg_lower    = mensaje.strip().lower()
    _respuesta_no = {"no", "nop", "nope", "nel", "sin cliente", "registra sin cliente", "registra asi"}
    if _msg_lower in _respuesta_no or _msg_lower.startswith("no "):
        with _estado_lock:
            ventas_para_registrar = list(ventas_pendientes.get(chat_id, []))
        if ventas_para_registrar:
            from handlers.callbacks import _enviar_botones_pago as _botones_central, _enviar_confirmacion_con_metodo
            await update.message.reply_text("👍 Registrando la venta sin crear el cliente...")
            metodo_conocido = ventas_para_registrar[0].get("metodo_pago", "").lower()
            if metodo_conocido:
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_para_registrar, metodo_conocido)
            else:
                await _botones_central(update.message, chat_id, ventas_para_registrar)
            return True

    return False
