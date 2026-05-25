# Plan — Pulido visual + UX del dashboard (post-merge)

**Origen**: feedback de Andrés tras mergear `feat/dashboard-redesign` a `main` (PR #2, commit `a9e7304`).
**Branch sugerida**: `feat/dashboard-polish`
**Fecha**: 2026-05-25

## Contexto inicial

Dashboard rediseñado vive en `main` con tokens shadcn (light + dark), 18 tabs, lazy loading, Lighthouse desktop 100/100, mobile 91/100. Detalles de la milestone cerrada en `.planning/dashboard-redesign/NEXT-STEPS.md` y `AUDIT-F6.md`.

Andrés probó la versión live y reportó 4 problemas + 1 pedido global de "menos aburrido". Este plan cierra eso.

## Requirements restatement

1. **🔴 CRITICAL — Dark mode contrast bug**: en dark mode, `bg-primary-soft text-primary` (sidebar activo, chips, KPIs rojos, "Caja cerrada", tabs activos de Proveedores) queda rojo sobre rojo → texto invisible. Causa raíz: `index.css` define `--accent-soft: 6 87% 42%` en dark mode (mismo H/L que `--accent`). Bloquea usabilidad.

2. **🟡 MEDIUM — Visual flatness ("aburrido")**: paleta muy neutra, fondos planos, sin diferenciación entre superficies. Querés más variación cromática y un fondo que respire (sin volver al `AnimatedBackground` viejo).

3. **🟡 MEDIUM — Hoy + Resumen consolidación**: duplican datos (Ventas hoy, ticket promedio, semana, mes). Unificar en **Hoy** + traer Evolución de ventas con mejor diseño. Reducir tipografía invasiva (la palabra "Cerrada" ocupa pantalla completa, los `$0` también).

4. **🟡 MEDIUM — Historial vs Histórico**: en Fase 1 se decidió unificar pero quedaron las dos rutas (`/historial` día, `/historico` calendario mensual). Comentario en `TabHistorial.jsx:5-6` lo admite: "la fusión se difiere a Wave 3". Deuda pendiente.

5. **🟢 LOW — TabProveedores proporciones**: título duplicado vs HeaderBar, panel "Facturas electrónicas recibidas" anidado dentro del tab (debería vivir solo en `/facturas-recibidas`), grid de KPIs distinto al de otros tabs.

## Implementation phases

### Fase A — Hotfix dark mode contrast (CRITICAL, ~30 min)

- **A.1** Cambiar `bg-primary-soft` en `tailwind.config.js` → `hsl(var(--accent) / 0.15)` (alpha). Un solo cambio cubre light + dark sin tocar HSL tokens.
- **A.2** Auditar pares `bg-*-soft text-*` (success/warning/destructive) en dark mode con skill `impeccable` "audit". Documentar contraste WCAG.
- **A.3** Validar con `npx serve -s dist -l 5050` + DevTools dark mode toggle.

**Riesgo**: BAJO.

### Fase B — Variación cromática + fondo (MEDIUM, ~1.5h)

- **B.1** Usar skill `ui-ux-pro-max` para explorar 2-3 direcciones manteniendo brand red como acento principal:
  - **Gradient mesh sutil** en `--bg-body` (3-4% opacity, fixed, no anima)
  - **Surface elevation tiers** — `--bg-surface-1/2/3` más perceptibles
  - **Accent tints secundarios** para KPIs (usar success/info/warning más, no todo rojo)
- **B.2** Validar con Stitch MCP (`stitch-design:generate-design`) 2 variantes.
- **B.3** Aplicar la dirección elegida sin tocar `--accent` ni semantic tokens existentes.

**Riesgo**: MEDIO (over-design). Mitigación: medir Lighthouse antes/después; rechazar cambios que bajen Perf <90.

### Fase C — Unificar Hoy + Resumen (MEDIUM, ~2h)

- **C.1** Inventario de datos:
  - **Hoy**: ventas hoy, caja, gastos hoy, acumulados (semana/mes), métodos de pago, últimas ventas, alertas stock, quick actions
  - **Resumen**: ventas hoy, pedidos hoy, stock alerta, ticket promedio, total semana, total mes, evolución 7d/mes, métodos de pago hoy, top 5 productos
  - **Único de Resumen a integrar**: evolución de ventas (chart), top 5 productos
- **C.2** Rediseñar TabHoy en 3 zonas:
  - **Zona 1 — Glance**: 3 KPI cards (Ventas / Caja / Gastos) tipografía calibrada (no `text-6xl`). "Cerrada" → badge tamaño normal + CTA "Abrir caja" prominente.
  - **Zona 2 — Evolución**: chart compact (200px alto, toggle 7d/30d), refinado.
  - **Zona 3 — Operativa**: últimas ventas + top productos + alertas stock + quick actions en grid 2x2 o tabs.
- **C.3** Eliminar ruta `/resumen` (redirect → `/hoy`). Sacar Resumen del sidebar. Borrar `TabResumen.jsx`.
- **C.4** Actualizar Command Palette + `routes.jsx`.

**Riesgo**: MEDIO. Feature-parity audit antes de borrar Resumen.

### Fase D — Unificar Historial + Histórico (MEDIUM, ~1.5h)

- **D.1** Una sola tab "Historial" con switch de vista:
  - **Vista Día** (default, actual `/historial`): tabla de ventas con filtros, exportar, editar/eliminar.
  - **Vista Mes** (actual `/historico`): calendario heatmap mensual, KPIs del mes, nav meses.
- **D.2** Tabs internos shadcn `<Tabs>` "Día | Mes". Persistir en URL search param (`?view=mes`).
- **D.3** Eliminar `/historico` (redirect → `/historial?view=mes`). Borrar `TabHistoricoVentas.jsx` (su contenido inline en la vista Mes).

**Riesgo**: BAJO.

### Fase E — TabProveedores layout fix (LOW, ~45 min)

- **E.1** Eliminar título duplicado "Proveedores" interno (HeaderBar ya lo muestra).
- **E.2** Mover "Facturas electrónicas recibidas" exclusivamente a su ruta `/facturas-recibidas` (sacarla del interior de Proveedores).
- **E.3** Normalizar grid de KPI cards al patrón de otros tabs (`grid-cols-4` desktop, gap consistente).
- **E.4** Spacing del CTA "Nueva Factura" alineado con otros tabs.

**Riesgo**: BAJO.

### Fase F — QA + cierre (~30 min)

- Build, Lighthouse re-medición (Perf mantenerse, A11y debería mejorar por fix contraste), QA visual tab por tab en light + dark.
- Commits separados por fase. PR `feat/dashboard-polish` a `main`.

## Dependencies

- **Skills**: `impeccable` (audit + iterate), `ui-ux-pro-max` (palette), opcional `stitch-design:generate-design`.
- **MCPs**: `shadcn` (componentes nuevos si faltan, ej. Tabs), `stitch` (variantes visuales).
- **Sin cambios de backend.**

## Risks

| Severidad | Riesgo | Mitigación |
|---|---|---|
| HIGH | Fase B termina en over-design (bonito pero lento) | Medir Lighthouse antes/después de B; rechazar cambios que bajen Perf <90 |
| MEDIUM | Borrar `/resumen` rompe links guardados | Redirect 301 desde `/resumen` → `/hoy` |
| MEDIUM | Unificar Historial/Histórico complica el componente | Sub-componentes `HistorialDia` + `HistorialMes`; la ruta y tabs los envuelven |
| LOW | Fase B introduce regresiones dark mode | QA dark obligatorio en cada commit |

## Estimated complexity: MEDIUM

| Fase | Tiempo | Severidad |
|---|---|---|
| A — Dark mode contrast | 30 min | CRITICAL |
| B — Variación cromática | 1.5 h | MEDIUM |
| C — Hoy + Resumen | 2 h | MEDIUM |
| D — Historial + Histórico | 1.5 h | MEDIUM |
| E — Proveedores | 45 min | LOW |
| F — QA + cierre | 30 min | — |
| **Total** | **~6.5 h** | |

**Fase A es no-negociable** (bug bloqueante). Resto se puede partir en PRs separados.

## Estado de aprobación

- [ ] Plan aprobado por Andrés (esperando confirmación post-/clear)
- [ ] Branch creada (`feat/dashboard-polish`)
- [ ] Fase A ejecutada
- [ ] Fase B ejecutada
- [ ] Fase C ejecutada
- [ ] Fase D ejecutada
- [ ] Fase E ejecutada
- [ ] Fase F ejecutada
- [ ] PR creada
- [ ] PR mergeada
