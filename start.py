"""
start.py — Proceso unificado para desarrollo local.

DISEÑO:
  - API FastAPI    → hilo SECUNDARIO (daemon)
  - Bot Telegram   → hilo PRINCIPAL

MODOS:
  - Polling  (WEBHOOK_URL no definido): borra webhook anterior, usa long-polling
  - Webhook  (WEBHOOK_URL definido):    main.py registra el webhook y corre run_webhook()

RAILWAY (producción):
  Usar dos servicios separados en lugar de este script:
    Servicio 1 (API):  uvicorn api:app --host 0.0.0.0 --port $PORT
    Servicio 2 (Bot):  python3 start-bot.py  (con WEBHOOK_URL configurado en Railway)
"""
import asyncio
import os
import sys
import threading
import logging

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
# Silenciar librerías verbosas que generan ruido en logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("start")

# ── Importar config AQUÍ — antes de arrancar hilos
import config  # noqa: E402

# ── Inicializar PostgreSQL (si DATABASE_URL esta configurado) ──────────────────
import db as _db  # noqa: E402
_db.init_db()  # determina DB_DISPONIBLE una vez; no falla si DATABASE_URL ausente

# ── Warm-up del cache en background ──────────────────────────────────────────
# Precarga la memoria desde PG para que el primer request de chat no espere.
if _db.DB_DISPONIBLE:
    def _warmup_cache() -> None:
        try:
            from memoria import cargar_memoria
            cargar_memoria()
            log.info("🔥 Cache de memoria precargado al arranque (warm-up)")
        except Exception as e:
            log.warning(f"⚠️ Warm-up cache falló (no fatal): {e}")
    threading.Thread(target=_warmup_cache, name="cache-warmup", daemon=True).start()

# ── API en hilo SECUNDARIO (daemon) ────────────────────────────────────────────
def _run_api() -> None:
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    log.info(f"🌐 Iniciando API en puerto {port}...")
    uvicorn.run("api:app", host="0.0.0.0", port=port, log_level="info")

api_thread = threading.Thread(target=_run_api, name="ferreapi", daemon=True)
api_thread.start()
log.info("🧵 Hilo de la API iniciado")

# ── Safety net histórico: si /cerrar no se ejecutó, persiste a las 9pm ────────
def _run_historico_safety_net() -> None:
    """
    Hilo daemon — safety net por si /cerrar no se ejecutó.
    Revisa una vez por hora; si son las 9pm+ y hoy no está en el histórico,
    persiste el total desde Sheets.
    """
    import time as _time
    from datetime import datetime as _dt

    _time.sleep(120)  # esperar 2 min al arranque
    log.info("[historico-safety] Iniciado — revisa cada hora, persiste a las 9pm si falta")

    while True:
        _time.sleep(60 * 60)  # cada hora
        try:
            ahora = _dt.now(config.COLOMBIA_TZ)
            if ahora.hour >= 21:  # 9pm+
                from routers.historico import _leer_historico, _sync_historico_hoy
                hoy = ahora.strftime("%Y-%m-%d")
                historico = _leer_historico()
                if hoy not in historico:
                    result = _sync_historico_hoy()
                    if result.get("ok"):
                        log.info(
                            f"[historico-safety] {hoy}: ${result['monto']:,.0f} "
                            f"guardado (safety net — /cerrar no fue ejecutado)"
                        )
        except Exception as e:
            log.warning(f"[historico-safety] Error: {e}")

historico_safety_thread = threading.Thread(target=_run_historico_safety_net, name="historico-safety", daemon=True)
historico_safety_thread.start()
log.info("📊 Histórico safety net iniciado (backup nocturno si /cerrar no se ejecutó)")

from main import main  # noqa: E402

if config.WEBHOOK_URL:
    # ── Modo WEBHOOK ──────────────────────────────────────────────────────────
    # main() llama a app.run_webhook() que gestiona su propio event loop y
    # registra el webhook con Telegram automáticamente.
    log.info(f"🌐 Modo WEBHOOK — {config.WEBHOOK_URL}")
    main()
else:
    # ── Modo POLLING ──────────────────────────────────────────────────────────
    # Borrar webhook anterior para evitar conflictos con run_polling().
    # asyncio.run() cierra el loop → crear uno nuevo para run_polling().
    from telegram import Bot  # noqa: E402

    async def _delete_webhook():
        async with Bot(token=config.TELEGRAM_TOKEN) as bot:
            await bot.delete_webhook(drop_pending_updates=True)
        log.info("🧹 Webhook anterior eliminado")

    asyncio.run(_delete_webhook())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    log.info("🤖 Iniciando FerreBot (polling)...")
    main()
