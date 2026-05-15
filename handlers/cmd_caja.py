"""
handlers/cmd_caja.py — Comandos de caja, gastos y dashboard.

Handlers: comando_caja, comando_gastos, comando_dashboard
"""

# -- stdlib --
import logging

# -- terceros --
from telegram import Update
from telegram.ext import ContextTypes

# -- propios --
from memoria import (
    obtener_resumen_caja,
    cargar_gastos_hoy,
)
from middleware import protegido

logger = logging.getLogger("ferrebot.handlers.cmd_caja")


# ─────────────────────────────────────────────────────────────────────────────
# /caja, /gastos, /dashboard
# ─────────────────────────────────────────────────────────────────────────────

@protegido
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


@protegido
async def comando_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 *Dashboard Ferretería Punto Rojo*\n\n"
        "🔗 https://bot-ventas-ferreteria-production.up.railway.app/",
        parse_mode="Markdown"
    )


@protegido
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
