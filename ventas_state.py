"""
Estado en memoria para ventas pendientes de confirmación y borrados pendientes.
Protegido con threading.Lock para evitar race conditions en el event loop async.

CORRECCIONES v4:
  - ventas_pendientes con timestamp para expiración automática (5 min)
  - limpiar_pendientes_expirados() evita estado atascado tras excepción
"""

import json as _json
import logging
import asyncio
import threading
import time

import config
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, es_thinner, parsear_precio
from db import obtener_siguiente_consecutivo, obtener_nombre_id_cliente
from memoria import cargar_inventario, guardar_inventario, cargar_caja, guardar_caja, cargar_memoria, descontar_inventario

_estado_lock = threading.Lock()

# Límite máximo de mensajes en standby por chat
MAX_STANDBY = 3

# Tiempo máximo que una venta puede estar pendiente de confirmación (segundos)
_TIMEOUT_PENDIENTE = 300  # 5 minutos

# {chat_id: [lista de ventas pendientes de confirmar método de pago]}
ventas_pendientes: dict[int, list] = {}

# {chat_id: timestamp} — cuándo se guardó cada pendiente
_ventas_pendientes_ts: dict[int, float] = {}

# ─────────────────────────────────────────────────────────────────────────
# PASO 4 — Carrito conversacional de audio
# ─────────────────────────────────────────────────────────────────────────
# Cuando el vendedor manda varios audios seguidos (p.ej. "me trajo 3 clavos",
# luego "y 2 martillos", luego "todo junto a Pedro"), no queremos pedirle el
# método de pago en cada audio: acumulamos las ventas en un "carrito" y solo
# cerramos cuando:
#   (a) el vendedor lo cierra explícitamente ("cobra"/"cierra"/"efectivo al final"), o
#   (b) pasan 90 segundos sin nuevos audios → auto-cierre con método=efectivo.
#
# Todo es efímero: si el proceso se reinicia el carrito se pierde (a propósito
# — no queremos revivir ventas a medio cobrar tras un redeploy).

# {chat_id: "audio" | "texto"} — origen del último turno que tocó el carrito.
# Usado por response_builder para decidir si APPEND (audio) o REPLACE (texto).
_carrito_origen: dict[int, str] = {}

# {chat_id: asyncio.Task} — timer activo que cerrará el carrito por inactividad.
# Cada audio nuevo cancela el timer anterior y arma uno fresco.
_timers_carrito: dict[int, "asyncio.Task"] = {}

# {chat_id: str} — método de pago elegido explícitamente por el vendedor dentro
# del carrito ("efectivo" / "transferencia" / "datafono"). None/ausente = aún
# no declarado.
_carrito_metodo: dict[int, str] = {}

# Timeout de inactividad del carrito (segundos). Configurable por env.
import os as _os
_TIMEOUT_CARRITO = float(_os.getenv("CARRITO_TIMEOUT_SEG", "90"))

# {chat_id: [mensajes en standby esperando que se confirme el pago anterior]}
mensajes_standby: dict[int, list[str]] = {}

# chat_id -> "modificar" | True cuando hay corrección pendiente
esperando_correccion: dict[int, bool] = {}

# {chat_id: numero_venta} para confirmar borrado
borrados_pendientes: dict[int, int] = {}

# {chat_id: [historial de mensajes]}
historiales: dict[int, list] = {}

# {chat_id: dict con datos del cliente en proceso de creación}
clientes_en_proceso: dict[int, dict] = {}

# {chat_id: {"ventas": [...], "metodo": "efectivo"|None}}
ventas_esperando_cliente: dict[int, dict] = {}

# {chat_id: dict} — guarda contexto cuando Claude hizo una pregunta aclaratoria sin
# registrar venta. Estructura: {"mensaje": str, "pregunta": str}
#   "mensaje" → lo que envió el usuario originalmente (lista de productos, etc.)
#   "pregunta" → la pregunta que hizo el bot (para enriquecer el prompt de Whisper
#                y el contexto de Claude en el siguiente turno)
mensaje_contexto_pendiente: dict[int, dict] = {}

# {chat_id: True} — el usuario está en modo actualización de precios via /actualizar_precio
actualizando_precios: dict[int, bool] = {}

