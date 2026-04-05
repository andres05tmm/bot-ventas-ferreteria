"""
handlers/cmd_facturacion.py — Comandos de Facturación Electrónica DIAN

Comandos:
  /factura_electronica [consecutivo]  — emite FE para una venta del día actual
  /nota_credito [consecutivo]         — emite nota crédito para una venta ya facturada
  /estado_factura [numero]            — consulta estado DIAN de una factura emitida

Nota: /factura_electronica (NO /factura) para evitar colisión con
cmd_proveedores.py que ya usa /factura para facturas de proveedores.
"""
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config import COLOMBIA_TZ
from middleware import protegido
import db as _db

logger = logging.getLogger("ferrebot.facturacion")


@protegido
async def comando_factura_electronica(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /factura_electronica [consecutivo]
    Emite la factura electrónica DIAN de una venta del día actual.
    Ejemplo: /factura_electronica 5  →  factura el consecutivo 5 de hoy
    """
    args = ctx.args

    if not args:
        await update.message.reply_text(
            "📄 *Factura Electrónica DIAN*\n\n"
            "Uso: `/factura_electronica [consecutivo]`\n"
            "Ejemplo: `/factura_electronica 3`\n\n"
            "Emite la factura electrónica del consecutivo indicado del día de hoy.",
            parse_mode="Markdown",
        )
        return

    try:
        consecutivo = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ El consecutivo debe ser un número entero.")
        return

    hoy = datetime.now(COLOMBIA_TZ).strftime('%Y-%m-%d')

    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, cliente_nombre, total, factura_estado
                FROM ventas
                WHERE consecutivo = %s AND fecha::date = %s
                """,
                (consecutivo, hoy),
            )
            venta = cur.fetchone()

    if not venta:
        await update.message.reply_text(
            f"❌ No encontré el consecutivo *{consecutivo}* de hoy ({hoy}).\n"
            "Verifica con /ventas que la venta existe.",
            parse_mode="Markdown",
        )
        return

    if (venta.get("factura_estado") or "") == "emitida":
        await update.message.reply_text(
            f"⚠️ La venta #{consecutivo} ya tiene factura electrónica emitida."
        )
        return

    await update.message.reply_text(
        f"⏳ Emitiendo factura electrónica para venta #{consecutivo}...\n"
        f"Cliente: {venta['cliente_nombre'] or 'Consumidor Final'}"
    )

    from services.facturacion_service import emitir_factura

    resultado = await emitir_factura(venta["id"])

    if not resultado["ok"]:
        await update.message.reply_text(
            f"❌ Error DIAN:\n{resultado['error']}",
            # Sin parse_mode para evitar crash con caracteres especiales en el error
        )
        return

    cufe_corto = resultado["cufe"][:40] if resultado["cufe"] else "N/A"

    if resultado.get("pdf_telegram"):
        entrega = "📲 Sin correo registrado — PDF enviado al grupo de Telegram."
    else:
        entrega = "📧 PDF enviado al correo del cliente automáticamente."

    await update.message.reply_text(
        f"✅ *Factura {resultado['numero']} emitida ante la DIAN*\n\n"
        f"🏢 Cliente: {venta['cliente_nombre'] or 'Consumidor Final'}\n"
        f"💰 Total: ${venta['total']:,}\n"
        f"🔑 CUFE: `{cufe_corto}...`\n\n"
        f"{entrega}",
        parse_mode="Markdown",
    )


# ── /nota_credito — Emitir nota crédito para una venta ya facturada ──────────

