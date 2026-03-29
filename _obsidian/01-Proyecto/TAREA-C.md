# TAREA C — `migrations/` reorganizar

| Campo | Valor |
|---|---|
| **Fase** | 1 — paralelo total |
| **Prioridad** | 🟡 IMPORTANTE |
| **Estado** | #pendiente |
| **Agente** | — |
| **Depende de** | nada |
| **Desbloquea** | nada (tarea independiente) |

---

## 📁 Archivos a MOVER / REORGANIZAR

Los archivos `migrate_*.py` del root deben moverse a `migrations/`:

- [ ] Crear `migrations/__init__.py`
- [ ] Mover `migrate_compras.py` → `migrations/migrate_compras.py`
- [ ] Mover `migrate_fiados.py` → `migrations/migrate_fiados.py`
- [ ] Mover `migrate_gastos_caja.py` → `migrations/migrate_gastos_caja.py`
- [ ] Mover `migrate_historico.py` → `migrations/migrate_historico.py`
- [ ] Mover `migrate_memoria.py` → `migrations/migrate_memoria.py`
- [ ] Mover `migrate_proveedores.py` → `migrations/migrate_proveedores.py`
- [ ] Mover `migrate_ventas.py` → `migrations/migrate_ventas.py`

---

## 🎯 Propósito

Limpiar el root del proyecto. Los scripts de migración no son módulos del bot, son herramientas de mantenimiento. Deben vivir en su propia carpeta.

---

## ✅ Checklist de entrega

- [ ] Carpeta `migrations/` creada con `__init__.py`
- [ ] Todos los `migrate_*.py` movidos (el root queda limpio de ellos)
- [ ] Los scripts siguen corriendo: `python migrations/migrate_ventas.py --help` (o lo que aplique)
- [ ] `python main.py` arranca sin errores
- [ ] Commit: `git commit -m "refactor: move migrate_*.py to migrations/ (Tarea C)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-C.md y ejecuta todo lo que indica.
Mueve todos los migrate_*.py del root a una nueva carpeta migrations/.
Crea migrations/__init__.py vacío.
Verifica que main.py sigue arrancando sin errores.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[MAPA]]
