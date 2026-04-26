# Fase 02 — Split de _procesar_mensaje + completar cliente_flujo.py

## Prerequisito
Fase 01 completa. `pytest tests/ -x -q` pasa en verde.

## Objetivo
Dos cosas en paralelo:

1. Dividir `_procesar_mensaje` (L170-L788, 619 líneas) extrayendo flujos especiales a `handlers/dispatch.py` e `handlers/intent.py`
2. Terminar la migración que quedó pendiente del v2.0: mover `_insertar_cliente_pg` de `_procesar_mensaje` a `handlers/cliente_flujo.py`

**Resultado esperado:**
- `handlers/mensajes.py`: 1297 → ≤900 líneas
- `handlers/dispatch.py`: nuevo, ~350 líneas
- `handlers/intent.py`: nuevo, ~60 líneas
- `handlers/cliente_flujo.py`: crece de 52 → ~120 líneas (absorbe el INSERT)

---

## REGLA DE ORO — Lazy imports en dispatch.py

`dispatch.py` importará de `ventas_state`, `memoria`, y posiblemente `ai`.
**TODOS estos imports deben ser lazy** (dentro de la función, no al nivel del módulo)
para mantener el patrón ya establecido en el proyecto y evitar ciclos.

Ejemplo correcto:
```python
async def manejar_flujo_cliente(update, chat_id, mensaje):
    from ventas_state import clientes_en_proceso, _estado_lock  # ← lazy
    ...
```

Ejemplo incorrecto:
```python
from ventas_state import clientes_en_proceso  # ← nivel de módulo = ciclo potencial
```

---

## PASO 1 — Leer el código antes de escribir nada

```bash
# Ver el mapa completo de _procesar_mensaje
sed -n '170,788p' handlers/mensajes.py | grep -n "# ──\|async def\|def \|return\|if await"
```

Esto da el mapa de bloques sin leer las 619 líneas completas.

---

## PASO 2 — Crear handlers/intent.py

Función de **detección pura**: lee estado, retorna string o None. Sin efectos.

```python
"""
handlers/intent.py — Detección de intención del mensaje entrante.

Lee el estado global y retorna la intención activa para el chat_id,
o None si el mensaje debe procesarse normalmente por Claude.

Sin efectos secundarios: no envía mensajes, no modifica estado.
"""


def detectar_flujo_activo(chat_id: int) -> str | None:
    """
    Retorna la intención activa para este chat_id.

    Valores posibles:
      "cliente_en_proceso"  — wizard de creación de cliente activo
      "correccion_activa"   — venta en modo modificación/corrección
      None                  — mensaje normal, continuar al flujo Claude

    Nota: "excel_pendiente" y "pago_pendiente" se detectan dentro de
    manejar_flujo_excel y manejar_flujo_pago_texto respectivamente,
    porque leen context.user_data que no está disponible aquí.
    """
    # Lazy imports — patrón obligatorio del proyecto
    from ventas_state import clientes_en_proceso, esperando_correccion, _estado_lock

    with _estado_lock:
        if clientes_en_proceso.get(chat_id):
            return "cliente_en_proceso"
        if esperando_correccion.get(chat_id):
            return "correccion_activa"

    return None
```

---

## PASO 3 — Completar handlers/cliente_flujo.py

`cliente_flujo.py` existe pero le falta la lógica de **guardar** el cliente en DB
(actualmente vive en `_procesar_mensaje` L218-L268).

Agregar al final de `handlers/cliente_flujo.py`:

```python
async def guardar_cliente_y_continuar(update, chat_id: int, telefono: str, en_proceso: dict):
    """
    Inserta el cliente nuevo en PostgreSQL y, si hay venta pendiente,
    dispara la confirmación de pago.

    Mueve la lógica que estaba en _procesar_mensaje L218-L268.
    """
    import asyncio
    import logging
    from ventas_state import (
        ventas_pendientes, ventas_esperando_cliente,
        _estado_lock, _guardar_pendiente,
    )

    logger = logging.getLogger("ferrebot.handlers.cliente_flujo")

    def _insertar_cliente_pg():
        import db as _db
        if not _db.DB_DISPONIBLE:
            return False
        try:
            _db.execute(
                """INSERT INTO clientes
                       (nombre, tipo_id, identificacion, tipo_persona, correo, telefono)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    en_proceso["nombre"].upper().strip(),
                    en_proceso["tipo_id"],
                    en_proceso.get("identificacion", "").strip() or None,
                    en_proceso.get("tipo_persona"),
                    en_proceso.get("correo", "").strip() or None,
                    telefono.strip() or None,
                ),
            )
            return True
        except Exception as _e:
            logger.error("Error INSERT cliente PG: %s", _e)
            return False

    from memoria import invalidar_cache_memoria
    ok = await asyncio.to_thread(_insertar_cliente_pg)
    invalidar_cache_memoria()

    if ok:
        tipo_map = {"CC": "Cédula de ciudadanía", "NIT": "NIT", "CE": "Cédula de extranjería"}
        tipo_legible = tipo_map.get(en_proceso.get("tipo_id", ""), en_proceso.get("tipo_id", ""))
        await update.message.reply_text(
            f"✅ Cliente creado exitosamente:\n\n"
            f"👤 {en_proceso['nombre']}\n"
            f"📄 {tipo_legible}: {en_proceso.get('identificacion', '')}\n"
            f"🏷️ {en_proceso.get('tipo_persona', '')}\n"
            f"📧 {en_proceso.get('correo', '') or 'Sin correo'}\n"
            f"📞 {telefono or 'Sin teléfono'}"
        )
        with _estado_lock:
            ventas_pend = list(ventas_pendientes.get(chat_id, []))

        if ventas_pend:
            # Importar lazy para no crear ciclo con mensajes.py
            from handlers.mensajes import _enviar_botones_pago, _enviar_confirmacion_con_metodo
            metodo = ventas_pend[0].get("metodo_pago", "").lower()
            if metodo in ("efectivo", "transferencia", "datafono"):
                await _enviar_confirmacion_con_metodo(update.message, chat_id, ventas_pend, metodo)
            else:
                await _enviar_botones_pago(update.message, chat_id, ventas_pend)
    else:
        await update.message.reply_text("⚠️ No pude guardar el cliente. Intenta de nuevo.")
```

---

## PASO 4 — Crear handlers/dispatch.py

Copiar literalmente los bloques de `_procesar_mensaje`. **No reescribir lógica.**

