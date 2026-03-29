# 📓 Vault Obsidian — FerreBot

Esta carpeta `_obsidian/` es el vault de Obsidian para gestionar la refactorización de FerreBot.

## Cómo abrirlo

1. Abre Obsidian
2. "Open folder as vault"
3. Selecciona esta carpeta `_obsidian/`

## Plugins requeridos (instalar en Community Plugins)

| Plugin | ID | Para qué |
|---|---|---|
| Tasks | `obsidian-tasks-plugin` | Checkboxes con estado y filtros |
| Kanban | `obsidian-kanban` | Tablero visual por fase |
| Dataview | `dataview` | Queries en MAPA.md |

## Estructura

```
_obsidian/
├── 00-Inbox/          ← notas rápidas y pendientes sin clasificar
├── 01-Proyecto/       ← MAPA.md + TAREA-A.md ... TAREA-J.md
├── 02-Contextos/      ← prompts de contexto para Claude Code y Claude web
├── 03-Archivo/        ← tareas completadas (mover aquí al terminar)
└── KANBAN.md          ← tablero visual de todas las tareas
```

## Flujo de trabajo

1. Abre `MAPA.md` → ve qué tareas están disponibles
2. Abre la nota de tarea (ej. `TAREA-A.md`)
3. Copia el prompt de "Prompt para Claude Code" y pégalo en Claude Code
4. Pega el output/log en la sección "Log / Notas" de la tarea
5. Marca el checklist de entrega
6. Mueve la tarjeta en `KANBAN.md` a "Completo"
