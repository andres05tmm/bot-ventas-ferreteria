"""
Handlers de comandos de Telegram.
Persistencia: exclusivamente PostgreSQL.
Fotos de facturas/abonos: Cloudinary (ver upload_foto_cloudinary).

MIGRACIÓN CLOUDINARY — variables de entorno necesarias:
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET
  O alternativamente CLOUDINARY_URL en el formato:
    cloudinary://<api_key>:<api_secret>@<cloud_name>

  Instalar: pip install cloudinary
  La integración real está en handlers/mensajes.py donde se recibe la foto.
  Esta función upload_foto_cloudinary() es el helper compartido.
"""

import asyncio
import json
import os
import traceback
from datetime import datetime

import db as _db
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from memoria import (
    cargar_memoria, obtener_resumen_caja, cargar_gastos_hoy,
    verificar_alertas_inventario,
    resumen_fiados, detalle_fiado_cliente, abonar_fiado,
    importar_catalogo_desde_excel,
    registrar_conteo_inventario, ajustar_inventario,
    buscar_productos_inventario, buscar_clave_inventario,
    registrar_compra, obtener_resumen_margenes,
)
from utils import convertir_fraccion_a_decimal, obtener_nombre_hoja
from ventas_state import borrados_pendientes, _estado_lock


# ─────────────────────────────────────────────────────────────────────────────
# CLOUDINARY HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def upload_foto_cloudinary(
    foto_bytes: bytes,
    public_id: str,
    carpeta: str = "ferreteria",
) -> dict:
    """
    Sube foto a Cloudinary y devuelve {ok, url, public_id, error}.

    Uso desde mensajes.py cuando se recibe una foto de factura o abono:

        from handlers.comandos import upload_foto_cloudinary
        result = await upload_foto_cloudinary(
            foto_bytes = await foto.download_as_bytearray(),
            public_id  = f"facturas/{fac_id}",
        )
        if result["ok"]:
            url_foto = result["url"]
            # guardar url_foto en PG: UPDATE facturas SET foto_url = %s WHERE id = %s

    Requiere: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
    """
    import io
    try:
        import cloudinary
        import cloudinary.uploader

        # Configurar desde env vars (se puede hacer una sola vez en config.py también)
        cloudinary.config(
            cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            api_key    = os.environ.get("CLOUDINARY_API_KEY",    ""),
            api_secret = os.environ.get("CLOUDINARY_API_SECRET", ""),
        )

        full_public_id = f"{carpeta}/{public_id}"

        def _do_upload():
            return cloudinary.uploader.upload(
                io.BytesIO(foto_bytes),
                public_id    = full_public_id,
                overwrite    = True,
                resource_type= "image",
            )

        result = await asyncio.to_thread(_do_upload)
        return {
            "ok":        True,
            "url":       result.get("secure_url", ""),
            "public_id": result.get("public_id",  ""),
            "error":     None,
        }
    except ImportError:
        return {
            "ok":    False,
            "url":   "",
            "public_id": public_id,
            "error": "cloudinary no instalado — pip install cloudinary",
        }
    except Exception as e:
        return {
            "ok":    False,
            "url":   "",
            "public_id": public_id,
            "error": str(e),
        }


# ─────────────────────────────────────────────────────────────────────────────
# /start y /ayuda
# ─────────────────────────────────────────────────────────────────────────────

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
# /buscar  — búsqueda en PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

async def comando_buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Indica que quieres buscar.\nEjemplos:\n/buscar tornillos\n/buscar Juan\n/buscar 2025-06"
        )
        return
    termino = " ".join(context.args)
    await update.message.reply_text(f"🔍 Buscando '{termino}'...")

    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible.")
        return

    pat = f"%{termino}%"
    rows = await asyncio.to_thread(
        _db.query_all,
        """
        SELECT v.consecutivo          AS "#",
               v.fecha::text          AS fecha,
               vd.producto_nombre     AS producto,
               vd.total,
               v.vendedor,
               v.fecha::text          AS hoja
        FROM   ventas_detalle vd
        JOIN   ventas v ON v.id = vd.venta_id
        WHERE  vd.producto_nombre ILIKE %s
           OR  v.vendedor        ILIKE %s
           OR  v.cliente_nombre  ILIKE %s
           OR  v.fecha::text     ILIKE %s
        ORDER  BY v.fecha DESC, v.consecutivo
        LIMIT  50
        """,
        [pat, pat, pat, pat],
    )

    if not rows:
        await update.message.reply_text(f"No encontre ventas que coincidan con '{termino}'.")
        return

    texto = f"🔍 {len(rows)} resultado(s) para '{termino}':\n\n"
    for r in rows[:15]:
        num   = r.get("#", "?")
        fecha = r.get("fecha", "?")
        prod  = r.get("producto", "?")
        total = r.get("total", "?")
        vend  = r.get("vendedor", "?")
        try:
            total_fmt = f"${float(total):,.0f}" if total else "?"
        except Exception:
            total_fmt = str(total)
        texto += f"#{num} {fecha[:10] if fecha else '?'} — {prod} — {total_fmt} — {vend}\n"
    if len(rows) > 15:
        texto += f"\n... y {len(rows) - 15} mas. Usa un termino mas especifico."
    await update.message.reply_text(texto)


# ─────────────────────────────────────────────────────────────────────────────
# /borrar  — solo PostgreSQL (sin fallback a Sheets/Excel)
# ─────────────────────────────────────────────────────────────────────────────

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
# /precios
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# /caja, /gastos, /inventario
# ─────────────────────────────────────────────────────────────────────────────

async def comando_caja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if args and args[0].lower() == "abrir":
        from memoria import cargar_caja, guardar_caja
        monto = 0
        if len(args) > 1:
            try:
                monto = int(args[1].replace(",", "").replace(".", ""))
            except ValueError:
                await update.message.reply_text("Formato: /caja abrir 50000")
                return
        caja = cargar_caja()
        if caja.get("abierta"):
            await update.message.reply_text("⚠️ La caja ya está abierta.")
            return
        import datetime
        caja["abierta"]         = True
        caja["fecha"]           = datetime.date.today().isoformat()
        caja["monto_apertura"]  = monto
        caja["efectivo"]        = 0
        caja["transferencias"]  = 0
        caja["datafono"]        = 0
        guardar_caja(caja)
        await update.message.reply_text(f"💰 Caja abierta con ${monto:,} de base.")

    elif args and args[0].lower() == "reset":
        from memoria import cargar_caja, guardar_caja
        caja = cargar_caja()
        if caja.get("abierta"):
            await update.message.reply_text("⚠️ La caja está abierta. Ciérrala primero con /cerrar.")
            return
        guardar_caja({
            "abierta": False, "fecha": None,
            "monto_apertura": 0, "efectivo": 0,
            "transferencias": 0, "datafono": 0,
        })
        await update.message.reply_text(
            "🗑️ Caja reseteada.\n"
            "Usa /caja abrir [monto] para comenzar un nuevo día."
        )
    else:
        resumen = obtener_resumen_caja()
        await update.message.reply_text(f"💰 {resumen}")


async def comando_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 *Dashboard Ferretería Punto Rojo*\n\n"
        "🔗 https://bot-ventas-ferreteria-production.up.railway.app/",
        parse_mode="Markdown"
    )


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
    """Alias de /stock."""
    await comando_stock(update, context)


# ─────────────────────────────────────────────────────────────────────────────
# /inv - Registrar conteo de inventario
# ─────────────────────────────────────────────────────────────────────────────

def _resolver_grm(nombre_producto: str, cantidad: float, es_cajas: bool = False) -> tuple:
    from memoria import buscar_producto_en_catalogo as _bpc
    _PESO_CAJA_GR = 500
    prod = _bpc(nombre_producto)
    if prod and prod.get("unidad_medida", "").upper() == "GRM":
        if es_cajas:
            gr    = cantidad * _PESO_CAJA_GR
            label = f"{int(cantidad)} caja{'s' if cantidad > 1 else ''} ({int(gr)} gr)"
        else:
            gr    = cantidad
            cajas = gr / _PESO_CAJA_GR
            label = (
                f"{int(gr)} gr ({cajas:.1f} caja{'s' if cajas != 1 else ''})"
                if gr >= _PESO_CAJA_GR else f"{int(gr)} gr"
            )
        return prod["nombre"], gr, label
    return nombre_producto, cantidad, str(int(cantidad) if cantidad == int(cantidad) else cantidad)


