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

async def comando_precios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memoria  = cargar_memoria()
    catalogo = memoria.get("catalogo", {})
    precios  = memoria.get("precios", {})

    if not catalogo and not precios:
        await update.message.reply_text("No hay precios guardados aun.")
        return

    if catalogo:
        categorias: dict = {}
        for prod in catalogo.values():
            cat    = prod.get("categoria", "Otros")
            sufijo = " *" if prod.get("precios_fraccion") else ""
            categorias.setdefault(cat, []).append(f"  • {prod['nombre']}: ${prod['precio_unidad']:,}{sufijo}")

        await update.message.reply_text(
            f"🧠 Catalogo de precios ({len(catalogo)} productos)\n"
            f"* = tiene precios por fraccion\n\nTe envio una categoria a la vez:"
        )
        for cat, items in sorted(categorias.items()):
            encabezado = f"📂 {cat} ({len(items)} productos):\n"
            bloque = encabezado
            for item in items:
                linea = item + "\n"
                if len(bloque) + len(linea) > 4000:
                    await update.message.reply_text(bloque)
                    bloque = f"📂 {cat} (continuacion):\n"
                bloque += linea
            if bloque.strip():
                await update.message.reply_text(bloque)
    else:
        items = [f"  • {p}: ${v:,}" for p, v in sorted(precios.items())]
        await update.message.reply_text(f"🧠 Precios guardados ({len(items)} productos):")
        bloque = ""
        for item in items:
            linea = item + "\n"
            if len(bloque) + len(linea) > 4000:
                await update.message.reply_text(bloque)
                bloque = ""
            bloque += linea
        if bloque.strip():
            await update.message.reply_text(bloque)


# ─────────────────────────────────────────────
# /caja, /gastos, /inventario
# ─────────────────────────────────────────────

async def comando_caja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resumen = obtener_resumen_caja()
    await update.message.reply_text(f"💰 {resumen}")


async def comando_gastos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gastos = cargar_gastos_hoy()
    if not gastos:
        await update.message.reply_text("No hay gastos registrados hoy.")
        return
    texto = "💸 Gastos de hoy:\n\n"
    total = 0
    for g in gastos:
        texto += f"• {g['concepto']}: ${g['monto']:,.0f} ({g['categoria']}) — {g['origen']}\n"
        total += g["monto"]
    texto += f"\nTotal gastos: ${total:,.0f}"
    await update.message.reply_text(texto)


async def comando_inventario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inventario = cargar_inventario()
    if not inventario:
        await update.message.reply_text(
            "No hay productos en inventario aun. Dile al bot cuantas unidades tienes de cada producto."
        )
        return
    texto   = "📦 Inventario actual:\n\n"
    alertas = []
    for producto, datos in inventario.items():
        if isinstance(datos, dict):
            cantidad = datos.get("cantidad", 0)
            minimo   = datos.get("minimo", 3)
            emoji    = "⚠️" if cantidad <= minimo else "✅"
            texto   += f"{emoji} {producto}: {cantidad} unidades\n"
            if cantidad <= minimo:
                alertas.append(producto)
    if alertas:
        texto += f"\n⚠️ Stock bajo en: {', '.join(alertas)}"
    await update.message.reply_text(texto)


# ─────────────────────────────────────────────
# /clientes
# ─────────────────────────────────────────────

async def comando_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        termino    = " ".join(args)
        resultados = await asyncio.to_thread(buscar_clientes_multiples, termino, 5)
        if not resultados:
            await update.message.reply_text(f"No encontre clientes con '{termino}'.")
            return
        texto = f"👥 Clientes encontrados para '{termino}':\n\n"
        for c in resultados:
            nombre = c.get("Nombre tercero", "")
            id_c   = c.get("Identificación", "")
            tipo   = c.get("Tipo de identificación", "")
            texto += f"• {nombre} — {tipo}: {id_c}\n"
        await update.message.reply_text(texto)
    else:
        clientes = await asyncio.to_thread(cargar_clientes)
        await update.message.reply_text(
            f"👥 Tienes {len(clientes)} clientes registrados.\n\n"
            f"Usa /clientes [nombre] para buscar uno especifico.\n"
            f"O dile al bot: 'Crea un cliente nuevo' para agregar uno."
        )


