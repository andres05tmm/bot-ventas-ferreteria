# Milestone v3.0 — Refactorización Fase 3

## ⚠️ Leer antes de ejecutar cualquier fase

## Orden de ejecución obligatorio

```
01 → 02 → 03 → 04
```

| Orden | Archivo | Qué hace | Prerequisito |
|-------|---------|----------|--------------|
| 1° | `01-tests-routers-catalogo-caja-PLAN.md` | Tests para routers/catalogo.py y routers/caja.py (0 cobertura hoy) | Ninguno |
| 2° | `02-split-procesar-mensaje-PLAN.md` | Extrae dispatch.py e intent.py desde _procesar_mensaje (619 líneas); termina migración a cliente_flujo.py | 01 completo, pytest verde |
| 3° | `03-split-prompts-PLAN.md` | Extrae prompt_context.py y prompt_products.py desde _construir_parte_dinamica (1069 líneas) | 01 completo, pytest verde |
| 4° | `04-tests-cmd-inventario-PLAN.md` | Tests para handlers/cmd_inventario.py (1011 líneas, 0 cobertura) | Puede ir paralelo a 02 y 03 |

## Comando estándar GSD para cada fase

```bash
claude "Lee .planning/milestones/v3.0-refactoring/01-tests-routers-catalogo-caja-PLAN.md
completamente y ejecútalo paso a paso sin saltarte ninguna verificación"
```

Hacer `/clear` entre fases para contexto limpio.

## Criterio de éxito del milestone completo

- `pytest tests/ -x -q` pasa en verde con ≥30 tests nuevos
- `handlers/mensajes.py` baja de 1297 a ≤900 líneas
- `ai/prompts.py` baja de 1370 a ≤400 líneas
- Archivos nuevos creados: `handlers/dispatch.py`, `handlers/intent.py`, `ai/prompt_context.py`, `ai/prompt_products.py`
- `routers/catalogo.py` y `routers/caja.py` tienen cobertura básica
- `python -c "import handlers.mensajes; import ai.prompts; print('OK')"` sin errores

## Estado del proyecto al entrar a v3.0

- `pytest tests/ -x -q` → 97 tests, todos verdes (confirmado antes de empezar v3.0)
- `handlers/parsing.py` y `handlers/cliente_flujo.py` existen (creados en v2.0)
- `ai/response_builder.py` existe (extraído en v2.0)
- PostgreSQL es la única fuente de verdad (migración completada)
- `_insertar_cliente_pg` aún vive en `_procesar_mensaje` — la fase 02 la migra a `cliente_flujo.py`

## Diferencia clave con v2.0

Las fases 02 y 03 son más complejas porque `_procesar_mensaje` y `_construir_parte_dinamica`
tienen funciones anidadas (nested defs) y estado compartido que el v2.0 no tenía.
Claude Code necesitará más iteraciones de verificación — no saltarse los pasos de `wc -l` y `pytest`.
