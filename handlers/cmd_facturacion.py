"""
handlers/cmd_facturacion.py — Comando /factura_electronica

Emite una factura electrónica DIAN para una venta del día actual.
Se llama /factura_electronica (NO /factura) para evitar colisión con
cmd_proveedores.py que ya usa /factura para facturas de proveedores.
"""
import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

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

    hoy = str(date.today())

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
            f"❌ *Error DIAN:*\n{resultado['error']}",
            parse_mode="Markdown",
        )
        return

    cufe_corto = resultado["cufe"][:40] if resultado["cufe"] else "N/A"

    await update.message.reply_text(
        f"✅ *Factura {resultado['numero']} emitida ante la DIAN*\n\n"
        f"🏢 Cliente: {venta['cliente_nombre'] or 'Consumidor Final'}\n"
        f"💰 Total: ${venta['total']:,}\n"
        f"🔑 CUFE: `{cufe_corto}...`\n\n"
        f"📧 El PDF fue enviado al correo del cliente automáticamente.",
        parse_mode="Markdown",
    )
