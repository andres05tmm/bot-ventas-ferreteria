"""
start.py — Proceso unificado para Railway.

Railway expone un solo puerto público ($PORT).
La API FastAPI ocupa ese puerto (hilo principal, bloqueante).
El bot de Telegram corre en modo polling en un hilo secundario
(no necesita puerto público propio).

IMPORTANTE: se fuerza WEBHOOK_URL='' antes de importar config
para que el bot arranque siempre en modo polling aquí.
Si se necesita modo webhook puro, correr main.py directamente.
"""
import asyncio
import os
import sys
import threading
import logging

# ── Forzar polling en el bot ───────────────────────────────────────────────────
# Debe ejecutarse ANTES de cualquier import de config o main,
# porque config.py lee WEBHOOK_URL a nivel de módulo.
os.environ["WEBHOOK_URL"] = ""

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("start")


# ── Bot en hilo secundario ─────────────────────────────────────────────────────
def _run_bot() -> None:
    # FIX 1: Los hilos secundarios en Python 3.10+ no tienen event loop.
    # run_polling() lo necesita → crear uno explícitamente para este hilo.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        log.info("🤖 Iniciando FerreBot en modo polling...")

        # FIX 2: Borrar webhook viejo de Telegram antes de arrancar polling.
        # Si quedó un webhook registrado de un deploy anterior, Telegram
        # sigue mandando POSTs → 404 en cascada. Eliminarlo aquí garantiza
        # que Telegram cambie a push de updates vía polling.
        import config
        from telegram import Bot

        async def _delete_webhook():
            async with Bot(token=config.TELEGRAM_TOKEN) as bot:
                await bot.delete_webhook(drop_pending_updates=True)
                log.info("🧹 Webhook eliminado — Telegram usará polling")

        loop.run_until_complete(_delete_webhook())

        from main import main
        main()

    except Exception:
        log.exception("❌ Error fatal en el hilo del bot — bot detenido")


bot_thread = threading.Thread(target=_run_bot, name="ferrebot", daemon=True)
bot_thread.start()
log.info("🧵 Hilo del bot iniciado")

# ── API en el hilo principal ───────────────────────────────────────────────────
import uvicorn  # noqa: E402 — importar después del override de WEBHOOK_URL

port = int(os.getenv("PORT", "8001"))
log.info(f"🌐 Iniciando API en puerto {port}...")
uvicorn.run("api:app", host="0.0.0.0", port=port, log_level="info")
