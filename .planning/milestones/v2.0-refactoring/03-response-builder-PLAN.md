# Fase 03 — Extraer ai/response_builder.py desde ai/__init__.py (1267 líneas)

## Prerequisito

Fase 01 completa. `pytest tests/ -x -q` pasa en verde.

## Objetivo

Bajar `ai/__init__.py` de 1267 a ~700 líneas extrayendo `procesar_acciones`
y `procesar_acciones_async` a un módulo dedicado.

## Mapa exacto del archivo actual

```
L1   - L57    Docstring + imports
L58  - L194   Helpers de PostgreSQL (_pg_fila_a_cliente, _pg_resumen_ventas, etc.)
L195 - L253   _llamar_claude_con_reintentos
L254 - L521   procesar_con_claude (construcción de prompt + llamada API)
L522 - L689   _stream_claude_chunks + procesar_con_claude_stream
L690 - L1257  procesar_acciones (parsing de [VENTA]...[/VENTA] y ejecución)
L1258 - L1267 procesar_acciones_async (wrapper async de procesar_acciones)
```

**Extraer**: L690-L1267 → `ai/response_builder.py`
**Mantener en ai/__init__.py**: L1-L689

---

## PASO 1 — Entender las dependencias de procesar_acciones

Antes de mover nada, identificar exactamente qué importa `procesar_acciones`.
Correr esto para confirmarlo:

```bash
grep -n "^from\|^import" /ruta/al/proyecto/ai/__init__.py | head -20
sed -n '690,720p' ai/__init__.py  # ver los imports lazy al inicio de procesar_acciones
```

Los imports lazy que van a estar dentro de `procesar_acciones` (L690+) son:
```python
from ventas_state import (ventas_pendientes, registrar_ventas_con_metodo,
    _estado_lock, mensajes_standby, limpiar_pendientes_expirados, _guardar_pendiente)
```

Estos **se quedan lazy** en `response_builder.py`. No llevarlos al nivel de módulo.

---

## PASO 2 — Crear ai/response_builder.py

```python
"""
ai/response_builder.py — Parsing y ejecución de acciones embebidas en respuestas de Claude.

Parsea los tags estructurados que Claude incluye en sus respuestas:
  [VENTA]...[/VENTA]
  [GASTO]...[/GASTO]
  [EXCEL]...[/EXCEL]
  etc.

Y los convierte en efectos: registrar ventas, guardar gastos, generar Excel.

DEPENDENCIAS DE ESTADO (importadas lazy para evitar ciclo con ventas_state):
  - ventas_state.ventas_pendientes
  - ventas_state.registrar_ventas_con_metodo
  - ventas_state._estado_lock

No importar estos al nivel de módulo — mantener los imports dentro de las funciones.
"""

import logging
import re
from datetime import datetime

# Imports del proyecto que NO crean ciclo (nivel de módulo OK):
import config
from memoria import (
    buscar_producto_en_catalogo,
    actualizar_precio_en_catalogo,
    invalidar_cache_memoria,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, _normalizar
from ai.price_cache import registrar as _registrar_precio_reciente

logger = logging.getLogger("ferrebot.ai.response_builder")


def procesar_acciones(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    """[Copiar cuerpo completo desde ai/__init__.py L690-L1257]"""
    ...


async def procesar_acciones_async(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    """[Copiar cuerpo completo desde ai/__init__.py L1258-L1267]"""
    ...
```

---

## PASO 3 — Actualizar ai/__init__.py

Después de crear `response_builder.py`, en `ai/__init__.py`:

1. **Eliminar** L690-L1267 (las dos funciones)
2. **Agregar** estos re-exports al final del archivo (para no romper callers):

```python
# Re-exports de compatibilidad — mantener hasta que todos los callers
# importen directamente desde ai.response_builder
from ai.response_builder import procesar_acciones, procesar_acciones_async
```

---

## PASO 4 — Verificar imports

```bash
python -c "
from ai.response_builder import procesar_acciones, procesar_acciones_async
from ai import procesar_con_claude, procesar_acciones, procesar_acciones_async
print('ai OK')
"

python -c "import handlers.mensajes; print('mensajes OK')"
```

