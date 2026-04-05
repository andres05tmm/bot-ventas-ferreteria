"""
SSE (Server-Sent Events) — canal de notificaciones en tiempo real para el dashboard.

El frontend escucha GET /events y recibe un mensaje cada vez que ocurre un cambio
relevante (venta registrada, inventario modificado, caja cerrada, etc.).

Uso desde routers FastAPI (async):
    from routers.events import notify_all
    await notify_all("venta_registrada", {"vendedor": vendedor_id})

    notify_all() envía pg_notify → TODAS las instancias Railway reciben el evento
    vía _pg_listen_worker → broadcast() → SSE clients de esa instancia.

Uso directo (interno, por _pg_listen_worker desde api.py):
    from routers.events import broadcast
    broadcast("venta_registrada", {...})

Thread safety
─────────────
broadcast() puede llamarse desde dos contextos:
  1. _pg_listen_worker → hilo daemon FUERA del loop → usar call_soon_threadsafe().
  2. Fallback en notify_all() si pg_notify falla → DENTRO del event loop → put_nowait() directo.

notify_all() siempre corre dentro del event loop (es async), así que usa put_nowait() directo
mediante broadcast(). La diferencia con la versión anterior es que ahora el camino principal
pasa por pg_notify, lo que garantiza que TODAS las réplicas reciban el evento.

set_main_loop(loop) debe llamarse desde el lifespan de api.py inmediatamente después
de que el event loop de uvicorn esté corriendo.
"""

import asyncio
import json
import logging
import os
from typing import AsyncGenerator

import jwt as _jwt
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

log = logging.getLogger("ferrebot.events")
router = APIRouter()

# ── Semáforo para notify_all ──────────────────────────────────────────────────
# Limita a 3 llamadas concurrentes de notify_all() usando el pool de PG.
# Con maxconn=10, esto reserva 7 conexiones para queries normales y evita
# que una ráfaga de eventos agote el pool y bloquee el resto de la API.
_notify_sem = asyncio.Semaphore(3)

# ── Event loop del proceso principal ─────────────────────────────────────────
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """
    Registra el event loop principal de uvicorn.
    Llamar desde el lifespan de api.py antes de iniciar el hilo pg_listener.
    """
    global _main_loop
    _main_loop = loop
    log.debug("Event loop principal registrado en events.py")


# ── Registro de suscriptores ──────────────────────────────────────────────────
_subscribers: list[asyncio.Queue] = []


def _do_broadcast(payload: str) -> None:
    """
    Pone el payload en todas las colas activas.
    DEBE ejecutarse dentro del event loop.
    """
    dead: list[asyncio.Queue] = []
    for q in _subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def broadcast(event_type: str, data: dict | None = None) -> None:
    """
    Broadcast local en memoria a los clientes SSE de ESTA instancia.
    Thread-safe: puede llamarse desde routers async O desde hilos externos.

    ⚠️  Uso interno — llamar desde _pg_listen_worker o como fallback de notify_all().
        Desde routers FastAPI, usar await notify_all() para garantizar que TODAS
        las réplicas de Railway reciban el evento.
    """
    payload = json.dumps({"type": event_type, "data": data or {}})
    try:
        asyncio.get_running_loop()
        _do_broadcast(payload)
    except RuntimeError:
        if _main_loop and _main_loop.is_running():
            _main_loop.call_soon_threadsafe(_do_broadcast, payload)
        else:
            log.warning("broadcast(%s) descartado — event loop no disponible aún", event_type)


