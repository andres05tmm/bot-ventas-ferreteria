"""
Estado en memoria para ventas pendientes de confirmacion y borrados pendientes.
Protegido con threading.Lock para evitar race conditions en el event loop async.
"""

import asyncio
import threading

import config
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, es_thinner, cantidad_thinner_por_precio
from excel import (
    obtener_siguiente_consecutivo,
    guardar_venta_excel,
    obtener_nombre_id_cliente,
)
from memoria import cargar_inventario, guardar_inventario, cargar_caja, guardar_caja


_estado_lock = threading.Lock()

# {chat_id: [lista de ventas pendientes de confirmar metodo de pago]}
ventas_pendientes: dict[int, list] = {}

# {chat_id: numero_venta} para confirmar borrado
borrados_pendientes: dict[int, int] = {}

# {chat_id: [historial de mensajes]}
historiales: dict[int, list] = {}

# {chat_id: dict con datos del cliente en proceso de creacion}
clientes_en_proceso: dict[int, dict] = {}

# {chat_id: {"ventas": [...], "metodo": "efectivo"|None}}
# Ventas que quedaron en pausa esperando que se cree el cliente
# Una vez creado el cliente, se registran automaticamente
ventas_esperando_cliente: dict[int, dict] = {}


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
    """
    Registra una lista de ventas con el metodo de pago dado.
    Todos los productos de una misma transaccion comparten el mismo consecutivo.
    """
    confirmaciones = []
    consecutivo    = obtener_siguiente_consecutivo()

    # Resolver cliente (del primer producto que lo mencione)
    id_c, nombre_c = "CF", "Consumidor Final"
    for venta in ventas:
        if venta.get("cliente"):
            id_c, nombre_c = obtener_nombre_id_cliente(venta["cliente"])
            break

    total_transaccion = 0
    for venta in ventas:
        producto       = venta.get("producto", "Sin nombre")
        cantidad       = convertir_fraccion_a_decimal(venta.get("cantidad", 1))
        precio_cobrado = float(venta.get("precio_unitario", 0))

        # ── Thinner: el precio pagado ES el total; la cantidad se deriva del precio ──
        # Claude manda precio_unitario=lo que pago el cliente y cantidad=fraccion calculada.
        # El total NUNCA debe multiplicarse: es exactamente lo que pago el cliente.
        if es_thinner(producto):
            # Si Claude no supo calcular bien la cantidad, la derivamos del precio
            cantidad_esperada, frac_legible = cantidad_thinner_por_precio(precio_cobrado)
            if cantidad_esperada > 0 and abs(cantidad - cantidad_esperada) > 0.05:
                # Corregir cantidad si difiere significativamente de la tabla oficial
                print(f"[THINNER] corrigiendo cantidad {cantidad:.4f} → {cantidad_esperada:.6g} para precio ${precio_cobrado:,.0f}")
                cantidad = cantidad_esperada
            # Para thinner: total = lo que pago el cliente (precio_cobrado), sin multiplicar
            total = round(precio_cobrado)
        else:
            # Resto de productos: total = precio_unitario × cantidad
            total = round(precio_cobrado * cantidad)

        total_transaccion += total
        cantidad_legible   = decimal_a_fraccion_legible(cantidad)

        guardar_venta_excel(
            producto, cantidad, precio_cobrado, total, vendedor, metodo,
            cliente_nombre=nombre_c, cliente_id=id_c,
            consecutivo=consecutivo,
        )

        cliente_txt = f" | {nombre_c}" if nombre_c != "Consumidor Final" else ""
        confirmaciones.append(f"• {producto} x{cantidad_legible} = ${total:,.0f}{cliente_txt}")

        # Descontar inventario
        inventario = cargar_inventario()
        prod_lower = producto.lower()
        prod_key   = next((k for k in inventario if k in prod_lower or prod_lower in k), None)
        if prod_key and isinstance(inventario[prod_key], dict):
            inv = inventario[prod_key]
            inv["cantidad"] = max(0, round(inv.get("cantidad", 0) - cantidad, 4))
            guardar_inventario(inventario)
            restante = decimal_a_fraccion_legible(inv["cantidad"])
            unidad   = inv.get("unidad", "")
            if inv["cantidad"] <= inv.get("minimo", 0.5):
                confirmaciones.append(f"⚠️ Stock bajo: {prod_key} — quedan {restante} {unidad}")

    # Actualizar caja
    caja = cargar_caja()
    if caja.get("abierta"):
        campo_map = {"efectivo": "efectivo", "transferencia": "transferencias", "datafono": "datafono"}
        campo = campo_map.get(metodo, "efectivo")
        caja[campo] = caja.get(campo, 0) + total_transaccion
        guardar_caja(caja)

    confirmaciones.insert(0, f"🧾 Consecutivo #{consecutivo}")
    return confirmaciones


async def registrar_ventas_con_metodo_async(ventas, metodo, vendedor, chat_id) -> list[str]:
    """Wrapper async para no bloquear el event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: registrar_ventas_con_metodo(ventas, metodo, vendedor, chat_id)
    )