@protegido
async def comando_nota_credito(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /nota_credito [consecutivo]
    Emite una nota crédito DIAN para anular la factura de una venta del día actual.
    Ejemplo: /nota_credito 5  →  anula la factura del consecutivo 5 de hoy

    Por defecto usa razon_id=2 (Anulación de factura).
    Para devolución parcial usar el dashboard web.
    """
    args = ctx.args

    if not args:
        await update.message.reply_text(
            "🔄 *Nota Crédito DIAN*\n\n"
            "Uso: `/nota_credito [consecutivo]`\n"
            "Ejemplo: `/nota_credito 3`\n\n"
            "Anula la factura electrónica del consecutivo indicado de hoy.\n"
            "Para devoluciones parciales, usa el dashboard web.",
            parse_mode="Markdown",
        )
        return

    try:
        consecutivo = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ El consecutivo debe ser un número entero.")
        return

    hoy = datetime.now(COLOMBIA_TZ).strftime('%Y-%m-%d')

    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, cliente_nombre, total,
                       factura_estado, factura_cufe, factura_numero, fecha::text AS fecha
                FROM ventas
                WHERE consecutivo = %s AND fecha::date = %s
                """,
                (consecutivo, hoy),
            )
            venta = cur.fetchone()

    if not venta:
        await update.message.reply_text(
            f"❌ No encontré el consecutivo *{consecutivo}* de hoy ({hoy}).\n"
            "Verifica con /ventas que la venta existe.",
            parse_mode="Markdown",
        )
        return

    if (venta.get("factura_estado") or "") != "emitida":
        await update.message.reply_text(
            f"⚠️ La venta #{consecutivo} no tiene factura electrónica emitida.\n"
            "Primero emite la factura con `/factura_electronica {consecutivo}`.",
            parse_mode="Markdown",
        )
        return

    factura_cufe   = venta.get("factura_cufe") or ""
    factura_numero = venta.get("factura_numero") or ""
    factura_fecha  = (venta.get("fecha") or hoy)[:10]

    if not factura_cufe:
        await update.message.reply_text(
            "❌ La factura no tiene CUFE registrado. No se puede emitir nota crédito."
        )
        return

    await update.message.reply_text(
        f"⏳ Emitiendo nota crédito (anulación) para factura *{factura_numero}*...\n"
        f"Cliente: {venta['cliente_nombre'] or 'Consumidor Final'}",
        parse_mode="Markdown",
    )

    # Recuperar el detalle completo de la venta para las líneas de la nota
    rows = _db.query_all(
        """
        SELECT vd.producto_nombre, vd.producto_id, vd.cantidad,
               vd.precio_unitario, vd.total, vd.unidad_medida,
               COALESCE(p.tiene_iva, FALSE)      AS tiene_iva,
               COALESCE(p.porcentaje_iva, 0)     AS porcentaje_iva
        FROM ventas_detalle vd
        LEFT JOIN productos p ON vd.producto_id = p.id
        WHERE vd.venta_id = %s
        """,
        (venta["id"],),
    )
    lineas = [dict(r) for r in rows]

    from services.facturacion_service import emitir_nota_credito

    resultado = await emitir_nota_credito(
        factura_cufe     = factura_cufe,
        factura_numero   = factura_numero,
        factura_fecha    = factura_fecha,
        razon_id         = 2,   # 2 = Anulación de factura
        venta_id         = venta["id"],
        lineas_devueltas = lineas,
    )

    if not resultado["ok"]:
        await update.message.reply_text(
            f"❌ Error al emitir nota crédito DIAN:\n{resultado['error']}"
        )
        return

    cufe_corto = resultado["cufe"][:40] if resultado["cufe"] else "N/A"
    await update.message.reply_text(
        f"✅ *Nota Crédito {resultado['numero']} emitida*\n\n"
        f"📋 Factura anulada: {factura_numero}\n"
        f"🏢 Cliente: {venta['cliente_nombre'] or 'Consumidor Final'}\n"
        f"💰 Total: ${venta['total']:,}\n"
        f"🔑 CUFE: `{cufe_corto}...`",
        parse_mode="Markdown",
    )


# ── /estado_factura — Consultar estado DIAN ──────────────────────────────────

@protegido
async def comando_estado_factura(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /estado_factura [numero]
    Consulta el estado de validación DIAN de una factura emitida.
    Ejemplo: /estado_factura LZT5280  o  /estado_factura 5280
    """
    args = ctx.args

    if not args:
        await update.message.reply_text(
            "📊 *Estado DIAN de factura*\n\n"
            "Uso: `/estado_factura [numero]`\n"
            "Ejemplo: `/estado_factura LZT5280`",
            parse_mode="Markdown",
        )
        return

    numero = args[0].upper()

    await update.message.reply_text(f"🔍 Consultando estado DIAN para *{numero}*...", parse_mode="Markdown")

    from services.facturacion_service import consultar_estado_dian, MATIAS_PREFIX

    try:
        # Si el número no incluye prefijo, lo agrega automáticamente
        if not any(c.isalpha() for c in numero):
            data = await consultar_estado_dian(numero, MATIAS_PREFIX)
        else:
            data = await consultar_estado_dian(numero)
    except RuntimeError as e:
        await update.message.reply_text(f"❌ Error consultando DIAN:\n{e}")
        return

    # Extraer campos relevantes (MATIAS API puede variar la estructura)
    status_desc = (
        data.get("StatusDescription")
        or data.get("status_description")
        or data.get("status")
        or "Sin descripción"
    )
    is_valid = data.get("is_valid") or data.get("IsValid") or data.get("success")
    emoji    = "✅" if is_valid else "⚠️"

    await update.message.reply_text(
        f"{emoji} *Estado DIAN — {numero}*\n\n"
        f"Estado: {status_desc}\n"
        f"Válido: {'Sí' if is_valid else 'No'}",
        parse_mode="Markdown",
    )
