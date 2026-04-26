"""
handlers/cmd_auth.py — Comandos de autenticación.
Proporciona /confirmar y /registrar_vendedor para gestionar acceso de usuarios.
"""

# -- stdlib --
import logging

# -- terceros --
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("ferrebot.handlers.cmd_auth")


async def comando_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /confirmar: registra el telegram_id del usuario a un vendedor existente.
    Uso: /confirmar TuNombre
    """
    if not context.args:
        await update.message.reply_text(
            "Uso: /confirmar TuNombre  (ej: /confirmar Farid M)"
        )
        return

    nombre = " ".join(context.args)
    from auth.usuarios import registrar_telegram_id
    result = registrar_telegram_id(nombre, update.effective_user.id)

    if result:
        await update.message.reply_text(
            f"✅ {nombre} registrado correctamente. Ya puedes usar el bot."
        )
    else:
        await update.message.reply_text(
            "❌ No encontré ese nombre o ya está registrado. Pídele a Andrés que verifique."
        )


async def comando_registrar_vendedor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /registrar_vendedor: crea un nuevo vendedor (solo admin).
    Uso: /registrar_vendedor NombreCompleto
    """
    from auth.usuarios import is_admin, crear_vendedor

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Solo Andrés puede hacer esto.")
        return

    if not context.args:
        await update.message.reply_text("Uso: /registrar_vendedor NombreCompleto")
        return

    nombre = " ".join(context.args)
    result = crear_vendedor(nombre)

    if result:
        await update.message.reply_text(
            f"✅ Vendedor '{nombre}' creado. Dile que escriba: /confirmar {nombre}"
        )
    else:
        await update.message.reply_text("❌ Error al crear el vendedor.")
