"""
Estado en memoria para ventas pendientes de confirmacion y borrados pendientes.
Protegido con threading.Lock para evitar race conditions en el event loop async.
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

        # ── LOGICA DE PRECIO BLINDADA ──
        # Claude a veces manda precios como string ("$4,000" o "4.000")
        # Esta funcion limpia cualquier formato antes de convertir a float
        def _parsear_precio(clave):
            val = venta.get(clave, 0)
            if isinstance(val, str):
                val = val.replace("$", "").replace(",", "").replace(".", "").strip()
                # Si tenia punto decimal real (ej: "4000.5"), restaurarlo
                try:
                    return float(val)
                except:
                    return 0.0
            try:
                return float(val)
            except:
                return 0.0

        total                   = _parsear_precio("total")
        precio_unitario_enviado = _parsear_precio("precio_unitario")

        if total > 0:
            # Si la cantidad es mayor a 1 y el total parece ser solo el precio unitario,
            # multiplicar. Detectamos esto si total < precio_catalogo * cantidad.
            # Caso simple: si cantidad entera > 1 y total = precio de 1 unidad, multiplicar.
            if cantidad > 1.0 and precio_unitario_enviado > 0 and abs(total - precio_unitario_enviado) < 1:
                valor_final = round(precio_unitario_enviado * cantidad)
            elif cantidad > 1.0 and precio_unitario_enviado == 0:
                # Solo tenemos total — verificar si parece precio unitario buscando en catálogo
                valor_final = total  # confiamos en Claude por ahora
            else:
                valor_final = total
        elif precio_unitario_enviado > 0:
            valor_final = round(precio_unitario_enviado * cantidad)
        else:
            valor_final = 0

        total_transaccion += valor_final
        cantidad_legible   = decimal_a_fraccion_legible(cantidad)

        # Unitario para el Excel (registro contable)
        precio_u_excel = valor_final / cantidad if cantidad > 0 else valor_final

        guardar_venta_excel(
            producto, cantidad, precio_u_excel, valor_final, vendedor, metodo,
            cliente_nombre=nombre_c, cliente_id=id_c,
            consecutivo=consecutivo,
        )

        cliente_txt = f" | {nombre_c}" if nombre_c != "Consumidor Final" else ""
        # Orden: Cantidad + Producto + Valor
        confirmaciones.append(f"• {cantidad_legible} {producto} ${valor_final:,.0f}{cliente_txt}")

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
        campo = {"efectivo": "efectivo", "transferencia": "transferencias", "datafono": "datafono"}.get(metodo, "efectivo")
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
