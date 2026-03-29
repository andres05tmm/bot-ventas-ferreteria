# TAREA A — `middleware/` auth + rate_limit

| Campo | Valor |
|---|---|
| **Fase** | 1 — paralelo total |
| **Prioridad** | 🔴 CRÍTICA |
| **Estado** | #pendiente |
| **Agente** | — |
| **Depende de** | nada |
| **Desbloquea** | [[TAREA-F]] |

---

## 📁 Archivos a CREAR

- [ ] `middleware/__init__.py`
- [ ] `middleware/auth.py`
- [ ] `middleware/rate_limit.py`
- [ ] `tests/test_middleware_auth.py`
- [ ] `tests/test_middleware_rate_limit.py`

## 📝 Archivos a EDITAR
- ninguno en esta fase

---

## 🎯 Propósito

Centralizar en un solo lugar la autorización de `chat_id` y el límite de peticiones a Claude. Hoy esta lógica está dispersa (o no existe).

---

## ✅ Checklist de entrega

- [ ] `middleware/__init__.py` importa sin errores
- [ ] `middleware/auth.py` — con `AUTHORIZED_CHAT_IDS=""` todos pasan; con `"123"` solo 123 pasa
- [ ] `middleware/rate_limit.py` — enviar 21 mensajes seguidos → el 21 es rechazado
- [ ] `python -m pytest tests/test_middleware_auth.py -v` → ✅
- [ ] `python -m pytest tests/test_middleware_rate_limit.py -v` → ✅
- [ ] `python main.py` arranca sin errores
- [ ] Commit: `git commit -m "feat: add middleware auth + rate_limit (Tarea A)"`

---

## 📋 Prompt para Claude Code

```
Lee el archivo _obsidian/01-Proyecto/TAREA-A.md y ejecuta todo lo que indica.
Crea los 3 archivos de middleware exactamente como están en GUIA_REFACTORIZACION.
Después crea los tests y verifica que pasan.
No toques db.py, config.py ni main.py.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[MAPA]] | siguiente → [[TAREA-F]]
