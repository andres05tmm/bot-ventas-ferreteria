# Milestone v2.0 — Refactorización Fase 2

## ⚠️ Leer antes de ejecutar cualquier fase

Las fases tienen dependencias duras. Ejecutar fuera de orden rompe el proceso.

## Orden de ejecución obligatorio

```
01 → 02 → 03 → 04
```

| Orden | Archivo | Qué hace | Prerequisito |
|-------|---------|----------|--------------|
| 1° | `01-tests-PLAN.md` | Agrega tests para callbacks.py y routers sin cobertura | Ninguno |
| 2° | `02-mensajes-PLAN.md` | Divide handlers/mensajes.py en parsing.py + cliente_flujo.py | 01 completo, pytest verde |
| 3° | `03-response-builder-PLAN.md` | Extrae ai/response_builder.py desde ai/__init__.py | 01 completo, pytest verde |
| 4° | `04-memoria-doc-PLAN.md` | Documenta memoria.py y imports lazy de catalogo_service | Ninguno (puede ir last) |

## Por qué este orden

- **01 primero siempre**: crea el net de seguridad. Las fases 02 y 03 mueven código real — sin tests no hay forma de verificar que nada se rompió.
- **02 y 03 son independientes entre sí**: se pueden ejecutar en paralelo si se usan ramas, pero en serie van 02 → 03.
- **04 es aislado**: solo agrega comentarios, no toca lógica. Puede ir en cualquier momento pero conviene dejarlo último para no distraerse.

## Comando estándar para ejecutar cada fase

```bash
claude "Lee .planning/milestones/v2.0-refactoring/01-tests-PLAN.md completamente y ejecútalo paso a paso sin saltarte ninguna verificación"
```

Cambiar `01-tests-PLAN.md` por el archivo de la fase correspondiente.

## Criterio de éxito del milestone completo

- `pytest tests/ -x -q` pasa en verde con al menos 12 tests nuevos
- `handlers/mensajes.py` baja de 1509 a ≤1100 líneas
- `ai/__init__.py` baja de 1267 a ≤750 líneas
- `handlers/parsing.py`, `handlers/cliente_flujo.py`, `ai/response_builder.py` existen
- `memoria.py` tiene el bloque de advertencia visible al inicio
- `python -c "import handlers.mensajes; import ai; import handlers.callbacks; print('OK')"` sin errores
