"""
handlers/cmd_inventario.py — Comandos de inventario, precios y catálogo.

Handlers públicos: comando_buscar, comando_precios, comando_inventario, comando_inv,
                   comando_stock, comando_ajuste, comando_compra, comando_margenes,
                   comando_agregar_producto, comando_actualizar_precio,
                   comando_actualizar_catalogo, manejar_flujo_agregar_producto,
                   manejar_mensaje_precio
Helpers privados:  _resolver_grm, _texto_categoria_prompt, _mostrar_confirmacion,
                   _guardar_producto, _procesar_linea_precio
"""

# -- stdlib --
import asyncio
import logging

# -- terceros --
from telegram import Update
from telegram.ext import ContextTypes

# -- propios --
import config
import db as _db
from memoria import (
    cargar_memoria,
    buscar_productos_inventario,
    ajustar_inventario,
    registrar_conteo_inventario,
    registrar_compra,
    obtener_resumen_margenes,
)
from middleware import protegido

logger = logging.getLogger("ferrebot.handlers.cmd_inventario")


# ─────────────────────────────────────────────────────────────────────────────
# /buscar  — búsqueda en PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

@protegido
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
# /precios
# ─────────────────────────────────────────────────────────────────────────────

@protegido
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
# /inventario — alias de /stock
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_inventario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias de /stock."""
    await comando_stock(update, context)


# ─────────────────────────────────────────────────────────────────────────────
# Helper privado: _resolver_grm
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


# ─────────────────────────────────────────────────────────────────────────────
# /inv - Registrar conteo de inventario
# ─────────────────────────────────────────────────────────────────────────────

@protegido
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

@protegido
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

@protegido
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

@protegido
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

            usuario_id = context.user_data.get("usuario", {}).get("id") if context else None
            await asyncio.to_thread(
                _db.execute,
                """
                INSERT INTO compras
                    (fecha, hora, proveedor, producto_nombre,
                     cantidad, costo_unitario, costo_total, usuario_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (ahora.date(), ahora.strftime("%H:%M"), prov, prod_n, cant_n, cu, ct, usuario_id),
            )
        except Exception as _e_pg:
            import logging as _log
            _log.getLogger("ferrebot").warning(f"PG compra write falló: {_e_pg}")

    await update.message.reply_text(mensaje)


# ─────────────────────────────────────────────────────────────────────────────
# /margenes - Ver márgenes de ganancia
# ─────────────────────────────────────────────────────────────────────────────

@protegido
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
# /actualizar_catalogo  — acepta archivo adjunto (sin Drive)
# ─────────────────────────────────────────────────────────────────────────────

@protegido
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
# AGREGAR PRODUCTO AL CATÁLOGO — constantes y helpers
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


@protegido
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
    """Flujo conversacional para agregar producto. NO lleva @protegido — se llama desde mensajes.py."""
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

@protegido
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
    from memoria import buscar_producto_en_catalogo, invalidar_cache_memoria, actualizar_precio_en_catalogo

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

    # ── Buscar el producto en PG ──────────────────────────────────────────────
    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible."); return

    prod_pg = _db.query_one(
        "SELECT id FROM productos WHERE nombre_lower = %s AND activo = TRUE",
        (prod.get("nombre_lower", nombre_display.lower()),),
    )
    if not prod_pg:
        await update.message.reply_text(f"⚠️ '{nombre_display}' no encontrado en la base de datos."); return

    prod_id = prod_pg["id"]

    try:
        if precio_mayorista is not None:
            # ── Precio doble: unitario + mayorista ────────────────────────────
            _db.execute(
                "UPDATE productos SET precio_unidad=%s, updated_at=NOW() WHERE id=%s",
                (round(precio), prod_id),
            )
            _db.execute(
                """INSERT INTO productos_precio_cantidad
                       (producto_id, umbral, precio_bajo_umbral, precio_sobre_umbral)
                   VALUES (%s, 50, %s, %s)
                   ON CONFLICT (producto_id) DO UPDATE
                       SET precio_bajo_umbral  = EXCLUDED.precio_bajo_umbral,
                           precio_sobre_umbral = EXCLUDED.precio_sobre_umbral""",
                (prod_id, round(precio), round(precio_mayorista)),
            )
            # Mantener caché de memoria sincronizada
            actualizar_precio_en_catalogo(nombre_display, round(precio), None)
            invalidar_cache_memoria()
            await update.message.reply_text(
                f"✅ {nombre_display}\n"
                f"   Unitario: ${round(precio):,} → Mayorista: ${round(precio_mayorista):,}"
            )

        elif fraccion:
            # ── Precio de fracción ────────────────────────────────────────────
            rows = _db.execute(
                "UPDATE productos_fracciones SET precio_total=%s WHERE producto_id=%s AND fraccion=%s",
                (round(precio), prod_id, fraccion),
            )
            if rows == 0:
                _db.execute(
                    """INSERT INTO productos_fracciones (producto_id, fraccion, precio_total, precio_unitario)
                       VALUES (%s, %s, %s, %s)""",
                    (prod_id, fraccion, round(precio), round(precio)),
                )
            actualizar_precio_en_catalogo(nombre_display, round(precio), fraccion)
            invalidar_cache_memoria()
            await update.message.reply_text(f"✅ {nombre_display} ({fraccion}) → ${round(precio):,}")

        else:
            # ── Precio unitario simple ────────────────────────────────────────
            _db.execute(
                "UPDATE productos SET precio_unidad=%s, updated_at=NOW() WHERE id=%s",
                (round(precio), prod_id),
            )
            actualizar_precio_en_catalogo(nombre_display, round(precio), None)
            invalidar_cache_memoria()
            await update.message.reply_text(f"✅ {nombre_display} → ${round(precio):,}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error guardando precio: {e}")


async def manejar_mensaje_precio(update, mensaje: str) -> bool:
    """Flujo conversacional para actualizar precios. NO lleva @protegido — se llama desde mensajes.py."""
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
