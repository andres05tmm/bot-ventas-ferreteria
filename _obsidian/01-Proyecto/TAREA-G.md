# TAREA G — `ai/prompts.py` + `ai/excel_gen.py`

| Campo | Valor |
|---|---|
| **Fase** | 2 — después de Fase 1 |
| **Prioridad** | 🟠 ALTA |
| **Estado** | #bloqueada |
| **Agente** | — |
| **Depende de** | [[TAREA-B]] ✅ |
| **Desbloquea** | [[TAREA-I]] |

---

## 📁 Archivos a CREAR

- [ ] `ai/prompts.py`
- [ ] `ai/excel_gen.py`

## 📝 Archivos a EDITAR
- ninguno en esta fase (ai.py se edita en Tarea I)

---

## 🎯 Propósito

Extraer de `ai.py` (2685 líneas) dos módulos grandes:
- `prompts.py` — toda la construcción del prompt de Claude (parte estática, catálogo, dinámica)
- `excel_gen.py` — generación y edición de Excel con Claude

---

## 📦 Qué va a `ai/prompts.py`

| Función | Líneas aprox. en ai.py |
|---|---|
| `aplicar_alias_ferreteria()` | 293–308 |
| `_construir_parte_estatica()` | 309–800 |
| `_construir_catalogo_imagen()` | 801–1100 |
| `_construir_parte_dinamica()` | 1101–1475 |
| `_calcular_historial()` | (buscar) |
| `_elegir_modelo()` | (buscar) |

## 📦 Qué va a `ai/excel_gen.py`

| Función | Líneas aprox. en ai.py |
|---|---|
| `generar_excel_personalizado()` | 68–99 |
| `editar_excel_con_claude()` | ~2622 |

---

## ✅ Checklist de entrega

- [ ] `ai/prompts.py` importa sin errores
- [ ] `ai/excel_gen.py` importa sin errores
- [ ] Las funciones extraídas están completas y sin modificar lógica
- [ ] `python main.py` arranca sin errores (ai.py aún tiene las funciones originales — se limpian en Tarea I)
- [ ] Commit: `git commit -m "feat: extract ai/prompts.py + ai/excel_gen.py (Tarea G)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-G.md. Verifica que TAREA-B está completa.
Extrae las funciones de construcción de prompts de ai.py hacia ai/prompts.py.
Extrae generar_excel_personalizado y editar_excel_con_claude hacia ai/excel_gen.py.
NO borres nada de ai.py todavía — eso es Tarea I.
Verifica que main.py arranca sin errores.
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[TAREA-B]] | [[MAPA]] | siguiente → [[TAREA-I]]
