"""
FerreBot — Entry point.
Inicializa los servicios y arranca el bot en modo webhook (Railway) o polling (local).
"""

import asyncio
import logging as _logging

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

import config

# ── Sentry — captura de errores en producción ─────────────────────────────────
if config.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        integrations=[
            LoggingIntegration(level=_logging.WARNING, event_level=_logging.ERROR),
        ],
        traces_sample_rate=0.0,
        environment="production",
        release=getattr(config, "VERSION", "unknown"),
    )
    print("✅ Sentry inicializado (bot)")

from handlers.comandos import (
    comando_inicio, comando_ventas, comando_buscar,
    comando_borrar, comando_precios, comando_caja, comando_gastos,
    comando_inventario, comando_clientes, comando_nuevo_cliente, comando_grafica, comando_fiados, comando_abono,
    comando_pendientes,
    manejar_callback_grafica, comando_cerrar_dia,
    comando_reset_ventas, comando_actualizar_catalogo, comando_consistencia,
    comando_exportar_precios, comando_keepalive, comando_dashboard,
    comando_agregar_producto, comando_actualizar_precio,
    comando_inv, comando_stock, comando_ajuste,
    comando_compra, comando_margenes,

    comando_modelo,
    comando_factura, comando_abonar, comando_deudas, comando_borrar_factura, comando_facturas,
    comando_confirmar, comando_registrar_vendedor,
)
from handlers.mensajes import manejar_mensaje, manejar_audio, manejar_documento, manejar_foto
from handlers.callbacks import manejar_metodo_pago, manejar_callback_cliente, manejar_callback_foto
from handlers.productos import comando_productos, manejar_callback_productos
from handlers.alias_handler import manejar_alias
from keepalive import loop_keepalive
from handlers.cmd_facturacion import (
    comando_factura_electronica,
    comando_nota_credito,
    comando_estado_factura,
)

_logger = _logging.getLogger("ferrebot.main")


async def _error_handler(update: object, context) -> None:
    """
    Handler global de errores del bot.
    Captura cualquier excepción no manejada en handlers/comandos/callbacks
    y la envía a Sentry con contexto del update para facilitar el debug.
    """
    if context.error is None:
        return

    # Contexto adicional para Sentry: qué chat y qué mensaje causó el error
    if config.SENTRY_DSN:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if update and hasattr(update, "effective_chat") and update.effective_chat:
                scope.set_user({"id": str(update.effective_chat.id)})
            if update and hasattr(update, "effective_message") and update.effective_message:
                texto = getattr(update.effective_message, "text", "") or ""
                scope.set_extra("mensaje_usuario", texto[:300])
            scope.set_tag("componente", "bot-telegram")
            sentry_sdk.capture_exception(context.error)

    _logger.error("Excepción no manejada en el bot:", exc_info=context.error)


