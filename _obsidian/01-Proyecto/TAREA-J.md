# TAREA J — `tests/` por módulo

| Campo | Valor |
|---|---|
| **Fase** | 🔄 Paralelo con TODO |
| **Prioridad** | 🟢 CONTINUA |
| **Estado** | #en-progreso |
| **Agente** | — |
| **Depende de** | cada test va junto con su tarea |
| **Desbloquea** | calidad general del proyecto |

---

## 📁 Archivos a CREAR

- [ ] `tests/__init__.py`
- [ ] `tests/test_middleware_auth.py` ← junto con [[TAREA-A]]
- [ ] `tests/test_middleware_rate_limit.py` ← junto con [[TAREA-A]]
- [ ] `tests/test_price_cache.py` ← junto con [[TAREA-B]]
- [ ] `tests/test_catalogo_service.py` ← junto con [[TAREA-D]]
- [ ] `tests/test_inventario_service.py` ← junto con [[TAREA-E]]
- [ ] `tests/test_caja_service.py` ← junto con [[TAREA-H]]

## 📝 Archivos a NO TOCAR

- `test_suite.py` — mantener como está (54K, prueba integración)

---

## 🎯 Propósito

El `test_suite.py` actual prueba todo junto y tarda mucho. Los nuevos tests son **unitarios, rápidos y aislados** — uno por módulo nuevo.

---

## 🧪 Plantilla base para cada test

```python
"""tests/test_price_cache.py"""
import pytest
from unittest.mock import patch

def test_registrar_y_recuperar():
    from ai.price_cache import registrar, get_activos, _cache
    _cache.clear()
    registrar("tornillo", 500.0)
    activos = get_activos()
    assert "tornillo" in activos
    assert activos["tornillo"] == 500.0

def test_expiracion():
    from ai.price_cache import registrar, get_activos, _cache
    _cache.clear()
    with patch("ai.price_cache._TTL_SEG", 0):
        registrar("tornillo", 500.0)
        activos = get_activos()
        assert "tornillo" not in activos

def test_thread_safety():
    import threading
    from ai.price_cache import registrar, get_activos, _cache
    _cache.clear()
    errores = []
    def worker(i):
        try:
            registrar(f"prod_{i}", float(i * 100))
        except Exception as e:
            errores.append(e)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errores) == 0
```

---

## ✅ Checklist de entrega

- [ ] `tests/__init__.py` creado
- [ ] Todos los archivos de test listados arriba creados
- [ ] `python -m pytest tests/ -v --ignore=test_suite.py` → ✅ todos pasan
- [ ] Cada test tiene al menos: caso feliz, caso borde, y caso de error

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-J.md.
Crea tests/__init__.py y todos los test_*.py listados.
Usa la plantilla de la nota como guía de estructura.
Corre pytest tests/ -v --ignore=test_suite.py al final.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[MAPA]]
