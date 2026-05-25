# Fase 02 — Split de handlers/mensajes.py (1509 líneas)

## Prerequisito

**Fase 01 completa.** `pytest tests/ -x -q` debe pasar antes de empezar.

## Objetivo

Dividir `handlers/mensajes.py` en tres módulos con responsabilidades únicas:

| Módulo nuevo | Responsabilidad | Líneas aprox |
|---|---|---|
| `handlers/parsing.py` | Parsing puro de texto sin efectos | ~250 |
| `handlers/cliente_flujo.py` | Estado del flujo de creación de cliente | ~200 |
| `handlers/mensajes.py` (reducido) | Despacho, orquestación, audio, foto, documento | ~600 |

## Mapa exacto del archivo actual

```
L1   - L55    Docstring + imports (se mantiene en mensajes.py)
L57  - L106   _enviar_botones_pago, _enviar_pregunta_cliente → MOVER a cliente_flujo.py
L108 - L275   _parsear_actualizacion_masiva (parsing puro) → MOVER a parsing.py
L277 - L360   _manejar_actualizacion_masiva (lógica DB + respuesta) → QUEDA en mensajes.py
L361 - L999   manejar_mensaje + _procesar_mensaje (despacho) → QUEDA en mensajes.py
L1000 - L1099 _manejar_foto_factura_o_abono → QUEDA en mensajes.py
L1100 - L1232 manejar_foto, _procesar_foto → QUEDA en mensajes.py
L1233 - L1424 manejar_audio, _procesar_audio → QUEDA en mensajes.py
L1425 - L1509 manejar_documento → QUEDA en mensajes.py
```

---

## PASO 1 — Crear handlers/parsing.py

**Copiar** (no mover todavía) `_parsear_actualizacion_masiva` (L108-L275).

```python
"""
handlers/parsing.py — Parsing puro de mensajes de texto.

Funciones sin efectos secundarios: no escriben a DB, no envían mensajes,
no acceden a estado global. Solo toman texto y retornan datos estructurados.
"""

import re

def parsear_actualizacion_masiva(mensaje: str):
    """
    [Copiar el cuerpo completo de _parsear_actualizacion_masiva desde mensajes.py]
    """
    ...
```

**Importante**: el nombre público es `parsear_actualizacion_masiva` (sin guión bajo).
La versión privada en mensajes.py se convierte en alias temporal:

```python
# En mensajes.py — al tope, después de los imports actuales:
from handlers.parsing import parsear_actualizacion_masiva as _parsear_actualizacion_masiva
```

Esto mantiene compatibilidad con cualquier caller interno sin cambiar nada más.

---

## PASO 2 — Crear handlers/cliente_flujo.py

**Copiar** `_enviar_pregunta_cliente` (L62-L106).

```python
"""
handlers/cliente_flujo.py — Flujo paso a paso de creación de cliente.

Maneja las preguntas y botones del wizard de creación de cliente.
Depende de ventas_state para leer clientes_en_proceso.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ventas_state import clientes_en_proceso, _estado_lock


async def enviar_pregunta_cliente(message, chat_id: int):
    """
    [Copiar el cuerpo completo de _enviar_pregunta_cliente desde mensajes.py]
    """
    ...
```

En `mensajes.py`, reemplazar la definición por import:

```python
from handlers.cliente_flujo import enviar_pregunta_cliente as _enviar_pregunta_cliente
```

---

## PASO 3 — Limpiar imports en mensajes.py

Después de los pasos 1 y 2, los imports en mensajes.py deben quedar:

```python
# Agregar al bloque de imports propios:
from handlers.parsing import parsear_actualizacion_masiva as _parsear_actualizacion_masiva
from handlers.cliente_flujo import enviar_pregunta_cliente as _enviar_pregunta_cliente
```

Eliminar las definiciones originales de esas dos funciones del archivo.

---

## PASO 4 — Verificar que no hay ImportError

```bash
python -c "
import handlers.parsing
import handlers.cliente_flujo
import handlers.mensajes
print('imports OK')
"
```

Si falla → revisar si `handlers/cliente_flujo.py` está importando algo de `mensajes.py`
(eso sería un ciclo nuevo). La solución: mover el import problemático dentro del cuerpo
de la función (lazy import), igual que ya lo hace el proyecto.

---

## PASO 5 — Correr tests

```bash
pytest tests/ -x -q --tb=short
```

Si algún test falla porque `_parsear_actualizacion_masiva` no se encuentra → significa
que hay un test en el proyecto que importa directamente desde mensajes. Buscar con:

```bash
grep -rn "_parsear_actualizacion_masiva\|_enviar_pregunta_cliente" tests/
```

Actualizar esos imports para apuntar a los módulos nuevos.

---

## PASO 6 — Commit

```bash
git add handlers/parsing.py handlers/cliente_flujo.py handlers/mensajes.py
git commit -m "refactor(handlers): extraer parsing.py y cliente_flujo.py desde mensajes.py

- _parsear_actualizacion_masiva → handlers/parsing.py (parsing puro, sin efectos)
- _enviar_pregunta_cliente → handlers/cliente_flujo.py (flujo wizard de cliente)
- mensajes.py mantiene alias de compatibilidad temporal
- sin cambios funcionales, todos los tests pasan"
```

---

## Decisiones de diseño que Claude NO debe tomar solo

1. **`_manejar_actualizacion_masiva` (L277-L360)** tiene parsing implícito (itera sobre pares).
   Se QUEDA en mensajes.py por ahora porque depende de `update.message.reply_text` (efecto).
   No moverla a parsing.py — rompería la separación de responsabilidades.

2. **El flujo de creación de cliente (L382-L490 dentro de `_procesar_mensaje`)** está
   embebido en el despacho. No extraerlo todavía — requiere refactor del estado compartido
   que es Fase 02-B futura.

3. **`_enviar_botones_pago` en mensajes.py (L57-L60)** es un delegador a `callbacks.py`.
   Ya es correcto. No moverlo.

---

## Criterio de éxito

- `handlers/parsing.py` existe con `parsear_actualizacion_masiva`
- `handlers/cliente_flujo.py` existe con `enviar_pregunta_cliente`
- `handlers/mensajes.py` baja de 1509 a ≤1100 líneas
- `pytest tests/ -x -q` pasa en verde
- `python -c "import handlers.mensajes"` no lanza ningún error

## Herramienta recomendada

**Claude Code directo** (no GSD autónomo para esta fase).

```bash
claude "Lee .planning/phases/02-mensajes.md completamente. 
Sigue los pasos 1 al 6 en orden. 
Antes de crear cada archivo, muéstrame las primeras y últimas 5 líneas 
de lo que vas a copiar para que pueda confirmar el alcance."
```