# ─────────────────────────────────────────────
# /sheets
# ─────────────────────────────────────────────

async def comando_sheets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.SHEETS_ID:
        await update.message.reply_text(
            "⚠️ Google Sheets no configurado. Agrega la variable SHEETS_ID en Railway."
        )
        return
    ventas = await asyncio.to_thread(sheets_leer_ventas_del_dia)
    estado = "✅ Conectado" if config.SHEETS_DISPONIBLE else "⚠️ Sin conexion"
    url    = f"https://docs.google.com/spreadsheets/d/{config.SHEETS_ID}/edit"
    if not ventas:
        texto = f"📊 Google Sheets — {estado}\n\nNo hay ventas registradas hoy todavia.\n\n🔗 {url}"
    else:
        total_dia = sum(float(v.get("total", 0) or 0) for v in ventas)
        texto = (
            f"📊 Google Sheets — {estado}\n\n"
            f"Ventas de hoy: {len(ventas)}\n"
            f"Total del dia: ${total_dia:,.0f}\n\n"
            f"🔗 {url}"
        )
    await update.message.reply_text(texto)


# ─────────────────────────────────────────────
# /grafica
# ─────────────────────────────────────────────

async def comando_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📅 Ventas por día",   callback_data="grafica_dias"),
        InlineKeyboardButton("📦 Productos",         callback_data="grafica_productos"),
    ], [
        InlineKeyboardButton("💳 Métodos de pago",  callback_data="grafica_pagos"),
    ]])
    await update.message.reply_text("¿Qué gráfica quieres ver?", reply_markup=keyboard)


async def manejar_callback_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from graficas import (
        generar_grafica_ventas_por_dia_async,
        generar_grafica_productos_async,
        generar_grafica_metodos_pago_async,
    )
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    tipo    = query.data
    await query.edit_message_text("📊 Generando gráfica...")

    ruta = None
    try:
        if tipo == "grafica_dias":
            ruta   = await generar_grafica_ventas_por_dia_async()
            titulo = "ventas_por_dia.png"
        elif tipo == "grafica_productos":
            ruta   = await generar_grafica_productos_async()
            titulo = "productos_mas_vendidos.png"
        elif tipo == "grafica_pagos":
            ruta   = await generar_grafica_metodos_pago_async()
            titulo = "metodos_de_pago.png"
        else:
            return

        if not ruta or not os.path.exists(ruta):
            await context.bot.send_message(chat_id=chat_id, text="No hay datos suficientes para esta gráfica aun.")
            return
        with open(ruta, "rb") as f:
            await context.bot.send_photo(chat_id=chat_id, photo=f, filename=titulo)
    except Exception:
        print(f"Error generando grafica: {traceback.format_exc()}")
        await context.bot.send_message(chat_id=chat_id, text="Tuve un problema generando la gráfica. Intenta de nuevo.")
    finally:
        if ruta and os.path.exists(ruta):
            os.remove(ruta)


# ─────────────────────────────────────────────
# /cerrar
# ─────────────────────────────────────────────

