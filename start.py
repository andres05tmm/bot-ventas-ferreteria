"""
start.py — Proceso unificado para Railway.

DISEÑO:
  - API FastAPI    → hilo SECUNDARIO (daemon)
  - Bot Telegram   → hilo PRINCIPAL  (run_polling necesita signal handlers)

SECUENCIA DE EVENT LOOPS:
  1. asyncio.run(_delete_webhook()) — crea loop, lo usa, lo CIERRA
  2. asyncio.new_event_loop()       — crea loop fresco para run_polling()
  3. main() → run_polling()         — usa ese loop
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

# ── Watcher de Excel: sincroniza memoria.json si el Excel cambia en Drive ──────
EXCEL_WATCH_INTERVAL = 5 * 60   # cada 5 minutos
EXCEL_NOMBRE         = "BASE_DE_DATOS_PRODUCTOS.xlsx"

def _get_excel_modified_time() -> str | None:
    """Retorna el modifiedTime del Excel en Drive, o None si falla."""
    try:
        service = config.get_drive_service()
        query   = (
            f"name='{EXCEL_NOMBRE}' "
            f"and '{config.GOOGLE_FOLDER_ID}' in parents "
            f"and trashed=false"
        )
        res   = service.files().list(q=query, fields="files(id,modifiedTime)").execute()
        files = res.get("files", [])
        return files[0]["modifiedTime"] if files else None
    except Exception as e:
        log.warning(f"[excel-watcher] No pudo leer modifiedTime: {e}")
        return None

def _run_excel_watcher() -> None:
    """
    Hilo daemon que cada EXCEL_WATCH_INTERVAL segundos compara el
    modifiedTime del Excel en Drive con el último conocido.
    Si cambió, reimporta todos los precios a memoria.json.
    """
    import time, tempfile, os as _os
    last_modified = None

    # Esperar 30s al arranque para que la API ya esté lista
    time.sleep(30)
    last_modified = _get_excel_modified_time()
    log.info(f"[excel-watcher] Iniciado. modifiedTime inicial: {last_modified}")

    while True:
        time.sleep(EXCEL_WATCH_INTERVAL)
        try:
            current = _get_excel_modified_time()
            if current is None or current == last_modified:
                continue

            log.info(f"[excel-watcher] Excel cambió ({last_modified} → {current}). Reimportando…")
            from drive import descargar_de_drive
            from precio_sync import importar_catalogo_desde_excel

            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                ruta_tmp = tmp.name

            try:
                ok = descargar_de_drive(EXCEL_NOMBRE, ruta_tmp)
                if not ok:
                    log.warning("[excel-watcher] No pudo descargar Excel de Drive")
                    continue
                resultado = importar_catalogo_desde_excel(ruta_tmp)
                last_modified = current
                log.info(
                    f"[excel-watcher] Reimportados {resultado['importados']} productos. "                    f"Errores: {len(resultado.get('errores', []))}"                )
            finally:
                try:
                    _os.unlink(ruta_tmp)
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[excel-watcher] Error en ciclo: {e}")

excel_watcher_thread = threading.Thread(target=_run_excel_watcher, name="excel-watcher", daemon=True)
excel_watcher_thread.start()
log.info("👀 Excel watcher iniciado (intervalo: 5 min)")

# ── Borrar webhook viejo ───────────────────────────────────────────────────────
import config  # noqa: E402
from telegram import Bot  # noqa: E402

async def _delete_webhook():
    async with Bot(token=config.TELEGRAM_TOKEN) as bot:
        await bot.delete_webhook(drop_pending_updates=True)
    log.info("🧹 Webhook eliminado — Telegram usará polling")

asyncio.run(_delete_webhook())
# asyncio.run() cierra el loop al terminar → crear uno nuevo para run_polling()
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ── Bot en hilo PRINCIPAL ──────────────────────────────────────────────────────
log.info("🤖 Iniciando FerreBot en modo polling...")
from main import main  # noqa: E402
main()
