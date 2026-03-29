# 🔧 FerreBot — Panel de Control
*Refactorización v9.0 → v10.0 · Cartagena, Colombia*

---

## 🗺️ Mapa de dependencias

```
config.py ← todos los módulos
db.py ← memoria.py, routers/, ventas_state.py
memoria.py ← ai.py, handlers/
ai.py ← handlers/mensajes.py, handlers/comandos.py
ventas_state.py ← handlers/callbacks.py, handlers/mensajes.py
```

---

## 🟢 Fase 1 — Paralelo total (empezar aquí)

- [ ] 🔴 [[TAREA-A]] — `middleware/` auth + rate_limit
- [ ] 🔴 [[TAREA-B]] — `ai/price_cache.py` (race condition activa)
- [ ] 🟡 [[TAREA-C]] — `migrations/` reorganizar
- [ ] 🟡 [[TAREA-D]] — `services/catalogo_service.py`
- [ ] 🟡 [[TAREA-E]] — `services/inventario_service.py`

## 🟡 Fase 2 — Después de Fase 1

- [ ] [[TAREA-F]] — `handlers/cmd_*.py` ⬆️ depende: A
- [ ] [[TAREA-G]] — `ai/prompts.py` + `ai/excel_gen.py` ⬆️ depende: B
- [ ] [[TAREA-H]] — `services/caja_service.py` + `fiados_service.py` ⬆️ depende: D + E

## 🔴 Fase 3 — Solo al final

- [ ] [[TAREA-I]] — Limpiar `ai.py` (2685 → ~800 líneas) ⬆️ depende: B + G

## 🔄 Paralelo con todo

- [ ] [[TAREA-J]] — `tests/` por módulo (corre en paralelo con cada tarea)

---

## 📊 Estado general

```dataview
TABLE estado, fase, prioridad, agente
FROM "01-Proyecto"
WHERE file.name != "MAPA"
SORT fase ASC
```

---

## 🔗 Cadena de desbloqueo

[[TAREA-A]] → [[TAREA-F]]
[[TAREA-B]] → [[TAREA-G]] → [[TAREA-I]]
[[TAREA-D]] + [[TAREA-E]] → [[TAREA-H]] → [[TAREA-I]]

---

## ⚠️ Reglas de oro

1. **Cada tarea es independiente** — ningún agente toca el archivo que trabaja otro
2. **Nunca borrar** — solo crear archivos nuevos o editar dentro del archivo asignado
3. **Respetar los imports existentes** — `memoria.py` sigue existiendo como thin wrapper
4. **Commit por tarea** — cada agente hace su propio commit al terminar
5. **Sin cambios en `db.py`, `config.py`, `main.py`** — estos archivos están bien, no tocar

---

## 🔐 Variables de entorno nuevas (Tarea A)

Añadir a Railway / `.env`:
```
AUTHORIZED_CHAT_IDS=123456789,987654321
```
