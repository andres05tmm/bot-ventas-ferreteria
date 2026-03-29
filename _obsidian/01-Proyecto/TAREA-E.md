# TAREA E — `services/inventario_service.py`

| Campo | Valor |
|---|---|
| **Fase** | 1 — paralelo total |
| **Prioridad** | 🟡 IMPORTANTE |
| **Estado** | #pendiente |
| **Agente** | — |
| **Depende de** | nada |
| **Desbloquea** | [[TAREA-H]] |

---

## 📁 Archivos a CREAR

- [ ] `services/inventario_service.py` (services/ ya existe si Tarea D fue primero)
- [ ] `tests/test_inventario_service.py`

## 📝 Archivos a EDITAR
- ninguno en esta fase

---

## 🎯 Propósito

Extraer de `memoria.py` todas las funciones de inventario en un módulo independiente. `memoria.py` seguirá re-exportando estas funciones (thin wrapper — Tarea H).

---

## 📦 Funciones a mover desde `memoria.py`

| Función | Línea aprox. |
|---|---|
| `cargar_inventario()` | ~850 |
| `guardar_inventario()` | ~900 |
| `verificar_alertas_inventario()` | ~950 |
| `descontar_inventario()` | ~1000 |
| `ajustar_inventario()` | ~1050 |
| `buscar_productos_inventario()` | ~1100 |
| `registrar_compra()` | ~1150 |
| `obtener_costo_producto()` | ~1180 |
| `calcular_margen()` | ~1200 |
| `obtener_resumen_margenes()` | ~1220 |

---

## ✅ Checklist de entrega

- [ ] `services/inventario_service.py` importa sin errores
- [ ] Todas las funciones listadas están en el nuevo módulo
- [ ] `python -m pytest tests/test_inventario_service.py -v` → ✅
- [ ] `python main.py` arranca sin errores
- [ ] Commit: `git commit -m "feat: extract inventario_service (Tarea E)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-E.md y ejecuta todo lo que indica.
Crea services/inventario_service.py extrayendo las funciones de inventario
de memoria.py. NO modifiques memoria.py todavía — eso es Tarea H.
Crea tests básicos para las funciones principales.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[MAPA]] | siguiente → [[TAREA-H]]
