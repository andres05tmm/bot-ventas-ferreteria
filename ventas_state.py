"""
Estado en memoria para ventas pendientes de confirmación y borrados pendientes.
Protegido con threading.Lock para evitar race conditions en el event loop async.

CORRECCIONES v2:
  - _parsear_precio eliminada — se usa parsear_precio de utils (era duplicado)
  - mensajes_standby tiene cap de MAX_STANDBY mensajes por chat (evita crecimiento infinito)
  - consecutivo siempre >= 1: se usa obtener_siguiente_consecutivo() directamente
    en lugar de obtener_consecutivo_actual() que podía retornar 0
  - Docstring movido ANTES del import logging

CORRECCIONES v3:
  - Protección mejorada en descuento de inventario (manejo explícito de None)
"""

import logging
import asyncio
import threading

import config
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, es_thinner, parsear_precio
from excel import (
    obtener_siguiente_consecutivo,
    guardar_venta_excel,
    obtener_nombre_id_cliente,
)
from memoria import cargar_inventario, guardar_inventario, cargar_caja, guardar_caja, cargar_memoria, descontar_inventario

_estado_lock = threading.Lock()

# Límite máximo de mensajes en standby por chat (evita crecimiento infinito)
MAX_STANDBY = 3

# {chat_id: [lista de ventas pendientes de confirmar método de pago]}
ventas_pendientes: dict[int, list] = {}

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

_chat_locks: dict[int, asyncio.Lock] = {}
_chat_locks_meta = threading.Lock()


def get_chat_lock(chat_id: int) -> asyncio.Lock:
    with _chat_locks_meta:
        if chat_id not in _chat_locks:
            _chat_locks[chat_id] = asyncio.Lock()
        return _chat_locks[chat_id]


def agregar_al_historial(chat_id: int, role: str, content: str):
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


def get_historial(chat_id: int) -> list:
    with _estado_lock:
        return list(historiales.get(chat_id, []))


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


def registrar_ventas_con_metodo(ventas: list, metodo: str, vendedor: str, chat_id: int) -> list[str]:
    with _estado_lock:
        ventas_pendientes.pop(chat_id, None)
        # CORRECCIÓN Bug 5: consecutivo se obtiene DENTRO del lock para evitar
        # que dos ventas simultáneas reciban el mismo número de consecutivo.
        consecutivo = obtener_siguiente_consecutivo()

    confirmaciones    = []
    total_transaccion = 0

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

        precio_u_excel = valor_final / cantidad if cantidad > 0 else valor_final

        guardar_venta_excel(
            producto, cantidad, precio_u_excel, valor_final, vendedor, metodo,
            cliente_nombre=nombre_c, cliente_id=id_c,
            consecutivo=consecutivo,
        )

        cliente_txt = f" | {nombre_c}" if nombre_c != "Consumidor Final" else ""
        confirmaciones.append(f"• {cantidad_legible} {producto} ${valor_final:,.0f}{cliente_txt}")

        # Descontar inventario (solo si el producto está registrado).
        # descontar_inventario() siempre retorna (bool, str|None, float|None).
        descontado, alerta, cantidad_restante = descontar_inventario(producto, cantidad)
        if descontado and alerta:
            confirmaciones.append(alerta)

    # Actualizar caja
    caja = cargar_caja()
    if caja.get("abierta"):
        campo        = {"efectivo": "efectivo", "transferencia": "transferencias", "datafono": "datafono"}.get(metodo, "efectivo")
        caja[campo]  = caja.get(campo, 0) + total_transaccion
        guardar_caja(caja)

    confirmaciones.insert(0, f"🧾 Consecutivo #{consecutivo}")
    confirmaciones.append(f"💰 Total: ${total_transaccion:,.0f}")
    return confirmaciones


async def registrar_ventas_con_metodo_async(ventas, metodo, vendedor, chat_id) -> list[str]:
    """Wrapper async para no bloquear el event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: registrar_ventas_con_metodo(ventas, metodo, vendedor, chat_id)
    )
