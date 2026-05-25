# Próximos pasos — Dashboard Redesign

**Última actualización**: 2026-05-24 — Wave 3.c COMPLETADA · Wave 4 2/6 (FacturasElectronicasRecibidas + TabLibroIVA)

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

✅ **FASE 3 COMPLETADA** (2026-05-24):
  - `dashboard/tailwind.config.js` + `postcss.config.js` con tokens primitive (brand-red 50-900, escala 4-based, type scale calibrada, radii, shadows)
  - `dashboard/src/index.css` con CSS vars semantic light + dark + auto `prefers-color-scheme`, focus-visible, reduce-motion
  - `dashboard/components.json` + `src/lib/utils.js` (`cn()`) + alias `@` en `vite.config.js`
  - Inter cargada vía `@fontsource/inter` (400/500/600/700) en `main.jsx`
  - Primitives shadcn en `src/components/ui/`: button, card, input, label, badge, tooltip, dialog, select, dropdown-menu, table, tabs, avatar, command, sonner (Toaster)
  - `Toaster` montado globalmente en `App.jsx`
  - `shared.jsx` con nota de adapter (Fase 4 migra cada tab a `ui/*`)
  - `npm run build` verde, sin regresiones visuales en tabs legacy
  - **Deliverable**: design system en código operativo, listo para Fase 4

