# TAREA D — `services/catalogo_service.py`

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

- [ ] `services/__init__.py`
- [ ] `services/catalogo_service.py`
- [ ] `tests/test_catalogo_service.py`

## 📝 Archivos a EDITAR
- ninguno en esta fase

---

## 🎯 Propósito

Extraer de `memoria.py` todas las funciones de catálogo en un módulo independiente. `memoria.py` seguirá re-exportando estas funciones para compatibilidad (thin wrapper — se hace en Tarea H).

---

## 📦 Funciones a mover desde `memoria.py`

| Función | Línea aprox. |
|---|---|
| `buscar_producto_en_catalogo()` | ~450 |
| `buscar_multiples_en_catalogo()` | ~520 |
| `buscar_multiples_con_alias()` | ~580 |
| `obtener_precio_para_cantidad()` | ~630 |
| `obtener_precios_como_texto()` | ~680 |
| `obtener_info_fraccion_producto()` | ~720 |
| `actualizar_precio_en_catalogo()` | ~780 |

---

## ✅ Checklist de entrega

- [ ] `services/catalogo_service.py` importa sin errores
- [ ] Todas las funciones listadas están en el nuevo módulo
- [ ] `python -m pytest tests/test_catalogo_service.py -v` → ✅
- [ ] `python main.py` arranca sin errores (memoria.py sigue funcionando igual)
- [ ] Commit: `git commit -m "feat: extract catalogo_service (Tarea D)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-D.md y ejecuta todo lo que indica.
Crea services/__init__.py y services/catalogo_service.py extrayendo las funciones
de catálogo de memoria.py. NO modifiques memoria.py todavía — eso es Tarea H.
Crea tests básicos para las funciones principales.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[MAPA]] | siguiente → [[TAREA-H]]
