"""
handlers/cmd_ventas.py — Comandos de ventas y gestión del día.

Handlers: comando_inicio, comando_ventas, comando_borrar,
          comando_pendientes, comando_grafica, manejar_callback_grafica,
          comando_cerrar_dia, comando_reset_ventas
"""

# -- stdlib --
import asyncio
import os
import traceback
from datetime import datetime

# -- terceros --
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging

# -- propios --
import config
import db as _db
from memoria import obtener_resumen_caja
from middleware import protegido
from ventas_state import borrados_pendientes, _estado_lock

logger = logging.getLogger("ferrebot.handlers.cmd_ventas")


# ─────────────────────────────────────────────────────────────────────────────
# /start y /ayuda
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    estado_pg = "✅ Base de datos conectada" if _db.DB_DISPONIBLE else "⚠️ DB offline"
    await update.message.reply_text(
        "👋 Hola! Soy tu asistente de la ferreteria.\n\n"
        "📦 VENTAS\n"
        "/ventas — Ver ventas del dia\n"
        "/buscar [texto] — Buscar ventas por producto o cliente\n"
        "/borrar [#] — Borrar consecutivo completo\n\n"
        "💰 CAJA Y GASTOS\n"
        "/caja — Estado actual de caja\n"
        "/caja abrir [monto] — Abrir caja del dia (ej: /caja abrir 50000)\n"
        "/gastos — Gastos registrados hoy\n"
        "/cerrar — Cierre del dia\n"
        "/resetventas CONFIRMAR — Limpiar ventas del dia actual\n"
        "/resetventas pg CONFIRMAR DD/MM/YYYY — Borrar ventas de una fecha en PG\n\n"
        "📊 REPORTES\n"
        "/grafica — Graficas de ventas\n\n"
        "🏪 INVENTARIO Y PRECIOS\n"
        "/inventario — Ver inventario actual\n"
        "/inv [cantidad] [producto] — Registrar conteo de inventario\n"
        "/stock [producto] — Detalle de stock\n"
        "/ajuste [+/-cantidad] [producto] — Ajustar stock\n"
        "/compra [cantidad] [producto] a [costo] — Registrar compra\n"
        "/precios — Ver catalogo de precios\n"
        "/actualizar_precio — Cambiar precios de productos\n"
        "/margenes — Ver margenes de ganancia\n"
        "/actualizar_catalogo — Recargar catalogo (adjunta .xlsx)\n\n"
        "👥 CLIENTES Y FIADOS\n"
        "/clientes — Ver lista de clientes\n"
        "/fiados — Ver todas las cuentas fiadas\n"
        "/fiados [nombre] — Ver detalle de un cliente\n"
        "/abono [nombre] [monto] — Registrar abono\n\n"
        "🧾 PROVEEDORES\n"
        "/factura Proveedor Total Desc — Registrar factura\n"
        "/abonar FAC-001 Monto — Registrar pago\n"
        "/deudas — Resumen de deudas\n\n"
        "⚙️ SISTEMA\n"
        "/agregar_producto — Agregar nuevo producto al catalogo\n"
        "/consistencia — Verificar consistencia del catalogo\n"
        "/alias — Gestionar alias de productos\n"
        "/keepalive on/off — Activar/desactivar cache de prompts\n\n"
        f"{estado_pg}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /ventas  — lee directamente desde PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_ventas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible.")
        return

    rows = await asyncio.to_thread(
        _db.query_all,
        """
        SELECT v.consecutivo          AS num,
               vd.producto_nombre     AS producto,
               v.vendedor,
               vd.total,
               v.metodo_pago          AS metodo
        FROM   ventas_detalle vd
        JOIN   ventas v ON v.id = vd.venta_id
        WHERE  v.fecha::date = CURRENT_DATE
        ORDER  BY v.consecutivo, vd.id
        """,
    )

    if not rows:
        await update.message.reply_text(
            "No hay ventas registradas hoy.\n"
            "Usa el bot para registrar ventas durante el día."
        )
        return

    total_dia = 0
    encabezado = f"📋 Ventas de hoy ({len(rows)}):\n\n"
    lineas = []
    for r in rows:
        num      = r.get("num", "?")
        producto = r.get("producto", "?")
        vendedor = r.get("vendedor", "?")
        total_raw = r.get("total", 0)
        try:
            t = float(total_raw) if total_raw else 0
            total_dia += t
            total_fmt = f"${t:,.0f}"
        except (ValueError, TypeError):
            total_fmt = str(total_raw) if total_raw else "?"
        metodo = r.get("metodo", "") or ""
        linea = f"#{num} — {producto} — {total_fmt} — {vendedor}"
        if metodo:
            linea += f" ({metodo})"
        lineas.append(linea)

    pie = f"\n💰 Total del día: ${total_dia:,.0f}\n\nUsa /borrar [numero] para eliminar una venta."

    bloque = encabezado
    for linea in lineas:
        if len(bloque) + len(linea) + 1 > 4000:
            await update.message.reply_text(bloque)
            bloque = ""
        bloque += linea + "\n"
    bloque += pie
    await update.message.reply_text(bloque)


