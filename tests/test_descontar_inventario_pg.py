"""
tests/test_descontar_inventario_pg.py — Tests del descuento transaccional.

Cubre la nueva función descontar_inventario_pg que opera con un cursor
recibido (atomicidad con la venta).

No requiere DATABASE_URL — usa un cursor mock que registra ejecuciones
y devuelve filas configurables.
"""

# -- stdlib --
import sys
import types
from unittest.mock import MagicMock, patch

# ── Stubs ─────────────────────────────────────────────────────────────────────
# Solo stubeamos config porque services.inventario_service lo importa
# transitivamente. NO stubeamos db — la función bajo test recibe el cursor
# como parámetro y no usa el módulo db, y stubear `db` rompería otros tests
# que sí lo usan (test_consecutivo_atomico).
if "config" not in sys.modules:
    sys.modules["config"] = types.ModuleType("config")


def _cursor(rows):
    """Cursor mock que devuelve filas configuradas en orden FIFO."""
    cur = MagicMock()
    cur.queries = []
    cur._rows = list(rows)

    def _execute(sql, params=None):
        cur.queries.append((sql, params))

    def _fetchone():
        return cur._rows.pop(0) if cur._rows else None

    cur.execute = _execute
    cur.fetchone = _fetchone
    return cur


def test_devuelve_false_cuando_no_hay_clave_en_inventario():
    """Si buscar_clave_inventario retorna None, no se ejecuta SQL."""
    from services.inventario_service import descontar_inventario_pg

    cur = _cursor([])
    with patch("services.inventario_service.cargar_inventario", return_value={}), \
         patch("services.inventario_service.buscar_clave_inventario", return_value=None):
        ok, alerta, cant = descontar_inventario_pg(cur, "producto_inexistente", 5.0)

    assert ok is False
    assert alerta is None
    assert cant is None
    assert cur.queries == []  # no se ejecutó ninguna query


def test_devuelve_false_cuando_producto_no_existe_en_tabla():
    """Si productos.clave no encuentra match, retorna (False, None, None)."""
    from services.inventario_service import descontar_inventario_pg

    cur = _cursor([None])  # SELECT productos.id devuelve None
    with patch("services.inventario_service.cargar_inventario", return_value={}), \
         patch("services.inventario_service.buscar_clave_inventario", return_value="martillo"):
        ok, alerta, cant = descontar_inventario_pg(cur, "martillo", 1.0)

    assert ok is False
    assert alerta is None
    assert cant is None


def test_descuento_exitoso_genera_update_con_for_update():
    """Descuento normal: SELECT FOR UPDATE + UPDATE inventario."""
    from services.inventario_service import descontar_inventario_pg

    # fetchone() devuelve en orden:
    #   1. {"id": 42} para SELECT id FROM productos
    #   2. {"cantidad": 10, "minimo": 3, "unidad": "und", "nombre_original": "Martillo"}
    rows = [
        {"id": 42},
        {"cantidad": 10.0, "minimo": 3.0, "unidad": "und", "nombre_original": "Martillo"},
    ]
    cur = _cursor(rows)
    with patch("services.inventario_service.cargar_inventario", return_value={}), \
         patch("services.inventario_service.buscar_clave_inventario", return_value="martillo"):
        ok, alerta, cant = descontar_inventario_pg(cur, "martillo", 2.0)

    assert ok is True
    assert alerta is None  # 10-2=8 > minimo 3
    assert cant == 8.0

    # Verificar que se emitió SELECT … FOR UPDATE
    sqls = [q[0] for q in cur.queries]
    assert any("FOR UPDATE" in s for s in sqls)
    # Y que el UPDATE incluye cantidad
    assert any(
        "UPDATE inventario" in s and "cantidad = %s" in s and "ultima_venta" in s
        for s in sqls
    )


def test_descuento_genera_alerta_stock_bajo():
    """Cuando cantidad_nueva <= minimo, se genera mensaje de alerta."""
    from services.inventario_service import descontar_inventario_pg

    rows = [
        {"id": 1},
        {"cantidad": 5.0, "minimo": 3.0, "unidad": "und", "nombre_original": "Tornillo"},
    ]
    cur = _cursor(rows)
    with patch("services.inventario_service.cargar_inventario", return_value={}), \
         patch("services.inventario_service.buscar_clave_inventario", return_value="tornillo"):
        ok, alerta, cant = descontar_inventario_pg(cur, "tornillo", 3.0)

    assert ok is True
    assert cant == 2.0
    assert alerta is not None
    assert "Stock bajo" in alerta
    assert "Tornillo" in alerta


def test_descuento_no_va_debajo_de_cero():
    """max(0, ...) impide que el stock baje a negativo."""
    from services.inventario_service import descontar_inventario_pg

    rows = [
        {"id": 1},
        {"cantidad": 2.0, "minimo": 0, "unidad": "und", "nombre_original": "X"},
    ]
    cur = _cursor(rows)
    with patch("services.inventario_service.cargar_inventario", return_value={}), \
         patch("services.inventario_service.buscar_clave_inventario", return_value="x"):
        ok, _, cant = descontar_inventario_pg(cur, "x", 10.0)

    assert ok is True
    assert cant == 0.0  # no negativo
