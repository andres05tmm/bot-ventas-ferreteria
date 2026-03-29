# TAREA H — `services/caja_service.py` + `fiados_service.py` + thin wrapper

| Campo | Valor |
|---|---|
| **Fase** | 2 — después de Fase 1 |
| **Prioridad** | 🟡 IMPORTANTE |
| **Estado** | #bloqueada |
| **Agente** | — |
| **Depende de** | [[TAREA-D]] ✅ + [[TAREA-E]] ✅ |
| **Desbloquea** | [[TAREA-I]] (indirectamente) |

---

## 📁 Archivos a CREAR

- [ ] `services/caja_service.py`
- [ ] `services/fiados_service.py`
- [ ] `tests/test_caja_service.py`

## 📝 Archivos a EDITAR

- [ ] `memoria.py` — convertir en thin wrapper (última acción de esta tarea)

---

## 🎯 Propósito

Completar la extracción de `memoria.py`. Con D y E ya hechos, esta tarea extrae los dos dominios restantes (caja/gastos y fiados) y finalmente convierte `memoria.py` en un thin wrapper que solo re-exporta.

---

## 📦 Funciones a mover a `services/caja_service.py`

| Función | Línea aprox. |
|---|---|
| `_guardar_gasto_postgres()` | ~1243 |
| `_guardar_caja_postgres()` | ~1261 |
| `_leer_caja_postgres()` | ~1289 |
| `_leer_gastos_postgres()` | ~1312 |
| `cargar_caja()` | ~1339 |
| `guardar_caja()` | ~1349 |
| `obtener_resumen_caja()` | ~1356 |
| `cargar_gastos_hoy()` | ~1390 |
| `guardar_gasto()` | ~1403 |

## 📦 Funciones a mover a `services/fiados_service.py`

| Función | Línea aprox. |
|---|---|
| `cargar_fiados()` | ~1414 |
| `guardar_fiado_movimiento()` | buscar en archivo |
| `abonar_fiado()` | buscar en archivo |
| Cualquier función con "fiado" en el nombre | — |

---

## 🔄 Cómo debe quedar `memoria.py` (thin wrapper)

```python
"""
memoria.py — Thin wrapper de compatibilidad.
La lógica real vive en services/.
"""
from memoria_core import (cargar_memoria, guardar_memoria, ...)

from services.catalogo_service import (buscar_producto_en_catalogo, ...)
from services.inventario_service import (cargar_inventario, ...)
from services.caja_service import (cargar_caja, guardar_caja, ...)
from services.fiados_service import (cargar_fiados, ...)
```

---

## ✅ Checklist de entrega

- [ ] `services/caja_service.py` importa sin errores
- [ ] `services/fiados_service.py` importa sin errores
- [ ] `memoria.py` convertido a thin wrapper y funciona igual que antes
- [ ] `python -m pytest tests/test_caja_service.py -v` → ✅
- [ ] `python main.py` arranca sin errores
- [ ] Commit: `git commit -m "refactor: extract caja+fiados services, memoria thin wrapper (Tarea H)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-H.md. Verifica que TAREA-D y TAREA-E están completas.
Extrae las funciones de caja/gastos a services/caja_service.py.
Extrae las funciones de fiados a services/fiados_service.py.
Finalmente convierte memoria.py en thin wrapper que re-exporta todo.
Verifica que main.py sigue arrancando sin errores.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[TAREA-D]] ← [[TAREA-E]] | [[MAPA]]