# ─────────────────────────────────────────────────────────────────────────────
# /borrar  — solo PostgreSQL (sin fallback a Sheets/Excel)
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_borrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Indica el consecutivo a borrar.\nEjemplo: /borrar 5")
        return
    arg = context.args[0].lstrip("#")
    try:
        numero = int(arg)
    except ValueError:
        await update.message.reply_text("El numero debe ser entero.\nEjemplo: /borrar 5")
        return

    chat_id = update.message.chat_id

    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible.")
        return

    rows = await asyncio.to_thread(
        _db.query_all,
        """
        SELECT vd.producto_nombre  AS producto,
               vd.total,
               vd.cantidad,
               v.fecha::text       AS fecha,
               v.vendedor
        FROM   ventas_detalle vd
        JOIN   ventas v ON v.id = vd.venta_id
        WHERE  v.consecutivo = %s
          AND  v.fecha::date  = CURRENT_DATE
        """,
        [numero],
    )
    filas = [dict(r) for r in rows]

    if not filas:
        await update.message.reply_text(f"No encontré el consecutivo #{numero}.")
        return

    with _estado_lock:
        borrados_pendientes[chat_id] = numero

    lineas = []
    total_sum = 0
    for f in filas:
        prod  = f.get("producto", "?")
        total = f.get("total", 0)
        try:
            total_sum += float(total)
            lineas.append(f"  • {prod} ${float(total):,.0f}")
        except Exception:
            lineas.append(f"  • {prod}")
    fecha    = filas[0].get("fecha", "?")
    vendedor = filas[0].get("vendedor", "?")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Sí, borrar todo", callback_data=f"borrar_si_{chat_id}"),
        InlineKeyboardButton("❌ Cancelar",        callback_data=f"borrar_no_{chat_id}"),
    ]])
    await update.message.reply_text(
        f"⚠️ ¿Borrar el consecutivo #{numero} completo?\n"
        f"Fecha: {fecha} | Vendedor: {vendedor}\n\n"
        + "\n".join(lineas)
        + f"\n\nTotal: ${total_sum:,.0f}",
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────────────────────────────────────
# /pendientes
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ El comando /pendientes fue eliminado en la migración v9.0.\n"
        "La tabla productos_pendientes ya no existe.\n\n"
        "Usa el catálogo del dashboard para gestionar productos."
    )


# ─────────────────────────────────────────────────────────────────────────────
# /grafica
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📅 Ventas por día", callback_data="grafica_dias"),
        InlineKeyboardButton("📦 Productos",      callback_data="grafica_productos"),
    ]])
    await update.message.reply_text("¿Qué gráfica quieres ver?", reply_markup=keyboard)


@protegido
async def manejar_callback_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from graficas import (
        generar_grafica_ventas_por_dia_async,
        generar_grafica_productos_async,
    )
    query   = update.callback_query
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


