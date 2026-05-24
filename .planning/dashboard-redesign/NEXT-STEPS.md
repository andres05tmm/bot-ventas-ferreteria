# Próximos pasos — Dashboard Redesign

**Última actualización**: 2026-05-23 — Fase 1 cerrada

## Estado actual

✅ Fase 0 completada (PRODUCT.md, DESIGN.md baseline, AUDIT.md, baseline-screenshots/)
✅ **FASE 1 COMPLETADA** — deliverables:
  - `IA.md` — sitemap nuevo (15 destinos + Hoy), wireframes ASCII del cockpit y del shell con sidebar
  - Cleanup P0 ejecutado:
    - `dashboard/src/index.css` vaciado (antes contenía HTML basura)
    - Viewport en `dashboard/index.html` sin `maximum-scale=1.0, user-scalable=no` (mejora accesibilidad de zoom)

⏸️ Fase 2 sin iniciar

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

## Para retomar — Fase 2: Dirección visual por evidencia

1. **Configurar proyecto Stitch** y subir baseline (assets actuales + IA.md como input semántico).
2. **`stitch::taste-design`** → DESIGN.md anti-slop premium (tipo extremo, color calibrado `#C8200E`, layout asimétrico, micro-motion).
3. **Generar 3-4 mockups exploratorios** del cockpit "HOY" + Ventas Rápidas + Caja:
   - A: Bento minimalista (Linear-style)
   - B: Industrial denso (Bloomberg/POS)
   - C: Glassmorphism + motion
   - D: Editorial/serio (banking)
4. **Revisión con Andrés** → elegir dirección → consolidar `DESIGN.md` definitivo.
5. **Deliverables**: 4 mockups + `DESIGN.md` final.

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