async def comando_cerrar_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    await update.message.reply_text("🔒 Iniciando cierre del dia...")

    if not config.SHEETS_ID:
        await update.message.reply_text(
            "⚠️ Google Sheets no configurado.\nUsa /excel para descargar el archivo acumulado."
        )
        return

    ventas_sheets = await asyncio.to_thread(sheets_leer_ventas_del_dia)
    if not ventas_sheets:
        await update.message.reply_text("📭 El Sheets no tiene ventas hoy. Si las hay en el Excel, usa /excel.")
        return

    await update.message.reply_text(f"📋 {len(ventas_sheets)} ventas encontradas en el Sheets...")

    diferencias = await asyncio.to_thread(sheets_detectar_ediciones_vs_excel)
    if diferencias:
        await update.message.reply_text(
            "✏️ Correcciones manuales detectadas (se aplicaran al Excel):\n\n" + "\n".join(diferencias)
        )

    hoy      = datetime.now(config.COLOMBIA_TZ)
    fecha_str = hoy.strftime("%Y-%m-%d")

    try:
        await asyncio.to_thread(inicializar_excel)
        wb = await asyncio.to_thread(openpyxl.load_workbook, config.EXCEL_FILE)
        nombre_hoja = obtener_nombre_hoja()
        ws          = obtener_o_crear_hoja(wb, nombre_hoja)
        cols        = detectar_columnas(ws)

        col_fecha = next((v for k, v in cols.items() if "fecha" in k), None)

        # Borrar filas de hoy (de abajo hacia arriba)
        if col_fecha:
            filas_hoy = [
                fila for fila in range(config.EXCEL_FILA_DATOS, ws.max_row + 1)
                if str(ws.cell(row=fila, column=col_fecha).value or "")[:10] == fecha_str
            ]
            for fila in reversed(filas_hoy):
                ws.delete_rows(fila)

        # Insertar ventas del Sheets
        total_general = 0
        for v in ventas_sheets:
            fila_nueva = ws.max_row + 1
            try:
                cantidad_dec = convertir_fraccion_a_decimal(v.get("cantidad", 1))
            except Exception:
                cantidad_dec = v.get("cantidad", 1)

            datos = {
                "fecha":                v.get("fecha", fecha_str),
                "hora":                 v.get("hora", ""),
                "id cliente":           v.get("id_cliente", "CF"),
                "cliente":              v.get("cliente", "Consumidor Final"),
                "código del producto":  v.get("codigo_producto", ""),
                "producto":             v.get("producto", ""),
                "cantidad":             v.get("cantidad", ""),
                "valor unitario":       v.get("precio_unitario", 0),
                "total":                v.get("total", 0),
                "consecutivo de venta": v.get("num", fila_nueva - 1),
                "alias":                v.get("alias", str(v.get("num", ""))),
                "vendedor":             v.get("vendedor", ""),
                "metodo de pago":       v.get("metodo", ""),
            }

            for nombre_col, num_col in cols.items():
                clave = nombre_col.lower().strip()
                if clave in datos:
                    ws.cell(row=fila_nueva, column=num_col, value=datos[clave])

            if fila_nueva % 2 == 0:
                for col in range(1, ws.max_column + 1):
                    ws.cell(row=fila_nueva, column=col).fill = PatternFill("solid", fgColor="EFF6FF")

            try:
                total_general += float(v.get("total", 0) or 0)
            except (ValueError, TypeError):
                pass

        await asyncio.to_thread(wb.save, config.EXCEL_FILE)
        await asyncio.to_thread(subir_a_drive, config.EXCEL_FILE)

        await update.message.reply_text(
            f"✅ ventas.xlsx actualizado — {len(ventas_sheets)} ventas de hoy\n"
            f"Total del dia: ${total_general:,.0f}\n"
            f"Pestana: {nombre_hoja}"
        )
        await update.message.reply_text("📎 Aqui esta el archivo actualizado:")
        with open(config.EXCEL_FILE, "rb") as f:
            await update.message.reply_document(document=f, filename="ventas.xlsx")

    except Exception:
        print(f"Error en cierre: {traceback.format_exc()}")
        await update.message.reply_text(
            "❌ Hubo un error actualizando el Excel. Los datos siguen en el Sheets, no se perdio nada."
        )
        return

    await update.message.reply_text("🧹 Limpiando el Sheets para manana...")
    ok = await asyncio.to_thread(sheets_limpiar)

    # Limpiar historial en memoria para que /ventas quede vacio
    try:
        from ventas_state import ventas_pendientes, borrados_pendientes, historiales
        with _estado_lock:
            ventas_pendientes.clear()
            borrados_pendientes.clear()
            historiales.clear()
    except Exception as e:
        print(f"Error limpiando memoria tras cierre: {e}")

    if ok:
        await update.message.reply_text(
            "✅ Cierre completado.\n\n• ventas.xlsx actualizado en Drive\n• Sheets limpio y listo para manana"
        )
    else:
        await update.message.reply_text(
            "⚠️ El Excel se actualizo correctamente pero no se pudo limpiar el Sheets.\n"
            "Puedes borrarlo a mano, los datos ya quedaron en el Excel."
        )


# ─────────────────────────────────────────────
# /resetventas
# ─────────────────────────────────────────────