# ─────────────────────────────────────────────────────────────────────────────
# /cerrar  — cierre del día, solo PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_cerrar_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id   = update.message.chat_id
    await update.message.reply_text("🔒 Iniciando cierre del dia...")

    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible.")
        return

    # Leer ventas del día desde PG
    ventas_hoy = await asyncio.to_thread(
        _db.query_all,
        """
        SELECT v.consecutivo     AS num,
               v.fecha::text     AS fecha,
               v.hora,
               v.cliente_nombre  AS cliente,
               v.vendedor,
               v.metodo_pago     AS metodo,
               v.total,
               vd.producto_nombre AS producto,
               vd.cantidad,
               vd.precio_unitario,
               vd.total          AS total_item
        FROM   ventas v
        LEFT JOIN ventas_detalle vd ON vd.venta_id = v.id
        WHERE  v.fecha::date = CURRENT_DATE
        ORDER  BY v.consecutivo, vd.id
        """,
    )

    hoy       = datetime.now(config.COLOMBIA_TZ)
    fecha_str = hoy.strftime("%Y-%m-%d")

    if not ventas_hoy:
        # Sin ventas: cerrar caja igualmente
        from memoria import cargar_caja, guardar_caja
        caja = cargar_caja()
        resumen_caja = ""
        if caja.get("abierta"):
            resumen_caja = obtener_resumen_caja()
            caja["abierta"] = False
            guardar_caja(caja)
        msg = "📭 Sin ventas hoy — nada que sincronizar."
        if resumen_caja:
            msg += f"\n\n💰 Caja cerrada:\n{resumen_caja}"
        await update.message.reply_text(msg)
        return

    # Calcular totales
    total_general = sum(float(r.get("total_item") or 0) for r in ventas_hoy)
    num_ventas    = len({r["num"] for r in ventas_hoy})
    await update.message.reply_text(
        f"✅ {num_ventas} venta(s) del día — Total: ${total_general:,.0f}"
    )

    # Guardar total del día en histórico
    try:
        from api import _leer_historico, _guardar_historico
        historico = _leer_historico()
        historico[fecha_str] = int(total_general)
        _guardar_historico(historico)
        await update.message.reply_text(f"📊 Histórico actualizado: {fecha_str} → ${total_general:,.0f}")
    except Exception as e_hist:
        print(f"⚠️ Error guardando histórico: {e_hist}")

    # Sincronizar gastos al histórico
    try:
        from routers.historico import _sync_historico_hoy
        resultado_sync = await asyncio.to_thread(_sync_historico_hoy)
        gastos_dia = resultado_sync.get("gastos", 0)
        if gastos_dia > 0:
            await update.message.reply_text(f"💸 Gastos del día guardados: ${gastos_dia:,.0f}")
    except Exception as e_sync:
        print(f"⚠️ Error sincronizando gastos al histórico: {e_sync}")

    # Cerrar caja
    from memoria import cargar_caja, guardar_caja
    caja = cargar_caja()
    resumen_caja = ""
    if caja.get("abierta"):
        resumen_caja = obtener_resumen_caja()
        caja["abierta"] = False
        guardar_caja(caja)

    msg_cierre = "✅ Cierre completado."
    if resumen_caja:
        msg_cierre += f"\n\n💰 Caja cerrada:\n{resumen_caja}"
    await update.message.reply_text(msg_cierre)

    # Análisis del día con Claude
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        por_metodo   = {}
        por_vendedor = {}
        por_producto = {}
        for r in ventas_hoy:
            m_pago = str(r.get("metodo", "efectivo") or "efectivo").lower()
            por_metodo[m_pago]     = por_metodo.get(m_pago, 0)     + float(r.get("total_item") or 0)
            vend = str(r.get("vendedor", "?"))
            por_vendedor[vend]     = por_vendedor.get(vend, 0)     + float(r.get("total_item") or 0)
            prod = str(r.get("producto", "?"))
            por_producto[prod]     = por_producto.get(prod, 0)     + float(r.get("total_item") or 0)

        top_prod = sorted(por_producto.items(), key=lambda x: x[1], reverse=True)[:3]
        top_txt  = ", ".join(f"{p} (${t:,.0f})" for p, t in top_prod)

        try:
            from api import _leer_historico
            from datetime import timedelta
            historico  = _leer_historico()
            ultimos    = sorted(historico.keys(), reverse=True)[:8]
            ultimos    = [d for d in ultimos if d != fecha_str][:7]
            if ultimos:
                promedio_semana = sum(historico[d] for d in ultimos) / len(ultimos)
                mejor_dia       = max(ultimos, key=lambda d: historico[d])
                hist_txt = (
                    f"Promedio últimos {len(ultimos)} días: ${promedio_semana:,.0f}\n"
                    f"Mejor día reciente: {mejor_dia} con ${historico[mejor_dia]:,.0f}"
                )
            else:
                hist_txt = "Sin histórico previo disponible"
        except Exception:
            hist_txt = "Sin histórico previo disponible"

        prompt_analisis = (
            f"Eres el asistente de Ferretería Punto Rojo. Hoy fue {fecha_str}.\n"
            f"\nDATOS DEL DÍA:\n"
            f"- Total vendido: ${total_general:,.0f}\n"
            f"- Número de ventas: {num_ventas}\n"
            f"- Por método: {', '.join(f'{k}: ${v:,.0f}' for k,v in por_metodo.items())}\n"
            f"- Por vendedor: {', '.join(f'{k}: ${v:,.0f}' for k,v in por_vendedor.items())}\n"
            f"- Top 3 productos: {top_txt}\n"
            f"\nHISTÓRICO RECIENTE:\n{hist_txt}\n"
            f"\nEscribe un análisis breve del día (máximo 5 líneas). "
            f"Compara con el promedio, destaca lo notable, menciona si fue buen o mal día y por qué. "
            f"Sé directo y concreto. Sin markdown, sin asteriscos. "
            f"Si fue un día excepcional o muy flojo, dilo claramente."
        )

        respuesta_analisis = None
        for _ca_intento in range(3):
            try:
                respuesta_analisis = await asyncio.to_thread(
                    lambda: config.claude_client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=400,
                        messages=[{"role": "user", "content": prompt_analisis}],
                    )
                )
                break
            except Exception as _ca_e:
                if _ca_intento < 2:
                    await asyncio.sleep(2)
                else:
                    print(f"[cerrar] Claude sin respuesta tras 3 intentos: {_ca_e}")
                    respuesta_analisis = None

        if respuesta_analisis:
            analisis_txt = respuesta_analisis.content[0].text.strip()
            await update.message.reply_text(f"🧠 Análisis del día:\n\n{analisis_txt}")

    except Exception as e_an:
        print(f"[cerrar] Error en análisis Claude: {e_an}")


