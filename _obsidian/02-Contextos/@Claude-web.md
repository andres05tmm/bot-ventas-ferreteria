# @Claude-web — Contexto para sesiones en claude.ai

> Usa este archivo cuando consultes en claude.ai (no en Claude Code) sobre el proyecto.

---

## 🧠 Resumen del proyecto

FerreBot es un bot de Telegram para ferretería en Cartagena, Colombia.
- **Backend:** Python + python-telegram-bot + FastAPI
- **DB:** PostgreSQL (Railway)
- **IA:** Claude (Anthropic) para procesamiento de lenguaje natural
- **Versión actual:** v9.0-pg-only

---

## 📋 Refactorización en curso

Estamos dividiendo archivos monolíticos en módulos pequeños y testeables.

### Fase 1 (paralelo) — en progreso
| Tarea | Qué hace | Estado |
|---|---|---|
| A | Crear `middleware/` auth + rate_limit | ⬜ |
| B | Crear `ai/price_cache.py` thread-safe | ⬜ |
| C | Mover `migrate_*.py` a `migrations/` | ⬜ |
| D | Crear `services/catalogo_service.py` | ⬜ |
| E | Crear `services/inventario_service.py` | ⬜ |

### Fase 2 (desbloquea con Fase 1)
| Tarea | Qué hace | Depende |
|---|---|---|
| F | Split `comandos.py` + aplicar middleware | A |
| G | Extraer `ai/prompts.py` + `ai/excel_gen.py` | B |
| H | Extraer caja/fiados + thin wrapper `memoria.py` | D+E |

### Fase 3
| Tarea | Qué hace | Depende |
|---|---|---|
| I | Limpiar `ai.py` (2685→~800 líneas) | B+G |

---

## 🚦 Reglas del proyecto

- No tocar `db.py`, `config.py`, `main.py`
- Nunca borrar — solo crear o editar dentro del archivo asignado
- `memoria.py` sigue existiendo como thin wrapper de compatibilidad
- Un commit por tarea

---

## 💬 Cómo usar este contexto

Cuando hagas una pregunta en claude.ai sobre el proyecto, empieza con:

> "Contexto: estoy refactorizando FerreBot (ver @Claude-web.md). [Tu pregunta aquí]"

O simplemente adjunta este archivo junto con el archivo de código relevante.