🚧 **FASE 4 — Wave 1.a EN CURSO** (2026-05-24):
  - ✅ Shell nuevo: `Sidebar.jsx` (240px desktop, colapsable, grupos Operación/Gestión/Reportes/Fiscal + Hoy top-level) y `MobileNav.jsx` (5 botones + drawer)
  - ✅ Router real: `App.jsx` con `react-router` y 17 rutas (`/hoy`, `/ventas`, `/caja`, etc.). `/` redirige a `/hoy`
  - ✅ `routes.jsx`: fuente única de verdad consumida por Sidebar, MobileNav y CommandPalette
  - ✅ `TabHoy.jsx` cockpit (bento: ventas/caja/gastos, acumulados, métodos de pago, últimas 8 ventas, alertas stock, quick actions)
  - ✅ `CommandPalette.jsx` (⌘K/Ctrl+K, ⌘N nueva venta) con navegación + acciones rápidas
  - ✅ `HeaderBar.jsx` simplificado (título de ruta + vendor selector + refresh + bot status)
  - ✅ `AppShell.jsx` con tema light/dark (data-theme en html, persiste en localStorage, respeta prefers-color-scheme); `ThemeContext` legacy mapea caramelo↔forja para tabs aún no migradas
  - ✅ `npm run build` verde (1.9MB main, 7.7KB css gzipped)
  - ✅ **Wave 1.b completada** (2026-05-24): migrados a primitives `ui/*` + tokens semantic
    - `TabResumen.jsx`: KPIs en grid de Cards, AreaChart con CSS vars, métodos de pago + top 5 + vendedores. Sin THEMES legacy
    - `TabTopProductos.jsx`: reescrito limpio. Chips de criterio, barras inline (sin SVG custom), tabla shadcn, categorías como cards
    - `TabResultados.jsx`: shadcn Tabs internas — P&L (default) + Top productos (TabTopProductos embedded). EstadoResultados, GraficaHistorica, ProyeccionCaja tokenizados
    - `npm run build` verde (8.04 KB css gzipped)
  - 🚧 **Wave 2 parcial completada** (2026-05-24): 4/5 tabs migradas a primitives `ui/*` + tokens
    - `TabKardex.jsx`: cards de productos colapsables, tabla movimientos con badges Entrada/Salida tokenizados (226 → 220 LOC)
    - `TabClientes.jsx`: tabla densa desktop + lista mobile, Avatar shadcn, modales con `Dialog`+`Label`+`Input`, paginación con `Button`, edición/eliminación (792 → 470 LOC)
    - `TabHistorial.jsx`: KPIs + filtros pagado/pendiente, tabla con badges método tokenizados, modal editar y eliminar (con eliminación granular por línea de venta multi-producto), export a Excel via `DropdownMenu` shadcn (676 → 480 LOC)
    - **Fusión Historial + Histórico**: pospuesta — ambas conviven en `/historial` (transacciones del día tokenizado) y `/historico` (calendario mensual legacy). Cmd+K solo apunta a `/historial`
    - `npm run build` verde (8.35 KB css gzipped, 555 KB js gzipped)
  - ✅ **Wave 2.b completada** (2026-05-24): `TabInventario.jsx` reescrito (1328 → 765 LOC). PrecioInline/StockInline/FraccionesEditor/MayoristaInline + 3 modales (Crear/Editar/Eliminar) migrados a `Dialog`+`Button`+`Input`+`Label` shadcn. Cards de categoría con `Card`, subcategorías como chips tokenizadas, tabla densa desktop y MobileProductCard. Icons via lucide-react (Pencil/Trash2/Plus/Search/ChevronUp/Down/Check/X/AlertCircle/Package/Loader2). `UNIDAD_COLORES` hex → `UNIDAD_CLASS` tokens (warning/success/primary). Sin `useTheme()` ni inline styles. `npm run build` verde (8.60 KB css gzipped, 553 KB js gzipped)
  - ✅ **Wave 3.a completada** (2026-05-24): POS — Caja + Gastos
    - `TabCaja.jsx` (415 → 330 LOC): toast con sonner global, `Dialog` confirmar cierre, `Dialog` venta varia, KPIs Card+lucide, tabla gastos del día tokenizada
    - `TabGastos.jsx` (323 → 310 LOC): **`ModalRegistrarGasto` exportado como named export (listo para reuso en Fase C desde el POS)**, gráficas con colores `hsl(var(--*))` tokenizados, period selector chips, tabla tokenizada
    - `npm run build` verde (8.63 KB css gzipped, 555 KB js gzipped)
  - ✅ **Wave 3.b COMPLETADA** (2026-05-24): `TabVentasRapidas.jsx` (**2911 → 2382 LOC**). 7/7 sub-tareas completadas en sesión dedicada:
    - ✅ **1. Constantes/helpers** (commit `2796e58`): nuevo archivo `dashboard/src/tabs/ventasRapidas.helpers.js` (154 LOC) con `FAV_KEY`/`CART_KEY` + load/save, `CAT_ICON`/`iconCat`/`catLabel`, `nl`, `SUBCATS`, `ordenarTornilleria`, `tipoProd`, `GRUPOS_CONFIG`/`SUBCATS_COLORES`/`buildGrupos`. Mismas claves storage (`vr_favs_v2`/`vr_carrito_v1`)
    - ✅ **2. ProdCard + Seccion** (commit `b48a544`): `<Card>` shadcn con `bg-primary-soft`/`border-primary` cuando hay items en carrito, `ring-primary` highlighted. Estrella favorito → lucide `<Star fill-current />`. Badges cantidad/tipo (cm/ml/gr/kg/fracción) tokenizados. `Seccion` sin `useTheme`
    - ✅ **3. PanelCarrito + CartItem** (commit `e4ad1d3`): tokens shadcn (`bg-card`, `bg-primary-soft`, `border-border`), `animate-in fade-in slide-in`, iconos lucide `Trash2`/`ShoppingCart`. Multiplicadores (×1/×2/×3/×5/×10) y edición de cantidad intactos. Toggle "calcular cambio" tokenizado
    - ✅ **4. Modales (×9) a Dialog shadcn** (commit `9edf12b`): `Modal` base montado sobre `<Dialog>` preservando API → los 6 modales hijos (Fraccion/Cm/Mlt/Grm/Kg/Qty) heredan el shell sin tocar lógica interna. `ModalCheckout`/`ModalMiscelanea`/`ModalColorPreparado` reescritos con Dialog y tokens. `PrecioEditor` tokenizado (warning/primary). `createPortal`/`getPortalRoot` se conservan para FAB/drawer móvil
    - ✅ **5. SelectorCliente + reuso ModalCliente** (commit `92f1e18`): `ModalCliente` ahora es **named export** desde `TabClientes.jsx` con prop opcional `nombreInicial`. `ModalNuevoCliente` eliminado (~260 LOC duplicadas borradas). `SelectorCliente` reescrito con tokens (`bg-muted`, `bg-primary-soft`) e iconos lucide `User`/`Plus`/`X`/`Loader2`. Prop `t` removido de `PanelCarrito` y sus dos call sites
    - ✅ **6. VistaGrupos + GrupoColores** (commit `04dfa11`): `GrupoColores` con `<Card>` shadcn, pills `bg-primary-soft+border-primary` en carrito, "ver más" con `border-dashed`, "color preparado" con `border-primary/40`. Grids de sueltas con columnas dinámicas vía inline `style` (Tailwind no genera `repeat(N)` en build)
    - ✅ **7. Shell del tab + smoke test** (commit `cbdbc6d`): `TabVentasRapidas` sin `useTheme()`. Filtros y subcats como chips `bg-primary-soft+border-primary`, buscador con `Input` shadcn + icono `Search` lucide, vista vacía de favoritos con `Star` lucide `fill-current`. FAB móvil (barra fija inferior) y drawer del carrito a tokens (`bg-card`, `border-border`, `ShoppingCart`/`X`/`Loader2`); toggle calcular cambio conservado. Toasts via `bg-success`/`border-destructive` y animaciones movidas a `<style>` global del tab. Imports nuevos: `Search`, `Sparkles` (lucide), `Input` (ui). Claves storage intactas (`vr_favs_v2`/`vr_carrito_v1`/`vr_vendedor`). Modales internos (Fraccion/Cm/Mlt/Grm/Kg/Qty) heredan el shell Dialog ya migrado en sub-tarea 4 — sus internals con `useTheme()` quedan fuera del scope de Wave 3.b
    - Commit + build verde tras cada sub-tarea (último build: 9.39 KB css gzipped, 552.85 KB js gzipped)
    - Riesgo ALTO: tab crítico de operación diaria. Mantener mismas claves localStorage (`vr_favs_v2`) y sessionStorage (`vr_carrito_v1`) ✅ preservadas
  - ✅ **Wave 3.c COMPLETADA** (2026-05-24, commit `f06b79e`): atajos POS
    - `CajaStatusPill` en `HeaderBar.jsx`: fetch `/caja`, pill verde (`bg-success/10` + efectivo esperado en >=xl) o muted (cerrada). Click navega a `/caja`. Refresca con `refreshKey` global (ya disparado por SSE `caja_abierta`/`caja_cerrada`)
    - `ModalRegistrarGasto` reusado en `TabVentasRapidas`: nuevo botón "Registrar gasto" junto a "Venta miscelánea". SSE `gasto_registrado` dispara el refresh global, `onSaved` es no-op
    - `AppShell` ahora pasa `refreshKey` a `HeaderBar`
    - `npm run build` verde (9.47 KB css gzipped, 553.20 KB js gzipped)
  - 🚧 **Wave 4 EN PROGRESO — Fiscal** (2/6 tabs migradas):
    - ✅ **FacturasElectronicasRecibidas.jsx** (292 → 282 LOC, commit `6d2b38c`, 2026-05-24): tokens shadcn, `Card`/`Dialog`/`Label`/`Button`, iconos lucide (Mail/Clock/CheckCircle2/AlertTriangle/Inbox/Loader2), `BadgeEvento` con `bg-success`/`bg-border`, `ModalReclamo` con Dialog, toasts via sonner. Build: 9.51 KB css gz / 553.42 KB js gz
    - ✅ **TabLibroIVA.jsx** (582 → 764 LOC, commit `f7a95e7`, 2026-05-24): banner RST + selector bimestral/custom con chips `bg-primary-soft+border-primary`, KPIs con `Card`+tonos primary/success/warning (Receipt/ShoppingCart/Scale lucide), `CuadroNeto` tokenizado (IVA generado primary, descontable success, resultado favor/pago), `HistorialCierres` con tabla tokenizada y `Button` shadcn (Lock/RefreshCw), `TablaVentasFE`/`TablaComprasIVA` con cabecera `bg-muted`, chips de tarifa `primary-soft`/`success/10`, `ModalCierre` migrado a `Dialog`+`Label`+`Input`, toasts via sonner. LOC subió por verbosidad de Tailwind classNames vs inline styles. Build: 9.64 KB css gz / 554.13 KB js gz
    - ⏸️ Pendientes (orden sugerido): TabFacturacion (780) → TabCompras (859) → TabProveedores (866) → TabComprasFiscal (1697)

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