# {chat_id: str} — respuesta_raw de Claude de una foto, esperando confirmación del vendedor
# ANTES de ejecutar las ventas, el usuario debe aprobar la lista leída
fotos_pendientes_confirmacion: dict[int, str] = {}

_chat_locks: dict[int, asyncio.Lock] = {}
_chat_locks_meta = threading.Lock()


def _guardar_pendiente(chat_id: int, ventas: list):
    """Guarda ventas pendientes con timestamp. Usar DENTRO del lock."""
    ventas_pendientes[chat_id]     = ventas
    _ventas_pendientes_ts[chat_id] = time.time()


def append_a_pendiente(chat_id: int, ventas_nuevas: list):
    """
    Suma ventas al carrito en vez de reemplazarlas. Usar para audios sucesivos.
    Refresca el timestamp (extiende la ventana de inactividad).
    No toma el lock — el caller debe estar dentro de _estado_lock.
    """
    if not ventas_nuevas:
        return
    actual = ventas_pendientes.get(chat_id) or []
    actual.extend(ventas_nuevas)
    ventas_pendientes[chat_id]     = actual
    _ventas_pendientes_ts[chat_id] = time.time()


def marcar_origen_carrito(chat_id: int, origen: str):
    """Marca el origen del carrito: 'audio' acumula, cualquier otro reemplaza."""
    with _estado_lock:
        if origen in ("audio", "texto"):
            _carrito_origen[chat_id] = origen


def origen_carrito(chat_id: int) -> str:
    """Retorna el origen actual del carrito ('audio'/'texto'/'' si no hay)."""
    with _estado_lock:
        return _carrito_origen.get(chat_id, "")


def fijar_metodo_carrito(chat_id: int, metodo: str):
    """Guarda el método de pago declarado por el vendedor durante el carrito."""
    metodo_norm = (metodo or "").lower().strip()
    if metodo_norm not in ("efectivo", "transferencia", "datafono"):
        return
    with _estado_lock:
        _carrito_metodo[chat_id] = metodo_norm


def obtener_metodo_carrito(chat_id: int) -> str | None:
    """Retorna el método declarado (si hubo) o None."""
    with _estado_lock:
        return _carrito_metodo.get(chat_id)


def limpiar_carrito(chat_id: int):
    """Limpia todo el estado del carrito para un chat (ventas, origen, método, timer)."""
    with _estado_lock:
        ventas_pendientes.pop(chat_id, None)
        _ventas_pendientes_ts.pop(chat_id, None)
        _carrito_origen.pop(chat_id, None)
        _carrito_metodo.pop(chat_id, None)
        timer = _timers_carrito.pop(chat_id, None)
    if timer is not None and not timer.done():
        try:
            timer.cancel()
        except Exception:
            pass


def cancelar_timer_carrito(chat_id: int):
    """Cancela el timer activo del carrito (si lo hay). No toca las ventas."""
    with _estado_lock:
        timer = _timers_carrito.pop(chat_id, None)
    if timer is not None and not timer.done():
        try:
            timer.cancel()
        except Exception:
            pass


def armar_timer_carrito(
    chat_id: int,
    coroutine_factory,
    segundos: float | None = None,
):
    """
    Arma (o re-arma) el timer de auto-cierre del carrito.

    `coroutine_factory` es un callable sin argumentos que retorna la corrutina
    que se ejecutará al vencer el timeout (por ejemplo, el cierre forzado con
    método=efectivo). Se pasa como factory para que no se cree la corrutina
    hasta que realmente se necesite ejecutarla.

    Requiere estar dentro de un event loop asyncio activo.
    """
    if segundos is None:
        segundos = _TIMEOUT_CARRITO

    # Cancelar timer previo si existía
    cancelar_timer_carrito(chat_id)

    async def _esperar_y_disparar():
        try:
            await asyncio.sleep(segundos)
        except asyncio.CancelledError:
            return
        # Ejecutar callback; cualquier excepción queda contenida
        try:
            await coroutine_factory()
        except asyncio.CancelledError:
            return
        except Exception as _e:
            logging.getLogger("ferrebot.ventas_state").warning(
                f"[carrito] timer callback falló chat={chat_id}: {_e}"
            )

    try:
        task = asyncio.create_task(_esperar_y_disparar())
    except RuntimeError:
        # No hay event loop — caller se ejecutó desde thread sin loop
        logging.getLogger("ferrebot.ventas_state").warning(
            f"[carrito] armar_timer_carrito sin event loop chat={chat_id}"
        )
        return

    with _estado_lock:
        _timers_carrito[chat_id] = task


