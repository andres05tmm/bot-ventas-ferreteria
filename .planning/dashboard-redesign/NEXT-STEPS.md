# Próximos pasos — Dashboard Redesign

**Última actualización**: 2026-05-23 — Fase 0 cerrada

## Estado actual

✅ Plan completo aprobado (ver `PLAN.md`)
✅ Branch `feat/dashboard-redesign` creado desde master (no main — main estaba muy atrasado)
✅ MCPs `magic`, `shadcn`, `stitch`, `postgres` cargados
✅ **FASE 0 COMPLETADA** — 4 deliverables:
  - `PRODUCT.md` (raíz repo) — register=product, 3 usuarios, 5 principios
  - `.stitch/DESIGN.md` — baseline visual con frontmatter YAML para Stitch
  - `.planning/dashboard-redesign/AUDIT.md` — score 8/20, 32 issues mapeados a fases
  - `.planning/dashboard-redesign/baseline-screenshots/README.md` — pendiente que Andrés capture 7-8 PNGs de producción

⏸️ Fase 1 sin iniciar

## Pendiente de Andrés (asíncrono, no bloqueante)

Capturar los screenshots listados en `baseline-screenshots/README.md` antes de Fase 2 (Stitch mockups). 5-10 minutos en `bot-ventas-ferreteria-production.up.railway.app`.

## Para retomar en la próxima sesión

1. **Cleanup ligero (opcional, 30 min)** — los 2 fixes P0 más baratos del AUDIT:
   - Vaciar `dashboard/src/index.css` (hoy contiene HTML basura)
   - Quitar `maximum-scale=1.0, user-scalable=no` del viewport en `dashboard/index.html`

2. **Arrancar Fase 1 — Information Architecture nueva**:
   - Decidir patrón de navegación (sidebar agrupado vs command palette vs top-nav con grupos)
   - Agrupar los 17 tabs por dominio:
     - **Operación diaria**: Resumen, VentasRapidas, Caja, Inventario
     - **Gestión**: Clientes, Compras, Proveedores, Gastos
     - **Reportes**: Historial, HistoricoVentas, Resultados, Kardex, TopProductos
     - **Fiscal**: Facturacion, FacturasElectronicasRecibidas, LibroIVA, ComprasFiscal
   - Replantear `TabResumen` como cockpit/home (bento de KPIs + quick actions)
   - **Deliverable**: `.planning/dashboard-redesign/IA.md` con sitemap + wireframes de bajo nivel

3. **Confirmar disponibilidad de Andrés** para validar mockups en Fase 2.

## Decisiones pendientes para Fase 1

- ¿Sidebar persistente con grupos collapsibles, command palette (Cmd+K) como nav primaria, o top-nav agrupada en 4 categorías?
- ¿TabResumen es la "home" o hay un "Hoy" más operativo (caja del día + ventas pendientes + alertas)?
- ¿Dark mode es feature core o se decide en Fase 3? (PRODUCT.md dice "opcional")
- ¿Eliminamos algún tab? (TabTopProductos podría ser sección de Reportes en lugar de tab propio)

## Lo que NO se debe tocar (recordatorio)

- `useRealtime.js` (SSE) — capa de tiempo real intocable
- `routers/events.py` y `_pg_listen_worker`
- Lógica de negocio en `services/`, `routers/`, `handlers/`
- Tablas DB y migraciones
- El bot completo (`main.py`, `handlers/`, `ai/`)

Solo se rediseña la **capa de presentación** del dashboard React.