async def comando_inv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "📦 *Registrar inventario*\n\n"
            "Uso: `/inv [cantidad] [producto]`\n\n"
            "Ejemplos:\n"
            "• `/inv 25 brocha 2\"`\n"
            "• `/inv 18 rodillo de 4 pulgadas`\n"
            "• `/inv 50 tornillo drywall 6x1`\n"
            "• `/inv 3.5 galones vinilo t1`",
            parse_mode="Markdown"
        )
        return

    import re as _re_inv
    texto_inv  = " ".join(args)
    _m_cajas   = _re_inv.match(r'^(\d+(?:[.,]\d+)?)\s+cajas?\s+(.+)$', texto_inv, _re_inv.IGNORECASE)
    _m_gramos  = _re_inv.match(r'^(\d+(?:[.,]\d+)?)\s+gr(?:amos?)?\s+(.+)$', texto_inv, _re_inv.IGNORECASE)

    if _m_cajas:
        try:
            _n_cajas = float(_m_cajas.group(1).replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Cantidad inválida.")
            return
        nombre_producto = _m_cajas.group(2).strip()
        nombre_producto, cantidad, _lbl = _resolver_grm(nombre_producto, _n_cajas, es_cajas=True)
    elif _m_gramos:
        try:
            _gr = float(_m_gramos.group(1).replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Cantidad inválida.")
            return
        nombre_producto = _m_gramos.group(2).strip()
        nombre_producto, cantidad, _lbl = _resolver_grm(nombre_producto, _gr, es_cajas=False)
    else:
        try:
            cantidad = float(args[0].replace(",", "."))
        except ValueError:
            await update.message.reply_text(
                f"❌ '{args[0]}' no es una cantidad válida.\n"
                "Usa números: `/inv 25 brocha 2\"`",
                parse_mode="Markdown"
            )
            return
        nombre_producto = " ".join(args[1:])
        _lbl = None

    if len(nombre_producto) < 3:
        await update.message.reply_text("❌ Nombre del producto muy corto.")
        return

    exito, mensaje = await asyncio.to_thread(
        registrar_conteo_inventario, nombre_producto, cantidad
    )
    if exito and _lbl:
        mensaje = mensaje.replace(str(cantidad), _lbl)
    await update.message.reply_text(mensaje)


# ─────────────────────────────────────────────────────────────────────────────
# /stock - Ver inventario
# ─────────────────────────────────────────────────────────────────────────────

async def comando_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args    = context.args
    termino = " ".join(args) if args else None
    productos = await asyncio.to_thread(buscar_productos_inventario, termino)

    if not productos:
        if termino:
            await update.message.reply_text(f"❌ No encontré '{termino}' en inventario.")
        else:
            await update.message.reply_text(
                "📦 *Inventario vacío*\n\n"
                "Usa `/inv [cantidad] [producto]` para agregar.\n"
                "Ejemplo: `/inv 25 brocha 2\"`",
                parse_mode="Markdown"
            )
        return

    texto = f"📦 *Inventario — '{termino}':*\n\n" if termino else f"📦 *Inventario ({len(productos)} productos):*\n\n"
    alertas = 0
    for p in productos:
        cantidad = p["cantidad"]
        minimo   = p["minimo"]

        if cantidad <= 0:
            emoji = "🔴"; alertas += 1
        elif cantidad <= minimo:
            emoji = "⚠️"; alertas += 1
        else:
            emoji = "✅"

        from memoria import buscar_producto_en_catalogo as _bpc_s
        _prod_s = _bpc_s(p["nombre"])
        if _prod_s and _prod_s.get("unidad_medida", "").upper() == "GRM" and cantidad >= 500:
            _cajas     = cantidad / 500
            _cajas_txt = f"{int(_cajas)}" if _cajas == int(_cajas) else f"{_cajas:.1f}"
            texto += f"{emoji} *{p['nombre']}*: {_cajas_txt} caja(s) ({int(cantidad)} gr)\n"
        elif _prod_s and _prod_s.get("unidad_medida", "").upper() == "GRM":
            texto += f"{emoji} *{p['nombre']}*: {int(cantidad)} gr\n"
        else:
            texto += f"{emoji} *{p['nombre']}*: {cantidad} {p['unidad']}\n"

    if alertas > 0:
        texto += f"\n⚠️ {alertas} producto(s) con stock bajo"

    if len(texto) > 4000:
        for parte in [texto[i:i+4000] for i in range(0, len(texto), 4000)]:
            await update.message.reply_text(parte, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# /ajuste - Ajustar inventario
# ─────────────────────────────────────────────────────────────────────────────

async def comando_ajuste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "🔧 *Ajustar inventario*\n\n"
            "Uso: `/ajuste [+/-cantidad] [producto]`\n\n"
            "Ejemplos:\n"
            "• `/ajuste +10 brocha 2\"` (suma 10)\n"
            "• `/ajuste -5 rodillo 4\"` (resta 5)",
            parse_mode="Markdown"
        )
        return

    try:
        ajuste = float(args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text(
            f"❌ '{args[0]}' no es válido.\nUsa +10 o -5 para ajustar.",
            parse_mode="Markdown"
        )
        return

    nombre_producto = " ".join(args[1:])
    exito, mensaje  = await asyncio.to_thread(ajustar_inventario, nombre_producto, ajuste)
    await update.message.reply_text(mensaje)


# ─────────────────────────────────────────────────────────────────────────────
# /compra - Registrar compra de mercancía
# ─────────────────────────────────────────────────────────────────────────────

async def comando_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text(
            "📦 *Registrar compra de mercancía*\n\n"
            "Uso: `/compra [cantidad] [producto] a [costo]`\n"
            "Opcional: `de [proveedor]`\n\n"
            "Ejemplos:\n"
            "• `/compra 20 brocha 2\" a 2500`\n"
            "• `/compra 20 brocha 2\" a 2500 de Ferrisariato`\n"
            "• `/compra 50 tornillo 6x1 a 25 de JS Tools`",
            parse_mode="Markdown"
        )
        return

    import re
    texto_completo = " ".join(args)

    if " a " not in texto_completo.lower():
        await update.message.reply_text(
            "❌ Formato incorrecto. Usa: `/compra 20 brocha 2\" a 2500`",
            parse_mode="Markdown"
        )
        return

    idx_a          = texto_completo.lower().find(" a ")
    parte_producto = texto_completo[:idx_a].strip()
    resto          = texto_completo[idx_a + 3:].strip()

    proveedor = None
    if " de " in resto.lower():
        idx_de      = resto.lower().rfind(" de ")
        parte_costo = resto[:idx_de].strip()
        proveedor   = resto[idx_de + 4:].strip()
    else:
        parte_costo = resto

    import re as _re_compra
    palabras_producto = parte_producto.split()
    _m_cajas_c  = _re_compra.match(r'^(\d+(?:[.,]\d+)?)\s+cajas?\s+(.+)$', parte_producto, _re_compra.IGNORECASE)
    _m_gramos_c = _re_compra.match(r'^(\d+(?:[.,]\d+)?)\s+gr(?:amos?)?\s+(.+)$', parte_producto, _re_compra.IGNORECASE)

    _label_compra = None
    _dividir_costo = False

    if _m_cajas_c:
        try:
            _n_cajas_c = float(_m_cajas_c.group(1).replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Cantidad inválida.", parse_mode="Markdown")
            return
        nombre_producto = _m_cajas_c.group(2).strip()
        try:
            from memoria import buscar_producto_en_catalogo as _bpc_c
            _prod_c_check = _bpc_c(nombre_producto)
        except Exception:
            _prod_c_check = None
        if _prod_c_check and _prod_c_check.get("unidad_medida", "").upper() == "GRM":
            cantidad       = float(500 * _n_cajas_c)
            nombre_producto = _prod_c_check["nombre"]
            _label_compra  = f"{int(_n_cajas_c)} caja(s) = {int(cantidad)} gr"
            _dividir_costo = True
        else:
            cantidad = _n_cajas_c
    elif _m_gramos_c:
        try:
            cantidad = float(_m_gramos_c.group(1).replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Cantidad inválida.", parse_mode="Markdown")
            return
        nombre_producto = _m_gramos_c.group(2).strip()
    else:
        try:
            cantidad = float(palabras_producto[0].replace(",", "."))
        except ValueError:
            await update.message.reply_text(
                f"❌ '{palabras_producto[0]}' no es una cantidad válida.",
                parse_mode="Markdown"
            )
            return
        nombre_producto = " ".join(palabras_producto[1:])

    if len(nombre_producto) < 2:
        await update.message.reply_text("❌ Nombre del producto muy corto.")
        return

    try:
        costo_limpio = parte_costo.replace("$", "").replace(",", "").strip()
        if "." in costo_limpio and costo_limpio.replace(".", "").isdigit():
            costo_limpio = costo_limpio.replace(".", "")
        costo = float(costo_limpio)
    except ValueError:
        await update.message.reply_text(
            f"❌ '{parte_costo}' no es un costo válido.",
            parse_mode="Markdown"
        )
        return

    costo_unitario = costo / 500 if (_dividir_costo and costo >= 500) else costo

    exito, mensaje, datos_compra = await asyncio.to_thread(
        registrar_compra, nombre_producto, cantidad, costo_unitario, proveedor
    )

    # Persistir en PostgreSQL
    if exito and _db.DB_DISPONIBLE:
        try:
            import datetime as _dt
            ahora = _dt.datetime.now()
            prov  = (datos_compra or {}).get("proveedor") or proveedor or ""
            prod_n = (datos_compra or {}).get("producto")  or nombre_producto
            cant_n = (datos_compra or {}).get("cantidad")  or cantidad
            cu     = (datos_compra or {}).get("costo_unitario") or costo_unitario
            ct     = (datos_compra or {}).get("costo_total")    or round(cant_n * cu)

            await asyncio.to_thread(
                _db.execute,
                """
                INSERT INTO compras
                    (fecha, hora, proveedor, producto_nombre,
                     cantidad, costo_unitario, costo_total)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (ahora.date(), ahora.strftime("%H:%M"), prov, prod_n, cant_n, cu, ct),
            )
        except Exception as _e_pg:
            import logging as _log
            _log.getLogger("ferrebot").warning(f"PG compra write falló: {_e_pg}")

    await update.message.reply_text(mensaje)


# ─────────────────────────────────────────────────────────────────────────────
# /margenes - Ver márgenes de ganancia
# ─────────────────────────────────────────────────────────────────────────────

async def comando_margenes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resultados = await asyncio.to_thread(obtener_resumen_margenes, 30)

    if not resultados:
        await update.message.reply_text(
            "📊 *No hay márgenes calculados*\n\n"
            "Para ver márgenes, primero registra compras:\n"
            "`/compra 20 brocha 2\" a 2500`",
            parse_mode="Markdown"
        )
        return

    excelentes = [r for r in resultados if r["margen_porcentaje"] >= 40]
    buenos      = [r for r in resultados if 25 <= r["margen_porcentaje"] < 40]
    bajos       = [r for r in resultados if r["margen_porcentaje"] < 25]

    texto = "📊 *MÁRGENES DE GANANCIA*\n\n"
    if excelentes:
        texto += f"🏆 *Excelentes (≥40%):* {len(excelentes)} productos\n"
        for p in excelentes[:5]:
            texto += f"  • {p['nombre']}: {p['margen_porcentaje']}%\n"
        if len(excelentes) > 5:
            texto += f"  _...y {len(excelentes) - 5} más_\n"
        texto += "\n"
    if buenos:
        texto += f"✅ *Buenos (25-40%):* {len(buenos)} productos\n"
        for p in buenos[:3]:
            texto += f"  • {p['nombre']}: {p['margen_porcentaje']}%\n"
        if len(buenos) > 3:
            texto += f"  _...y {len(buenos) - 3} más_\n"
        texto += "\n"
    if bajos:
        texto += f"⚠️ *Bajos (<25%):* {len(bajos)} productos\n"
        for p in bajos[:5]:
            texto += f"  • {p['nombre']}: {p['margen_porcentaje']}%\n"

    await update.message.reply_text(texto, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# /pendientes
# ─────────────────────────────────────────────────────────────────────────────

async def comando_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from memoria import cargar_memoria, guardar_memoria
    from datetime import datetime, timedelta

    args  = " ".join(context.args).strip() if context.args else ""
    mem   = cargar_memoria()
    lista = mem.get("productos_pendientes", [])

    if args.lower().startswith("agregar "):
        nombre = args[8:].strip().lower()
        if not nombre:
            await update.message.reply_text("Uso: /pendientes agregar nombre_producto"); return
        hoy  = datetime.now().strftime("%Y-%m-%d")
        hora = datetime.now().strftime("%H:%M")
        if any(p["nombre"].lower() == nombre and p.get("fecha") == hoy for p in lista):
            await update.message.reply_text(f"ℹ️ *{nombre}* ya está en la lista de hoy."); return
        lista.append({"nombre": nombre, "fecha": hoy, "hora": hora})
        mem["productos_pendientes"] = lista
        guardar_memoria(mem, urgente=True)
        await update.message.reply_text(f"✅ *{nombre}* agregado a pendientes."); return

    if args.lower().startswith("quitar "):
        nombre  = args[7:].strip().lower()
        antes   = len(lista)
        lista   = [p for p in lista if p["nombre"].lower() != nombre]
        if len(lista) == antes:
            await update.message.reply_text(f"ℹ️ No encontré *{nombre}* en la lista."); return
        mem["productos_pendientes"] = lista
        guardar_memoria(mem, urgente=True)
        await update.message.reply_text(f"🗑️ *{nombre}* quitado de pendientes."); return

    if args.lower() == "limpiar":
        mem["productos_pendientes"] = []
        guardar_memoria(mem, urgente=True)
        await update.message.reply_text("🧹 Lista de pendientes limpiada."); return

    hoy   = datetime.now().strftime("%Y-%m-%d")
    desde = None
    if args.lower() == "semana":
        desde  = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        titulo = "📋 *Productos pendientes — últimos 7 días:*"
    elif args.lower() == "todo":
        titulo = "📋 *Todos los productos pendientes:*"
    else:
        desde  = hoy
        titulo = "📋 *Productos pendientes de hoy:*"

    filtrados = [p for p in lista if p.get("fecha", "") >= desde] if desde else lista

    if not filtrados:
        periodo = "hoy" if not args else args
        await update.message.reply_text(
            f"✅ No hay productos pendientes para {periodo}.\n\n"
            "Comandos disponibles:\n"
            "• /pendientes semana\n"
            "• /pendientes agregar nombre\n"
            "• /pendientes quitar nombre\n"
            "• /pendientes limpiar"
        ); return

    por_fecha = {}
    for p in filtrados:
        por_fecha.setdefault(p.get("fecha", "?"), []).append(p)

    lineas = [titulo, ""]
    total_mostrados = 0
    for fecha in sorted(por_fecha.keys(), reverse=True):
        if args.lower() != "" and fecha != hoy:
            lineas.append(f"📅 *{fecha}*")
        vistos = set()
        for p in por_fecha[fecha]:
            nombre = p["nombre"].strip().lower()
            if nombre not in vistos:
                vistos.add(nombre)
                lineas.append(f"  • {p['nombre']}")
                total_mostrados += 1
        lineas.append("")

    lineas.append(f"_Total: {total_mostrados} productos_")
    lineas.append("")
    lineas.append("Para quitar: /pendientes quitar nombre")
    lineas.append("Para limpiar todo: /pendientes limpiar")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# /clientes  — lee desde PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

async def comando_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible.")
        return

    rows = await asyncio.to_thread(
        _db.query_all,
        "SELECT nombre, tipo_id, num_id, telefono FROM clientes ORDER BY nombre",
    )

    if not rows:
        await update.message.reply_text("👥 No hay clientes registrados.")
        return

    texto = f"👥 *{len(rows)} clientes registrados:*\n\n"
    for r in rows:
        telefono = f" — {r['telefono']}" if r.get("telefono") else ""
        doc      = f" ({r['tipo_id']} {r['num_id']})" if r.get("num_id") else ""
        texto   += f"• {r['nombre']}{doc}{telefono}\n"
        if len(texto) > 3800:
            await update.message.reply_text(texto, parse_mode="Markdown")
            texto = ""

    if texto.strip():
        await update.message.reply_text(texto, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# /nuevo_cliente
# ─────────────────────────────────────────────────────────────────────────────

async def comando_nuevo_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from ventas_state import clientes_en_proceso, _estado_lock
    from handlers.mensajes import _enviar_pregunta_flujo_cliente

    chat_id = update.effective_chat.id
    if context.args:
        nombre = " ".join(context.args).strip()
        with _estado_lock:
            clientes_en_proceso[chat_id] = {"paso": "tipo_id", "nombre": nombre}
    else:
        with _estado_lock:
            clientes_en_proceso[chat_id] = {"paso": "nombre"}
    await _enviar_pregunta_flujo_cliente(update.message, chat_id)


# ─────────────────────────────────────────────────────────────────────────────
# /fiados  /abono (fiados)
# ─────────────────────────────────────────────────────────────────────────────

async def comando_fiados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        cliente = " ".join(context.args)
        texto   = detalle_fiado_cliente(cliente)
    else:
        texto = resumen_fiados()
    await update.message.reply_text(texto, parse_mode="Markdown")


async def comando_abono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Uso: /abono [nombre] [monto]\nEjemplo: /abono Juan Perez 50000"
        )
        return
    try:
        monto = float(context.args[-1].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text("❌ El monto debe ser un número. Ej: /abono Juan Perez 50000")
        return

    nombre     = " ".join(context.args[:-1])
    ok, msg    = await asyncio.to_thread(abonar_fiado, nombre, monto)
    if ok:
        from memoria import detalle_fiado_cliente
        detalle = detalle_fiado_cliente(nombre)
        await update.message.reply_text(
            f"✅ Abono registrado\n\n"
            f"👤 {nombre.upper()}\n"
            f"💰 Abono: ${monto:,.0f}\n\n"
            f"{detalle}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# /grafica
# ─────────────────────────────────────────────────────────────────────────────

async def comando_grafica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📅 Ventas por día", callback_data="grafica_dias"),
        InlineKeyboardButton("📦 Productos",      callback_data="grafica_productos"),
    ]])
    await update.message.reply_text("¿Qué gráfica quieres ver?", reply_markup=keyboard)


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

        respuesta_analisis = await asyncio.to_thread(
            lambda: config.claude_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt_analisis}],
            )
        )
        analisis_txt = respuesta_analisis.content[0].text.strip()
        await update.message.reply_text(f"🧠 Análisis del día:\n\n{analisis_txt}")

    except Exception as e_an:
        print(f"[cerrar] Error en análisis Claude: {e_an}")


# ─────────────────────────────────────────────────────────────────────────────
# /resetventas  — solo PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# /actualizar_catalogo  — acepta archivo adjunto (sin Drive)
# ─────────────────────────────────────────────────────────────────────────────

async def comando_actualizar_catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Reimporta productos desde BASE_DE_DATOS_PRODUCTOS.xlsx.
    Adjunta el archivo directamente en este chat (no usa Drive).
    """
    await update.message.reply_text(
        "📦 *Actualizar catálogo*\n\n"
        "Adjunta el archivo `BASE_DE_DATOS_PRODUCTOS.xlsx` directamente en este chat.\n\n"
        "El bot procesará el archivo tan pronto lo reciba.",
        parse_mode="Markdown"
    )
    # La recepción real del archivo se maneja en mensajes.py
    # cuando llega un documento .xlsx con el nombre BASE_DE_DATOS_PRODUCTOS
    context.user_data["esperando_catalogo_xlsx"] = True


# ─────────────────────────────────────────────────────────────────────────────
# /consistencia  — compara memoria vs catálogo (sin Drive)
# ─────────────────────────────────────────────────────────────────────────────

async def comando_consistencia(update, context):
    """
    Verifica consistencia del catálogo en memoria.
    Sin comparación con Excel en Drive — compara solo la memoria interna.
    Para una verificación completa adjunta BASE_DE_DATOS_PRODUCTOS.xlsx.
    """
    from precio_sync import verificar_consistencia
    await update.message.reply_text("🔍 Verificando consistencia del catálogo en memoria…")
    try:
        resultado = await asyncio.to_thread(verificar_consistencia)
        if "error" in resultado:
            await update.message.reply_text(f"❌ Error: {resultado['error']}")
            return

        iguales    = resultado["iguales"]
        diferentes = resultado["diferentes"]
        solo_mem   = resultado["solo_memoria"]
        solo_xls   = resultado["solo_excel"]

        lineas = [
            "📊 CONSISTENCIA DE PRECIOS", "─" * 30,
            f"✅ Iguales:          {iguales}",
            f"⚠️  Con diferencias: {len(diferentes)}",
            f"🧠 Solo en memoria:  {len(solo_mem)}",
            f"📋 Solo en Excel:    {len(solo_xls)}",
        ]
        if not diferentes and not solo_mem and not solo_xls:
            lineas += ["", "🎉 ¡Todo sincronizado correctamente!"]
        elif diferentes:
            lineas += ["", "── DIFERENCIAS DE PRECIO ──"]
            for d in diferentes[:5]:
                lineas.append(f"\n📦 {d['nombre']}")
                for diff in d["diffs"]:
                    lineas.append(f"   {diff}")

        await update.message.reply_text("\n".join(lineas))
    except Exception as e:
        await update.message.reply_text(f"❌ Error en verificación: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# /exportar_precios  — genera reporte local (sin Drive)
# ─────────────────────────────────────────────────────────────────────────────

async def comando_exportar_precios(update, context):
    """
    Vuelca precios de memoria a un Excel temporal y lo envía en el chat.
    Sin subir a Drive.
    """
    await update.message.reply_text("📤 Exportando precios…")
    try:
        from precio_sync import exportar_catalogo_a_excel
        resultado    = await asyncio.to_thread(exportar_catalogo_a_excel)
        actualizados = resultado["actualizados"]
        sin_match    = resultado["sin_match"]
        errores      = resultado["errores"]

        lineas = [
            "📤 EXPORTACIÓN COMPLETADA", "─" * 30,
            f"✅ Productos actualizados: {actualizados}",
        ]
        if sin_match:
            lineas.append(f"⚠️  No encontrados: {len(sin_match)}")
        if errores:
            lineas.append(f"❌ Errores: {len(errores)}")
        await update.message.reply_text("\n".join(lineas))

        if sin_match:
            try:
                from precio_sync import generar_reporte_discrepancias
                reporte_data = {"sin_match": sin_match, "diferentes": [], "solo_memoria": [], "solo_excel": []}
                ruta = await asyncio.to_thread(generar_reporte_discrepancias, reporte_data)
                with open(ruta, "rb") as f:
                    await update.message.reply_document(
                        document=f, filename="reporte_exportacion.xlsx",
                        caption="📎 Productos en memoria no encontrados en Excel"
                    )
                os.remove(ruta)
            except Exception as e:
                await update.message.reply_text(f"⚠️ No se pudo generar el reporte: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error en exportación: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# /keepalive
# ─────────────────────────────────────────────────────────────────────────────

async def comando_keepalive(update, context):
    from keepalive import keepalive_activo, set_keepalive

    args = context.args
    if args:
        arg = args[0].lower().strip()
        if arg == "on":
            set_keepalive(True)
            await update.message.reply_text("✅ Keep-alive ACTIVADO")
        elif arg == "off":
            set_keepalive(False)
            await update.message.reply_text("⏸ Keep-alive DESACTIVADO")
        else:
            await update.message.reply_text("Uso: /keepalive on | /keepalive off")
        return

    from datetime import time
    activo  = keepalive_activo()
    ahora   = datetime.now(config.COLOMBIA_TZ).time()
    horario = time(8, 0) <= ahora <= time(11, 0)

    if activo and horario:
        estado_emoji, estado_texto = "🟢", "ACTIVO y en horario (ping cada 4 min)"
    elif activo:
        estado_emoji, estado_texto = "🟡", "ACTIVADO pero fuera de horario 8-11am"
    else:
        estado_emoji, estado_texto = "🔴", "DESACTIVADO manualmente"

    await update.message.reply_text(
        f"{estado_emoji} Keep-alive: {estado_texto}\n\n"
        "/keepalive on  → activar\n"
        "/keepalive off → desactivar"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AGREGAR PRODUCTO AL CATÁLOGO
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIAS_DISPONIBLES = {
    "1": "1 Artículos de Ferreteria",
    "2": "2 Pinturas y Disolventes",
    "3": "3 Tornilleria",
    "4": "4 Impermeabilizantes y Materiales de construcción",
    "5": "5 Materiales Electricos",
}
CATEGORIAS_DISPLAY = {
    "1": "Artículos de Ferreteria",
    "2": "Pinturas y Disolventes",
    "3": "Tornilleria",
    "4": "Impermeabilizantes y Materiales de construcción",
    "5": "Materiales Eléctricos",
}
_PASOS_ORDEN               = ["nombre", "categoria", "precio"]
CATEGORIAS_CON_FRACCIONES  = {"2 pinturas y disolventes"}
CATEGORIAS_TORNILLERIA     = {"3 tornilleria"}


async def comando_agregar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nuevo_producto"] = {}
    context.user_data["paso_producto"]  = "nombre"
    await update.message.reply_text(
        "➕ Agregar producto nuevo\n\n"
        "Escribe el nombre del producto:\n\n"
        "_(Escribe 'cancelar' en cualquier momento para salir)_",
        parse_mode="Markdown"
    )


def _texto_categoria_prompt(nombre_prod: str) -> str:
    cats = "\n".join(f"  {k}. {v}" for k, v in CATEGORIAS_DISPLAY.items())
    return (
        f"Producto: *{nombre_prod}*\n\n"
        f"Elige la categoría:\n{cats}\n\n"
        f"Responde con el número (1-5):\n\n"
        f"_(Escribe 'volver' para cambiar el nombre o 'cancelar' para salir)_"
    )


async def manejar_flujo_agregar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    paso = context.user_data.get("paso_producto")
    if not paso:
        return False

    texto = update.message.text.strip()

    if texto.lower() in {"cancelar", "/cancelar"}:
        context.user_data.pop("nuevo_producto", None)
        context.user_data.pop("paso_producto", None)
        await update.message.reply_text("❌ Registro cancelado.")
        return True

    prod = context.user_data.get("nuevo_producto", {})

    # Volver al paso anterior
    if texto.lower() in {"volver", "atras", "atrás"}:
        if paso == "categoria":
            context.user_data["paso_producto"] = "codigo"
            await update.message.reply_text(
                "↩️ Volvemos al código.\n\n¿Cuál es el código del producto?\n_(Escribe 'omitir' si no tiene código)_",
                parse_mode="Markdown"
            )
            return True
        elif paso == "precio":
            context.user_data["paso_producto"] = "categoria"
            await update.message.reply_text(_texto_categoria_prompt(prod.get("nombre", "")), parse_mode="Markdown")
            return True
        elif paso in {"fracciones_3_4", "mayorista"}:
            context.user_data["paso_producto"] = "precio"
            await update.message.reply_text(
                "↩️ Volvemos al precio.\n\n¿Cuál es el precio de la unidad completa?",
                parse_mode="Markdown"
            )
            return True
        elif paso.startswith("fracciones_"):
            orden_fracs = ["fracciones_3_4", "fracciones_1_2", "fracciones_1_4", "fracciones_1_8", "fracciones_1_16"]
            idx         = orden_fracs.index(paso) if paso in orden_fracs else -1
            if idx > 0:
                paso_ant  = orden_fracs[idx - 1]
                frac_ant  = {"fracciones_3_4":"3/4","fracciones_1_2":"1/2","fracciones_1_4":"1/4",
                              "fracciones_1_8":"1/8","fracciones_1_16":"1/16"}.get(paso_ant,"")
                context.user_data["paso_producto"] = paso_ant
                prod.get("fracciones", {}).pop(frac_ant, None)
                context.user_data["nuevo_producto"] = prod
                await update.message.reply_text(f"↩️ Volvemos a la fracción {frac_ant}.\n\n¿Precio unitario para vender {frac_ant}?\n(Escribe 0 si no aplica)")
            else:
                context.user_data["paso_producto"] = "precio"
                await update.message.reply_text("↩️ Volvemos al precio.\n\n¿Cuál es el precio de la unidad completa?")
            return True
        elif paso == "confirmar":
            cat_lower = prod.get("categoria", "").lower()
            if cat_lower in CATEGORIAS_CON_FRACCIONES:
                context.user_data["paso_producto"] = "fracciones_1_16"
                await update.message.reply_text("↩️ Volvemos a la última fracción.\n\n¿Precio unitario para vender 1/16?\n(Escribe 0 si no aplica)")
            elif cat_lower in CATEGORIAS_TORNILLERIA:
                context.user_data["paso_producto"] = "mayorista"
                await update.message.reply_text("↩️ Volvemos al precio mayorista.\n\n¿Precio unitario para 50+ unidades?\n(Escribe 0 si no aplica)")
            else:
                context.user_data["paso_producto"] = "precio"
                await update.message.reply_text("↩️ Volvemos al precio.\n\n¿Cuál es el precio de la unidad completa?")
            return True
        else:
            await update.message.reply_text("Ya estás en el primer paso. Escribe 'cancelar' para salir.")
            return True

    if paso == "nombre":
        if len(texto) < 2:
            await update.message.reply_text("Nombre muy corto."); return True
        prod["nombre"] = texto
        context.user_data["nuevo_producto"] = prod
        context.user_data["paso_producto"]  = "codigo"
        await update.message.reply_text(
            f"Nombre: *{texto}*\n\n¿Cuál es el código del producto?\n"
            f"_(Escribe 'omitir' si no tiene código)_",
            parse_mode="Markdown"
        )
        return True

    if paso == "codigo":
        prod["codigo"] = "" if texto.lower() in {"omitir","no","ninguno","-"} else texto.strip()
        context.user_data["nuevo_producto"] = prod
        context.user_data["paso_producto"]  = "categoria"
        await update.message.reply_text(_texto_categoria_prompt(prod["nombre"]), parse_mode="Markdown")
        return True

    if paso == "categoria":
        if texto not in CATEGORIAS_DISPONIBLES:
            await update.message.reply_text("Responde con un número del 1 al 5:"); return True
        prod["categoria"] = CATEGORIAS_DISPONIBLES[texto]
        context.user_data["nuevo_producto"] = prod
        context.user_data["paso_producto"]  = "precio"
        await update.message.reply_text(
            f"Categoría: *{CATEGORIAS_DISPLAY[texto]}*\n\n"
            f"¿Cuál es el precio de la unidad completa?\n(solo el número, ej: 50000)\n\n"
            f"_(Escribe 'volver' para cambiar la categoría)_",
            parse_mode="Markdown"
        )
        return True

    if paso == "precio":
        try:
            precio = float(texto.replace(",","").replace(".","").replace("$",""))
            if precio <= 0: raise ValueError
        except ValueError:
            await update.message.reply_text("Precio inválido. Escribe solo el número (ej: 50000):"); return True
        prod["precio_unidad"] = precio
        context.user_data["nuevo_producto"] = prod
        cat_lower = prod["categoria"].lower()
        if cat_lower in CATEGORIAS_CON_FRACCIONES:
            context.user_data["paso_producto"] = "fracciones_3_4"
            await update.message.reply_text(
                f"Precio base: ${precio:,.0f}\n\nEs de Pinturas/Disolventes — necesito los precios por fracción.\n"
                f"(Escribe 0 si no aplica esa fracción)\n\n¿Precio unitario para vender 3/4?",
                parse_mode="Markdown"
            )
        elif cat_lower in CATEGORIAS_TORNILLERIA:
            context.user_data["paso_producto"] = "mayorista"
            await update.message.reply_text(
                f"Precio base: ${precio:,.0f}\n\nEs Tornillería — ¿precio unitario para 50+ unidades?\n(Escribe 0 si no aplica)",
                parse_mode="Markdown"
            )
        else:
            context.user_data["paso_producto"] = "confirmar"
            await _mostrar_confirmacion(update, prod)
        return True

    for frac_paso, frac_key, frac_mult, siguiente_paso, siguiente_texto in [
        ("fracciones_3_4", "3/4",  0.75,   "fracciones_1_2", "¿Precio unitario para vender 1/2?"),
        ("fracciones_1_2", "1/2",  0.5,    "fracciones_1_4", "¿Precio unitario para vender 1/4?"),
        ("fracciones_1_4", "1/4",  0.25,   "fracciones_1_8", "¿Precio unitario para vender 1/8?"),
        ("fracciones_1_8", "1/8",  0.125,  "fracciones_1_16","¿Precio unitario para vender 1/16?"),
        ("fracciones_1_16","1/16", 0.0625, "confirmar",       None),
    ]:
        if paso == frac_paso:
            try:
                val = float(texto.replace(",","").replace(".","").replace("$",""))
            except ValueError:
                await update.message.reply_text("Escribe solo el número (ej: 52000 o 0):"); return True
            if val > 0:
                prod.setdefault("fracciones", {})[frac_key] = val
            context.user_data["nuevo_producto"] = prod
            context.user_data["paso_producto"]  = siguiente_paso
            if siguiente_paso == "confirmar":
                await _mostrar_confirmacion(update, prod)
            else:
                await update.message.reply_text(siguiente_texto)
            return True

    if paso == "mayorista":
        try:
            val = float(texto.replace(",","").replace(".","").replace("$",""))
        except ValueError:
            await update.message.reply_text("Escribe solo el número:"); return True
        if val > 0:
            prod["precio_mayorista"] = val
        context.user_data["nuevo_producto"] = prod
        context.user_data["paso_producto"]  = "confirmar"
        await _mostrar_confirmacion(update, prod)
        return True

    if paso == "confirmar":
        if texto.lower() in {"si","sí","s","yes"}:
            await _guardar_producto(update, context, prod)
        else:
            context.user_data.pop("nuevo_producto", None)
            context.user_data.pop("paso_producto",  None)
            await update.message.reply_text("❌ Cancelado. El producto no fue guardado.")
        return True

    return False


async def _mostrar_confirmacion(update, prod: dict):
    lineas = [
        f"📦 Confirmar producto nuevo:\n",
        f"Nombre:    {prod['nombre']}",
        f"Categoría: {prod['categoria']}",
        f"Precio:    ${prod['precio_unidad']:,.0f}",
    ]
    fracs = prod.get("fracciones", {})
    if fracs:
        lineas.append("Fracciones:")
        for frac, p_unit in fracs.items():
            mult  = {"3/4":0.75,"1/2":0.5,"1/4":0.25,"1/8":0.125,"1/16":0.0625}[frac]
            total = round(p_unit * mult)
            lineas.append(f"  {frac}: ${total:,.0f}  (unitario: ${p_unit:,.0f})")
    if prod.get("precio_mayorista"):
        lineas.append(f"Mayorista: ${prod['precio_mayorista']:,.0f} (x50+)")
    lineas.append("\n¿Confirmas? (si / no)\n_(Escribe 'volver' para corregir el último dato)_")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def _guardar_producto(update, context, prod: dict):
    """Guarda el producto en memoria/catálogo. Sin Drive ni Excel."""
    from utils import _normalizar
    from memoria import (cargar_memoria, guardar_memoria, invalidar_cache_memoria,
                         _es_producto_con_fracciones, _es_tornillo_drywall)

    mem      = cargar_memoria()
    catalogo = mem.get("catalogo", {})

    nombre        = prod["nombre"]
    categoria     = prod["categoria"]
    precio_unidad = prod["precio_unidad"]
    fracs_input   = prod.get("fracciones", {})
    p_mayorista   = prod.get("precio_mayorista")

    nombre_lower = _normalizar(nombre)
    clave        = nombre_lower.replace(" ", "_")

    entrada = {
        "nombre":        nombre,
        "nombre_lower":  nombre_lower,
        "categoria":     categoria,
        "precio_unidad": round(precio_unidad),
    }
    codigo_prod = prod.get("codigo", "").strip()
    if codigo_prod:
        entrada["codigo"] = codigo_prod

    if _es_tornillo_drywall(nombre) and p_mayorista:
        entrada["precio_por_cantidad"] = {
            "umbral":              50,
            "precio_bajo_umbral":  round(precio_unidad),
            "precio_sobre_umbral": round(p_mayorista),
        }
    elif fracs_input:
        mult_map  = {"3/4":0.75,"1/2":0.5,"1/4":0.25,"1/8":0.125,"1/16":0.0625}
        fracs_cat = {}
        for frac, p_unit in fracs_input.items():
            fracs_cat[frac] = {"precio": round(p_unit * mult_map[frac])}
        entrada["precios_fraccion"] = fracs_cat

    catalogo[clave] = entrada
    mem["catalogo"] = catalogo
    guardar_memoria(mem, urgente=True)
    invalidar_cache_memoria()

    try:
        from fuzzy_match import construir_indice
        construir_indice(catalogo)
    except Exception:
        pass

    context.user_data.pop("nuevo_producto", None)
    context.user_data.pop("paso_producto",  None)

    await update.message.reply_text(
        f"✅ Producto guardado en el catálogo.\n\n"
        f"Ya puedes registrar ventas de '{nombre}'.\n\n"
        f"_Nota: para agregarlo al Excel BASE_DE_DATOS_PRODUCTOS.xlsx, "
        f"usa /actualizar_catalogo y sube el archivo actualizado._",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /actualizar_precio
# ─────────────────────────────────────────────────────────────────────────────

async def comando_actualizar_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from ventas_state import actualizando_precios, _estado_lock

    chat_id   = update.effective_chat.id
    args_text = " ".join(context.args) if context.args else ""
    if args_text and "=" in args_text:
        await _procesar_linea_precio(args_text, update)
        return

    with _estado_lock:
        actualizando_precios[chat_id] = True

    await update.message.reply_text(
        "💰 Modo actualización de precios\n\n"
        "Envía los precios así:\n"
        "  producto= precio\n"
        "  producto= precio / precio_mayorista\n"
        "  producto 1/4= precio_fraccion\n\n"
        "Ejemplo:\n"
        "  Tornillo drywall 6x1= 42/30\n"
        "  Vinilo T1 Blanco= 50000\n"
        "  Thinner 1/4= 8000\n\n"
        "Escribe 'listo' para salir."
    )


async def _procesar_linea_precio(linea: str, update):
    import re as _re
    from precio_sync import actualizar_precio as _ap
    from memoria import buscar_producto_en_catalogo, invalidar_cache_memoria, cargar_memoria, guardar_memoria

    linea = linea.strip()
    if not linea:
        return

    _FRACCIONES = {"1/16", "1/8", "1/4", "1/3", "3/8", "1/2", "3/4"}

    def _parse_precio(s):
        return float(s.replace(".", "").replace(",", ""))

    PAT_DOS = _re.compile(r"^(.+?)\s*(?:=|:|→|->)\s*\$?\s*([\d][\d.,]*)\s*/\s*\$?\s*([\d][\d.,]*)$")
    PAT_UNO = _re.compile(r"^(.+?)\s*(?:=|:|→|->)\s*\$?\s*([\d][\d.,]*)$")

    precio_mayorista = None
    m = PAT_DOS.match(linea)
    if m:
        nombre_raw = m.group(1).strip()
        try:
            precio = _parse_precio(m.group(2))
            precio_mayorista = _parse_precio(m.group(3))
        except ValueError:
            await update.message.reply_text(f"❌ No entendí el precio: {linea}"); return
    else:
        m = PAT_UNO.match(linea)
        if not m:
            await update.message.reply_text(f"❌ Formato: producto= precio. Ej: Vinilo T1= 50000"); return
        nombre_raw = m.group(1).strip()
        try:
            precio = _parse_precio(m.group(2))
        except ValueError:
            await update.message.reply_text(f"❌ No entendí el precio: {linea}"); return

    if precio <= 0:
        await update.message.reply_text("❌ El precio debe ser mayor a 0."); return

    fraccion     = None
    nombre_lower = nombre_raw.lower()
    for frac in _FRACCIONES:
        if nombre_lower.endswith(" " + frac):
            fraccion   = frac
            nombre_raw = nombre_raw[:-(len(frac)+1)].strip()
            break

    prod = buscar_producto_en_catalogo(nombre_raw)
    if not prod:
        await update.message.reply_text(f"⚠️ No encontré '{nombre_raw}' en el catálogo."); return

    nombre_display = prod["nombre"]

    if precio_mayorista is not None:
        mem  = cargar_memoria()
        cat  = mem.get("catalogo", {})
        clave = next((k for k,v in cat.items() if v.get("nombre_lower") == prod.get("nombre_lower","")), None)
        if clave:
            cat[clave]["precio_unidad"] = round(precio)
            pxc = cat[clave].get("precio_por_cantidad", {})
            pxc["precio_bajo_umbral"]  = round(precio)
            pxc["precio_sobre_umbral"] = round(precio_mayorista)
            if "umbral" not in pxc:
                pxc["umbral"] = 50
            cat[clave]["precio_por_cantidad"] = pxc
            mem["catalogo"] = cat
            guardar_memoria(mem)
            invalidar_cache_memoria()
            try:
                _ap(nombre_display, round(precio), fraccion)
            except Exception:
                pass
            await update.message.reply_text(
                f"✅ {nombre_display}\n"
                f"   Unitario: ${round(precio):,} → Mayorista: ${round(precio_mayorista):,}"
            )
        else:
            await update.message.reply_text(f"⚠️ No encontré '{nombre_raw}' en el catálogo.")
        return

    ok, desc = _ap(nombre_display, round(precio), fraccion)
    if ok:
        frac_txt = f" ({fraccion})" if fraccion else ""
        await update.message.reply_text(f"✅ {nombre_display}{frac_txt} → ${round(precio):,}")
    else:
        await update.message.reply_text(f"⚠️ {desc}")


async def manejar_mensaje_precio(update, mensaje: str) -> bool:
    from ventas_state import actualizando_precios, _estado_lock

    chat_id = update.effective_chat.id
    with _estado_lock:
        if not actualizando_precios.get(chat_id):
            return False

    msg = mensaje.strip().lower()
    if msg in ("listo", "salir", "exit", "ok", "ya", "fin"):
        with _estado_lock:
            actualizando_precios.pop(chat_id, None)
        await update.message.reply_text("✅ Modo actualización de precios finalizado.")
        return True

    lineas = [l.strip() for l in mensaje.strip().split("\n") if l.strip()]
    if len(lineas) == 1 and "," in lineas[0]:
        lineas = [l.strip() for l in lineas[0].split(",") if l.strip()]
    for linea in lineas:
        await _procesar_linea_precio(linea, update)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# /modelo
# ─────────────────────────────────────────────────────────────────────────────

async def comando_modelo(update, context):
    chat_id = update.effective_chat.id
    args    = context.args
    opciones_validas = ("auto", "haiku", "sonnet")

    if not args:
        actual = context.user_data.get("modelo_preferido", "auto")
        await update.message.reply_text(
            f"🤖 *Modelo actual:* `{actual}`\n\n"
            f"  `/modelo auto` — selección automática\n"
            f"  `/modelo haiku` — ⚡ rápido y eficiente\n"
            f"  `/modelo sonnet` — 🧠 más inteligente",
            parse_mode="Markdown"
        )
        return

    seleccion = args[0].lower()
    if seleccion not in opciones_validas:
        await update.message.reply_text("❌ Opción inválida. Usa: `auto`, `haiku` o `sonnet`", parse_mode="Markdown")
        return

    context.user_data["modelo_preferido"] = seleccion
    emojis       = {"auto":"⚙️","haiku":"⚡","sonnet":"🧠"}
    descripciones = {
        "auto":   "selección automática según el mensaje",
        "haiku":  "rápido y eficiente para ventas simples",
        "sonnet": "más inteligente para consultas complejas",
    }
    await update.message.reply_text(
        f"{emojis[seleccion]} *Modelo cambiado a `{seleccion}`*\n_{descripciones[seleccion]}_",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /factura - Registrar factura de proveedor
# ─────────────────────────────────────────────────────────────────────────────
# Fotos: se manejan en mensajes.py con upload_foto_cloudinary()
# Estado: context.user_data["esperando_foto_factura"] = fac_id
# ─────────────────────────────────────────────────────────────────────────────

async def comando_factura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Registra una factura de proveedor.
    Uso: /factura Proveedor Total descripción opcional

    La foto de la factura se guarda en Cloudinary (ver mensajes.py).
    """
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "📄 *Registrar factura de proveedor*\n\n"
            "Uso: `/factura Proveedor Total Descripción`\n\n"
            "Ejemplos:\n"
            "• `/factura Ferrisariato 700000 surtido tornillería`\n"
            "• `/factura Pinturas Davinci 350000 brochas`\n\n"
            "Después podrás adjuntar la foto de la factura (se guarda en Cloudinary).",
            parse_mode="Markdown"
        )
        return

    import re as _re
    texto    = " ".join(args)
    m_total  = _re.search(r'(\d[\d.,]*)', texto)
    if not m_total:
        await update.message.reply_text("❌ No encontré el monto. Ejemplo: `/factura Ferrisariato 700000`", parse_mode="Markdown")
        return

    total_str = m_total.group(1).replace(".", "").replace(",", "")
    try:
        total = float(total_str)
    except ValueError:
        await update.message.reply_text("❌ Monto inválido.", parse_mode="Markdown")
        return

    idx_num     = texto.find(m_total.group(0))
    proveedor   = texto[:idx_num].strip().strip('"').strip("'")
    if not proveedor:
        await update.message.reply_text("❌ Falta el nombre del proveedor.", parse_mode="Markdown")
        return

    descripcion = texto[idx_num + len(m_total.group(0)):].strip() or "Sin descripción"

    from memoria import registrar_factura_proveedor
    factura = registrar_factura_proveedor(
        proveedor   = proveedor,
        descripcion = descripcion,
        total       = total,
    )
    fac_id = factura["id"]

    # Estado para recibir la foto → mensajes.py llamará upload_foto_cloudinary()
    context.user_data["esperando_foto_factura"] = fac_id

    await update.message.reply_text(
        f"✅ *Factura {fac_id} registrada*\n\n"
        f"🏪 Proveedor: {proveedor}\n"
        f"💰 Total: ${total:,.0f}\n"
        f"📝 Descripción: {descripcion}\n"
        f"📊 Estado: PENDIENTE\n\n"
        f"📸 Envía la foto de la factura ahora (se guardará en Cloudinary)\n"
        f"_(o escribe `sin foto` para omitir)_",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /abonar - Registrar abono a factura
# ─────────────────────────────────────────────────────────────────────────────
# Fotos: se manejan en mensajes.py con upload_foto_cloudinary()
# Estado: context.user_data["esperando_foto_abono"] = fac_id
# ─────────────────────────────────────────────────────────────────────────────

async def comando_abonar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Registra un abono a una factura existente.
    Uso: /abonar FAC-001 500000

    El comprobante de pago se guarda en Cloudinary (ver mensajes.py).
    """
    args = context.args
    if len(args) < 2:
        from memoria import listar_facturas
        pendientes = listar_facturas(solo_pendientes=True)
        if not pendientes:
            await update.message.reply_text(
                "📋 No hay facturas pendientes.\n\n"
                "Usa `/factura Proveedor Total` para registrar una.",
                parse_mode="Markdown"
            )
            return
        lineas = ["📋 *Facturas pendientes:*\n"]
        for f in pendientes[:8]:
            lineas.append(
                f"• `{f['id']}` — {f['proveedor']} — "
                f"Pendiente: ${f['pendiente']:,.0f} ({f['estado']})"
            )
        lineas.append("\nUso: `/abonar FAC-001 500000`")
        await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")
        return

    fac_id    = args[0].upper()
    monto_str = args[1].replace(".", "").replace(",", "")
    try:
        monto = float(monto_str)
    except ValueError:
        await update.message.reply_text("❌ Monto inválido.", parse_mode="Markdown")
        return

    from memoria import registrar_abono_factura
    result = registrar_abono_factura(fac_id=fac_id, monto=monto)

    if not result["ok"]:
        await update.message.reply_text(f"❌ {result['error']}", parse_mode="Markdown")
        return

    fac          = result["factura"]
    estado_emoji = {"pagada":"✅","parcial":"🔶","pendiente":"🔴"}.get(fac["estado"], "📄")

    # Estado para recibir el comprobante → mensajes.py llamará upload_foto_cloudinary()
    context.user_data["esperando_foto_abono"] = fac_id

    await update.message.reply_text(
        f"✅ *Abono registrado — {fac_id}*\n\n"
        f"🏪 Proveedor: {fac['proveedor']}\n"
        f"💸 Abono: ${monto:,.0f}\n"
        f"✔️ Total pagado: ${fac['pagado']:,.0f}\n"
        f"⏳ Pendiente: ${fac['pendiente']:,.0f}\n"
        f"{estado_emoji} Estado: {fac['estado'].upper()}\n\n"
        f"📸 Envía el comprobante de pago (se guardará en Cloudinary)\n"
        f"_(o escribe `sin foto` para omitir)_",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /deudas
# ─────────────────────────────────────────────────────────────────────────────

async def comando_deudas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from memoria import listar_facturas
    from collections import defaultdict

    todas      = listar_facturas()
    if not todas:
        await update.message.reply_text(
            "📋 No hay facturas registradas.\n"
            "Usa `/factura Proveedor Total` para registrar una.",
            parse_mode="Markdown"
        )
        return

    pendientes  = [f for f in todas if f["estado"] != "pagada"]
    total_deuda = sum(f["pendiente"] for f in pendientes)

    por_proveedor = defaultdict(float)
    for f in pendientes:
        por_proveedor[f["proveedor"]] += f["pendiente"]

    lineas = [f"💳 *DEUDAS CON PROVEEDORES*\n"]
    for prov, deuda in sorted(por_proveedor.items(), key=lambda x: -x[1]):
        lineas.append(f"• {prov}: ${deuda:,.0f}")
    lineas.append(f"\n💰 *Total deuda: ${total_deuda:,.0f}*")
    lineas.append(f"\n{len(pendientes)} factura(s) pendiente(s)")
    lineas.append("\nUsa `/abonar` para ver las facturas o registrar un pago.")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# /facturas — historial completo con fotos
# ─────────────────────────────────────────────────────────────────────────────

async def comando_facturas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Muestra historial de facturas con sus abonos y links de fotos.

    Uso:
      /facturas              → todas las facturas
      /facturas pagadas      → solo las pagadas
      /facturas pendientes   → solo pendientes/parciales
      /facturas Davinci      → filtra por nombre de proveedor
    """
    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible.")
        return

    filtro = " ".join(context.args).strip() if context.args else ""
    filtro_lower = filtro.lower()

    # Armar query según filtro
    if filtro_lower == "pagadas":
        where = "WHERE fp.estado = 'pagada'"
        params = []
        titulo = "✅ Facturas PAGADAS"
    elif filtro_lower in ("pendientes", "pendiente"):
        where = "WHERE fp.estado IN ('pendiente', 'parcial')"
        params = []
        titulo = "🔴 Facturas PENDIENTES / PARCIALES"
    elif filtro:
        where = "WHERE fp.proveedor ILIKE %s"
        params = [f"%{filtro}%"]
        titulo = f"📋 Facturas — {filtro}"
    else:
        where = ""
        params = []
        titulo = "📋 Historial completo de facturas"

    facturas = await asyncio.to_thread(
        _db.query_all,
        f"""
        SELECT fp.id, fp.proveedor, fp.descripcion, fp.total,
               fp.pagado, fp.pendiente, fp.estado, fp.fecha::text,
               fp.foto_url, fp.foto_nombre
        FROM   facturas_proveedores fp
        {where}
        ORDER  BY fp.fecha DESC, fp.id DESC
        """,
        params or None,
    )

    if not facturas:
        await update.message.reply_text(
            f"📋 No hay facturas{' para «' + filtro + '»' if filtro else ''}.\n\n"
            "Usa `/factura Proveedor Total Descripción` para registrar una.",
            parse_mode="Markdown"
        )
        return

    # Cargar abonos de todas las facturas de una sola query
    ids = [r["id"] for r in facturas]
    placeholders = ",".join(["%s"] * len(ids))
    abonos_rows = await asyncio.to_thread(
        _db.query_all,
        f"""
        SELECT factura_id, monto, fecha::text, foto_url, foto_nombre
        FROM   facturas_abonos
        WHERE  factura_id IN ({placeholders})
        ORDER  BY factura_id, id
        """,
        ids,
    )
    # Indexar abonos por factura_id
    abonos_por_fac: dict = {}
    for ab in (abonos_rows or []):
        abonos_por_fac.setdefault(ab["factura_id"], []).append(ab)

    estado_emoji = {"pagada": "✅", "parcial": "🔶", "pendiente": "🔴"}

    bloques = [f"*{titulo}* ({len(facturas)} factura(s))\n"]

    for fac in facturas:
        fid    = fac["id"]
        prov   = fac["proveedor"]
        desc   = fac["descripcion"] or "—"
        total  = int(fac["total"])
        pagado = int(fac["pagado"])
        pend   = int(fac["pendiente"])
        estado = fac["estado"]
        fecha  = str(fac["fecha"])[:10]
        emoji  = estado_emoji.get(estado, "📄")
        foto_fac = fac.get("foto_url", "")

        linea = (
            f"\n{emoji} *{fid}* — {prov}\n"
            f"   📅 {fecha}  |  💰 ${total:,.0f}  |  {estado.upper()}\n"
            f"   📝 {desc}\n"
        )
        if pagado > 0:
            linea += f"   ✔️ Pagado: ${pagado:,.0f}  |  ⏳ Pendiente: ${pend:,.0f}\n"
        if foto_fac:
            linea += f"   📎 [Ver factura]({foto_fac})\n"

        # Abonos de esta factura
        abonos = abonos_por_fac.get(fid, [])
        for i, ab in enumerate(abonos, 1):
            monto_ab = int(ab["monto"])
            fecha_ab = str(ab["fecha"])[:10]
            foto_ab  = ab.get("foto_url", "")
            linea += f"   💸 Abono {i}: ${monto_ab:,.0f} el {fecha_ab}"
            if foto_ab:
                linea += f"  [Ver comprobante]({foto_ab})"
            linea += "\n"

        bloques.append(linea)

    # Enviar en mensajes de máx 4000 chars
    msg = ""
    for bloque in bloques:
        if len(msg) + len(bloque) > 3800:
            await update.message.reply_text(msg, parse_mode="Markdown",
                                            disable_web_page_preview=True)
            msg = ""
        msg += bloque
    if msg.strip():
        await update.message.reply_text(msg, parse_mode="Markdown",
                                        disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# /borrar_factura
# ─────────────────────────────────────────────────────────────────────────────

async def comando_borrar_factura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    from memoria import cargar_memoria, guardar_memoria

    mem      = cargar_memoria()
    facturas = mem.get("cuentas_por_pagar", [])

    if not args:
        if not facturas:
            await update.message.reply_text("📋 No hay facturas registradas."); return
        lineas = ["📋 *Facturas registradas:*\n"]
        for f in sorted(facturas, key=lambda x: x.get("fecha",""), reverse=True):
            icon = {"pagada":"✅","parcial":"🔶","pendiente":"🔴"}.get(f["estado"],"📄")
            lineas.append(f"{icon} `{f['id']}` — {f['proveedor']} — ${f['total']:,.0f} ({f['estado']})")
        lineas.append("\nUso: `/borrar_factura FAC-001`")
        await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")
        return

    fac_id  = args[0].upper()
    if not fac_id.startswith("FAC-"):
        fac_id = "FAC-" + fac_id

    factura = next((f for f in facturas if f["id"].upper() == fac_id), None)
    if not factura:
        await update.message.reply_text(
            f"❌ No encontré la factura `{fac_id}`.\n"
            f"Usa `/borrar_factura` sin argumentos para ver la lista.",
            parse_mode="Markdown"
        )
        return

    tiene_abonos = len(factura.get("abonos", [])) > 0
    aviso_abonos = (
        f"\n⚠️ Esta factura tiene {len(factura['abonos'])} abono(s) registrado(s) que también se borrarán."
        if tiene_abonos else ""
    )

    mem["cuentas_por_pagar"] = [f for f in facturas if f["id"].upper() != fac_id]
    guardar_memoria(mem, urgente=True)

    await update.message.reply_text(
        f"🗑️ Factura `{fac_id}` eliminada.\n"
        f"Proveedor: {factura['proveedor']} — ${factura['total']:,.0f}"
        f"{aviso_abonos}\n\n"
        f"_Nota: las fotos en Cloudinary no se borran automáticamente._",
        parse_mode="Markdown"
    )