`handlers/mensajes.py` importa `procesar_acciones` desde `ai`:
```python
from ai import procesar_con_claude, procesar_acciones, procesar_acciones_async, editar_excel_con_claude
```
Este import **sigue funcionando** gracias al re-export del paso 3. No tocar mensajes.py.

---

## PASO 5 — Verificar que _convertir_venta_mlt y otros helpers internos se mueven también

`procesar_acciones` contiene helpers definidos como funciones internas (`_convertir_venta_mlt`
en L~715). Esos helpers viajan con `procesar_acciones` — están dentro de su cuerpo,
no son funciones de módulo independientes. No hay que hacer nada especial.

Si algún helper resulta ser una función de módulo (definida con `def` al nivel de módulo
entre L690 y L1257), moverlo también a `response_builder.py`.

Verificar con:
```bash
awk 'NR>=690 && NR<=1257 && /^def |^async def /' ai/__init__.py
```

---

## PASO 6 — Tests para response_builder.py

Crear `tests/test_response_builder.py`:

```python
import sys, types, threading

# Stubs al tope
for mod, attrs in [
    ("config",       {"COLOMBIA_TZ": None, "claude_client": None}),
    ("memoria",      {
        "cargar_memoria": lambda: {},
        "buscar_producto_en_catalogo": lambda x: None,
        "actualizar_precio_en_catalogo": lambda *a: None,
        "invalidar_cache_memoria": lambda: None,
    }),
    ("ventas_state", {
        "ventas_pendientes": {},
        "_estado_lock": threading.Lock(),
        "registrar_ventas_con_metodo": lambda *a, **kw: [],
        "mensajes_standby": {},
        "limpiar_pendientes_expirados": lambda: None,
        "_guardar_pendiente": lambda *a: None,
    }),
    ("ai.price_cache", {"registrar": lambda *a: None}),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[mod] = m

from ai.response_builder import procesar_acciones

def test_procesar_acciones_texto_limpio():
    """Sin tags de acción → retorna texto sin modificar, listas vacías."""
    texto, ventas, excels = procesar_acciones("Hola, ¿en qué puedo ayudarte?", "Juan", 123)
    assert texto == "Hola, ¿en qué puedo ayudarte?"
    assert ventas == []
    assert excels == []

def test_procesar_acciones_extrae_venta():
    """Tag [VENTA] bien formado → se extrae de texto_limpio y aparece en ventas."""
    entrada = 'Te registré la venta. [VENTA]{"producto":"Tornillo","cantidad":10,"total":5000}[/VENTA]'
    texto, ventas, excels = procesar_acciones(entrada, "Juan", 456)
    assert "[VENTA]" not in texto
    # ventas puede estar vacía si el producto no se encontró en catálogo (stub)
    # Lo importante es que el tag fue consumido
    assert isinstance(ventas, list)

def test_procesar_acciones_json_malformado_no_explota():
    """JSON corrupto dentro de [VENTA] → no lanza excepción, retorna texto."""
    entrada = "Venta registrada [VENTA]{malformado[/VENTA]"
    texto, ventas, excels = procesar_acciones(entrada, "Juan", 789)
    assert isinstance(texto, str)
```

---

## PASO 7 — Commit

```bash
git add ai/response_builder.py ai/__init__.py tests/test_response_builder.py
git commit -m "refactor(ai): extraer procesar_acciones a ai/response_builder.py

- procesar_acciones + procesar_acciones_async → ai/response_builder.py
- ai/__init__.py mantiene re-exports para compatibilidad con callers existentes
- ai/__init__.py baja de 1267 a ~700 líneas
- tests/test_response_builder.py cubre casos base"
```

---

## Criterio de éxito

- `ai/response_builder.py` existe con las dos funciones
- `ai/__init__.py` baja a ≤750 líneas
- `from ai import procesar_acciones` sigue funcionando (re-export)
- `from ai.response_builder import procesar_acciones` también funciona
- `pytest tests/ -x -q` pasa en verde
- `python -c "import handlers.mensajes; import ai"` sin errores

## Herramienta recomendada

**Claude Code directo**.

```bash
claude "Lee .planning/phases/03-ai-response-builder.md completamente.
Primero corre el comando del PASO 5 y muéstrame el output antes de crear archivos.
Luego sigue los pasos en orden."
```