async def notify_all(event_type: str, data: dict | None = None) -> None:
    """
    Notifica a TODAS las réplicas del servicio API via PostgreSQL NOTIFY.

    Flujo:
        notify_all()
          └─► SELECT pg_notify('ferrebot_events', payload)
                └─► _pg_listen_worker en CADA réplica recibe el notify
                      └─► broadcast() → SSE clients de esa réplica

    Esto garantiza que aunque Railway corra múltiples instancias del servicio API,
    todos los clientes del dashboard (conectados a cualquier instancia) reciban el evento.

    Fallback: si DATABASE_URL no está disponible o pg_notify falla, hace broadcast()
    local (funciona correctamente con una sola instancia).

    Uso desde routers (async):
        from routers.events import notify_all
        await notify_all("venta_registrada", {"vendedor": 42})
    """
    import db as _db

    payload = json.dumps({"type": event_type, "data": data or {}})

    try:
        async with _notify_sem:
            await _db.execute_async(
                "SELECT pg_notify('ferrebot_events', %s)",
                (payload,),
            )
        log.debug("notify_all via pg_notify: %s", event_type)
    except Exception as exc:
        log.warning(
            "notify_all: pg_notify falló (%s) — usando broadcast local como fallback", exc
        )
        broadcast(event_type, data)


# ── Generator SSE ─────────────────────────────────────────────────────────────

async def _event_generator(request: Request) -> AsyncGenerator[str, None]:
    """
    Generador async que mantiene la conexión SSE abierta y emite:
      - ": connected\\n\\n"   al conectar (confirma la conexión al cliente)
      - "data: {...}\\n\\n"    por cada evento de broadcast()
      - ": heartbeat\\n\\n"   cada 25 s si no hay eventos (evita timeout en proxies)

    El heartbeat de 25 s previene que Railway, nginx u otros proxies cierren
    la conexión por inactividad (timeout típico: 30–60 s).

    El ciclo interno usa un timeout de 5 s (en lugar de 25 s) para detectar
    desconexiones del cliente en hasta 5 s, reduciendo suscriptores fantasma
    que de otro modo vivirían hasta 25 s después de que el browser se cierre.
    El heartbeat se emite acumulando esos ciclos de 5 s hasta llegar a 25 s.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(queue)
    log.debug("SSE client conectado — total suscriptores: %d", len(_subscribers))

    try:
        yield ": connected\n\n"

        # Acumula tiempo sin actividad para disparar el heartbeat cada 25 s.
        idle_seconds = 0
        HEARTBEAT_INTERVAL = 25
        POLL_INTERVAL = 5  # cada cuántos segundos se verifica desconexión

        while True:
            if await request.is_disconnected():
                log.debug("SSE client detectado como desconectado — cerrando generator")
                break

            try:
                payload = await asyncio.wait_for(queue.get(), timeout=POLL_INTERVAL)
                idle_seconds = 0
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                idle_seconds += POLL_INTERVAL
                if idle_seconds >= HEARTBEAT_INTERVAL:
                    idle_seconds = 0
                    yield ": heartbeat\n\n"

    except asyncio.CancelledError:
        log.debug("SSE generator cancelado")
    finally:
        try:
            _subscribers.remove(queue)
        except ValueError:
            pass
        log.debug(
            "SSE client desconectado — suscriptores restantes: %d", len(_subscribers)
        )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/events")
async def sse_stream(
    request: Request,
    token: str = Query(..., description="JWT de sesión — requerido porque EventSource no soporta headers custom"),
) -> StreamingResponse:
    """
    Stream SSE para el dashboard.

    Autenticación: JWT como query param ?token=... porque EventSource del browser
    no permite headers custom (no puede enviar Authorization).

    Headers:
        Cache-Control: no-cache      → evita cacheo del stream
        X-Accel-Buffering: no        → desactiva buffering de nginx / Railway proxy
        Connection: keep-alive       → mantiene el socket TCP abierto
    """
    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        log.error("SECRET_KEY no configurada — SSE auth no puede validar tokens")
        raise HTTPException(status_code=500, detail="Configuración incompleta del servidor")

    try:
        _jwt.decode(token, secret, algorithms=["HS256"])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection":    "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/status")
async def sse_status() -> dict:
    """Endpoint de diagnóstico — cuántos clientes SSE hay conectados en esta instancia."""
    return {"suscriptores_activos": len(_subscribers)}
