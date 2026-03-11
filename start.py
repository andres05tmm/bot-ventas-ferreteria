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
    try:
        log.info("🤖 Iniciando FerreBot en modo polling...")
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
