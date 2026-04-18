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
import pytest

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
        # Paso 4 — carrito conversacional de audio
        "append_a_pendiente": lambda *a: None,
        "origen_carrito": lambda *a: "",
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

# Stub ai package so lazy `from ai import _pg_*` works.
# IMPORTANTE: el stub debe tener __path__ apuntando al directorio real del
# paquete para que Python pueda resolver `from ai.response_builder import X`
# (si no, falla con "ai is not a package" durante collection).
import os as _os  # noqa: E402
_AI_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "ai",
)
if "ai" not in sys.modules:
    _ai_pkg = types.ModuleType("ai")
    _ai_pkg.__path__ = [_AI_DIR]
    _ai_pkg._pg_buscar_cliente = lambda *a, **kw: None
    _ai_pkg._pg_guardar_cliente = lambda *a, **kw: None
    _ai_pkg._pg_borrar_cliente = lambda *a, **kw: None
    sys.modules["ai"] = _ai_pkg
else:
    # Ensure _pg_* stubs and __path__ exist on already-loaded ai module
    _ai_pkg = sys.modules["ai"]
    if not hasattr(_ai_pkg, "__path__"):
        _ai_pkg.__path__ = [_AI_DIR]
    for _fn in ("_pg_buscar_cliente", "_pg_guardar_cliente", "_pg_borrar_cliente"):
        if not hasattr(_ai_pkg, _fn):
            setattr(_ai_pkg, _fn, lambda *a, **kw: None)

# ─────────────────────────────────────────────────────────────────────────
# Stub del servicio de búsqueda (Paso 5) — evita golpear Postgres
# IMPORTANTE: debe ir ANTES de `from ai.response_builder` para que el lazy
# `from services.search_service import ...` dentro del handler resuelva al
# stub y no al módulo real (que tocaría Postgres).
# ─────────────────────────────────────────────────────────────────────────
if "services" not in sys.modules:
    _services_pkg = types.ModuleType("services")
    _services_pkg.__path__ = []
    sys.modules["services"] = _services_pkg

# Forzar reemplazo aunque ya esté cargado el real (otro test pudo importarlo)
_search_stub = types.ModuleType("services.search_service")
_search_stub.buscar_conversaciones = lambda *a, **kw: [
    {"id": 1, "role": "user", "content": "stub conv",
     "creado": None}
]
_search_stub.buscar_ventas_por_producto = lambda *a, **kw: [
    {"venta_id": 1, "consecutivo": 10,
     "fecha": None, "cliente_nombre": "Pedro",
     "vendedor": "andres", "producto_nombre": "Drywall",
     "cantidad": 3, "unidad_medida": "u", "linea_total": 15000}
]
_search_stub.buscar_ventas_por_cliente = lambda *a, **kw: []
_search_stub.formatear_resultados_ventas = lambda filas: (
    f"VENTAS_FMT:{len(filas)}"
)
_search_stub.formatear_resultados_conversaciones = lambda filas: (
    f"CONV_FMT:{len(filas)}"
)
sys.modules["services.search_service"] = _search_stub

from ai.response_builder import procesar_acciones  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# Autouse fixture — reinstala el stub de services.search_service ANTES de
# cada test. Pytest puede haber descargado el stub durante la collection
# de otros archivos (ej. test_search_service.py hace sys.modules.pop()
# para acceder al módulo real). Sin esto, los tests de [BUSCAR_HISTORICO]
# fallarían porque el lazy `from services.search_service import ...` dentro
# del handler resolvería al módulo real (que requiere Postgres).
# ─────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reinstall_search_stub():
    sys.modules["services.search_service"] = _search_stub
    yield


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


def test_procesar_acciones_buscar_historico_ventas_producto():
    """Tag [BUSCAR_HISTORICO] con tipo=ventas_producto → reemplazado por listado."""
    entrada = (
        'Mirá las ventas de drywall:\n'
        '[BUSCAR_HISTORICO]{"tipo":"ventas_producto","query":"drywall","dias":30}'
        '[/BUSCAR_HISTORICO]'
    )
    texto, acciones, _ = procesar_acciones(entrada, "Pedro", 123)
    assert "[BUSCAR_HISTORICO]" not in texto
    assert "VENTAS_FMT:1" in texto  # stub devolvió 1 fila
    # La acción se registra para métricas
    assert any(a.startswith("BUSQUEDA:ventas_producto") for a in acciones)


