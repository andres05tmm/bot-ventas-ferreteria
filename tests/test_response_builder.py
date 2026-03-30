"""
tests/test_response_builder.py — Tests básicos para ai/response_builder.py.

Cubre:
  - Texto sin tags → retorna sin modificar
  - Tag [VENTA] → consumido del texto limpio
  - JSON malformado → no lanza excepción
"""
import sys
import types
import threading

# -- Stubs al tope, antes de cualquier import propio --

for _mod, _attrs in [
    ("config", {
        "COLOMBIA_TZ": None,
        "claude_client": None,
        "openai_client": None,
        "DB_DISPONIBLE": True,
    }),
    ("db", {
        "DB_DISPONIBLE": False,
        "ejecutar_query": lambda *a, **kw: None,
        "obtener_conexion": lambda: None,
    }),
    ("memoria", {
        "cargar_memoria": lambda: {},
        "guardar_memoria": lambda x: None,
        "buscar_producto_en_catalogo": lambda x: None,
        "actualizar_precio_en_catalogo": lambda *a: None,
        "invalidar_cache_memoria": lambda: None,
        "cargar_caja": lambda: {},
        "obtener_resumen_caja": lambda: {},
        "guardar_gasto": lambda *a, **kw: None,
        "guardar_fiado_movimiento": lambda *a, **kw: None,
        "abonar_fiado": lambda *a, **kw: None,
        "cargar_inventario": lambda: [],
    }),
    ("ventas_state", {
        "ventas_pendientes": {},
        "_estado_lock": threading.Lock(),
        "registrar_ventas_con_metodo": lambda *a, **kw: [],
        "mensajes_standby": {},
        "limpiar_pendientes_expirados": lambda: None,
        "_guardar_pendiente": lambda *a: None,
    }),
    ("ai.price_cache", {
        "registrar": lambda *a: None,
    }),
    ("ai.excel_gen", {
        "generar_excel_personalizado": lambda *a, **kw: None,
    }),
    ("utils", {
        "convertir_fraccion_a_decimal": lambda x: float(x) if x else 0.0,
        "decimal_a_fraccion_legible": lambda x: str(x),
        "_normalizar": lambda x: (x or "").lower().strip(),
    }),
]:
    if _mod not in sys.modules:
        _m = types.ModuleType(_mod)
        for _k, _v in _attrs.items():
            setattr(_m, _k, _v)
        sys.modules[_mod] = _m
    else:
        # Add only missing attributes — don't overwrite what other tests set
        _m = sys.modules[_mod]
        for _k, _v in _attrs.items():
            if not hasattr(_m, _k):
                setattr(_m, _k, _v)

# Stub ai package so lazy `from ai import _pg_*` works
if "ai" not in sys.modules:
    _ai_pkg = types.ModuleType("ai")
    _ai_pkg._pg_buscar_cliente = lambda *a, **kw: None
    _ai_pkg._pg_guardar_cliente = lambda *a, **kw: None
    _ai_pkg._pg_borrar_cliente = lambda *a, **kw: None
    sys.modules["ai"] = _ai_pkg
else:
    # Ensure _pg_* stubs exist on already-loaded ai module
    _ai_pkg = sys.modules["ai"]
    for _fn in ("_pg_buscar_cliente", "_pg_guardar_cliente", "_pg_borrar_cliente"):
        if not hasattr(_ai_pkg, _fn):
            setattr(_ai_pkg, _fn, lambda *a, **kw: None)

from ai.response_builder import procesar_acciones  # noqa: E402


def test_procesar_acciones_texto_limpio():
    """Sin tags de acción → retorna texto sin modificar, listas vacías."""
    texto, ventas, excels = procesar_acciones("Hola, ¿en qué puedo ayudarte?", "Juan", 123)
    assert texto == "Hola, ¿en qué puedo ayudarte?"
    assert ventas == []
    assert excels == []


def test_procesar_acciones_extrae_venta():
    """Tag [VENTA] bien formado → se extrae de texto_limpio."""
    entrada = 'Te registré la venta. [VENTA]{"producto":"Tornillo","cantidad":10,"total":5000}[/VENTA]'
    texto, ventas, excels = procesar_acciones(entrada, "Juan", 456)
    assert "[VENTA]" not in texto
    assert isinstance(ventas, list)


def test_procesar_acciones_json_malformado_no_explota():
    """JSON corrupto dentro de [VENTA] → no lanza excepción, retorna texto."""
    entrada = "Venta registrada [VENTA]{malformado[/VENTA]"
    texto, ventas, excels = procesar_acciones(entrada, "Juan", 789)
    assert isinstance(texto, str)
    assert isinstance(ventas, list)
    assert isinstance(excels, list)


def test_procesar_acciones_multiples_tags():
    """Múltiples tags → todos consumidos del texto, sin error."""
    entrada = (
        "Listo. [VENTA]{\"producto\":\"Clavo\",\"cantidad\":5,\"total\":2000}[/VENTA] "
        "[EXCEL]reporte_diario[/EXCEL]"
    )
    texto, ventas, excels = procesar_acciones(entrada, "Pedro", 999)
    assert "[VENTA]" not in texto
    assert "[EXCEL]" not in texto
    assert isinstance(ventas, list)
    assert isinstance(excels, list)
