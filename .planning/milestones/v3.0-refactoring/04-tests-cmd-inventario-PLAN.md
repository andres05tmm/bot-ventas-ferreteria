# Fase 04 — Tests para handlers/cmd_inventario.py (1011 líneas, 0 cobertura)

## Prerequisito
Ninguno estricto. Va al final por convención pero no depende de 02 ni 03.

## Objetivo
Cobertura mínima de las funciones de mayor riesgo:
flujos multi-paso con estado (`manejar_flujo_agregar_producto`) y helpers de cálculo.

---

## PASO 0 — Leer las firmas reales antes de escribir nada

```bash
grep -n "^async def \|^def " handlers/cmd_inventario.py | head -30
```

Confirmar que existen: `_resolver_grm`, `_texto_categoria_prompt`,
`manejar_flujo_agregar_producto`, `comando_buscar`, `_mostrar_confirmacion`.
Si alguna no existe con ese nombre exacto, usar el nombre real del archivo.

---

## PASO 1 — Verificar pytest-asyncio en requirements.txt

```bash
grep "pytest" requirements.txt
```

Si `pytest-asyncio` no está:
```bash
echo "pytest-asyncio>=0.24.0" >> requirements.txt
```

Agregar `pytest.ini` o `pyproject.toml` si no existe:
```bash
# Verificar si ya hay configuración de asyncio_mode
cat pytest.ini 2>/dev/null || grep "asyncio_mode" pyproject.toml 2>/dev/null || echo "no config"
```

Si no hay configuración:
```bash
cat > pytest.ini << 'EOF'
[pytest]
asyncio_mode = auto
EOF
```

---

## PASO 2 — Crear tests/test_cmd_inventario.py

```python
"""
tests/test_cmd_inventario.py — Tests para handlers/cmd_inventario.py.

Cubre: _resolver_grm, _texto_categoria_prompt,
       manejar_flujo_agregar_producto, comando_buscar, _mostrar_confirmacion.
"""
import sys
import types
import threading
import asyncio

# ── Stubs ANTES de cualquier import propio ────────────────────────────────────

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

# get_chat_lock retorna un asyncio.Lock real (no una lambda con yield)
_fake_locks: dict = {}
def _fake_get_chat_lock(chat_id):
    if chat_id not in _fake_locks:
        _fake_locks[chat_id] = asyncio.Lock()
    return _fake_locks[chat_id]

sys.modules["ventas_state"].get_chat_lock = _fake_get_chat_lock

# Stub ai
if "ai" not in sys.modules:
    import os as _os
    _ai = types.ModuleType("ai")
    _ai.__path__ = [_os.path.abspath("ai")]
    _ai.__package__ = "ai"
    _ai.procesar_con_claude = lambda *a, **kw: ""
    sys.modules["ai"] = _ai

import pytest


# ── Tests de _resolver_grm ────────────────────────────────────────────────────

def test_resolver_grm_sin_gramos():
    """Producto sin precio_por_gramo → retorna None."""
    from handlers.cmd_inventario import _resolver_grm
    resultado = _resolver_grm("tornillo punta broca", 10, False)
    assert resultado is None


def test_resolver_grm_nombre_vacio():
    """Nombre vacío → no explota, retorna None."""
    from handlers.cmd_inventario import _resolver_grm
    resultado = _resolver_grm("", 5, False)
    assert resultado is None


# ── Tests de _texto_categoria_prompt ─────────────────────────────────────────

def test_texto_categoria_prompt_retorna_string():
    """Siempre retorna un string no vacío con instrucciones para Claude."""
    from handlers.cmd_inventario import _texto_categoria_prompt
    resultado = _texto_categoria_prompt("Tornillo punta broca 6x1")
    assert isinstance(resultado, str)
    assert len(resultado) > 0


def test_texto_categoria_prompt_nombre_vacio():
    """Nombre vacío → no explota."""
    from handlers.cmd_inventario import _texto_categoria_prompt
    resultado = _texto_categoria_prompt("")
    assert isinstance(resultado, str)


# ── Tests de manejar_flujo_agregar_producto ───────────────────────────────────

@pytest.mark.asyncio
async def test_manejar_flujo_sin_estado(mocker):
    """Sin flujo activo en user_data → retorna False inmediatamente."""
    from handlers.cmd_inventario import manejar_flujo_agregar_producto
    update = mocker.MagicMock()
    context = mocker.MagicMock()
    context.user_data = {}
    resultado = await manejar_flujo_agregar_producto(update, context)
    assert resultado is False


@pytest.mark.asyncio
async def test_manejar_flujo_paso_nombre(mocker):
    """Con paso 'nombre' activo → procesa el nombre y retorna True."""
    from handlers.cmd_inventario import manejar_flujo_agregar_producto
    update = mocker.MagicMock()
    update.message.text = "Tornillo 6x1 punta broca"
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.user_data = {"agregar_producto_paso": "nombre"}
    resultado = await manejar_flujo_agregar_producto(update, context)
    assert resultado is True


# ── Tests de comando_buscar ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_comando_buscar_sin_args(mocker):
    """Sin argumentos → responde con mensaje de ayuda."""
    from handlers.cmd_inventario import comando_buscar
    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.args = []
    await comando_buscar(update, context)
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_comando_buscar_producto_no_encontrado(mocker):
    """Producto no en catálogo → responde sin explotar."""
    from handlers.cmd_inventario import comando_buscar
    mocker.patch("handlers.cmd_inventario.buscar_producto_en_catalogo", return_value=None)
    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()
    context = mocker.MagicMock()
    context.args = ["tornillo", "inexistente"]
    await comando_buscar(update, context)
    update.message.reply_text.assert_called_once()


# ── Tests de _mostrar_confirmacion ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mostrar_confirmacion_producto_valido(mocker):
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
    await _mostrar_confirmacion(update, prod)
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_mostrar_confirmacion_precio_cero(mocker):
    """Precio 0 → no explota (producto sin precio asignado)."""
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
    await _mostrar_confirmacion(update, prod)
    # No debe lanzar excepción
```

---

## PASO 3 — Correr tests

```bash
pytest tests/test_cmd_inventario.py -v --tb=short
```

Si falla con `ImportError` en algún módulo → agregar el stub faltante
al bloque `for mod, attrs in [...]` del setup.

Si falla porque una función no existe con ese nombre → verificar con:
```bash
grep -n "^async def \|^def " handlers/cmd_inventario.py
```
Y ajustar el nombre en el test.

```bash
# Suite completa
pytest tests/ -x -q --tb=short
```

---

## PASO 4 — Verificar

```bash
pytest tests/test_cmd_inventario.py -v
# Target: ≥8 tests pasando
```

## Criterio de éxito
- ≥8 tests pasando en `test_cmd_inventario.py`
- `pytest tests/ -x -q` pasa en verde
- Ningún test usa conexión real a DB ni Telegram
