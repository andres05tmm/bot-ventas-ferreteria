"""
tests/test_cmd_inventario.py — Tests para handlers/cmd_inventario.py.

Cubre: _resolver_grm, _texto_categoria_prompt,
       manejar_flujo_agregar_producto, comando_buscar, _mostrar_confirmacion.

Patrón: stubs en sys.modules ANTES de cualquier import propio.
Async: asyncio.run() (patrón del proyecto — no requiere asyncio_mode=auto).
"""
import sys
import types
import threading
import asyncio

# ── Stubs ANTES de cualquier import propio ────────────────────────────────────


def _passthrough(func):
    """Stub del decorador @protegido — deja pasar sin auth."""
    return func


import os as _os
_middleware_stub = types.ModuleType("middleware")
_middleware_stub.protegido = _passthrough
# __path__ lo convierte en paquete, así middleware.auth puede resolverse normalmente
_middleware_stub.__path__ = [_os.path.abspath("middleware")]
_middleware_stub.__package__ = "middleware"
# Solo se registra el paquete — NO middleware.auth, para no interferir con test_middleware.py
sys.modules.setdefault("middleware", _middleware_stub)

for mod, attrs in [
    ("config", {
        "COLOMBIA_TZ": None,
        "claude_client": None,
        "openai_client": None,
    }),
    ("db", {
        "DB_DISPONIBLE": False,
        "query_one": lambda *a, **kw: None,
        "query_all": lambda *a, **kw: [],
        "execute": lambda *a, **kw: None,
        "obtener_siguiente_consecutivo": lambda *a, **kw: 1,
        "obtener_nombre_id_cliente": lambda *a, **kw: None,
    }),
    ("memoria", {
        "cargar_memoria": lambda: {"catalogo": {}, "inventario": {}},
        "invalidar_cache_memoria": lambda: None,
        "buscar_producto_en_catalogo": lambda x: None,
        "actualizar_precio_en_catalogo": lambda *a, **kw: None,
        "cargar_inventario": lambda: {},
        "guardar_inventario": lambda *a, **kw: None,
        "cargar_caja": lambda: {},
        "guardar_caja": lambda *a, **kw: None,
        "descontar_inventario": lambda *a, **kw: None,
        "buscar_produtos_inventario": lambda *a, **kw: [],
        "buscar_productos_inventario": lambda *a, **kw: [],
        "ajustar_inventario": lambda *a, **kw: None,
        "registrar_conteo_inventario": lambda *a, **kw: None,
        "registrar_compra": lambda *a, **kw: None,
        "obtener_resumen_margenes": lambda *a, **kw: {},
        "_es_producto_con_fracciones": lambda x: False,
        "_es_tornillo_drywall": lambda x: False,
        "guardar_memoria": lambda *a, **kw: None,
    }),
    ("ventas_state", {
        "ventas_pendientes": {},
        "clientes_en_proceso": {},
        "esperando_correccion": {},
        "mensajes_standby": {},
        "_estado_lock": threading.Lock(),
        "_guardar_pendiente": lambda *a: None,
        "limpiar_pendientes_expirados": lambda: None,
        "registrar_ventas_con_metodo": lambda *a, **kw: [],
        "get_chat_lock": lambda cid: asyncio.Lock(),
    }),
    ("utils", {
        "convertir_fraccion_a_decimal": lambda x: float(x) if x else 0.0,
        "decimal_a_fraccion_legible": lambda x: str(x),
        "es_thinner": lambda x: False,
        "parsear_precio": lambda x: float(x) if x else 0.0,
        "_normalizar": lambda x: (x or "").lower().strip(),
    }),
    ("alias_manager", {
        "aplicar_alias_ferreteria": lambda x: x,
        "normalizar_nombre": lambda x: x,
    }),
    ("fuzzy_match", {
        "buscar_fuzzy": lambda *a, **kw: [],
    }),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[mod] = m
    else:
        m = sys.modules[mod]
        for k, v in attrs.items():
            if not hasattr(m, k):
                setattr(m, k, v)

# Stub ai package
if "ai" not in sys.modules:
    import os as _os
    _ai = types.ModuleType("ai")
    _ai.__path__ = [_os.path.abspath("ai")]
    _ai.__package__ = "ai"
    _ai.procesar_con_claude = lambda *a, **kw: ""
    sys.modules["ai"] = _ai

import pytest


# ── Tests de _resolver_grm ────────────────────────────────────────────────────

def test_resolver_grm_producto_sin_grm_retorna_tuple():
    """Producto que no es GRM → retorna (nombre, cantidad, label) con los valores originales."""
    from handlers.cmd_inventario import _resolver_grm
    nombre, cantidad, label = _resolver_grm("tornillo punta broca", 10, False)
    assert nombre == "tornillo punta broca"
    assert cantidad == 10
    assert label == "10"


def test_resolver_grm_nombre_vacio_no_explota():
    """Nombre vacío → no explota, retorna tuple con valores originales."""
    from handlers.cmd_inventario import _resolver_grm
    nombre, cantidad, label = _resolver_grm("", 5, False)
    assert nombre == ""
    assert cantidad == 5


def test_resolver_grm_fraccion_cantidad():
    """Cantidad fraccionaria → label como string del número."""
    from handlers.cmd_inventario import _resolver_grm
    nombre, cantidad, label = _resolver_grm("clavo", 2.5, False)
    assert nombre == "clavo"
    assert cantidad == 2.5
    assert "2.5" in label


# ── Tests de _texto_categoria_prompt ─────────────────────────────────────────

def test_texto_categoria_prompt_retorna_string():
    """Siempre retorna un string no vacío con instrucciones para el usuario."""
    from handlers.cmd_inventario import _texto_categoria_prompt
    resultado = _texto_categoria_prompt("Tornillo punta broca 6x1")
    assert isinstance(resultado, str)
    assert len(resultado) > 0


def test_texto_categoria_prompt_nombre_vacio():
    """Nombre vacío → no explota."""
    from handlers.cmd_inventario import _texto_categoria_prompt
    resultado = _texto_categoria_prompt("")
    assert isinstance(resultado, str)


def test_texto_categoria_prompt_contiene_opciones():
    """El prompt incluye algún número de categoría para guiar al usuario."""
    from handlers.cmd_inventario import _texto_categoria_prompt
    resultado = _texto_categoria_prompt("pintura blanca")
    # Debe contener al menos un dígito (opciones de categoría)
    assert any(c.isdigit() for c in resultado)


# ── Tests de manejar_flujo_agregar_producto ───────────────────────────────────

def test_manejar_flujo_sin_estado(mocker):
    """Sin 'paso_producto' en user_data → retorna False inmediatamente (no es flujo activo)."""
    from handlers.cmd_inventario import manejar_flujo_agregar_producto
    update = mocker.MagicMock()
    context = mocker.MagicMock()
    context.user_data = {}
    resultado = asyncio.run(manejar_flujo_agregar_producto(update, context))
    assert resultado is False


def test_manejar_flujo_cancelar(mocker):
    """Texto 'cancelar' con flujo activo → retorna True y limpia el estado."""
    from handlers.cmd_inventario import manejar_flujo_agregar_producto
    update = mocker.MagicMock()
    update.message.text = "cancelar"
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.user_data = {"paso_producto": "nombre", "nuevo_producto": {}}
    resultado = asyncio.run(manejar_flujo_agregar_producto(update, context))
    assert resultado is True
    assert "paso_producto" not in context.user_data


def test_manejar_flujo_paso_nombre_corto(mocker):
    """Nombre de 1 carácter → responde con error y retorna True."""
    from handlers.cmd_inventario import manejar_flujo_agregar_producto
    update = mocker.MagicMock()
    update.message.text = "A"
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.user_data = {"paso_producto": "nombre"}
    resultado = asyncio.run(manejar_flujo_agregar_producto(update, context))
    assert resultado is True
    update.message.reply_text.assert_called_once()


def test_manejar_flujo_paso_nombre_valido(mocker):
    """Nombre válido (≥2 chars) → avanza al paso 'codigo' y retorna True."""
    from handlers.cmd_inventario import manejar_flujo_agregar_producto
    update = mocker.MagicMock()
    update.message.text = "Tornillo 6x1 punta broca"
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.user_data = {"paso_producto": "nombre"}
    resultado = asyncio.run(manejar_flujo_agregar_producto(update, context))
    assert resultado is True
    assert context.user_data.get("paso_producto") == "codigo"


# ── Tests de comando_buscar ───────────────────────────────────────────────────

def test_comando_buscar_sin_args(mocker):
    """Sin argumentos → responde con mensaje de ayuda."""
    from handlers.cmd_inventario import comando_buscar
    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.args = []
    asyncio.run(comando_buscar(update, context))
    update.message.reply_text.assert_called_once()


def test_comando_buscar_db_no_disponible(mocker):
    """Con término pero DB no disponible → responde con aviso y no explota."""
    import db as _db_stub
    _db_stub.DB_DISPONIBLE = False
    from handlers.cmd_inventario import comando_buscar
    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.args = ["tornillo", "inexistente"]
    asyncio.run(comando_buscar(update, context))
    # Debe haber exactamente 2 llamadas: "buscando..." + "DB no disponible"
    assert update.message.reply_text.call_count == 2


# ── Tests de _mostrar_confirmacion ────────────────────────────────────────────

def test_mostrar_confirmacion_producto_valido(mocker):
    """Producto válido → envía mensaje de confirmación sin error."""
    from handlers.cmd_inventario import _mostrar_confirmacion
    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()
    prod = {
        "nombre": "Tornillo 6x1 punta broca",
        "precio_unidad": 150,
        "unidad": "Unidad",
        "categoria": "Tornillos",
        "stock": 100,
    }
    asyncio.run(_mostrar_confirmacion(update, prod))
    update.message.reply_text.assert_called_once()


def test_mostrar_confirmacion_precio_cero(mocker):
    """Precio 0 → no explota (producto sin precio asignado aún)."""
    from handlers.cmd_inventario import _mostrar_confirmacion
    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()
    prod = {
        "nombre": "Producto sin precio",
        "precio_unidad": 0,
        "unidad": "Unidad",
        "categoria": "General",
        "stock": 0,
    }
    asyncio.run(_mostrar_confirmacion(update, prod))
    update.message.reply_text.assert_called_once()


def test_mostrar_confirmacion_con_fracciones(mocker):
    """Producto con fracciones → las incluye en el mensaje sin error."""
    from handlers.cmd_inventario import _mostrar_confirmacion
    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()
    prod = {
        "nombre": "Tornillo drywall 6x1",
        "precio_unidad": 200,
        "categoria": "Tornillos",
        "fracciones": {"3/4": 8000, "1/2": 5000},
    }
    asyncio.run(_mostrar_confirmacion(update, prod))
    update.message.reply_text.assert_called_once()
    # El mensaje debe mencionar alguna fracción
    msg = update.message.reply_text.call_args[0][0]
    assert "3/4" in msg or "1/2" in msg
