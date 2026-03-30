"""
Handlers de mensajes: texto, audio (voz) y documentos Excel.

CORRECCIONES v2:
  - manejar_audio: ruta_audio se inicializa a None ANTES del try/finally para
    evitar NameError si download_to_drive falla antes de asignar la variable
  - mensajes_standby: se usa agregar_a_standby() de ventas_state que tiene cap MAX_STANDBY
  - Docstring ANTES del import logging

CORRECCIONES v3:
  - Todos los imports de stdlib (re, json, base64, datetime) movidos al nivel de módulo.
  - Imports de callbacks hoistados (no hay ciclo: callbacks no importa mensajes).
  - Imports que SÍ crean ciclo (handlers.comandos → mensajes) siguen siendo lazy.
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import base64
import json
import logging
import asyncio
import os
import re
import tempfile
import traceback
from datetime import datetime

# ── terceros ──────────────────────────────────────────────────────────────────
import openpyxl
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# ── propios ───────────────────────────────────────────────────────────────────
import config
from ai import procesar_con_claude, procesar_acciones, procesar_acciones_async, editar_excel_con_claude
from ventas_state import (
    agregar_al_historial, get_historial,
    ventas_pendientes, clientes_en_proceso, _estado_lock,
    get_chat_lock, registrar_ventas_con_metodo, mensajes_standby,
    limpiar_pendientes_expirados,
    esperando_correccion, ventas_esperando_cliente,
    agregar_a_standby,
    mensaje_contexto_pendiente,
)
from handlers.comandos import manejar_flujo_agregar_producto
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, corregir_texto_audio
from memoria import invalidar_cache_memoria, importar_catalogo_desde_excel
# Callbacks: no crean ciclo (callbacks.py no importa mensajes.py en nivel de módulo)
from handlers.callbacks import (
    _enviar_botones_pago as _botones_central,
    _enviar_confirmacion_con_metodo,
    _procesar_siguiente_standby,
)
from handlers.parsing import parsear_actualizacion_masiva as _parsear_actualizacion_masiva
from handlers.cliente_flujo import enviar_pregunta_cliente as _enviar_pregunta_cliente

logger = logging.getLogger("ferrebot.mensajes")


async def _enviar_botones_pago(message, chat_id: int, ventas: list):
    """Delega a callbacks._enviar_botones_pago (importado al nivel de módulo)."""
    await _botones_central(message, chat_id, ventas)



async def _manejar_actualizacion_masiva(update, vendedor: str, pares: list):
    """Actualiza todos los precios directamente en PostgreSQL."""
    import db as _db
    from memoria import buscar_producto_en_catalogo, invalidar_cache_memoria

    exitos, errores = [], []
    for item in pares:
        nombre, precio, fraccion, precio_mayorista = item if len(item) == 4 else (*item, None)
        try:
            prod = buscar_producto_en_catalogo(nombre)
            nombre_display = prod["nombre"] if prod else nombre

            if not prod:
                errores.append(f"❌ {nombre}: no encontrado")
                continue

            row = _db.query_one(
                "SELECT id, precio_unidad FROM productos WHERE nombre_lower = %s AND activo = TRUE",
                [prod.get("nombre_lower", nombre.lower())]
            )
            if not row:
                errores.append(f"❌ {nombre}: no encontrado en BD")
                continue

            if precio_mayorista is not None:
                # precio_unidad + precio_por_cantidad (tornillería)
                _db.execute(
                    "UPDATE productos SET precio_unidad = %s, updated_at = NOW() WHERE id = %s",
                    [round(precio), row["id"]],
                )
                _db.execute(
                    """
                    INSERT INTO productos_precio_cantidad
                        (producto_id, umbral, precio_bajo_umbral, precio_sobre_umbral)
                    VALUES (%s, 50, %s, %s)
                    ON CONFLICT (producto_id) DO UPDATE
                    SET precio_bajo_umbral  = EXCLUDED.precio_bajo_umbral,
                        precio_sobre_umbral = EXCLUDED.precio_sobre_umbral
                    """,
                    (row["id"], round(precio), round(precio_mayorista)),
                )
                linea = f"✅ {nombre_display}: ${int(precio):,} / ${int(precio_mayorista):,} ×50".replace(",", ".")
            elif fraccion:
                try:
                    # float("1/4") lanza ValueError — parsear manualmente
                    if "/" in str(fraccion):
                        num, den = str(fraccion).split("/", 1)
                        decimal_frac = int(num.strip()) / int(den.strip())
                    else:
                        decimal_frac = float(fraccion)
                    precio_unit = round(precio / decimal_frac, 2) if decimal_frac else precio
                except (ValueError, ZeroDivisionError, TypeError):
                    precio_unit = precio
                _db.execute(
                    """
                    INSERT INTO productos_fracciones
                        (producto_id, fraccion, precio_total, precio_unitario)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT uq_prod_fraccion DO UPDATE
                    SET precio_total    = EXCLUDED.precio_total,
                        precio_unitario = EXCLUDED.precio_unitario
                    """,
                    (row["id"], fraccion, round(precio), int(precio_unit)),
                )
                linea = f"✅ {nombre_display} {fraccion} → ${int(precio):,}".replace(",", ".")
            else:
                _db.execute(
                    "UPDATE productos SET precio_unidad = %s, updated_at = NOW() WHERE id = %s",
                    [round(precio), row["id"]],
                )
                linea = f"✅ {nombre_display} → ${int(precio):,}".replace(",", ".")

            exitos.append(linea)
        except Exception as e:
            errores.append(f"❌ {nombre}: {e}")

    invalidar_cache_memoria()

    resumen = f"💰 *{len(exitos)} precio(s) actualizado(s):*\n" + "\n".join(exitos)
    if errores:
        resumen += "\n\n" + "\n".join(errores)

    await update.message.reply_text(resumen, parse_mode="Markdown")

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje  = update.message.text
    chat_id  = update.message.chat_id
    vendedor = update.message.from_user.first_name or "Desconocido"

    if mensaje.startswith("/"):
        return

    # ── "sin foto" en flujo /factura o /abonar ───────────────────────────────
    if mensaje.strip().lower() in ("sin foto", "sinfoto", "sin fotos", "omitir", "skip"):
        if (context.user_data.get("esperando_foto_factura")
                or context.user_data.get("esperando_foto_abono")):
            context.user_data.pop("esperando_foto_factura", None)
            context.user_data.pop("esperando_foto_abono", None)
            await update.message.reply_text("👍 Foto omitida. La factura queda registrada sin foto.")
            return

    async with get_chat_lock(chat_id):
        await _procesar_mensaje(update, context, mensaje, chat_id, vendedor)


async def _procesar_mensaje(update, context, mensaje, chat_id, vendedor):
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Flujo paso a paso de agregar producto ──
    if await manejar_flujo_agregar_producto(update, context):
        return

    # ── Modo actualización de precios (/actualizar_precio) ──
    from handlers.comandos import manejar_mensaje_precio
    if await manejar_mensaje_precio(update, mensaje):
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
            def _insertar_cliente_pg():
                import db as _db
                if not _db.DB_DISPONIBLE:
                    return False
                try:
                    _db.execute(
                        """INSERT INTO clientes
                               (nombre, tipo_id, identificacion, tipo_persona, correo, telefono)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT DO NOTHING""",
                        (
                            en_proceso["nombre"].upper().strip(),
                            en_proceso["tipo_id"],
                            en_proceso["identificacion"].strip() or None,
                            en_proceso["tipo_persona"],
                            en_proceso.get("correo", "").strip() or None,
                            telefono.strip() or None,
                        ),
                    )
                    return True
                except Exception as _e:
                    logger.error("Error INSERT cliente PG: %s", _e)
                    return False

            ok = await asyncio.to_thread(_insertar_cliente_pg)
            invalidar_cache_memoria()
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

            rutas_sospechosas  = re.findall(r'''load_workbook\s*\(\s*['"]([^'"]+)['"]''', codigo)
            rutas_sospechosas += re.findall(r'''\.save\s*\(\s*['"]([^'"]+)['"]''', codigo)
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
                await _enviar_botones_pago(update.message, chat_id, _venta_actual)
            return
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
                    await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_para_registrar, metodo_conocido)
                else:
                    await _enviar_botones_pago(update.message, chat_id, ventas_para_registrar)
                return

    # ── Actualización de precios: ahora es SOLO via /actualizar_precio ──
    # (Eliminada la intercepción automática que confundía ventas con precios)

    # ── Crear cliente sin venta: "agregar cliente: nombre" ──
    _msg_lower_cli = mensaje.strip().lower()
    _prefijos_cli = ("agregar cliente:", "nuevo cliente:", "crear cliente:", "add cliente:")
    _match_cli = next((p for p in _prefijos_cli if _msg_lower_cli.startswith(p)), None)
    if _match_cli:
        nombre_nuevo = mensaje.strip()[len(_match_cli):].strip()
        if nombre_nuevo:
            with _estado_lock:
                clientes_en_proceso[chat_id] = {"paso": "tipo_id", "nombre": nombre_nuevo}
            await _enviar_pregunta_flujo_cliente(update.message, chat_id)
        else:
            with _estado_lock:
                clientes_en_proceso[chat_id] = {"paso": "nombre"}
            await _enviar_pregunta_flujo_cliente(update.message, chat_id)
        return

    # ── Flujo normal con Claude ──
    try:
        limpiar_pendientes_expirados()
        # ── Reinyectar contexto pendiente si Claude solo hizo una pregunta antes ──
        _ctx_previo = None
        with _estado_lock:
            _ctx_previo = mensaje_contexto_pendiente.pop(chat_id, None)

        _mensaje_para_claude = mensaje
        if _ctx_previo and _ctx_previo != mensaje:
            # Combinar: contexto original + respuesta actual
            _mensaje_para_claude = f"{_ctx_previo} — {mensaje}"
            logging.getLogger("ferrebot.mensajes").info(
                f"[CONTEXTO] Reinyectando contexto previo: '{_ctx_previo}' + '{mensaje}'"
            )

        historial     = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", f"{vendedor}: {mensaje}")
        _modelo_pref = context.user_data.get("modelo_preferido", None)
        respuesta_raw = await procesar_con_claude(f"{vendedor}: {_mensaje_para_claude}", vendedor, historial, modelo_preferido=_modelo_pref)
        texto_respuesta, acciones, archivos_excel = await procesar_acciones_async(respuesta_raw, vendedor, chat_id)
        agregar_al_historial(chat_id, "assistant", texto_respuesta)

        pedir_metodo        = "PEDIR_METODO_PAGO"    in acciones
        iniciar_cliente     = "INICIAR_FLUJO_CLIENTE" in acciones
        pago_pend_aviso     = "PAGO_PENDIENTE_AVISO"  in acciones
        confirmacion_accion = next((a for a in acciones if a.startswith("PEDIR_CONFIRMACION:")), None)
        cliente_desconocido = next((a for a in acciones if a.startswith("CLIENTE_DESCONOCIDO:")), None)
        logging.getLogger("ferrebot.mensajes").debug(f"[ACCIONES] acciones={acciones} | pedir_metodo={pedir_metodo}")

        # ── Guardar contexto pendiente si Claude solo hizo una pregunta ──
        # Condición: hay texto (una pregunta), pero NO hay ninguna acción de venta/pago/cliente
        _acciones_venta = (pedir_metodo or confirmacion_accion or cliente_desconocido
                           or pago_pend_aviso or iniciar_cliente
                           or any(a.startswith("[VENTA]") or a.startswith("PRECIO_ACTUALIZADO") for a in acciones))
        if texto_respuesta and not _acciones_venta and "?" in texto_respuesta:
            with _estado_lock:
                mensaje_contexto_pendiente[chat_id] = _mensaje_para_claude
            logging.getLogger("ferrebot.mensajes").info(
                f"[CONTEXTO] Guardando contexto pendiente para chat {chat_id}: '{_mensaje_para_claude[:60]}...'"
            )

        _acciones_internas = ("PEDIR_METODO_PAGO", "INICIAR_FLUJO_CLIENTE", "PAGO_PENDIENTE_AVISO")

        # ── Separar aviso "no encontré en catálogo" del resto del texto ──
        _aviso_no_encontrado = ""
        if texto_respuesta:
            _lineas = texto_respuesta.splitlines()
            def _es_aviso_catalogo(l):
                ls = l.strip()
                return ls.startswith("⚠️") and ("catálogo" in ls.lower() or "catalogo" in ls.lower())

            _aviso_lineas_out = []
            _resto_lineas_out = []
            _en_aviso = False
            for _l in _lineas:
                if _es_aviso_catalogo(_l):
                    _en_aviso = True
                    _aviso_lineas_out.append(_l)
                elif _en_aviso:
                    _ls = _l.strip()
                    _es_nueva_accion = (_ls.startswith("✅") or _ls.startswith("🧠")
                                        or _ls.startswith("[VENTA]") or _ls.startswith("🧾")
                                        or _ls.startswith("💰") or _ls.startswith("📋")
                                        or (_ls.startswith("⚠️") and "catálogo" not in _ls.lower()))
                    if _es_nueva_accion or not _ls:
                        _en_aviso = False
                        _resto_lineas_out.append(_l)
                    else:
                        _aviso_lineas_out.append(_l)
                else:
                    _resto_lineas_out.append(_l)

            _aviso_no_encontrado = "\n".join(_aviso_lineas_out).strip()
            texto_respuesta      = "\n".join(_resto_lineas_out).strip()

        # Enviar aviso de no encontrado PRIMERO, como mensaje separado
        if _aviso_no_encontrado:
            await update.message.reply_text(_aviso_no_encontrado)

            # ── Guardar productos no encontrados en memoria ────────────────
            try:
                # Regex flexible: acepta con/sin tilde, aplanar multilinea
                _aviso_flat = " ".join(_aviso_no_encontrado.splitlines())
                _match_pend = re.search(
                    r'no encontr[eé] en cat[aá]logo[:\s]+(.+)',
                    _aviso_flat,
                    re.IGNORECASE
                )
                if _match_pend:
                    _nombres_raw = _match_pend.group(1).strip().rstrip('.')
                    # Pueden venir separados por coma o "y"
                    _nombres_lista = [
                        n.strip().strip('"\'').lower()
                        for n in re.split(r',| y ', _nombres_raw)
                        if n.strip()
                    ]
                    import db as _db_pend
                    if not _db_pend.DB_DISPONIBLE:
                        logger.warning("[PENDIENTES] Base de datos no disponible — no se guardaron pendientes")
                    else:
                        _hoy = datetime.now().strftime("%Y-%m-%d")
                        _hora = datetime.now().strftime("%H:%M")
                        _nuevos = 0
                        for _np in _nombres_lista:
                            if not _np:
                                continue
                            _existe = _db_pend.query_one(
                                "SELECT id FROM productos_pendientes WHERE LOWER(nombre) = LOWER(%s) AND fecha = %s",
                                (_np, _hoy),
                            )
                            if not _existe:
                                _db_pend.execute(
                                    "INSERT INTO productos_pendientes (nombre, fecha, hora) VALUES (%s, %s, %s)",
                                    (_np, _hoy, _hora),
                                )
                                _nuevos += 1
                        if _nuevos:
                            logger.info(f"[PENDIENTES] +{_nuevos} productos guardados en PG: {_nombres_lista}")
            except Exception as _e_pend:
                logger.warning(f"[PENDIENTES] Error guardando pendientes: {_e_pend}")

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
        _tb = traceback.format_exc()
        logger.error("Error en mensaje: %s", _tb)
        print(f"[ERROR _procesar_mensaje]\n{_tb}")  # visible en Railway
        await update.message.reply_text("Tuve un problema. Intenta de nuevo.")




async def _manejar_foto_factura_o_abono(update, context) -> bool:
    """
    Intercepta fotos cuando el usuario está en flujo /factura o /abonar.
    Retorna True si la foto fue manejada (y manejar_foto no debe continuar).
    """
    fac_factura = context.user_data.pop("esperando_foto_factura", None)
    fac_abono   = context.user_data.pop("esperando_foto_abono", None)
    fac_id      = fac_factura or fac_abono

    if not fac_id:
        return False

    chat_id = update.message.chat_id
    await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")

    try:
        foto    = update.message.photo[-1]
        archivo = await foto.get_file()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            ruta_tmp = tmp.name
        await archivo.download_to_drive(ruta_tmp)

        # Buscar factura en PostgreSQL (fuente de verdad)
        import db as _db
        row = await asyncio.to_thread(
            _db.query_one,
            "SELECT id, proveedor, fecha FROM facturas_proveedores WHERE id = %s",
            (fac_id.upper(),)
        )
        if not row:
            await update.message.reply_text(f"⚠️ Factura {fac_id} no encontrada.")
            return True

        proveedor = row["proveedor"]
        fecha_fac = str(row.get("fecha", ""))[:10]
        hoy       = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")

        if fac_factura:
            nombre_archivo = f"{fecha_fac}_{fac_id}.jpg"
        else:
            # Contar abonos existentes para nombrar el comprobante
            n_abono_row = await asyncio.to_thread(
                _db.query_one,
                "SELECT COUNT(*) AS n FROM facturas_abonos WHERE factura_id = %s",
                (fac_id.upper(),)
            )
            n_abono = int((n_abono_row or {}).get("n", 0))
            nombre_archivo = f"{hoy}_{fac_id}_abono{n_abono}.jpg"

        # Subir a Cloudinary
        from handlers.comandos import upload_foto_cloudinary
        with open(ruta_tmp, "rb") as _f:
            foto_bytes = _f.read()
        try:
            import os as _os; _os.unlink(ruta_tmp)
        except Exception:
            pass

        carpeta   = f"ferreteria/{proveedor.lower().replace(' ', '_')}"
        public_id = nombre_archivo.replace(".jpg", "")
        result    = await upload_foto_cloudinary(foto_bytes, public_id, carpeta)

        if not result["ok"]:
            await update.message.reply_text(
                f"⚠️ No se pudo subir la foto a Cloudinary: {result.get('error','')}"
            )
            return True

        # Guardar URL en Postgres
        if fac_factura:
            await asyncio.to_thread(
                _db.execute,
                "UPDATE facturas_proveedores SET foto_url=%s, foto_nombre=%s WHERE id=%s",
                (result["url"], nombre_archivo, fac_id.upper())
            )
        else:
            await asyncio.to_thread(
                _db.execute,
                "UPDATE facturas_abonos SET foto_url=%s, foto_nombre=%s "
                "WHERE factura_id=%s AND id = ("
                "  SELECT id FROM facturas_abonos WHERE factura_id=%s ORDER BY id DESC LIMIT 1"
                ")",
                (result["url"], nombre_archivo, fac_id.upper(), fac_id.upper())
            )

        tipo_txt = "factura" if fac_factura else "comprobante de abono"
        await update.message.reply_text(
            f"📎 Foto del {tipo_txt} guardada en Cloudinary\n"
            f"🏪 {proveedor} · {fac_id}\n"
            f"[Ver foto]({result['url']})",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return True

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error guardando foto: {e}")
        return True


async def manejar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler de fotos: transcribe ventas anotadas a mano usando visión de Claude.
    Descarga la foto, la convierte a base64 y la manda a procesar_con_claude
    con el system prompt completo (catálogo incluido).
    """
    vendedor = update.message.from_user.first_name or "Desconocido"
    chat_id  = update.message.chat_id

    async with get_chat_lock(chat_id):
        await _procesar_foto(update, context, vendedor, chat_id)


