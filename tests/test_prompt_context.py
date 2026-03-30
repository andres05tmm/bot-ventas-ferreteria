"""
tests/test_prompt_context.py — Tests basicos para ai/prompt_context.py y ai/prompt_products.py.
"""
import os
import sys
import types

_noop = lambda *a, **kw: None
_empty = lambda *a, **kw: []
_empty_dict = lambda *a, **kw: {}

for mod, attrs in [
    ("config", {"COLOMBIA_TZ": None, "claude_client": None, "AUTHORIZED_CHAT_IDS": [], "ADMIN_CHAT_ID": None}),
    ("db", {
        "DB_DISPONIBLE": False,
        "execute": _noop,
        "query_one": _noop,
        "query_all": _empty,
    }),
    ("memoria", {
        "cargar_memoria": _empty_dict,
        "guardar_memoria": _noop,
        "invalidar_cache_memoria": _noop,
        "cargar_inventario": _empty_dict,
        "cargar_caja": _empty_dict,
        "cargar_gastos_hoy": _empty,
        "obtener_resumen_caja": lambda: "",
        "guardar_gasto": _noop,
        "guardar_fiado_movimiento": _noop,
        "abonar_fiado": _noop,
        "actualizar_precio_en_catalogo": _noop,
        "buscar_producto_en_catalogo": _noop,
        "buscar_multiples_en_catalogo": _empty,
        "buscar_multiples_con_alias": _empty,
        "obtener_precios_como_texto": lambda: "",
        "obtener_info_fraccion_producto": _noop,
        "listar_facturas": lambda **kw: [],
    }),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items(): setattr(m, k, v)
        sys.modules[mod] = m
    else:
        m = sys.modules[mod]
        for k, v in attrs.items():
            if not hasattr(m, k): setattr(m, k, v)

# Stub ai con los helpers que prompt_context y prompt_products importan lazy
if "ai" not in sys.modules:
    _ai = types.ModuleType("ai")
    _ai.__path__ = [os.path.abspath("ai")]
    _ai.__package__ = "ai"
    _ai._pg_resumen_ventas = lambda: None
    _ai._pg_todos_los_datos = lambda limite=300: []
    _ai._pg_clientes_recientes = lambda limite=5: []
    _ai._pg_buscar_cliente = lambda termino: (None, [])
    _ai._get_precios_recientes_activos = lambda: {}
    sys.modules["ai"] = _ai
else:
    _ai = sys.modules["ai"]
    for _k, _v in [
        ("_pg_resumen_ventas", lambda: None),
        ("_pg_todos_los_datos", lambda limite=300: []),
        ("_pg_clientes_recientes", lambda limite=5: []),
        ("_pg_buscar_cliente", lambda termino: (None, [])),
        ("_get_precios_recientes_activos", lambda: {}),
    ]:
        if not hasattr(_ai, _k): setattr(_ai, _k, _v)


def test_construir_seccion_ventas_sin_db():
    """Sin DB → retorna tupla de strings sin explotar."""
    from ai.prompt_context import construir_seccion_ventas
    resumen, datos = construir_seccion_ventas("vender pintura")
    assert isinstance(resumen, str)
    assert isinstance(datos, str)


def test_construir_seccion_ventas_dashboard_mode():
    """dashboard_mode=True no explota."""
    from ai.prompt_context import construir_seccion_ventas
    resumen, datos = construir_seccion_ventas("cuanto vendimos hoy", dashboard_mode=True)
    assert isinstance(resumen, str)
    assert isinstance(datos, str)


def test_construir_seccion_operaciones_sin_db():
    """Sin DB y mensaje sin keywords → retorna string (puede estar vacio)."""
    from ai.prompt_context import construir_seccion_operaciones
    resultado = construir_seccion_operaciones("vender pintura")
    assert isinstance(resultado, str)


def test_construir_seccion_operaciones_con_keyword():
    """Mensaje con keyword 'inventario' → no explota aunque DB no disponible."""
    from ai.prompt_context import construir_seccion_operaciones
    resultado = construir_seccion_operaciones("cuanto inventario hay")
    assert isinstance(resultado, str)


def test_construir_seccion_clientes_mensaje_vacio():
    """Mensaje vacio → no explota."""
    from ai.prompt_context import construir_seccion_clientes
    resultado = construir_seccion_clientes("")
    assert isinstance(resultado, str)


def test_construir_seccion_clientes_con_termino():
    """Mensaje con nombre → no explota aunque no haya resultados."""
    from ai.prompt_context import construir_seccion_clientes
    resultado = construir_seccion_clientes("vender para juan perez")
    assert isinstance(resultado, str)


def test_construir_seccion_match_catalogo_vacio():
    """Catalogo vacio en memoria → retorna string (puede ser vacio)."""
    from ai.prompt_products import construir_seccion_match
    resultado = construir_seccion_match("quiero tornillos", "vendedor", {})
    assert isinstance(resultado, str)


def test_construir_precalculos_especiales_sin_mensaje():
    """Mensaje vacio → no explota."""
    from ai.prompt_products import construir_precalculos_especiales
    resultado = construir_precalculos_especiales("", {})
    assert isinstance(resultado, str)


def test_construir_parte_dinamica_orquesta():
    """El orquestador ensambla partes sin error."""
    from ai.prompts import _construir_parte_dinamica
    resultado = _construir_parte_dinamica("vender tornillos", "vendedor", {})
    assert isinstance(resultado, str)
