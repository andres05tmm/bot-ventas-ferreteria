"""
start.py — Proceso unificado para Railway.

DISEÑO CORRECTO:
  - API FastAPI → hilo SECUNDARIO (daemon)
  - Bot Telegram → hilo PRINCIPAL

Por qué: run_polling() registra signal handlers (SIGINT/SIGTERM) que
Python solo permite en el hilo principal. Si el bot corre en un hilo
secundario explota con: "set_wakeup_fd only works in main thread".
"""
import asyncio
import os
import sys
import threading
import logging

# ── Forzar polling (antes de importar config) ──────────────────────────────────
os.environ["WEBHOOK_URL"] = ""

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("start")

# ── API en hilo SECUNDARIO (daemon) ────────────────────────────────────────────
def _run_api() -> None:
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    log.info(f"🌐 Iniciando API en puerto {port}...")
    uvicorn.run("api:app", host="0.0.0.0", port=port, log_level="info")

api_thread = threading.Thread(target=_run_api, name="ferreapi", daemon=True)
api_thread.start()
log.info("🧵 Hilo de la API iniciado")

# ── Borrar webhook viejo antes de arrancar polling ─────────────────────────────
import config  # noqa: E402
from telegram import Bot  # noqa: E402

async def _delete_webhook():
    async with Bot(token=config.TELEGRAM_TOKEN) as bot:
        await bot.delete_webhook(drop_pending_updates=True)
    log.info("🧹 Webhook eliminado — Telegram usará polling")

asyncio.run(_delete_webhook())

# ── Bot en hilo PRINCIPAL (signal handlers requieren el hilo principal) ────────
log.info("🤖 Iniciando FerreBot en modo polling...")
from main import main  # noqa: E402
main()