async def comando_reset_ventas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /resetventas CONFIRMAR        → limpia Sheets + memoria del día
    /resetventas excel CONFIRMAR  → borra la hoja del mes actual en Excel
    """
    args = [a.upper() for a in (context.args or [])]

    # ── Modo Excel: /resetventas excel CONFIRMAR ──
    if args and args[0] == "EXCEL":
        if len(args) < 2 or args[1] != "CONFIRMAR":
            from utils import obtener_nombre_hoja
            hoja_actual = obtener_nombre_hoja()
            await update.message.reply_text(
                f"⚠️ *Este comando borra todas las ventas de la hoja \"{hoja_actual}\" del Excel.*\n\n"
                f"El Sheets no se toca.\n\n"
                f"Para confirmar escribe:\n"
                f"`/resetventas excel CONFIRMAR`",
                parse_mode="Markdown"
            )
            return

        await update.message.reply_text("🔄 Borrando ventas del Excel...")
        errores = []
        try:
            import openpyxl
            from utils import obtener_nombre_hoja
            inicializar_excel()
            hoja_actual = obtener_nombre_hoja()
            wb = openpyxl.load_workbook(config.EXCEL_FILE)
            if hoja_actual in wb.sheetnames:
                del wb[hoja_actual]
                wb.save(config.EXCEL_FILE)
                await asyncio.to_thread(subir_a_drive, config.EXCEL_FILE)
                msg_excel = f"✅ Hoja \"{hoja_actual}\" borrada del Excel"
            else:
                msg_excel = f"⚠️ No existe la hoja \"{hoja_actual}\" en el Excel (puede que no haya cierres aún)"
        except Exception as e:
            msg_excel = f"❌ Error: {e}"
            errores.append(str(e))

        await update.message.reply_text(
            f"🧹 *Reset Excel completado*\n\n"
            f"{msg_excel}\n\n"
            f"{'✅ Listo.' if not errores else '⚠️ Hubo errores, revisa arriba.'}",
            parse_mode="Markdown"
        )
        return

    # ── Modo normal: /resetventas CONFIRMAR → limpia Sheets + memoria ──
    if not args or args[0] != "CONFIRMAR":
        await update.message.reply_text(
            "⚠️ *Este comando borra las ventas del día (Sheets).*\n\n"
            "Para confirmar escribe:\n"
            "`/resetventas CONFIRMAR`\n\n"
            "¿Quieres borrar las ventas del Excel también?\n"
            "`/resetventas excel CONFIRMAR`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("🔄 Borrando las ventas del día...")
    errores = []

    # 1. Limpiar Google Sheets
    try:
        ok = await asyncio.to_thread(sheets_limpiar)
        msg_sheets = "✅ Google Sheets limpiado" if ok else "⚠️ No se pudo limpiar el Sheets"
        if not ok:
            errores.append("Sheets no limpiado")
    except Exception as e:
        msg_sheets = f"❌ Error limpiando Sheets: {e}"
        errores.append(str(e))

    # 2. Limpiar historial en memoria (para que /ventas quede limpio)
    try:
        from ventas_state import ventas_pendientes, borrados_pendientes, historiales
        with _estado_lock:
            ventas_pendientes.clear()
            borrados_pendientes.clear()
            historiales.clear()
        msg_memoria = "✅ Historial en memoria limpiado"
    except Exception as e:
        msg_memoria = f"⚠️ No se pudo limpiar memoria: {e}"

    # 3. Resetear consecutivo
    try:
        from memoria import cargar_memoria, guardar_memoria
        mem = cargar_memoria()
        mem["ultimo_consecutivo"] = 0
        guardar_memoria(mem)
        msg_consec = "✅ Consecutivo reseteado a 0"
    except Exception as e:
        msg_consec = f"⚠️ No se pudo resetear el consecutivo: {e}"

    await update.message.reply_text(
        f"🧹 *Reset del día completado*\n\n"
        f"{msg_sheets}\n"
        f"{msg_memoria}\n"
        f"{msg_consec}\n\n"
        f"El Excel histórico no fue modificado.\n"
        f"{'✅ Listo para empezar de nuevo.' if not errores else '⚠️ Hubo errores, revisa arriba.'}",
        parse_mode="Markdown"
    )