def build_app() -> Application:
    """
    Crea y configura el Application de python-telegram-bot con todos los handlers
    registrados, sin arrancarlo. Puede usarse tanto desde main() como desde un
    servidor externo (ej. FastAPI en start-bot.py).
    """
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start",      comando_inicio))
    app.add_handler(CommandHandler("ayuda",      comando_inicio))
    app.add_handler(CommandHandler("ventas",     comando_ventas))
    app.add_handler(CommandHandler("buscar",     comando_buscar))
    app.add_handler(CommandHandler("borrar",     comando_borrar))
    app.add_handler(CommandHandler("precios",    comando_precios))
    app.add_handler(CommandHandler("dashboard",  comando_dashboard))
    app.add_handler(CommandHandler("puntorojo",  comando_dashboard))
    app.add_handler(CommandHandler("modelo",      comando_modelo))
    app.add_handler(CommandHandler("caja",       comando_caja))
    app.add_handler(CommandHandler("gastos",     comando_gastos))
    app.add_handler(CommandHandler("inventario", comando_inventario))
    app.add_handler(CommandHandler("inv",        comando_inv))
    app.add_handler(CommandHandler("stock",      comando_stock))
    app.add_handler(CommandHandler("ajuste",     comando_ajuste))
    app.add_handler(CommandHandler("compra",     comando_compra))
    app.add_handler(CommandHandler("margenes",   comando_margenes))
    app.add_handler(CommandHandler("factura",    comando_factura))
    app.add_handler(CommandHandler("abonar",     comando_abonar))
    app.add_handler(CommandHandler("deudas",     comando_deudas))
    app.add_handler(CommandHandler("borrar_factura", comando_borrar_factura))
    app.add_handler(CommandHandler("facturas",       comando_facturas))
    app.add_handler(CommandHandler("factura_electronica", comando_factura_electronica))
    app.add_handler(CommandHandler("nota_credito",        comando_nota_credito))
    app.add_handler(CommandHandler("estado_factura",      comando_estado_factura))
    app.add_handler(CommandHandler("clientes",      comando_clientes))
    app.add_handler(CommandHandler("nuevo_cliente", comando_nuevo_cliente))
    app.add_handler(CommandHandler("grafica",    comando_grafica))
    app.add_handler(CommandHandler("fiados",     comando_fiados))
    app.add_handler(CommandHandler("abono",      comando_abono))
    app.add_handler(CommandHandler("cerrar",     comando_cerrar_dia))
    app.add_handler(CommandHandler("resetventas", comando_reset_ventas))
    app.add_handler(CommandHandler("catalogo",          comando_actualizar_catalogo))
    app.add_handler(CommandHandler("actualizar_catalogo", comando_actualizar_catalogo))
    app.add_handler(CommandHandler("consistencia",          comando_consistencia))
    app.add_handler(CommandHandler("exportar_precios",        comando_exportar_precios))
    app.add_handler(CommandHandler("keepalive",       comando_keepalive))
    app.add_handler(CommandHandler("agregar_producto", comando_agregar_producto))
    app.add_handler(CommandHandler("nuevo_producto",   comando_agregar_producto))
    app.add_handler(CommandHandler("actualizar_precio", comando_actualizar_precio))
    app.add_handler(CommandHandler("productos",        comando_productos))
    app.add_handler(CommandHandler("pendientes",       comando_pendientes))
    app.add_handler(CommandHandler("confirmar",           comando_confirmar))
    app.add_handler(CommandHandler("registrar_vendedor",  comando_registrar_vendedor))
    app.add_handler(CommandHandler("alias",            manejar_alias))
    app.add_handler(CommandHandler("aliases",          manejar_alias))

    # Mensajes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.add_handler(MessageHandler(filters.VOICE,       manejar_audio))
    app.add_handler(MessageHandler(filters.PHOTO,       manejar_foto))
    app.add_handler(MessageHandler(filters.Document.ALL, manejar_documento))

    # Callbacks (botones inline)
    app.add_handler(CallbackQueryHandler(manejar_metodo_pago,      pattern="^pago_"))
    app.add_handler(CallbackQueryHandler(manejar_metodo_pago,      pattern="^borrar_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_cliente,  pattern="^cli_crear_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_cliente,  pattern="^cli_tipoid_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_cliente,  pattern="^cli_persona_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_cliente,  pattern="^cli_ciudad_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_foto,    pattern="^foto_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_grafica,  pattern="^grafica_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_productos, pattern="^prod_"))

    # ── Error handler global — captura excepciones no manejadas y las envía a Sentry ──
    app.add_error_handler(_error_handler)

    return app


def main():
    print(f"🚀 Iniciando FerreBot {config.VERSION}")

    # Construir índice fuzzy al arrancar para que las búsquedas funcionen
    try:
        from fuzzy_match import construir_indice
        from memoria import cargar_memoria as _cm_init
        _mem_init = _cm_init()
        construir_indice(_mem_init.get("catalogo", {}))
        print(f"🔍 Índice fuzzy construido: {len(_mem_init.get('catalogo', {}))} productos")
    except Exception as e:
        print(f"⚠️ No se pudo construir índice fuzzy: {e}")

    app = build_app()

    if config.WEBHOOK_URL:
        print(f"🌐 Iniciando en modo WEBHOOK: {config.WEBHOOK_URL}")

        async def _iniciar_keepalive(app):
            """Inicia el loop de keepalive dentro del event loop correcto (post_init)."""
            asyncio.create_task(loop_keepalive())

        app.post_init = _iniciar_keepalive
        app.run_webhook(
            listen="0.0.0.0",
            port=config.WEBHOOK_PORT,
            url_path=config.TELEGRAM_TOKEN,
            webhook_url=f"{config.WEBHOOK_URL}/{config.TELEGRAM_TOKEN}",
        )
    else:
        print("⚙️ WEBHOOK_URL no configurada. Iniciando en modo polling (desarrollo local).")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
