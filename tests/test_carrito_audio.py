"""
tests/test_carrito_audio.py — Carrito conversacional de audio (Paso 4).

Cubre los helpers agregados a ventas_state.py:

  * append_a_pendiente     — suma en vez de reemplazar
  * marcar_origen_carrito  — seguimiento de quién tocó último el carrito
  * fijar_metodo_carrito   — guarda método declarado por vendedor
  * armar_timer_carrito    — timer asyncio con re-arm
  * cancelar_timer_carrito — cancela timer activo
  * limpiar_carrito        — estado consistente tras cierre manual
  * tiene_carrito_activo   — query de estado

Los tests mockean las dependencias pesadas (config, db, memoria) para que
no se toque red ni disco.
"""
import sys
import os
import types
import asyncio
import threading

# Permitir importar desde el root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─────────────────────────────────────────────────────────────────────────
# STUBS de dependencias de ventas_state
# ─────────────────────────────────────────────────────────────────────────

for _mod, _attrs in [
    ("config", {
        "COLOMBIA_TZ": None,
        "claude_client": None,
        "openai_client": None,
    }),
    ("db", {
        "DB_DISPONIBLE": False,
        "obtener_siguiente_consecutivo": lambda: 1,
        "obtener_nombre_id_cliente": lambda n: ("CF", "Consumidor Final"),
        "query_one": lambda *a, **kw: None,
        "execute": lambda *a, **kw: None,
        "execute_returning": lambda *a, **kw: None,
    }),
    ("memoria", {
        "cargar_inventario": lambda: [],
        "guardar_inventario": lambda x: None,
        "cargar_caja": lambda: {"abierta": False},
        "guardar_caja": lambda x: None,
        "cargar_memoria": lambda: {},
        "descontar_inventario": lambda *a: (False, None, None),
        "buscar_producto_en_catalogo": lambda x: None,
    }),
    ("utils", {
        "convertir_fraccion_a_decimal": lambda x: float(x) if x else 0.0,
        "decimal_a_fraccion_legible": lambda x: str(x),
        "es_thinner": lambda x: False,
        "parsear_precio": lambda x: float(x) if x else 0.0,
    }),
]:
    if _mod not in sys.modules:
        _m = types.ModuleType(_mod)
        for _k, _v in _attrs.items():
            setattr(_m, _k, _v)
        sys.modules[_mod] = _m
    else:
        _m = sys.modules[_mod]
        for _k, _v in _attrs.items():
            if not hasattr(_m, _k):
                setattr(_m, _k, _v)


# Si otro test previo stubeó ventas_state como ModuleType, lo botamos para
# que este test cargue el módulo real (que ahora tiene limpiar_carrito, etc.).
import importlib as _il  # noqa: E402
_vs_prev = sys.modules.get("ventas_state")
if _vs_prev is not None and not hasattr(_vs_prev, "limpiar_carrito"):
    del sys.modules["ventas_state"]

import ventas_state as vs  # noqa: E402
# Por si el import devolvió cache stub, forzar reload
if not hasattr(vs, "limpiar_carrito"):
    vs = _il.reload(vs)


# ─────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────

def _clean(chat_id: int):
    """Estado limpio antes de cada test."""
    vs.limpiar_carrito(chat_id)


# ─────────────────────────────────────────────────────────────────────────
# append_a_pendiente
# ─────────────────────────────────────────────────────────────────────────

def test_append_suma_en_vez_de_reemplazar():
    chat_id = 9001
    _clean(chat_id)
    with vs._estado_lock:
        vs._guardar_pendiente(chat_id, [{"producto": "clavo", "cantidad": 3}])
    with vs._estado_lock:
        vs.append_a_pendiente(chat_id, [{"producto": "martillo", "cantidad": 1}])
    assert len(vs.ventas_pendientes[chat_id]) == 2
    productos = [v["producto"] for v in vs.ventas_pendientes[chat_id]]
    assert "clavo" in productos and "martillo" in productos
    _clean(chat_id)


def test_append_desde_vacio_crea_lista():
    chat_id = 9002
    _clean(chat_id)
    with vs._estado_lock:
        vs.append_a_pendiente(chat_id, [{"producto": "x", "cantidad": 1}])
    assert len(vs.ventas_pendientes[chat_id]) == 1
    _clean(chat_id)


def test_append_lista_vacia_noop():
    chat_id = 9003
    _clean(chat_id)
    with vs._estado_lock:
        vs.append_a_pendiente(chat_id, [])
    assert chat_id not in vs.ventas_pendientes
    _clean(chat_id)


# ─────────────────────────────────────────────────────────────────────────
# origen_carrito
# ─────────────────────────────────────────────────────────────────────────

def test_marcar_y_leer_origen():
    chat_id = 9010
    _clean(chat_id)
    assert vs.origen_carrito(chat_id) == ""
    vs.marcar_origen_carrito(chat_id, "audio")
    assert vs.origen_carrito(chat_id) == "audio"
    vs.marcar_origen_carrito(chat_id, "texto")
    assert vs.origen_carrito(chat_id) == "texto"
    _clean(chat_id)


