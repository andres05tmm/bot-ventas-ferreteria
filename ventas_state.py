"""
Estado en memoria para ventas pendientes de confirmacion y borrados pendientes.
Protegido con threading.Lock para evitar race conditions.
"""

import asyncio
import threading

import config
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, es_thinner
from excel import (
    obtener_siguiente_consecutivo,
    guardar_venta_excel,
    obtener_nombre_id_cliente,
)
from memoria import cargar_inventario, guardar_inventario, cargar_caja, guardar_caja, cargar_memoria

_estado_lock = threading.Lock()

# Estado global en memoria
ventas_pendientes: dict[int, list] = {}
mensajes_standby: dict[int, list[str]] = {}
borrados_pendientes: dict[int, int] = {}
historiales: dict[int, list] = {}
clientes_en_proceso: dict[int, dict] = {}
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
            historiales[chat_id] = []
        historiales[chat_id].append({"role": role, "content": content})
        if len(historiales[chat_id]) > 20:
            historiales[chat_id] = historiales[chat_id][-20:]

def get_historial(chat_id: int) -> list:
    with _estado_lock:
        return list(historiales.get(chat_id, []))

def registrar_ventas_con_metodo(ventas: list, metodo: str, vendedor: str, chat_id: int) -> list[str]:
    with _estado_lock:
        ventas_pendientes.pop(chat_id, None)

    confirmaciones = []
    consecutivo    = obtener_siguiente_consecutivo()

    id_c, nombre_c = "CF", "Consumidor Final"
    for v_temp in ventas:
        if v_temp.get("cliente"):
            id_c, nombre_c = obtener_nombre_id_cliente(v_temp["cliente"])
            break

    total_transaccion = 0
    for venta in ventas:
        producto       = venta.get("producto", "Sin nombre")
        cantidad       = convertir_fraccion_a_decimal(venta.get("cantidad", 1))
        precio_enviado = float(venta.get("precio_unitario", 0))

        # Lógica de precios para fracciones vs enteros
        if cantidad < 1 or es_thinner(producto):
            # Si es fraccion, el precio enviado ya es el TOTAL
            total = round(precio_enviado)
            precio_unitario_excel = total / cantidad if cantidad > 0 else total
        else:
            # Si es 1 o mas, el precio enviado es UNITARIO
            total = round(precio_enviado * cantidad)
            precio_unitario_excel = precio_enviado

        total_transaccion += total
        cantidad_legible   = decimal_a_fraccion_legible(cantidad)

        guardar_venta_excel(
            producto, cantidad, precio_unitario_excel, total, vendedor, metodo,
            cliente_nombre=nombre_c, cliente_id=id_c,
            consecutivo=consecutivo,
        )

        cliente_txt = f" | {nombre_c}" if nombre_c != "Consumidor Final" else ""
        # Orden solicitado: Cantidad + Nombre + Valor
        confirmaciones.append(f"• {cantidad_legible} {producto} ${total:,.0f}{cliente_txt}")

        # Inventario
        inventario = cargar_inventario()
        prod_lower = producto.lower()
        prod_key   = next((k for k in inventario if k in prod_lower or prod_lower in k), None)
        if prod_key and isinstance(inventario[prod_key], dict):
            inv = inventario[prod_key]
            inv["cantidad"] = max(0, round(inv.get("cantidad", 0) - cantidad, 4))
            guardar_inventario(inventario)

    # Caja
    caja = cargar_caja()
    if caja.get("abierta"):
        campo_map = {"efectivo": "efectivo", "transferencia": "transferencias", "datafono": "datafono"}
        campo = campo_map.get(metodo, "efectivo")
        caja[campo] = caja.get(campo, 0) + total_transaccion
        guardar_caja(caja)

    confirmaciones.insert(0, f"🧾 Consecutivo #{consecutivo}")
    return confirmaciones