```python
"""
handlers/dispatch.py — Flujos especiales que no pasan por Claude.

Cada función maneja un caso específico y retorna:
  True  → mensaje manejado, _procesar_mensaje debe hacer return
  False → flujo no aplica, continuar con el siguiente check

TODOS los imports de ventas_state, memoria y ai son LAZY (dentro de función).
Esto es obligatorio — evita ciclos de importación con mensajes.py.
"""
import logging

logger = logging.getLogger("ferrebot.handlers.dispatch")


async def manejar_flujo_cliente(update, chat_id: int, mensaje: str) -> bool:
    """
    Maneja los pasos del wizard de creación de cliente.
    [Mover L182-L217 de _procesar_mensaje — los pasos nombre/tipo_id/identificacion/etc.]
    [El paso "telefono" (L218-L268) ahora llama a guardar_cliente_y_continuar de cliente_flujo.py]
    Retorna True si el paso fue procesado.
    """
    from ventas_state import clientes_en_proceso, _estado_lock
    from handlers.cliente_flujo import enviar_pregunta_cliente, guardar_cliente_y_continuar

    with _estado_lock:
        en_proceso = clientes_en_proceso.get(chat_id)
    if not en_proceso:
        return False

    paso = en_proceso.get("paso")
    texto_lower = mensaje.strip().lower()

    if paso == "nombre":
        en_proceso["nombre"] = mensaje.strip().upper()
        en_proceso["paso"] = "tipo_id"
        with _estado_lock:
            clientes_en_proceso[chat_id] = en_proceso
        await enviar_pregunta_cliente(update.message, chat_id)
        return True

    elif paso == "identificacion":
        en_proceso["identificacion"] = mensaje.strip()
        en_proceso["paso"] = "tipo_persona"
        with _estado_lock:
            clientes_en_proceso[chat_id] = en_proceso
        await enviar_pregunta_cliente(update.message, chat_id)
        return True

    elif paso == "correo":
        correo = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
        en_proceso["correo"] = correo
        en_proceso["paso"] = "telefono"
        with _estado_lock:
            clientes_en_proceso[chat_id] = en_proceso
        await update.message.reply_text("¿Cuál es el teléfono? (escribe 'no tiene' si no aplica)")
        return True

    elif paso == "telefono":
        telefono = "" if texto_lower in ("no tiene", "no", "ninguno", "-") else mensaje.strip()
        with _estado_lock:
            clientes_en_proceso.pop(chat_id, None)
        await guardar_cliente_y_continuar(update, chat_id, telefono, en_proceso)
        return True

    return False


async def manejar_flujo_excel(update, context, chat_id: int, mensaje: str) -> bool:
    """
    Maneja instrucciones sobre un Excel cargado previamente.
    [Mover L270-L317 de _procesar_mensaje]
    Retorna True si el mensaje fue procesado como instrucción de Excel.
    """
    import os
    excel_temp = context.user_data.get("excel_temp")
    excel_nombre = context.user_data.get("excel_nombre")
    if not excel_temp or not os.path.exists(excel_temp):
        return False

    # [Copiar bloque L270-L317 íntegro aquí]
    # Incluye: editar_excel_con_claude, validación rutas_sospechosas,
    # namespace_seguro, exec, envío del archivo modificado
    ...
    return True


async def manejar_flujo_pago_texto(update, chat_id: int, mensaje: str) -> bool:
    """
    Detecta si el usuario escribió el método de pago como texto (ej: "efectivo").
    [Mover L319-L367 de _procesar_mensaje]
    Retorna True si el mensaje era un método de pago y fue procesado.
    """
    from ventas_state import ventas_pendientes, _estado_lock

    with _estado_lock:
        ventas_pend = list(ventas_pendientes.get(chat_id, []))
    if not ventas_pend:
        return False

    texto_lower = mensaje.strip().lower()
    metodos = {"efectivo", "transferencia", "datafono", "nequi", "daviplata"}
    if texto_lower not in metodos:
        return False

    # [Copiar bloque L319-L367 íntegro aquí]
    # Incluye: _enviar_confirmacion_con_metodo
    ...
    return True


async def manejar_flujo_correccion(update, context, chat_id: int, mensaje: str, vendedor: str) -> bool:
    """
    Maneja el modo de modificación/corrección de una venta existente.
    [Mover L369-L543 de _procesar_mensaje]
    Retorna True si el mensaje fue procesado como corrección.
    """
    from ventas_state import esperando_correccion, _estado_lock

    with _estado_lock:
        en_correccion = esperando_correccion.get(chat_id)
    if not en_correccion:
        return False

    # [Copiar bloque L369-L543 íntegro aquí]
    ...
    return True


async def manejar_rechazo_cliente(update, chat_id: int, mensaje: str) -> bool:
    """
    Usuario respondió "no" a la pregunta de crear cliente.
    [Mover L563-L580 de _procesar_mensaje]
    Retorna True si el mensaje era un rechazo y fue procesado.
    """
    from ventas_state import ventas_esperando_cliente, _estado_lock

    with _estado_lock:
        esperando = ventas_esperando_cliente.get(chat_id)
    if not esperando:
        return False

    texto_lower = mensaje.strip().lower()
    if texto_lower not in ("no", "n", "no crear", "sin cliente"):
        return False

    # [Copiar bloque L563-L580 íntegro aquí]
    ...
    return True
```

