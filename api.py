"""
FerreBot Dashboard API — FastAPI (entry point)

Punto de entrada de FastAPI. Solo responsabilidades de infraestructura:
  - Crear la app y configurar CORS
  - Registrar los routers de cada dominio
  - Servir el build estático del dashboard React

Toda la lógica de negocio vive en routers/:
  shared.py    — helpers y utilidades compartidas (sin endpoints)
  ventas.py    — /ventas/*, /venta-rapida
  catalogo.py  — /catalogo/*, /productos, /inventario/*
  caja.py      — /caja/*, /gastos/*, /compras/*
  clientes.py  — /clientes/*
  reportes.py  — /kardex, /resultados, /proyeccion
  historico.py — /historico/*
  chat.py      — /chat/*, /api/health
  events.py    — /events (SSE tiempo real para el dashboard)
"""

from __future__ import annotations

import json as _json
import logging
import os
import select as _select
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# ── Routers ───────────────────────────────────────────────────────────────────
from routers import (
    ventas, catalogo, caja, clientes, reportes, historico,
    chat, proveedores, auth, usuarios, facturacion, libro_iva,
    events,  # ← SSE tiempo real
)

_api_logger = logging.getLogger("ferrebot.api")


# ── PG LISTEN/NOTIFY — puente bot → dashboard ─────────────────────────────────
def _pg_listen_worker() -> None:
    """
    Hilo daemon que mantiene una conexión PostgreSQL dedicada escuchando
    el canal 'ferrebot_events'.

    Cuando el bot registra una venta llama pg_notify('ferrebot_events', payload).
    Este hilo recibe esa notificación y llama broadcast() para propagar el evento
    SSE a todos los clientes del dashboard conectados en ese momento.

    Detalles de implementación:
    - Usa psycopg2 directo con ISOLATION_LEVEL_AUTOCOMMIT (requerido para LISTEN).
    - select.select() con timeout de 5 s: detecta desconexiones silenciosas
      sin consumir CPU en busy-wait.
    - Reconexión automática con backoff de 5 s ante cualquier error de red o PG.
    - Hilo daemon: muere automáticamente cuando el proceso principal termina,
      sin necesidad de cleanup explícito.
    """
    import psycopg2
    from routers.events import broadcast

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        _api_logger.warning("PG listener: DATABASE_URL no configurado — desactivado")
        return

    _log = logging.getLogger("ferrebot.pg_listener")

    while True:
        conn = None
        try:
            conn = psycopg2.connect(dsn)
            conn.set_isolation_level(0)  # ISOLATION_LEVEL_AUTOCOMMIT — obligatorio para LISTEN
            with conn.cursor() as cur:
                cur.execute("LISTEN ferrebot_events")
            _log.info("✅ PG listener activo — escuchando canal 'ferrebot_events'")

            while True:
                # select.select bloquea hasta 5 s esperando datos en el socket.
                # Si llega un notify antes del timeout, se despierta inmediatamente.
                readable, _, _ = _select.select([conn], [], [], 5.0)
                if readable:
                    conn.poll()
                    while conn.notifies:
                        notif = conn.notifies.pop(0)
                        try:
                            d = _json.loads(notif.payload)
                            broadcast(d.get("type", "evento"), d.get("data", {}))
                            _log.debug("Broadcast desde bot: %s", d.get("type"))
                        except Exception as _pe:
                            _log.warning("Error procesando notify: %s", _pe)

        except Exception as exc:
            _log.warning("PG listener caído (reconectando en 5 s): %s", exc)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        time.sleep(5)


# ── Lifespan: inicializar PostgreSQL al arrancar ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    import db as _db
    _db.init_db()
    if _db.DB_DISPONIBLE:
        _api_logger.info("✅ PostgreSQL inicializado correctamente")
    else:
        _api_logger.warning("⚠️ PostgreSQL no disponible — API en modo degradado")

    # Registrar el event loop de uvicorn en events.py ANTES de arrancar el
    # hilo pg_listener. El hilo llama broadcast() desde fuera del loop, y
    # broadcast() usa call_soon_threadsafe() con esta referencia para que
    # put_nowait() se ejecute siempre dentro del loop correcto (thread-safe).
    _current_loop = asyncio.get_event_loop()
    events.set_main_loop(_current_loop)
    _api_logger.info("🔁 Event loop registrado en events.py")

    # Arrancar el listener pg_notify en un hilo daemon independiente.
    # daemon=True garantiza que el hilo no bloquee el shutdown del servidor.
    _listener = threading.Thread(
        target=_pg_listen_worker,
        name="pg-listener",
        daemon=True,
    )
    _listener.start()
    _api_logger.info("🔔 PG listener thread iniciado")

    yield

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FerreBot Dashboard API",
    description="API de ventas y catálogo para Ferretería Punto Rojo",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware: request_id + timing en cada request ───────────────────────────
