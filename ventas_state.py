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
from memoria import cargar_inventario, guardar_inventario, cargar_caja, guardar_caja, cargar_memoria

_estado_lock = threading.Lock()

# {chat_id: [lista de ventas pendientes de confirmar metodo de pago]}
ventas_pendientes: dict[int, list] = {}

# {chat_id: [mensajes en standby esperando que se confirme el pago anterior]}
mensajes_standby: dict[int, list[str]] = {}

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

# Lock asyncio por chat para serializar mensajes del mismo chat
# Evita race conditions cuando dos mensajes llegan casi simultaneamente
_chat_locks: dict[int, asyncio.Lock] = {}
_chat_locks_meta = threading.Lock()

def get_chat_lock(chat_id: int) -> asyncio.Lock:
    """Retorna el lock asyncio para un chat, creandolo si no existe."""
    with _chat_locks_meta:
        if chat_id not in _chat_locks:
            _chat_locks[chat_id] = asyncio.Lock()
        return _chat_locks[chat_id]


def _precio_es_total_fraccion(nombre_producto: str, precio: float, cantidad: float) -> bool:
    """
    Retorna True si el precio ya corresponde al precio de esa fraccion en el catalogo.
    En ese caso el total = precio (no multiplicar por cantidad).

    Para productos con precios_fraccion, Claude manda el precio de la fraccion
    (ej: 26000 para 1/2 galon de vinilo T1), no el precio por galon completo.
    Multiplicar daria un total incorrecto (26000 x 0.5 = 13000 en lugar de 26000).
    """
    if es_thinner(nombre_producto):
        return True  # Thinner siempre maneja precio como total

    try:
        catalogo = cargar_memoria().get("catalogo", {})
        nombre_lower = nombre_producto.lower()
        # Buscar el producto en el catalogo (coincidencia parcial)
        for prod in catalogo.values():
            prod_lower = prod.get("nombre_lower", "")
            if not prod_lower:
                continue
            # Coincidencia: el nombre del producto contiene el del catalogo o viceversa
            if prod_lower in nombre_lower or nombre_lower in prod_lower:
                precios_fraccion = prod.get("precios_fraccion", {})
                if not precios_fraccion:
                    break
                # Verificar si el precio coincide con el precio de alguna fraccion
                precio_int = int(round(precio))
                for frac_data in precios_fraccion.values():
                    if int(round(frac_data.get("precio", 0))) == precio_int:
                        return True  # El precio ya es el total de esa fraccion
                break
    except Exception as e:
        print(f"[PRECIO_FRACCION] error buscando en catalogo: {e}")

    return False


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
    # Limpiar estado pendiente ANTES de registrar para que nuevas ventas
    # no queden bloqueadas mientras se procesa esta.
    with _estado_lock:
        ventas_pendientes.pop(chat_id, None)

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

        # ── Correccion especial thinner: cantidad se deriva del precio ──
        if es_thinner(producto):
            cantidad_esperada, _ = cantidad_thinner_por_precio(precio_cobrado)
            if cantidad_esperada > 0 and abs(cantidad - cantidad_esperada) > 0.05:
                print(f"[THINNER] corrigiendo cantidad {cantidad:.4f} → {cantidad_esperada:.6g} para precio ${precio_cobrado:,.0f}")
                cantidad = cantidad_esperada

        # ── Calcular total ──
        # Para productos con precios_fraccion (pinturas, thinner, etc.),
        # Claude manda el precio de la fraccion como precio_unitario — ese ya ES el total.
        # Para el resto, total = precio_unitario × cantidad.
        if _precio_es_total_fraccion(producto, precio_cobrado, cantidad):
            total = round(precio_cobrado)
        else:
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