# ─────────────────────────────────────────────────────────────────────────────
# /resetventas  — solo PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_reset_ventas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = [a.upper() for a in (context.args or [])]

    # /resetventas pg CONFIRMAR DD/MM/YYYY
    if args and args[0] == "PG":
        if len(args) < 3 or args[1] != "CONFIRMAR":
            await update.message.reply_text(
                "⚠️ Uso: `/resetventas pg CONFIRMAR DD/MM/YYYY`\n"
                "Ejemplo: `/resetventas pg CONFIRMAR 24/02/2026`",
                parse_mode="Markdown"
            )
            return
        try:
            fecha_str_raw = context.args[2]
            fecha_obj     = datetime.strptime(fecha_str_raw, "%d/%m/%Y")
            fecha_iso     = fecha_obj.strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Fecha inválida. Usa DD/MM/YYYY, ej: 24/02/2026")
            return

        if not _db.DB_DISPONIBLE:
            await update.message.reply_text("⚠️ Base de datos no disponible.")
            return

        try:
            from db import _get_conn
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM ventas_detalle WHERE venta_id IN "
                        "(SELECT id FROM ventas WHERE fecha::date = %s)",
                        (fecha_iso,)
                    )
                    cur.execute("DELETE FROM ventas WHERE fecha::date = %s", (fecha_iso,))
                    pg_borradas = cur.rowcount
                conn.commit()
            await update.message.reply_text(
                f"✅ Eliminadas {pg_borradas} venta(s) del {fecha_str_raw} en la base de datos."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        return

    if not args or args[0] != "CONFIRMAR":
        await update.message.reply_text(
            "⚠️ Escribe `/resetventas CONFIRMAR` para limpiar el dia.\n"
            "Para borrar una fecha específica: `/resetventas pg CONFIRMAR DD/MM/YYYY`",
            parse_mode="Markdown"
        )
        return

    # Limpiar estado en memoria
    try:
        from ventas_state import (
            ventas_pendientes, borrados_pendientes, historiales,
            mensajes_standby, clientes_en_proceso, ventas_esperando_cliente,
            _estado_lock
        )
        with _estado_lock:
            ventas_pendientes.clear()
            borrados_pendientes.clear()
            historiales.clear()
            mensajes_standby.clear()
            clientes_en_proceso.clear()
            ventas_esperando_cliente.clear()
    except Exception as e:
        print(f"Error limpiando memoria interna: {e}")

    # Borrar ventas de hoy en PG
    if _db.DB_DISPONIBLE:
        try:
            from db import _get_conn
            hoy_iso = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM ventas_detalle WHERE venta_id IN "
                        "(SELECT id FROM ventas WHERE fecha::date = %s)",
                        (hoy_iso,)
                    )
                    cur.execute("DELETE FROM ventas WHERE fecha::date = %s", (hoy_iso,))
                conn.commit()
        except Exception:
            pass

    await update.message.reply_text("✅ Reset del dia completado.")