def tiene_carrito_activo(chat_id: int) -> bool:
    """True si el chat tiene ventas pendientes acumuladas (carrito abierto)."""
    with _estado_lock:
        return bool(ventas_pendientes.get(chat_id))


def limpiar_pendientes_expirados():
    """
    Elimina ventas_pendientes que llevan más de _TIMEOUT_PENDIENTE sin confirmarse.
    Seguro de llamar con o sin _estado_lock tomado: usa trylock para no deadlockear.
    """
    ahora = time.time()
    # Usar acquire(blocking=False) para no bloquear si ya está tomado
    adquirido = _estado_lock.acquire(blocking=False)
    try:
        expirados = [
            cid for cid, ts in list(_ventas_pendientes_ts.items())
            if ahora - ts > _TIMEOUT_PENDIENTE
        ]
        for cid in expirados:
            ventas_pendientes.pop(cid, None)
            _ventas_pendientes_ts.pop(cid, None)
            mensajes_standby.pop(cid, None)
            logging.getLogger("ferrebot.ventas_state").info(
                f"[TIMEOUT] Pendiente expirado chat {cid} — estado limpiado"
            )
    finally:
        if adquirido:
            _estado_lock.release()


def get_chat_lock(chat_id: int) -> asyncio.Lock:
    with _chat_locks_meta:
        if chat_id not in _chat_locks:
            _chat_locks[chat_id] = asyncio.Lock()
        return _chat_locks[chat_id]


def agregar_al_historial(
    chat_id: int,
    role: str,
    content: str,
    vendedor_id: int | None = None,
    modelo: str | None = None,
):
    """
    Agrega un turno al historial del chat.

    En memoria: cap de 20 turnos por chat × 200 chats distintos (LRU).
    En DB:      persiste best-effort en conversaciones_bot (Capa 1 de
                memoria del bot — sobrevive a restarts de Railway).

    `vendedor_id` y `modelo` son opcionales y solo se usan para enriquecer
    el row persistido. La cache en memoria no los necesita.
    """
    with _estado_lock:
        if chat_id not in historiales:
            # Límite de 200 chats distintos en memoria
            if len(historiales) >= 200:
                oldest_chat = next(iter(historiales))
                del historiales[oldest_chat]
            historiales[chat_id] = []
        historiales[chat_id].append({"role": role, "content": content})
        if len(historiales[chat_id]) > 20:
            historiales[chat_id] = historiales[chat_id][-20:]

    # Persistencia best-effort fuera del lock — si la DB falla no afecta al chat.
    # Import lazy para evitar ciclos: ai/memoria_turno → db, y este módulo carga
    # antes que ai/* en algunos paths.
    try:
        from ai.memoria_turno import guardar_turno as _guardar_turno_db
        _guardar_turno_db(
            chat_id=chat_id,
            role=role,
            content=content,
            vendedor_id=vendedor_id,
            modelo=modelo,
        )
    except Exception as _e:
        # JAMÁS romper al usuario por un fallo de persistencia.
        logging.getLogger("ferrebot.ventas_state").debug(
            f"[memoria_turno] guardar falló: {_e}"
        )


def get_historial(chat_id: int) -> list:
    """
    Retorna el historial del chat. Si la cache en memoria está vacía
    (cold start tras un deploy de Railway), hidrata desde la tabla
    conversaciones_bot — así el bot no "olvida" la conversación.

    Solo se hidrata UNA VEZ por chat: tras la primera lectura la cache
    queda poblada y subsecuentes get_historial() no tocan la DB.
    """
    with _estado_lock:
        cache = historiales.get(chat_id)
        if cache:
            return list(cache)

    # Cache vacía → intentar hidratar desde DB (sin lock para no bloquear
    # otros chats mientras hablamos con PG).
    hidratado: list = []
    try:
        from ai.memoria_turno import cargar_turnos_recientes as _cargar_turnos_db
        hidratado = _cargar_turnos_db(chat_id, limite=8) or []
    except Exception as _e:
        logging.getLogger("ferrebot.ventas_state").debug(
            f"[memoria_turno] hidratar falló: {_e}"
        )
        hidratado = []

    if not hidratado:
        return []

    # Poblar la cache para evitar repetir el SELECT en el siguiente turno.
    with _estado_lock:
        # Doble-check por race: si otro hilo ya hidrató en paralelo, no
        # pisamos su trabajo.
        if not historiales.get(chat_id):
            if len(historiales) >= 200:
                oldest_chat = next(iter(historiales))
                del historiales[oldest_chat]
            historiales[chat_id] = list(hidratado)
        return list(historiales[chat_id])


