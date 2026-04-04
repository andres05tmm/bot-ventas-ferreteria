"""
SSE (Server-Sent Events) — canal de notificaciones en tiempo real para el dashboard.

El frontend escucha GET /events y recibe un mensaje cada vez que ocurre un cambio
relevante (venta registrada, inventario modificado, caja cerrada, etc.).

Uso desde cualquier router:
    from routers.events import broadcast
    broadcast("venta_registrada", {"vendedor": vendedor_id})
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

log = logging.getLogger("ferrebot.events")
router = APIRouter()

# ── Registro de suscriptores ──────────────────────────────────────────────────
# Cada conexión SSE activa tiene su propia asyncio.Queue.
# broadcast() pone un mensaje en todas las colas; cada generator lo consume.
_subscribers: list[asyncio.Queue] = []


def broadcast(event_type: str, data: dict | None = None) -> None:
    """
    Notifica a todos los clientes SSE conectados de un evento.

    Llamar al final de cualquier endpoint que modifique datos relevantes:
        broadcast("venta_registrada", {"vendedor": 42})
        broadcast("inventario_actualizado")
        broadcast("caja_cerrada")

    Es thread-safe para llamadas desde código síncrono normal de FastAPI,
    ya que put_nowait() no hace I/O bloqueante.
    """
    payload = json.dumps({"type": event_type, "data": data or {}})
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
    log.debug(f"SSE client conectado — total suscriptores: {len(_subscribers)}")

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
            pass  # ya fue removido por broadcast() si la cola estaba llena
        log.debug(f"SSE client desconectado — suscriptores restantes: {len(_subscribers)}")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/events")
async def sse_stream(request: Request) -> StreamingResponse:
    """
    Stream SSE para el dashboard.

    El cliente React se conecta con:
        const es = new EventSource('/events', { withCredentials: true })
        es.onmessage = (e) => { const { type, data } = JSON.parse(e.data) }

    Headers importantes:
        Cache-Control: no-cache      → evita que el browser o proxies cacheen el stream
        X-Accel-Buffering: no        → desactiva el buffering de nginx / Railway;
                                       sin este header los eventos llegan en bloques.
        Connection: keep-alive       → mantiene el socket TCP abierto
    """
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
