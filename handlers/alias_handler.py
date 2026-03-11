"""
handlers/alias_handler.py — Comando /alias para gestión dinámica de aliases.

COMANDOS:
  /alias pagaternit pegaternit    → agrega alias
  /alias ver                      → lista todos  
  /alias borrar pagaternit        → elimina alias
  /alias test 2 esmaltes rojos    → prueba transformación

Solo usuarios autorizados pueden modificar aliases (misma lista que otros comandos admin).
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

import config
import alias_manager

logger = logging.getLogger("ferrebot.alias_handler")


def _es_admin(update: Update) -> bool:
    """Verifica si el usuario está autorizado para modificar aliases."""
    chat_id = update.message.chat_id
    # Usa la misma lista de admins que el resto del bot
    admins = getattr(config, "ADMIN_CHAT_IDS", [])
    if not admins:
        # Si no hay lista configurada, permitir a todos (mismo comportamiento que otros comandos)
        return True
    return chat_id in admins


async def manejar_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler del comando /alias.

    Uso:
      /alias [termino] [reemplazo]  → agregar/actualizar
      /alias ver                    → listar todos
      /alias borrar [termino]       → eliminar
      /alias test [mensaje]         → probar transformación
    """
    args = context.args or []

    # Sin argumentos → mostrar ayuda
    if not args:
        await update.message.reply_text(
            "📝 *Gestión de Aliases*\n\n"
            "Ejemplos:\n"
            "`/alias pagaternit pegaternit`\n"
            "`/alias lijar lija esmeril`\n"
            "`/alias ver` — ver todos\n"
            "`/alias borrar pagaternit`\n"
            "`/alias test 2 esmaltes rojos` — probar\n\n"
            "Los aliases convierten términos que usan tus empleados al nombre "
            "exacto del catálogo antes de enviar el mensaje al bot.",
            parse_mode="Markdown",
        )
        return

    subcomando = args[0].lower()

    # ── VER: listar todos los aliases ──
    if subcomando == "ver":
        texto = alias_manager.listar_aliases()
        await update.message.reply_text(texto, parse_mode="Markdown")
        return

    # ── BORRAR: eliminar un alias ──
    if subcomando == "borrar":
        if not _es_admin(update):
            await update.message.reply_text("⛔ No tienes permiso para modificar aliases.")
            return
        if len(args) < 2:
            await update.message.reply_text("Uso: `/alias borrar [termino]`", parse_mode="Markdown")
            return
        termino = args[1]
        msg = alias_manager.borrar_alias(termino)
        await update.message.reply_text(msg)
        return

    # ── TEST: probar transformación ──
    if subcomando == "test":
        if len(args) < 2:
            await update.message.reply_text("Uso: `/alias test [mensaje]`", parse_mode="Markdown")
            return
        mensaje_test = " ".join(args[1:])
        msg = alias_manager.probar_alias(mensaje_test)
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ── AGREGAR: /alias [termino] [reemplazo] ──
    if not _es_admin(update):
        await update.message.reply_text("⛔ No tienes permiso para agregar aliases.")
        return

    if len(args) < 2:
        await update.message.reply_text(
            "Uso: `/alias [termino] [reemplazo]`\n"
            "Ejemplo: `/alias pagaternit pegaternit`",
            parse_mode="Markdown",
        )
        return

    termino = args[0]
    reemplazo = " ".join(args[1:])
    msg = alias_manager.agregar_alias(termino, reemplazo)
    await update.message.reply_text(msg)
