"""
handlers/cmd_clientes.py — Comandos de clientes y fiados.

Handlers: comando_clientes, comando_nuevo_cliente, comando_fiados, comando_abono
"""

# -- stdlib --
import asyncio
import logging

# -- terceros --
from telegram import Update
from telegram.ext import ContextTypes

# -- propios --
import db as _db
from memoria import (
    resumen_fiados,
    detalle_fiado_cliente,
    abonar_fiado,
)
from middleware import protegido

logger = logging.getLogger("ferrebot.handlers.cmd_clientes")


# ─────────────────────────────────────────────────────────────────────────────
# /clientes  — lee desde PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

@protegido
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

@protegido
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

@protegido
async def comando_fiados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        cliente = " ".join(context.args)
        texto   = detalle_fiado_cliente(cliente)
    else:
        texto = resumen_fiados()
    await update.message.reply_text(texto, parse_mode="Markdown")


@protegido
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