async def _procesar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE, vendedor: str, chat_id: int):

    ruta_foto = None

    try:
        # ── Interceptar fotos de facturas/abonos ─────────────────────────
        if await _manejar_foto_factura_o_abono(update, context):
            return

        # Chequeo de pago pendiente: si hay venta esperando, la foto va al standby
        with _estado_lock:
            _ventas_pend = list(ventas_pendientes.get(chat_id, []))

        if _ventas_pend:
            await update.message.reply_text("⚠️ Primero confirma el método de pago de la venta anterior:")
            await _enviar_botones_pago(update.message, chat_id, _ventas_pend)
            return

        await update.message.reply_text("📸 Leyendo la foto...")
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        # Descargar la foto en la resolución más alta disponible
        foto = update.message.photo[-1]  # última = máxima resolución
        _archivo = None
        for _intento in range(3):
            try:
                _archivo = await foto.get_file()
                break
            except Exception as _e:
                if _intento < 2:
                    await asyncio.sleep(1.5 * (_intento + 1))
                else:
                    raise _e

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            ruta_foto = tmp.name

        for _intento in range(3):
            try:
                await _archivo.download_to_drive(ruta_foto)
                break
            except Exception as _e:
                if _intento < 2:
                    await asyncio.sleep(1.5 * (_intento + 1))
                else:
                    raise _e

        # Convertir a base64
        with open(ruta_foto, "rb") as f:
            imagen_b64 = base64.b64encode(f.read()).decode("utf-8")

        # Detectar tipo de imagen (siempre jpeg en Telegram)
        media_type = "image/jpeg"

        # Caption de la foto como contexto adicional (si el vendedor escribió algo)
        caption = update.message.caption or ""
        mensaje_usuario = f"{vendedor}: {caption}" if caption else f"{vendedor}: foto de ventas"

        # Procesar con Claude (visión activa)
        historial = get_historial(chat_id)
        agregar_al_historial(chat_id, "user", mensaje_usuario)

        # Fix 1: Forzar Sonnet — Haiku no tiene buena vision de manuscritos
        respuesta_raw = await procesar_con_claude(
            mensaje_usuario,
            vendedor,
            historial,
            imagen_b64=imagen_b64,
            imagen_media_type=media_type,
            modelo_preferido="sonnet",
        )

        # Fix 4/5: Extraer resumen del texto de Claude y mostrar confirmacion
        # ANTES de ejecutar las ventas. El vendedor aprueba o cancela la lectura.
        import re as _re
        import json as _json

        # Extraer el texto visible (sin los tags [VENTA])
        _texto_preview = re.sub(r'\[VENTA\].*?\[/VENTA\]', '', respuesta_raw, flags=re.DOTALL).strip()

        # Contar ventas detectadas para el boton
        _ventas_raw = re.findall(r'\[VENTA\](.*?)\[/VENTA\]', respuesta_raw, re.DOTALL)
        _n_ventas = len(_ventas_raw)

        if _n_ventas == 0:
            # Nada registrable — solo mostrar lo que Claude dijo
            texto_limpio = _texto_preview or "No pude leer productos en la foto. Intenta con mejor iluminacion."
            await update.message.reply_text(texto_limpio)
            agregar_al_historial(chat_id, "assistant", texto_limpio)
            return

        # Guardar respuesta_raw en estado pendiente de confirmacion
        from ventas_state import fotos_pendientes_confirmacion
        with _estado_lock:
            fotos_pendientes_confirmacion[chat_id] = respuesta_raw

        agregar_al_historial(chat_id, "assistant", _texto_preview)

        # Mostrar resumen + botones de confirmar/cancelar
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        _msg_confirm = (
            (_texto_preview + "\n\n" if _texto_preview else "") +
            f"¿Registro estas {_n_ventas} {'venta' if _n_ventas == 1 else 'ventas'}?"
        )
        _kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Sí, registrar", callback_data=f"foto_confirmar_{chat_id}"),
            InlineKeyboardButton("❌ Cancelar",        callback_data=f"foto_cancelar_{chat_id}"),
        ]])
        await update.message.reply_text(_msg_confirm, reply_markup=_kb)

    except Exception as e:
        logger.error(f"[foto] Error procesando imagen: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error procesando la foto: {e}")
    finally:
        if ruta_foto and os.path.exists(ruta_foto):
            try:
                os.unlink(ruta_foto)
            except Exception:
                pass

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

            resumen_venta = json.dumps(ventas_actuales, ensure_ascii=False)

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
                    await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_nuevas, metodo_conocido, nota=nota)
                elif metodo_original:
                    with _estado_lock:
                        for v in ventas_pendientes.get(chat_id, []):
                            v["metodo_pago"] = metodo_original
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
