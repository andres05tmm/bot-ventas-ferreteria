"""
SSE (Server-Sent Events) — canal de notificaciones en tiempo real para el dashboard.

El frontend escucha GET /events y recibe un mensaje cada vez que ocurre un cambio
relevante (venta registrada, inventario modificado, caja cerrada, etc.).

Uso desde cualquier router:
    from routers.events import broadcast
    broadcast("venta_registrada", {"vendedor": vendedor_id})

Thread safety
─────────────
broadcast() puede llamarse desde dos contextos:
  1. Routers async de FastAPI  → corren DENTRO del event loop → put_nowait() directo.
  2. _pg_listen_worker          → hilo daemon FUERA del loop   → usar call_soon_threadsafe().

asyncio.Queue.put_nowait() NO es thread-safe si se llama desde fuera del event loop
(internamente llama fut.set_result() sobre Futures del loop, lo que causa race conditions
silenciosas en producción). La solución es que toda mutación de las colas ocurra dentro
del loop, usando call_soon_threadsafe() cuando la llamada viene de un hilo externo.

set_main_loop(loop) debe llamarse desde el lifespan de api.py inmediatamente después
de que el event loop de uvicorn esté corriendo, para que el hilo pg_listener pueda
referenciar el loop correcto.
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

# ── Event loop del proceso principal ─────────────────────────────────────────
# Se inicializa desde api.py lifespan vía set_main_loop().
# Necesario para que broadcast() sea thread-safe cuando lo llama _pg_listen_worker.
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
# Cada conexión SSE activa tiene su propia asyncio.Queue.
# _do_broadcast() pone un mensaje en todas las colas; cada generator lo consume.
# IMPORTANTE: _subscribers solo debe modificarse desde dentro del event loop
# (append/remove en _event_generator, put_nowait en _do_broadcast).
# broadcast() garantiza esto redirigiendo con call_soon_threadsafe() cuando
# la llamada viene de un hilo externo.
_subscribers: list[asyncio.Queue] = []


def _do_broadcast(payload: str) -> None:
    """
    Pone el payload en todas las colas activas.

    DEBE ejecutarse dentro del event loop (es llamada directamente desde
    coroutines o vía call_soon_threadsafe desde hilos externos).
    No llamar desde hilos sin pasar por broadcast().
    """
    dead: list[asyncio.Queue] = []

    for q in _subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Cliente lento o desconectado sin limpiar → marcar para eliminar
            dead.append(q)

    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass  # ya fue removido por el generator al desconectarse


def broadcast(event_type: str, data: dict | None = None) -> None:
    """
    Notifica a todos los clientes SSE conectados de un evento.

    Thread-safe: puede llamarse desde routers async (dentro del event loop)
    o desde hilos externos como _pg_listen_worker (fuera del event loop).

    Llamar al final de cualquier endpoint que modifique datos relevantes:
        broadcast("venta_registrada", {"vendedor": 42})
        broadcast("inventario_actualizado")
        broadcast("caja_cerrada")
    """
    payload = json.dumps({"type": event_type, "data": data or {}})

    try:
        # Si hay un loop corriendo en este hilo → estamos en una coroutine de FastAPI.
        # put_nowait() es seguro porque todo ocurre dentro del mismo loop.
        asyncio.get_running_loop()
        _do_broadcast(payload)

    except RuntimeError:
        # No hay loop en este hilo → llamada desde _pg_listen_worker u otro hilo.
        # call_soon_threadsafe() programa _do_broadcast en el loop principal,
        # garantizando que se ejecute en el thread correcto.
        if _main_loop and _main_loop.is_running():
            _main_loop.call_soon_threadsafe(_do_broadcast, payload)
        else:
            log.warning(
                "broadcast(%s) descartado — event loop no disponible aún", event_type
            )


# ── Generator SSE ─────────────────────────────────────────────────────────────

async def _event_generator(request: Request) -> AsyncGenerator[str, None]:
    """
    Generador async que mantiene la conexión SSE abierta y emite:
      - ": connected\\n\\n"   al conectar (confirma la conexión al cliente)
      - "data: {...}\\n\\n"    por cada evento de broadcast()
      - ": heartbeat\\n\\n"   cada 25 s si no hay eventos (evita timeout en proxies)
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(queue)
    log.debug("SSE client conectado — total suscriptores: %d", len(_subscribers))

    try:
        # Comentario inicial: confirma la conexión sin disparar onmessage en el cliente
        yield ": connected\n\n"

        while True:
            # Verificar desconexión del cliente antes de esperar el próximo evento
            if await request.is_disconnected():
                log.debug("SSE client detectado como desconectado — cerrando generator")
                break

            try:
                payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                # Heartbeat: mantiene viva la conexión en Railway / nginx / proxies
                # que cierran conexiones idle. Un comentario SSE no dispara onmessage.
                yield ": heartbeat\n\n"

    except asyncio.CancelledError:
        # El cliente cerró la pestaña o el servidor está apagándose
        log.debug("SSE generator cancelado")
    finally:
        try:
            _subscribers.remove(queue)
        except ValueError:
            pass  # ya fue removido por _do_broadcast() si la cola estaba llena
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

    Autenticación: se pasa el JWT como query param ?token=... porque la API
    EventSource del browser no permite headers custom (no puede enviar Authorization).

    El cliente React se conecta con:
        const es = new EventSource(`/events?token=${jwt}`, { withCredentials: true })
        es.onmessage = (e) => { const { type, data } = JSON.parse(e.data) }

    Headers importantes:
        Cache-Control: no-cache      → evita que el browser o proxies cacheen el stream
        X-Accel-Buffering: no        → desactiva el buffering de nginx / Railway;
                                       sin este header los eventos llegan en bloques.
        Connection: keep-alive       → mantiene el socket TCP abierto
    """
    # Validar JWT — el token se pasa como query param porque EventSource
    # no admite headers Authorization en el browser.
    try:
        _jwt.decode(
            token,
            os.environ.get("SECRET_KEY", ""),
            algorithms=["HS256"],
        )
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/status")
async def sse_status() -> dict:
    """Endpoint de diagnóstico — cuántos clientes SSE hay conectados."""
    return {"suscriptores_activos": len(_subscribers)}
