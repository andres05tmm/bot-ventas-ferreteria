"""
Tests unitarios para ai/price_cache.py.

Cubre: registrar, get_activos, invalidar, limpiar_expirados, tamaño, thread-safety.
No requiere DATABASE_URL ni TELEGRAM_TOKEN.

Nota de importación: ai/__init__.py importa config y otros módulos que requieren
credenciales. Inyectamos un stub vacío para ai en sys.modules antes de importar
el submódulo ai.price_cache, evitando que se ejecute ai/__init__.py.
"""

# -- stdlib --
import sys
import types
import threading
import time

# Inyectar stub para ai (evita cargar ai/__init__.py → config → SystemExit)
# El stub necesita __path__ para que Python lo trate como paquete y permita
# importar submodulos como ai.price_cache directamente.
if "ai" not in sys.modules:
    import pathlib as _pathlib
    _ai_stub = types.ModuleType("ai")
    _ai_stub.__path__ = [str(_pathlib.Path(__file__).parent.parent / "ai")]
    _ai_stub.__package__ = "ai"
    sys.modules["ai"] = _ai_stub

# -- terceros --
import pytest

# -- propios --
from ai.price_cache import registrar, get_activos, invalidar, limpiar_expirados, tamaño, TTL
import ai.price_cache as _pc


# ─────────────────────────────────────────────
# FIXTURE — limpia el cache antes y después de cada test
# ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_cache():
    """Resetea el estado global del cache para aislar cada test."""
    with _pc._lock:
        _pc._cache.clear()
    yield
    with _pc._lock:
        _pc._cache.clear()


# ─────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────

def test_registrar_stores_price():
    """registrar() guarda el precio y get_activos() lo devuelve."""
    registrar("tornillo", 500.0)
    activos = get_activos()
    assert "tornillo" in activos
    assert activos["tornillo"] == 500.0


def test_registrar_con_fraccion():
    """registrar() con fraccion crea clave compuesta nombre___fraccion."""
    registrar("tubo", 2000.0, fraccion="1/2")
    activos = get_activos()
    assert "tubo___1/2" in activos
    assert activos["tubo___1/2"] == 2000.0


def test_registrar_reemplaza_entradas_previas():
    """
    registrar() borra todas las entradas anteriores del mismo producto
    antes de guardar la nueva — evita inconsistencias entre fracciones.
    """
    registrar("clavo", 100.0)
    registrar("clavo", 150.0, fraccion="1/4")
    # Re-registrar precio base: limpia también la entrada fraccionada
    registrar("clavo", 200.0)
    activos = get_activos()
    assert "clavo" in activos
    assert activos["clavo"] == 200.0
    # La entrada de fracción fue eliminada al re-registrar el precio base
    assert "clavo___1/4" not in activos


def test_get_activos_excluye_expirados():
    """get_activos() no devuelve entradas cuyo timestamp superó el TTL."""
    registrar("viejo", 100.0)
    # Falsificar timestamp para que parezca expirado
    with _pc._lock:
        clave = list(_pc._cache.keys())[0]
        precio, _ = _pc._cache[clave]
        _pc._cache[clave] = (precio, time.time() - TTL - 1)
    activos = get_activos()
    assert "viejo" not in activos


def test_invalidar_elimina_todas_entradas():
    """invalidar() elimina precio base y todas las fracciones del producto."""
    registrar("lija", 300.0)
    registrar("lija", 150.0, fraccion="1/2")
    # Necesitamos insertar la fracción sin que registrar() limpie la base:
    # la segunda llamada a registrar ya limpió la primera; insertar directo
    with _pc._lock:
        _pc._cache["lija"] = (300.0, time.time())
        _pc._cache["lija___1/2"] = (150.0, time.time())
    count = invalidar("lija")
    assert count == 2
    activos = get_activos()
    assert "lija" not in activos
    assert "lija___1/2" not in activos


def test_limpiar_expirados():
    """limpiar_expirados() elimina solo las entradas vencidas."""
    registrar("nuevo", 500.0)
    # Insertar entrada expirada directamente para no borrar "nuevo"
    with _pc._lock:
        _pc._cache["viejo2"] = (100.0, time.time() - TTL - 1)
    removed = limpiar_expirados()
    assert removed == 1
    activos = get_activos()
    assert "nuevo" in activos
    assert "viejo2" not in activos


def test_tamaño_incluye_expirados():
    """tamaño() cuenta todas las entradas, incluyendo las expiradas."""
    registrar("a", 1.0)
    with _pc._lock:
        _pc._cache["b"] = (2.0, time.time() - TTL - 1)
    assert tamaño() == 2  # "a" activo + "b" expirado


def test_concurrent_reads_writes():
    """
    Lanza 10 threads escritores y 10 lectores simultáneamente.
    Verifica que no hay excepciones (p. ej. RuntimeError: dictionary changed
    size during iteration) y que el estado final es consistente.
    """
    errors = []

    def writer(i):
        try:
            for _ in range(20):
                registrar(f"prod_{i}", float(i * 100))
                time.sleep(0)
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(20):
                _ = get_activos()
                time.sleep(0)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    threads += [threading.Thread(target=reader) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert errors == [], f"Thread errors: {errors}"
    # El cache debe estar en un estado válido tras el acceso concurrente
    activos = get_activos()
    assert isinstance(activos, dict)
