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

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ── Routers ───────────────────────────────────────────────────────────────────
from routers import ventas, catalogo, caja, clientes, reportes, historico, chat, proveedores

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FerreBot Dashboard API",
    description="API de ventas y catálogo para Ferretería Punto Rojo",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Registrar routers ─────────────────────────────────────────────────────────
app.include_router(ventas.router)
app.include_router(catalogo.router)
app.include_router(caja.router)
app.include_router(clientes.router)
app.include_router(reportes.router)
app.include_router(historico.router)
app.include_router(chat.router)
app.include_router(proveedores.router)

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"estado": "activo", "version": "1.0.0"}

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
