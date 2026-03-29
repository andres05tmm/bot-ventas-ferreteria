# TAREA I — Limpiar `ai.py` (2685 → ~800 líneas)

| Campo | Valor |
|---|---|
| **Fase** | 3 — SOLO AL FINAL |
| **Prioridad** | 🟠 ALTA |
| **Estado** | #bloqueada |
| **Agente** | — |
| **Depende de** | [[TAREA-B]] ✅ + [[TAREA-G]] ✅ |
| **Desbloquea** | 🏁 Refactorización completa |

---

## ⚠️ NO EMPEZAR hasta que B y G estén completas y testeadas

---

## 📝 Archivos a EDITAR

- [ ] `ai.py` — limpieza de código ya extraído

---

## 🎯 Propósito

Con `price_cache.py`, `prompts.py` y `excel_gen.py` ya creados y funcionando, eliminar las funciones duplicadas de `ai.py` y reemplazarlas con imports.

---

## 🗑️ Qué eliminar de `ai.py` y cómo

### 1. Líneas 35–48 — caché de precios
```python
# ELIMINAR el código de _precios_recientes
# AGREGAR en su lugar:
from ai.price_cache import registrar as _registrar_precio, get_activos as _get_precios_activos
```

### 2. Líneas 68–99 — generación Excel
```python
# ELIMINAR generar_excel_personalizado
# AGREGAR:
from ai.excel_gen import generar_excel_personalizado
```

### 3. Líneas 293–308 — alias ferretería
```python
# ELIMINAR aplicar_alias_ferreteria
# AGREGAR:
from ai.prompts import aplicar_alias_ferreteria
```

### 4. Líneas 309–1475 — construcción de prompts
```python
# ELIMINAR _construir_parte_estatica, _construir_catalogo_imagen, _construir_parte_dinamica
# AGREGAR:
from ai.prompts import (_construir_parte_estatica, _construir_catalogo_imagen,
                        _construir_parte_dinamica, _calcular_historial, _elegir_modelo)
```

### 5. Línea ~2622 — edición Excel
```python
# ELIMINAR editar_excel_con_claude
# AGREGAR:
from ai.excel_gen import editar_excel_con_claude
```

---

## 📦 Qué se QUEDA en `ai.py`

- `_llamar_claude_con_reintentos`
- `procesar_con_claude`
- `_stream_claude_chunks`
- `procesar_con_claude_stream`
- `procesar_acciones` + `procesar_acciones_async`
- Funciones PG de clientes (`_pg_fila_a_cliente`, `_pg_resumen_ventas`, etc.)

**Objetivo: ai.py queda en ~800 líneas**

---

## ✅ Checklist de entrega

- [ ] `ai.py` importa sin errores
- [ ] Las 5 eliminaciones hechas y reemplazadas por imports
- [ ] `wc -l ai.py` → menor a 1000 líneas
- [ ] `python -m pytest tests/ -v` → ✅ todo pasa
- [ ] `python main.py` arranca sin errores
- [ ] Commit: `git commit -m "refactor: clean ai.py 2685→~800 lines (Tarea I)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-I.md. Verifica que TAREA-B y TAREA-G están COMPLETAS.
Limpia ai.py eliminando el código que ya fue extraído a ai/price_cache.py,
ai/prompts.py y ai/excel_gen.py. Reemplaza con imports correctos.
Verifica que todos los tests pasan y main.py arranca.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[TAREA-B]] ← [[TAREA-G]] | [[MAPA]] | 🏁 FIN