> **Nota importante sobre los `...`**: Los bloques marcados con `...` deben copiarse
> literalmente de `_procesar_mensaje` en mensajes.py. No reescribir ni simplificar.

---

## PASO 5 — Actualizar _procesar_mensaje en mensajes.py

Agregar imports al bloque de imports de mensajes.py:
```python
from handlers.dispatch import (
    manejar_flujo_cliente,
    manejar_flujo_excel,
    manejar_flujo_pago_texto,
    manejar_flujo_correccion,
    manejar_rechazo_cliente,
)
```

Reemplazar los bloques extraídos en `_procesar_mensaje` con las llamadas:

```python
async def _procesar_mensaje(update, context, mensaje, chat_id, vendedor):
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Flujos con handlers propios (sin cambio) ──
    if await manejar_flujo_agregar_producto(update, context):
        return
    from handlers.comandos import manejar_mensaje_precio
    if await manejar_mensaje_precio(update, mensaje):
        return

    # ── Flujos extraídos a dispatch.py ──
    if await manejar_flujo_cliente(update, chat_id, mensaje):
        return
    if await manejar_flujo_excel(update, context, chat_id, mensaje):
        return
    if await manejar_flujo_pago_texto(update, chat_id, mensaje):
        return
    if await manejar_flujo_correccion(update, context, chat_id, mensaje, vendedor):
        return
    if await manejar_rechazo_cliente(update, chat_id, mensaje):
        return

    # ── Flujo normal con Claude (L585-L786, sin cambios) ──
    # ... resto del código sin tocar
```

---

## PASO 6 — Verificar imports

```bash
python -c "
import sys, types, threading
# Stubs mínimos
for mod, attrs in [
    ('config', {'COLOMBIA_TZ': None, 'claude_client': None}),
    ('db', {'DB_DISPONIBLE': False, 'execute': lambda *a: None, 'query_all': lambda *a: [], 'query_one': lambda *a: None}),
    ('memoria', {'cargar_memoria': lambda: {}, 'invalidar_cache_memoria': lambda: None, 'cargar_inventario': lambda: {}}),
    ('ventas_state', {'ventas_pendientes': {}, 'clientes_en_proceso': {}, 'esperando_correccion': {}, 'ventas_esperando_cliente': {}, '_estado_lock': threading.Lock(), '_guardar_pendiente': lambda *a: None}),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items(): setattr(m, k, v)
        sys.modules[mod] = m

import handlers.intent
import handlers.dispatch
import handlers.cliente_flujo
print('imports OK')
"
```

Si hay `ImportError` → agregar el stub del módulo faltante al bloque `for mod, attrs in [...]`.

---

## PASO 7 — Correr tests

```bash
pytest tests/ -x -q --tb=short
```

---

## PASO 8 — Verificar reducción de líneas

```bash
wc -l handlers/mensajes.py handlers/dispatch.py handlers/intent.py handlers/cliente_flujo.py
# mensajes.py target: ≤900
# dispatch.py target: ~350
# intent.py target: ~60
# cliente_flujo.py target: ~120
```

---

## Decisiones que Claude NO debe tomar solo

1. **L601-L786 (flujo normal Claude)** — se queda en mensajes.py sin cambios.
2. **`_manejar_actualizacion_masiva` (L65-L148)** — se queda en mensajes.py. Tiene efectos (DB + reply_text) propios.
3. **Los imports lazy existentes** — no convertirlos a nivel de módulo.
4. **No reescribir lógica** — solo mover bloques literalmente. Si algo parece ineficiente, moverlo igual y documentarlo.

## Criterio de éxito
- `handlers/dispatch.py` con 5 funciones async
- `handlers/intent.py` con `detectar_flujo_activo`
- `handlers/cliente_flujo.py` con `guardar_cliente_y_continuar` (INSERT migrado desde _procesar_mensaje)
- `handlers/mensajes.py` baja de 1297 a ≤900 líneas
- `pytest tests/ -x -q` pasa en verde
- `python -c "import handlers.mensajes"` sin errores
