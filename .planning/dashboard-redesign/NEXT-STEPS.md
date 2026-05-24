# Próximos pasos — Dashboard Redesign

**Última actualización**: 2026-05-24 — Fase 2 bloqueada (Stitch MCP no responde)

## Estado actual

✅ Fase 0 completada (PRODUCT.md, DESIGN.md baseline, AUDIT.md, baseline-screenshots/)
✅ **FASE 1 COMPLETADA** — deliverables:
  - `IA.md` — sitemap nuevo (15 destinos + Hoy), wireframes ASCII del cockpit y del shell con sidebar
  - Cleanup P0 ejecutado:
    - `dashboard/src/index.css` vaciado (antes contenía HTML basura)
    - Viewport en `dashboard/index.html` sin `maximum-scale=1.0, user-scalable=no` (mejora accesibilidad de zoom)

✅ **FASE 2 COMPLETADA** (2026-05-24):
  - 13 mockups generados en Stitch (`projects/12113492557069924495`)
  - Comparativa: `MOCKUPS-COMPARATIVA.md`
  - **Andrés eligió**: dirección **A · Bento minimalista** (Linear-style) + variante **dark mode** complementaria
  - Feedback de calibración: cifras hero y subtítulos eran muy grandes → type scale bajada en DESIGN.md (hero tope **40px**, no 64-72px de Stitch)
  - **Deliverable final**: `.planning/dashboard-redesign/DESIGN.md` (locked) con tokens 3 capas (primitive → semantic → component), light + dark, type scale calibrada

⏸️ Fase 3 lista para arrancar

## Decisiones tomadas en Fase 1

| Decisión | Valor |
|---|---|
| Navegación primaria | Sidebar persistente agrupado (240px desktop, colapsable) + Cmd+K |
| Home / landing | Cockpit "HOY" — prioridad: ventas hoy, caja, gastos, totales semana/mes, métodos de pago, ticket promedio. Stock + fiados abajo. |
| Dark mode | Light + dark desde Fase 3 |
| Grupos sidebar | 4 grupos: Operación / Gestión / Reportes / Fiscal (+ Hoy top-level) |
| Cleanup tabs | Top10 → sección de Resultados · Cablear `FacturasElectronicasRecibidas` · Unificar Historial + Histórico |

## Pendiente de Andrés (asíncrono, no bloqueante)

Capturar los screenshots listados en `baseline-screenshots/README.md` antes de Fase 2 (para Stitch). 5-10 minutos en producción.

## Para retomar — Fase 3: Design System en código

1. `cd dashboard && npx shadcn@latest init` con stack Tailwind + tipografía Inter.
2. Convertir `DESIGN.md` capa semantic → CSS vars en `dashboard/src/index.css` (ya vaciado en Fase 1, listo para tokens).
3. Mapear capa component → preset Tailwind y `tailwind.config.js`.
4. Instalar base shadcn: `Button Input Select Dialog DropdownMenu Table Tabs Toast Tooltip Card Badge Avatar Command` + `Toaster` global.
5. Cargar Inter via `@fontsource/inter` (no `<link>` externo — Railway).
6. **Adapter pattern**: `shared.jsx` mantiene exports actuales y delega a shadcn por dentro. Cero refactor de tabs en Fase 3.
7. Sustituir `.stitch/DESIGN.md` baseline por `DESIGN.md` v2 de `.planning/dashboard-redesign/`.
8. Eliminar los 4 temas legados (caramelo/forja/brasa/ferrari) del baseline cuando ya nada los referencie.

**Deliverables Fase 3**: shadcn instalado, tokens en código, dos temas (light/dark) operativos vía `prefers-color-scheme` + toggle, `shared.jsx` adapter, sin regresión visual en tabs todavía sin migrar.

## Decisiones pendientes para Fase 2

- ¿Mockups en desktop, móvil, o ambos? (Recomendado: desktop primero, validar layout, móvil después.)
- ¿Cuántas iteraciones por dirección antes de descartarla? (Sugerencia: 2 rounds máximo por variante.)
- ¿Andrés revisa síncrono o asíncrono? (Síncrono acelera; asíncrono permite más calidad de feedback.)

## Lo que NO se debe tocar (recordatorio)

- `useRealtime.js` (SSE) — capa de tiempo real intocable
- `routers/events.py` y `_pg_listen_worker`
- Lógica de negocio en `services/`, `routers/`, `handlers/`
- Tablas DB y migraciones
- El bot completo (`main.py`, `handlers/`, `ai/`)

Solo se rediseña la **capa de presentación** del dashboard React.
