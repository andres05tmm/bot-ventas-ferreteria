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
"""

from __future__ import annotations

import logging
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
from routers import ventas, catalogo, caja, clientes, reportes, historico, chat, proveedores, auth, usuarios, facturacion, libro_iva

_api_logger = logging.getLogger("ferrebot.api")

# ── Lifespan: inicializar PostgreSQL al arrancar ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    import db as _db
    _db.init_db()
    if _db.DB_DISPONIBLE:
        _api_logger.info("✅ PostgreSQL inicializado correctamente")
    else:
        _api_logger.warning("⚠️ PostgreSQL no disponible — API en modo degradado")
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
    """
    # Prefijos GET que el dashboard encuesta continuamente — no loguear si son OK y rápidos
    _POLLING_PREFIXES = (
        "/ventas/hoy", "/ventas/resumen", "/ventas/top", "/ventas/semana",
        "/catalogo", "/caja", "/gastos", "/compras", "/historico",
        "/usuarios/vendedores", "/api/health",
    )
    _SLOW_MS = 800  # ms a partir del cual siempre loguear aunque sea GET polling

    async def dispatch(self, request: Request, call_next):
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
        # Prefijos de API — el catch-all nunca debe servirlos como SPA
        _API_PREFIXES = (
            "compras-fiscal", "compras", "ventas", "caja", "gastos",
            "catalogo", "historico", "auth", "usuarios", "reportes",
            "clientes", "proveedores", "facturacion", "libro-iva",
            "chat", "api/",
        )
        if any(full_path.startswith(p) for p in _API_PREFIXES):
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