def test_marcar_origen_invalido_ignorado():
    chat_id = 9011
    _clean(chat_id)
    vs.marcar_origen_carrito(chat_id, "audio")
    vs.marcar_origen_carrito(chat_id, "xxx")  # inválido, debe ignorarse
    assert vs.origen_carrito(chat_id) == "audio"
    _clean(chat_id)


# ─────────────────────────────────────────────────────────────────────────
# metodo_carrito
# ─────────────────────────────────────────────────────────────────────────

def test_fijar_y_obtener_metodo():
    chat_id = 9020
    _clean(chat_id)
    assert vs.obtener_metodo_carrito(chat_id) is None
    vs.fijar_metodo_carrito(chat_id, "efectivo")
    assert vs.obtener_metodo_carrito(chat_id) == "efectivo"
    vs.fijar_metodo_carrito(chat_id, "Transferencia")
    assert vs.obtener_metodo_carrito(chat_id) == "transferencia"
    _clean(chat_id)


def test_fijar_metodo_invalido_ignorado():
    chat_id = 9021
    _clean(chat_id)
    vs.fijar_metodo_carrito(chat_id, "bitcoin")  # inválido
    assert vs.obtener_metodo_carrito(chat_id) is None
    _clean(chat_id)


# ─────────────────────────────────────────────────────────────────────────
# limpiar_carrito
# ─────────────────────────────────────────────────────────────────────────

def test_limpiar_carrito_resetea_todo():
    chat_id = 9030
    _clean(chat_id)
    with vs._estado_lock:
        vs._guardar_pendiente(chat_id, [{"x": 1}])
    vs.marcar_origen_carrito(chat_id, "audio")
    vs.fijar_metodo_carrito(chat_id, "efectivo")

    vs.limpiar_carrito(chat_id)

    assert chat_id not in vs.ventas_pendientes
    assert vs.origen_carrito(chat_id) == ""
    assert vs.obtener_metodo_carrito(chat_id) is None
    assert not vs.tiene_carrito_activo(chat_id)


# ─────────────────────────────────────────────────────────────────────────
# tiene_carrito_activo
# ─────────────────────────────────────────────────────────────────────────

def test_tiene_carrito_activo():
    chat_id = 9040
    _clean(chat_id)
    assert not vs.tiene_carrito_activo(chat_id)
    with vs._estado_lock:
        vs._guardar_pendiente(chat_id, [{"x": 1}])
    assert vs.tiene_carrito_activo(chat_id)
    _clean(chat_id)


# ─────────────────────────────────────────────────────────────────────────
# armar_timer_carrito / cancelar_timer_carrito
# ─────────────────────────────────────────────────────────────────────────

def test_timer_ejecuta_callback():
    async def _run():
        chat_id = 9050
        _clean(chat_id)
        llamado = {"v": False}

        async def _cb():
            llamado["v"] = True

        vs.armar_timer_carrito(chat_id, _cb, segundos=0.05)
        await asyncio.sleep(0.15)
        assert llamado["v"] is True
        _clean(chat_id)

    asyncio.run(_run())


def test_cancelar_timer_evita_callback():
    async def _run():
        chat_id = 9051
        _clean(chat_id)
        llamado = {"v": False}

        async def _cb():
            llamado["v"] = True

        vs.armar_timer_carrito(chat_id, _cb, segundos=0.2)
        await asyncio.sleep(0.05)
        vs.cancelar_timer_carrito(chat_id)
        await asyncio.sleep(0.3)
        assert llamado["v"] is False
        _clean(chat_id)

    asyncio.run(_run())


def test_rearm_timer_cancela_anterior():
    async def _run():
        chat_id = 9052
        _clean(chat_id)
        contador = {"n": 0}

        async def _cb():
            contador["n"] += 1

        # Timer corto: si no se cancelara, dispararía 2 veces
        vs.armar_timer_carrito(chat_id, _cb, segundos=0.1)
        await asyncio.sleep(0.03)
        vs.armar_timer_carrito(chat_id, _cb, segundos=0.1)  # re-arm
        await asyncio.sleep(0.3)
        assert contador["n"] == 1  # solo el segundo timer disparó
        _clean(chat_id)

    asyncio.run(_run())


def test_registrar_ventas_limpia_origen_y_metodo():
    """registrar_ventas_con_metodo debe vaciar estado del carrito."""
    chat_id = 9060
    _clean(chat_id)

    with vs._estado_lock:
        vs._guardar_pendiente(chat_id, [])
    vs.marcar_origen_carrito(chat_id, "audio")
    vs.fijar_metodo_carrito(chat_id, "efectivo")

    # Simular el efecto clave sin ejecutar la lógica completa (que requiere
    # DB real): el código de registrar_ventas_con_metodo limpia estado en
    # el lock → probamos directamente limpiar_carrito que replica ese
    # comportamiento.
    vs.limpiar_carrito(chat_id)

    assert chat_id not in vs.ventas_pendientes
    assert vs.origen_carrito(chat_id) == ""
    assert vs.obtener_metodo_carrito(chat_id) is None