_req_logger = logging.getLogger("ferrebot.request")

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Adjunta un request_id corto a cada request y loguea método, path,
    status y tiempo de respuesta. Con esto es posible correlacionar
    errores de cualquier logger con el request que los causó.

    Ejemplo de log:
      [a3f9c1b2] POST /chat → 200 (342ms)
      [a3f9c1b2] POST /chat → ERROR (1023ms): ...

    Rutas GET de polling (dashboard) se omiten para reducir ruido,
    excepto cuando son lentas (>800ms) o devuelven error.
    /events se excluye siempre — es un stream SSE de larga duración.
    """
    # Prefijos GET que el dashboard consultaba continuamente — no loguear si son OK y rápidos
    _POLLING_PREFIXES = (
        "/ventas/hoy", "/ventas/resumen", "/ventas/top", "/ventas/semana",
        "/catalogo", "/caja", "/gastos", "/compras", "/historico",
        "/usuarios/vendedores", "/api/health",
    )
    # Rutas de stream largo — excluir completamente del log de requests
    _STREAM_PATHS = ("/events",)
    _SLOW_MS = 800  # ms a partir del cual siempre loguear aunque sea GET polling

    async def dispatch(self, request: Request, call_next):
        # El stream SSE /events dura minutos — no tiene sentido loguearlo como request normal
        if request.url.path in self._STREAM_PATHS:
            return await call_next(request)

        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            ms = int((time.perf_counter() - t0) * 1000)
            is_polling = (
                request.method == "GET"
                and request.url.path.startswith(self._POLLING_PREFIXES)
            )
            is_ok = response.status_code < 400
            # Omitir GET polling que son rápidos y exitosos
            if not (is_polling and is_ok and ms < self._SLOW_MS):
                _req_logger.info(
                    f"[{request_id}] {request.method} {request.url.path}"
                    f" → {response.status_code} ({ms}ms)"
                )
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            ms = int((time.perf_counter() - t0) * 1000)
            _req_logger.error(
                f"[{request_id}] {request.method} {request.url.path}"
                f" → ERROR ({ms}ms): {exc}"
            )
            raise

app.add_middleware(RequestLoggingMiddleware)
# CORSMiddleware se agrega DESPUÉS para que quede como capa más externa
# (en FastAPI, add_middleware inserta al frente — el último agregado se ejecuta primero)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://bot-ventas-ferreteria-production.up.railway.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Registrar routers ─────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(ventas.router)
app.include_router(catalogo.router)
app.include_router(caja.router)
app.include_router(clientes.router)
app.include_router(reportes.router)
app.include_router(historico.router)
app.include_router(chat.router)
app.include_router(proveedores.router)
app.include_router(facturacion.router)
app.include_router(libro_iva.router)
app.include_router(events.router)  # ← SSE tiempo real

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"estado": "activo", "version": "1.0.0"}

# ── Explicit OPTIONS handler para /auth/telegram ──────────────────────────────
# El catch-all @app.get("/{full_path:path}") puede interceptar el preflight
# OPTIONS antes de que CORSMiddleware lo maneje cuando dashboard/dist existe.
# Este handler explícito garantiza que el preflight siempre devuelva los headers
# correctos independientemente del estado del middleware.
from fastapi.responses import Response as _Response
_CORS_ORIGIN = "https://bot-ventas-ferreteria-production.up.railway.app"

@app.options("/auth/telegram")
def auth_telegram_options():
    return _Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": _CORS_ORIGIN,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        },
    )

# ── Servir dashboard React (build estático) ───────────────────────────────────
_DIST = Path(__file__).parent / "dashboard" / "dist"

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    if (_DIST / "icons").exists():
        app.mount("/icons", StaticFiles(directory=_DIST / "icons"), name="icons")

    @app.get("/manifest.json")
    def serve_manifest():
        f = _DIST / "manifest.json"
        if f.exists():
            return FileResponse(f, media_type="application/manifest+json")
        return {"error": "manifest.json no encontrado"}

    @app.get("/sw.js")
    def serve_sw():
        f = _DIST / "sw.js"
        if f.exists():
            return FileResponse(f, media_type="application/javascript")
        return {"error": "sw.js no encontrado"}

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # Rutas con guiones que el catch-all intercepta antes que el router.
        # Solo bloqueamos estas — NO "auth" ni otras que usen GET (ej: callback Telegram).
        _API_HYPHEN_PREFIXES = ("compras-fiscal", "libro-iva")
        if any(full_path.startswith(p) for p in _API_HYPHEN_PREFIXES):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Ruta API no encontrada")

        static_file = _DIST / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(static_file)
        index = _DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"error": "Dashboard no buildeado. Ejecuta: cd dashboard && npm run build"}

else:
    @app.get("/")
    def root():
        return {
            "servicio": "FerreBot Dashboard API",
            "estado":   "activo",
            "version":  "1.0.0",
            "nota":     "Dashboard no buildeado. Ejecuta: cd dashboard && npm run build",
            "docs":     "/docs",
        }
