"""
start-bot.py — Lanzador del bot de Telegram para Railway (servicio separado).

Usa FastAPI + uvicorn como servidor HTTP para recibir los webhooks de Telegram,
en lugar del servidor interno de run_webhook(). Esto permite que Railway enrute
el tráfico HTTPS (puerto 443 externo) al puerto $PORT interno correctamente.

Flujo:
  1. uvicorn escucha en 0.0.0.0:$PORT
  2. Railway hace SSL termination y reenvía los POST de Telegram a ese puerto
  3. El endpoint POST /{TELEGRAM_TOKEN} convierte el payload en un Update y
     lo procesa con application.process_update()

Requiere en Railway:
  - WEBHOOK_URL  = URL pública del servicio bot  (ej. https://ferrebot-xxx.railway.app)
  - PORT         = asignado por Railway automáticamente
  - TELEGRAM_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY
"""

# -- stdlib --
import asyncio
import logging
import sys
import threading
from contextlib import asynccontextmanager

# -- terceros --
import uvicorn
from fastapi import FastAPI, Request, Response
from telegram import Update

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
# Activar DEBUG solo para el módulo de facturación
logging.getLogger("ferrebot.facturacion").setLevel(logging.DEBUG)

# -- propios --
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

# ── Construir índice fuzzy ─────────────────────────────────────────────────────
try:
    from fuzzy_match import construir_indice
    from memoria import cargar_memoria as _cm_init
    _mem_init = _cm_init()
    construir_indice(_mem_init.get("catalogo", {}))
    log.info(f"🔍 Índice fuzzy construido: {len(_mem_init.get('catalogo', {}))} productos")
except Exception as e:
    log.warning(f"⚠️ No se pudo construir índice fuzzy: {e}")

# ── FastAPI + ciclo de vida del bot ───────────────────────────────────────────
from main import build_app          # noqa: E402
from keepalive import loop_keepalive  # noqa: E402

_WEBHOOK_PATH = f"/{config.TELEGRAM_TOKEN}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Inicia el Application de python-telegram-bot, registra el webhook con Telegram
    y arranca el keepalive. Al apagarse, detiene el bot limpiamente.

    Además arranca un APScheduler con el job nocturno del compresor (3 AM Colombia)
    que destila las conversaciones del día en notas de memoria de entidad.
    """
    tg_app = build_app()
    app.state.tg_app = tg_app

    await tg_app.initialize()
    await tg_app.start()

    # ── Prometheus metrics: marcar este proceso como "bot" ───────────────────
    try:
        import metrics as _metrics
        _metrics.set_service_label("bot", version=config.VERSION)
    except Exception as _me:
        log.warning(f"⚠️ No se pudo inicializar métricas: {_me}")

    # Registrar webhook: Telegram enviará los updates a WEBHOOK_URL/TOKEN
    webhook_url = f"{config.WEBHOOK_URL}{_WEBHOOK_PATH}"
    await tg_app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )
    log.info(f"✅ Webhook registrado: {webhook_url}")

    # Keepalive del prompt cache de Anthropic
    asyncio.create_task(loop_keepalive())

    # ── Scheduler nocturno (compresor de memoria de entidad) ────────────────
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from services.compresor_nocturno import compresor_nocturno_job

        scheduler = AsyncIOScheduler(timezone=str(config.COLOMBIA_TZ))
        scheduler.add_job(
            compresor_nocturno_job,
            trigger=CronTrigger(hour=3, minute=0, timezone=str(config.COLOMBIA_TZ)),
            id="compresor_nocturno",
            name="Compresor nocturno de memoria de entidad",
            replace_existing=True,
            misfire_grace_time=3600,  # si el bot estuvo caído, corre hasta 1h tarde
            max_instances=1,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        log.info("🌙 APScheduler iniciado — compresor nocturno a las 3:00 AM Colombia")
    except Exception as e:
        log.warning(f"⚠️ No se pudo iniciar el scheduler nocturno: {e}")

    yield

    # Apagado limpio
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
            log.info("🌙 APScheduler detenido")
        except Exception as e:
            log.warning(f"⚠️ Error apagando scheduler: {e}")

    await tg_app.stop()
    await tg_app.shutdown()
    log.info("🛑 Bot detenido")


fastapi_app = FastAPI(lifespan=lifespan)


@fastapi_app.post(_WEBHOOK_PATH)
async def telegram_webhook(request: Request) -> Response:
    """Recibe un update de Telegram y lo despacha al bot."""
    data = await request.json()
    tg_app = request.app.state.tg_app
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return Response(status_code=200)


@fastapi_app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": config.VERSION}


@fastapi_app.get("/metrics")
async def bot_metrics_endpoint(request: Request) -> Response:
    """
    Exposition format de Prometheus (text/plain; version=0.0.4).

    Acceso:
      - Por defecto: PÚBLICO.
      - Si se setea METRICS_BEARER_TOKEN en env, se requiere
        Authorization: Bearer <token> o devuelve 401.
    """
    from fastapi import HTTPException
    import metrics as _metrics

    auth = request.headers.get("Authorization")
    if not _metrics.auth_check(auth):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body, content_type = _metrics.render_metrics()
    return Response(content=body, media_type=content_type)


# ── Arrancar uvicorn ───────────────────────────────────────────────────────────
log.info(f"🤖 Iniciando FerreBot {config.VERSION} — FastAPI webhook en puerto {config.WEBHOOK_PORT}")
uvicorn.run(
    fastapi_app,
    host="0.0.0.0",
    port=config.WEBHOOK_PORT,
    log_level="info",
)