def test_procesar_acciones_buscar_historico_conversaciones():
    """Tag [BUSCAR_HISTORICO] con tipo=conversaciones → usa formateador de chats."""
    entrada = (
        'Acá lo que hablamos:\n'
        '[BUSCAR_HISTORICO]{"tipo":"conversaciones","query":"fiado"}'
        '[/BUSCAR_HISTORICO]'
    )
    texto, acciones, _ = procesar_acciones(entrada, "Juan", 456)
    assert "[BUSCAR_HISTORICO]" not in texto
    assert "CONV_FMT:1" in texto
    assert any(a.startswith("BUSQUEDA:conversaciones") for a in acciones)


def test_procesar_acciones_buscar_historico_json_malformado():
    """JSON malformado dentro del tag → no revienta, muestra mensaje benigno."""
    entrada = 'Buscando [BUSCAR_HISTORICO]{malformado[/BUSCAR_HISTORICO]'
    texto, _, _ = procesar_acciones(entrada, "Pedro", 789)
    assert "[BUSCAR_HISTORICO]" not in texto
    assert "no pude" in texto.lower() or "desconocido" in texto.lower()


def test_procesar_acciones_buscar_historico_tipo_desconocido():
    """Tipo no soportado → mensaje de error inline sin explotar."""
    entrada = (
        '[BUSCAR_HISTORICO]{"tipo":"inventario_magico","query":"x"}'
        '[/BUSCAR_HISTORICO]'
    )
    texto, _, _ = procesar_acciones(entrada, "Pedro", 321)
    assert "[BUSCAR_HISTORICO]" not in texto
    assert "desconocido" in texto.lower()


def test_procesar_acciones_audio_origen_append():
    """
    Cuando origen_carrito=='audio' y ya hay pendientes, las ventas nuevas
    deben APENDARSE al carrito (no reemplazar) y debe aparecer la acción
    CARRITO_AUDIO_ACUMULANDO si no hay método declarado.
    """
    import ventas_state as _vs

    chat_id = 31337

    # Guardar refs originales para restaurar al final (evita pollution de otros tests)
    _orig_append = getattr(_vs, "append_a_pendiente", None)
    _orig_origen = getattr(_vs, "origen_carrito", None)
    _orig_carrito_origen = getattr(_vs, "_carrito_origen", None)
    _orig_ventas = getattr(_vs, "ventas_pendientes", None)

    try:
        # Fijar origen='audio' y un pendiente previo de 1 ítem
        _vs._carrito_origen = {chat_id: "audio"}
        _vs.origen_carrito = lambda c: _vs._carrito_origen.get(c, "")
        _vs.ventas_pendientes = {chat_id: [{"producto": "clavo", "cantidad": 3}]}

        capturas = []
        def _append_fake(cid, nuevas):
            if not nuevas:
                return
            _vs.ventas_pendientes.setdefault(cid, []).extend(nuevas)
            capturas.append(("append", cid, len(nuevas)))
        _vs.append_a_pendiente = _append_fake

        entrada = (
            'Va. [VENTA]{"producto":"Martillo","cantidad":1,"total":15000}[/VENTA]'
        )
        _, acciones, _ = procesar_acciones(entrada, "Pedro", chat_id)

        # Nueva venta se agregó (append), carrito ahora tiene 2 ítems
        assert len(_vs.ventas_pendientes[chat_id]) == 2
        # Se disparó acción de acumulación (no PEDIR_METODO_PAGO, no aviso)
        assert "CARRITO_AUDIO_ACUMULANDO" in acciones
        assert "PEDIR_METODO_PAGO" not in acciones
        assert "PAGO_PENDIENTE_AVISO" not in acciones
    finally:
        # Restaurar estado original para no contaminar otros tests
        if _orig_append is not None:
            _vs.append_a_pendiente = _orig_append
        if _orig_origen is not None:
            _vs.origen_carrito = _orig_origen
        if _orig_carrito_origen is not None:
            _vs._carrito_origen = _orig_carrito_origen
        elif hasattr(_vs, "_carrito_origen"):
            delattr(_vs, "_carrito_origen")
        if _orig_ventas is not None:
            _vs.ventas_pendientes = _orig_ventas
