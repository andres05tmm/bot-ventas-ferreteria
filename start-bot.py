"""
start-bot.py — Lanzador del bot de Telegram para Railway (servicio separado).

Requiere en Railway:
  - WEBHOOK_URL  = URL pública del servicio bot  (ej. https://ferrebot-xxx.railway.app)
  - PORT         = asignado por Railway automáticamente

El servicio API corre por separado con:
  uvicorn api:app --host 0.0.0.0 --port $PORT
"""
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
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
log = logging.getLogger("start-bot")

# ── Importar config (lee WEBHOOK_URL del entorno) ──────────────────────────────
import config  # noqa: E402

if not config.WEBHOOK_URL:
    log.error("❌ WEBHOOK_URL no está configurado. Configúralo en Railway como variable de entorno.")
    sys.exit(1)

# ── Inicializar PostgreSQL ─────────────────────────────────────────────────────
import db as _db  # noqa: E402
_db.init_db()

# ── Warm-up del cache en background ──────────────────────────────────────────
if _db.DB_DISPONIBLE:
    def _warmup_cache() -> None:
        try:
            from memoria import cargar_memoria
            cargar_memoria()
            log.info("🔥 Cache precargado al arranque (warm-up)")
        except Exception as e:
            log.warning(f"⚠️ Warm-up cache falló (no fatal): {e}")
    threading.Thread(target=_warmup_cache, name="cache-warmup", daemon=True).start()

# ── Safety net histórico: persiste a las 9pm si /cerrar no se ejecutó ─────────
def _run_historico_safety_net() -> None:
    import time as _time
    from datetime import datetime as _dt

    _time.sleep(120)
    log.info("[historico-safety] Iniciado — revisa cada hora, persiste a las 9pm si falta")
    while True:
        _time.sleep(60 * 60)
        try:
            ahora = _dt.now(config.COLOMBIA_TZ)
            if ahora.hour >= 21:
                from routers.historico import _leer_historico, _sync_historico_hoy
                hoy = ahora.strftime("%Y-%m-%d")
                historico = _leer_historico()
                if hoy not in historico:
                    result = _sync_historico_hoy()
                    if result.get("ok"):
                        log.info(
                            f"[historico-safety] {hoy}: ${result['monto']:,.0f} "
                            f"guardado (safety net)"
                        )
        except Exception as e:
            log.warning(f"[historico-safety] Error: {e}")

threading.Thread(
    target=_run_historico_safety_net, name="historico-safety", daemon=True
).start()
log.info("📊 Histórico safety net iniciado")

# ── Arrancar el bot (webhook mode) ────────────────────────────────────────────
# main() detecta config.WEBHOOK_URL y llama a app.run_webhook(), que:
#   - Registra el webhook con Telegram (set_webhook)
#   - Levanta el servidor HTTP en 0.0.0.0:PORT para recibir updates
log.info(f"🤖 Iniciando FerreBot en modo WEBHOOK: {config.WEBHOOK_URL}")
from main import main  # noqa: E402
main()
