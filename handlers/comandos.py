# handlers/comandos.py — hub de re-exportacion (no borrar este archivo)
# main.py importa todo desde aqui — no debe cambiar.

from handlers.cmd_ventas import (
    comando_inicio, comando_ventas, comando_borrar,
    comando_pendientes, comando_grafica, manejar_callback_grafica,
    comando_cerrar_dia, comando_reset_ventas,
)
from handlers.cmd_inventario import (
    comando_buscar, comando_precios, comando_inventario, comando_inv,
    comando_stock, comando_ajuste, comando_compra, comando_margenes,
    comando_agregar_producto, comando_actualizar_precio,
    comando_actualizar_catalogo,
    manejar_flujo_agregar_producto, manejar_mensaje_precio,
)
from handlers.cmd_clientes import (
    comando_clientes, comando_nuevo_cliente, comando_fiados, comando_abono,
)
from handlers.cmd_caja import (
    comando_caja, comando_gastos, comando_dashboard,
)
from handlers.cmd_proveedores import (
    upload_foto_cloudinary,
    comando_factura, comando_abonar, comando_deudas,
    comando_facturas, comando_borrar_factura,
)
from handlers.cmd_admin import (
    comando_consistencia, comando_exportar_precios,
    comando_keepalive, comando_modelo,
)
from handlers.cmd_auth import (
    comando_confirmar, comando_registrar_vendedor,
)

__all__ = [
    "comando_inicio", "comando_ventas", "comando_borrar",
    "comando_pendientes", "comando_grafica", "manejar_callback_grafica",
    "comando_cerrar_dia", "comando_reset_ventas",
    "comando_buscar", "comando_precios", "comando_inventario", "comando_inv",
    "comando_stock", "comando_ajuste", "comando_compra", "comando_margenes",
    "comando_agregar_producto", "comando_actualizar_precio",
    "comando_actualizar_catalogo",
    "manejar_flujo_agregar_producto", "manejar_mensaje_precio",
    "comando_clientes", "comando_nuevo_cliente", "comando_fiados", "comando_abono",
    "comando_caja", "comando_gastos", "comando_dashboard",
    "upload_foto_cloudinary",
    "comando_factura", "comando_abonar", "comando_deudas",
    "comando_facturas", "comando_borrar_factura",
    "comando_consistencia", "comando_exportar_precios",
    "comando_keepalive", "comando_modelo",
    "comando_confirmar", "comando_registrar_vendedor",
]
