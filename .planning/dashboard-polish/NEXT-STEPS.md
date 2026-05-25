# Next Steps — Después de mergear `feat/dashboard-polish`

**Última actualización**: 2026-05-25
**Branch origen**: `feat/dashboard-polish` (5 commits, 5 fases del PLAN cerradas)

---

## 🔴 Inmediato — Después del merge

### 1. QA visual en deploy de Railway
Probar tab por tab en light + dark mode:
- [ ] **Hoy** — verificar Aurora bg sutil (no debe distraer), tints de KPIs, sparkline en Ventas, toggle 7d/30d del chart, pulse-dot del feed live
- [ ] **Historial** — switch Día/Mes con `?view=mes` en URL, vista Mes con calendario heatmap y nav
- [ ] **Proveedores** — sin sub-header duplicado, sin panel facturas embebido al final
- [ ] **Sidebar** — sin item "Resumen", item activo legible en dark (este fue el bug bloqueante de Fase A)
- [ ] **MobileNav** — bottom bar funciona con los nuevos iconos
- [ ] **CommandPalette** (Ctrl+K) — no muestra Resumen, sí muestra todo lo demás

### 2. Lighthouse re-medición
Comparar contra el baseline de `dashboard-redesign`:
- Baseline (post-merge PR #2): **Desktop 100/100, Mobile 91/100** (de `.planning/dashboard-redesign/AUDIT-F6.md`)
- Esperado: Performance debería mantenerse (Aurora bg es CSS estático sin blur ni animación). A11y puede mejorar levemente por el fix de contraste Fase A.

Si Perf cae <90 mobile, revisar:
- `body::before` con 3 gradients — fácil de simplificar a 2 si necesario
- Las animaciones nuevas (pulse-dot, hover lift) — todas usan `transform`/`opacity` (GPU)

### 3. Redirects funcionando
Probar que estos links viejos no se rompen:
- `/resumen` → debe redirigir a `/hoy`
- `/historico` → debe redirigir a `/historial?view=mes`

---

## 🟡 Backlog — Por priorizar

### Deuda técnica abierta

#### Contraste WCAG en dark mode
En Fase A se aplicó el alpha-tint de `bg-primary-soft`, pero el par `bg-primary-soft text-primary` en dark queda con contraste ~2.5:1 (visible, pero por debajo de AA 4.5:1). Tres caminos posibles:

1. **Lighten `--accent` en dark** a `brand-400` (`#E25A47`). Trade-off: botones `bg-primary` filled bajan a 3.6:1 white-on-red (AA Large, no AA normal).
2. **`dark:text-brand-300` quirúrgico** en los 16 archivos donde aparece `bg-primary-soft text-primary`. Más invasivo, sin tocar tokens globales.
3. **Dejar como está**. Legible aunque marginal — si nadie se queja, no es problema.

#### Pendiente de TabResumen no migrado a Hoy
La consolidación Fase C absorbió en Hoy: KPIs principales, evolución, métodos de pago, top productos, alertas stock. **Faltó**: ranking de vendedores del día (`Vendedores · Hoy`). Era una `Card` condicional admin-only en el viejo TabResumen. Migrar cuando se priorice — usar la misma agregación que `agruparVendedores()` (campo `v.vendedor` en `/ventas/hoy`).

### Componentes del catálogo 21st.dev — Wave 2/3

Plan curado de la sesión (orden recomendado):

| Wave | Componente | Tabs afectados | Estimación |
|---|---|---|---|
| Wave 2 | Data Table avanzada (TanStack + shadcn): filtros, sort, paginación, row actions, column visibility | Historial / Inventario / Compras | ~3h |
| Wave 3 | Sheet (drawer lateral) para detalle de movs y facturas | Caja / Proveedores | ~1.5h |
| Wave 3 | Command Palette (Ctrl+K) extendida con acciones rápidas | Global | ~2h |
| Backlog | Calendar heatmap estilo GitHub contributions | Histórico (mejora visual de VistaMes) | ~2h |
| Backlog | Combobox + multi-filter chips | Inventario | ~1h |
| Backlog | Stepper / Wizard | Facturación electrónica | ~2h |
| Backlog | Date range picker (Calendar shadcn) | Libro IVA | ~1h |
| Backlog | Skeleton loaders elegantes | Global (reemplaza spinners) | ~1h |
| Backlog | Empty states con ilustración | Global | ~1h |

---

## 🟢 Otras observaciones de la sesión

### Mockups guardados
Los 3 HTMLs de Fase B (`aurora.html`, `forja.html`, `bento.html`) + `index.html` quedan commiteados en `.planning/dashboard-polish/mockups/`. Útiles como:
- Referencia visual del look final (Aurora) para comparar futuras evoluciones.
- Tooling probado: si en el futuro hay que iterar visualmente otra vez, este patrón (HTML estático + Tailwind CDN + Google Fonts) funcionó mejor que Stitch MCP (que dio timeout repetido).

### MCPs probados y su utilidad real
- ✅ **shadcn MCP** — útil para descubrir patrones.
- ⚠️ **Stitch MCP** — generaciones tardan demasiado, timeout antes de devolver. Útil para review de proyectos existentes, no como herramienta de generación bajo presión.
- ✅ **Magic / 21st.dev** — buena para descubrir componentes específicos. Cuidado con el tamaño de las respuestas (algunas pasan los 250K tokens). Usar `searchQuery` corto (2-4 palabras max).
- ❌ **ui-ux-pro-max skill** — el bulk de los datos (palettes, fonts) vive en scripts Python que no están instalados con la skill; solo está SKILL.md. Sirve como guía de principios, no como motor de búsqueda.

### Patrones a mantener en futuras fases
- Commit por fase con header `tipo(scope): descripción (Fase X)`
- Subagentes/redirects para no romper links de usuarios
- Documentar deuda en NEXT-STEPS.md inmediatamente, no dejar para "después"
- Cuando una decisión visual tiene >1 camino, ofrecer mockups locales — Andrés decide más rápido viendo

### Pendientes administrativos
- [ ] Limpieza eventual de `.planning/dashboard-polish/mockups/` cuando ya no se necesiten como referencia (decisión post-deploy)
- [ ] Actualizar `CLAUDE.md` con la ruta nueva `tabs/historial/` y el patrón Tabs interno si se vuelve común
