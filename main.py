"""
FerreBot — Entry point.
Inicializa los servicios y arranca el bot en modo webhook (Railway) o polling (local).
"""

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

import config
from drive import sincronizar_archivos
from excel import inicializar_excel
from sheets import _obtener_hoja_sheets

from handlers.comandos import (
    comando_inicio, comando_excel, comando_ventas, comando_buscar,
    comando_borrar, comando_precios, comando_caja, comando_gastos,
    comando_inventario, comando_clientes, comando_grafica,
    manejar_callback_grafica, comando_sheets, comando_cerrar_dia,
)
from handlers.mensajes import manejar_mensaje, manejar_audio, manejar_documento
from handlers.callbacks import manejar_metodo_pago


def main():
    print(f"🚀 Iniciando FerreBot {config.VERSION}")
    sincronizar_archivos()
    inicializar_excel()

    if config.SHEETS_ID:
        print(f"📊 Google Sheets configurado: {config.SHEETS_ID}")
        ws_test = _obtener_hoja_sheets()
        if ws_test:
            print("✅ Conexion a Google Sheets OK")
        else:
            print("⚠️ No se pudo conectar al Sheets")
    else:
        print("ℹ️ SHEETS_ID no configurado — funciones de Sheets desactivadas")

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start",      comando_inicio))
    app.add_handler(CommandHandler("ayuda",      comando_inicio))
    app.add_handler(CommandHandler("excel",      comando_excel))
    app.add_handler(CommandHandler("ventas",     comando_ventas))
    app.add_handler(CommandHandler("buscar",     comando_buscar))
    app.add_handler(CommandHandler("borrar",     comando_borrar))
    app.add_handler(CommandHandler("precios",    comando_precios))
    app.add_handler(CommandHandler("caja",       comando_caja))
    app.add_handler(CommandHandler("gastos",     comando_gastos))
    app.add_handler(CommandHandler("inventario", comando_inventario))
    app.add_handler(CommandHandler("clientes",   comando_clientes))
    app.add_handler(CommandHandler("grafica",    comando_grafica))
    app.add_handler(CommandHandler("sheets",     comando_sheets))
    app.add_handler(CommandHandler("cerrar",     comando_cerrar_dia))

    # Mensajes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.add_handler(MessageHandler(filters.VOICE,       manejar_audio))
    app.add_handler(MessageHandler(filters.Document.ALL, manejar_documento))

    # Callbacks (botones inline)
    app.add_handler(CallbackQueryHandler(manejar_metodo_pago,      pattern="^pago_"))
    app.add_handler(CallbackQueryHandler(manejar_metodo_pago,      pattern="^borrar_"))
    app.add_handler(CallbackQueryHandler(manejar_metodo_pago,      pattern="^cli_tipoid_"))
    app.add_handler(CallbackQueryHandler(manejar_metodo_pago,      pattern="^cli_persona_"))
    app.add_handler(CallbackQueryHandler(manejar_callback_grafica, pattern="^grafica_"))

    if config.WEBHOOK_URL:
        print(f"🌐 Iniciando en modo WEBHOOK: {config.WEBHOOK_URL}")
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
