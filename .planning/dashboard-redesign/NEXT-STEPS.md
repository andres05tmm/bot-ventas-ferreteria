# Próximos pasos — Dashboard Redesign

**Última actualización**: 2026-05-23 sesión inicial

## Estado actual

✅ Plan completo aprobado (ver `PLAN.md`)
✅ Skills de diseño inventariados y entendidos
✅ MCPs `shadcn` + `stitch` configurados en `~/.claude.json` (key TitleCase)
⚠️ **MCPs NO cargados todavía** — requieren restart de Claude Code
⏸️ Fase 0 sin iniciar

## Para retomar en la próxima sesión

1. **Verificar que los MCPs cargaron**: correr `/mcp` y confirmar que aparecen `magic`, `shadcn`, `stitch` conectados
   - Si NO aparecen `shadcn` y `stitch`: revisar `~/.claude.json` clave `projects['C:/Users/Dell/Documents/GitHub/bot-ventas-ferreteria'].mcpServers` (backup en `~/.claude.json.bak-20260523-211954`)

2. **Decidir branch**: crear `feat/dashboard-redesign` desde `main` y trabajar ahí

3. **Arrancar Fase 0**:
   - `impeccable teach` → genera `PRODUCT.md` (preguntará sobre Andrés, vendedores, tono, anti-referencias)
   - Luego `stitch::extract-design-md` sobre `dashboard/src/` para baseline
   - Luego `impeccable audit` para lista de anti-patterns actuales

4. **Confirmar disponibilidad de Andrés** para validar mockups en Fase 2 (es el punto de decisión más crítico)

## Decisiones pendientes (no bloquean Fase 0)

- Patrón de navegación final (sidebar agrupado / command palette / top-nav) → se decide en Fase 1
- Estilo visual final → se decide en Fase 2 viendo los 4 mockups
- Si dark mode es requirement o nice-to-have
- Si responsive móvil es prioridad alta (Andrés vendiendo en la calle)

## Lo que NO se debe tocar

- `useRealtime.js` (SSE) — capa de tiempo real intocable
- `routers/events.py` y `_pg_listen_worker`
- Lógica de negocio en `services/`, `routers/`, `handlers/`
- Tablas DB y migraciones
- El bot completo (`main.py`, `handlers/`, `ai/`)

Solo se rediseña la **capa de presentación** del dashboard React.