def agregar_a_standby(chat_id: int, mensaje: str):
    """
    Agrega un mensaje al standby del chat.
    CORRECCIÓN: limitado a MAX_STANDBY mensajes para evitar crecimiento infinito.
    """
    with _estado_lock:
        if chat_id not in mensajes_standby:
            mensajes_standby[chat_id] = []
        if len(mensajes_standby[chat_id]) < MAX_STANDBY:
            mensajes_standby[chat_id].append(mensaje)
        else:
            # Descartamos el más antiguo y guardamos el nuevo
            mensajes_standby[chat_id].pop(0)
            mensajes_standby[chat_id].append(mensaje)


def registrar_ventas_con_metodo(ventas: list, metodo: str, vendedor: str, chat_id: int, usuario_id: int | None = None) -> list[str]:
    with _estado_lock:
        ventas_pendientes.pop(chat_id, None)
        _ventas_pendientes_ts.pop(chat_id, None)
        # Carrito queda cerrado: limpiamos origen/método. Timer lo cancelamos
        # fuera del lock para no bloquear.
        _carrito_origen.pop(chat_id, None)
        _carrito_metodo.pop(chat_id, None)
        timer = _timers_carrito.pop(chat_id, None)
        # CORRECCIÓN Bug 5: consecutivo se obtiene DENTRO del lock para evitar
        # que dos ventas simultáneas reciban el mismo número de consecutivo.
        consecutivo = obtener_siguiente_consecutivo()
    if timer is not None and not timer.done():
        try:
            timer.cancel()
        except Exception:
            pass

    confirmaciones    = []
    total_transaccion = 0
    items_para_pg     = []

    # Resolver cliente (del primer producto que lo mencione)
    id_c, nombre_c = "CF", "Consumidor Final"
    for venta in ventas:
        if venta.get("cliente"):
            id_c, nombre_c = obtener_nombre_id_cliente(venta["cliente"])
            break

    for venta in ventas:
        producto = venta.get("producto", "Sin nombre")
        cantidad = convertir_fraccion_a_decimal(venta.get("cantidad", 1))

        # CORRECCIÓN: usar parsear_precio de utils en lugar de la función local duplicada
        total                   = parsear_precio(venta.get("total", 0))
        precio_unitario_enviado = parsear_precio(venta.get("precio_unitario", 0))

        # ── Resolver unidad de medida desde el catálogo ──────────────
        unidad = venta.get("unidad_medida", "")
        if not unidad:
            try:
                from memoria import buscar_producto_en_catalogo
                prod_cat = buscar_producto_en_catalogo(str(producto))
                if prod_cat:
                    unidad = prod_cat.get("unidad_medida", "Unidad") or "Unidad"
            except Exception:
                pass
        if not unidad:
            unidad = "Unidad"

        # REGLA DEFINITIVA DE PRECIO:
        # Si llega "total" > 0, es el valor definitivo.
        # "precio_unitario" es fallback por compatibilidad.
        if total > 0:
            valor_final = round(total)
        elif precio_unitario_enviado > 0:
            if cantidad < 1.0:
                valor_final = round(precio_unitario_enviado)
            else:
                valor_final = round(precio_unitario_enviado * cantidad)
        else:
            valor_final = 0

        total_transaccion += valor_final
        cantidad_legible   = decimal_a_fraccion_legible(cantidad)

        # Recopilar datos para Postgres (se insertan después del loop)
        precio_u_pg = round(valor_final / cantidad) if cantidad > 0 else valor_final
        items_para_pg.append({
            "producto":    producto,
            "cantidad":    cantidad,
            "unidad":      unidad,
            "precio_u":    precio_u_pg,
            "valor_final": valor_final,
            "alias":       venta.get("alias"),
            "sin_detalle": venta.get("sin_detalle", False),
        })

        cliente_txt = f" | {nombre_c}" if nombre_c != "Consumidor Final" else ""
        confirmaciones.append(f"• {cantidad_legible} {producto} ${valor_final:,.0f}{cliente_txt}")

        # Descontar inventario (solo si el producto está registrado y no es venta sin detalle).
        # descontar_inventario() siempre retorna (bool, str|None, float|None).
        es_sin_detalle = venta.get("sin_detalle", False)
        if not es_sin_detalle:
            descontado, alerta, cantidad_restante = descontar_inventario(producto, cantidad)
            if descontado and alerta:
                confirmaciones.append(alerta)

    # Actualizar caja
    caja = cargar_caja()
    if caja.get("abierta"):
        campo        = {"efectivo": "efectivo", "transferencia": "transferencias", "datafono": "datafono"}.get(metodo, "efectivo")
        caja[campo]  = caja.get(campo, 0) + total_transaccion
        guardar_caja(caja)

    # ── Postgres write (non-fatal, additive) ─────────────────────────────────
    try:
        import db as _db
        if _db.DB_DISPONIBLE:
            from datetime import datetime as _dt
            _logger = logging.getLogger("ferrebot.ventas_state")
            fecha_hoy   = _dt.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
            hora_actual = _dt.now(config.COLOMBIA_TZ).strftime("%H:%M:%S")
            # Resolver cliente_id desde tabla clientes si no es CF
            cliente_id_pg = None
            if id_c != "CF":
                cliente_row = _db.query_one(
                    "SELECT id FROM clientes WHERE LOWER(nombre) = LOWER(%s)",
                    (nombre_c,)
                )
                if cliente_row:
                    cliente_id_pg = cliente_row["id"]
            row = _db.execute_returning(
                """INSERT INTO ventas
                       (consecutivo, fecha, hora, cliente_id, cliente_nombre,
                        vendedor, metodo_pago, total, usuario_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (consecutivo, fecha_hoy, hora_actual, cliente_id_pg,
                 nombre_c, vendedor, metodo, total_transaccion, usuario_id)
            )
            if row:
                venta_id = row["id"]
                for item in items_para_pg:
                    _db.execute(
                        """INSERT INTO ventas_detalle
                               (venta_id, producto_nombre, cantidad, unidad_medida,
                                precio_unitario, total, alias_usado, sin_detalle)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (venta_id, item["producto"], item["cantidad"],
                         item["unidad"], item["precio_u"], item["valor_final"],
                         item.get("alias"), item.get("sin_detalle", False))
                    )
                # Notificar al dashboard via PostgreSQL LISTEN/NOTIFY.
                # El dashboard escucha 'ferrebot_events' y llama broadcast()
                # para propagar el evento SSE a todos los clientes conectados.
                # El notify es parte de la misma transacción: se envía solo
                # cuando el commit ocurre, garantizando que el dashboard
                # nunca recibe un evento de una venta que no llegó a guardarse.
                try:
                    _notify_payload = _json.dumps({
                        "type": "venta_registrada",
                        "data": {
                            "consecutivo": consecutivo,
                            "total":       total_transaccion,
                            "metodo":      metodo,
                            "vendedor":    vendedor,
                        },
                    })
                    _db.execute(
                        "SELECT pg_notify('ferrebot_events', %s)",
                        [_notify_payload],
                    )
                except Exception as _ne:
                    logging.getLogger("ferrebot.ventas_state").warning(
                        f"pg_notify failed (no crítico): {_ne}"
                    )
    except Exception as e:
        logging.getLogger("ferrebot.ventas_state").warning(
            f"Postgres ventas write failed: {e}"
        )
    # ─────────────────────────────────────────────────────────────────────────

    confirmaciones.insert(0, f"🧾 Consecutivo #{consecutivo}")
    confirmaciones.append(f"💰 Total: ${total_transaccion:,.0f}")
    return confirmaciones


async def registrar_ventas_con_metodo_async(ventas, metodo, vendedor, chat_id) -> list[str]:
    """Wrapper async para no bloquear el event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: registrar_ventas_con_metodo(ventas, metodo, vendedor, chat_id)
    )
