# TAREA B — `ai/price_cache.py`

| Campo | Valor |
|---|---|
| **Fase** | 1 — paralelo total |
| **Prioridad** | 🔴 CRÍTICA |
| **Estado** | #pendiente |
| **Agente** | — |
| **Depende de** | nada |
| **Desbloquea** | [[TAREA-G]] → [[TAREA-I]] |

---

## 📁 Archivos a CREAR

- [ ] `ai/price_cache.py` ← **ÚNICO archivo nuevo dentro del directorio `ai/`**
- [ ] `tests/test_price_cache.py`

> ⚠️ **NO crear `ai/__init__.py`** — si se crea ahora, Python deja de ver `ai.py`
> como módulo y todas las llamadas a `from ai import procesar_con_claude` se rompen
> inmediatamente en producción. El `ai/__init__.py` se crea en **Tarea I** como
> parte del rename atómico `ai.py → ai/__init__.py`.

## 📝 Archivos a EDITAR
- ninguno en esta fase (ai.py se edita en Tarea I)

---

## 🎯 Propósito

Extraer la caché de precios recientes de `ai.py` (líneas 35–48) en un módulo aislado con `threading.Lock` correcto. El dict `_precios_recientes` actual se modifica desde múltiples threads **sin protección** → race condition activa en producción.

---

## 🔁 Migración futura (Tarea I)

Cuando se edite `ai.py`:
- `_registrar_precio_reciente(...)` → `from ai.price_cache import registrar`
- `_get_precios_recientes_activos()` → `from ai.price_cache import get_activos`
- Líneas 35–48 de `ai.py` se eliminan

---

## ✅ Checklist de entrega

- [ ] Verificar que `ai/__init__.py` **NO existe** después del commit
- [ ] `python -c "import ai; print(type(ai.procesar_con_claude))"` → imprime el tipo de la función (no error)
- [ ] `ai/price_cache.py` importa sin errores
- [ ] `registrar("tornillo", 500.0)` → aparece en `get_activos()`
- [ ] Con TTL mockeado a 0 → no aparece en `get_activos()`
- [ ] `python -m pytest tests/test_price_cache.py -v` → ✅
- [ ] `python main.py` arranca sin errores
- [ ] Commit: `git commit -m "feat: add ai/price_cache thread-safe (Tarea B)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-B.md y ejecuta todo lo que indica.

IMPORTANTE: Crea SOLO el archivo ai/price_cache.py dentro del directorio ai/.
NO crees ai/__init__.py — si lo creas, Python shadowea ai.py y el bot se rompe en producción.
El ai/__init__.py se crea en Tarea I, no ahora.

Crea tests/test_price_cache.py con pruebas de registro, expiración y concurrencia.
No modifiques ai.py todavía — eso es Tarea I.

Verificación obligatoria antes del commit:
  python -c "import ai; print(type(ai.procesar_con_claude))"
Debe imprimir el tipo de la función. Si lanza ImportError, creaste ai/__init__.py por error — bórralo.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[MAPA]] | siguiente → [[TAREA-G]]
