# Plan: Rediseño completo Dashboard FerreBot

**Estado**: Plan aprobado, esperando arranque de Fase 0
**Creado**: 2026-05-23
**Aprobado por**: Andrés
**Branch sugerido**: `feat/dashboard-redesign` (todavía no creado)

---

## Decisiones tomadas

| Decisión | Valor | Razón |
|---|---|---|
| Alcance | **Rediseño completo** (nueva IA + migración a shadcn + nuevo DS) | Andrés quiere salto cualitativo, no solo restyling |
| Estilo visual | **Decidir por evidencia** — generar 3-4 mockups con Stitch primero | Evitar comprometerse a estética sin ver opciones |
| Componentes | **Migrar a shadcn/ui** | Accesibilidad gratis (Radix), consistencia, ecosistema |
| Estrategia migración | **Adapter pattern + waves por riesgo** | Cero big-bang; `shared.jsx` queda como adapter durante transición |

---

## Skills y MCPs disponibles

### Skills de diseño instalados (revisados en sesión 2026-05-23)

**Estratégicos:**
- `impeccable` ⭐ — skill líder. Sub-comandos: `teach`, `document`, `craft`, `shape`, `audit`, `live`
- `distinctive-frontend` — filosofía anti-AI-slop (4 vectores: tipo, color, motion, fondos)
- `ui-ux-pro-max` — DB de 50+ estilos, 161 paletas, 57 pairings, 99 UX guidelines
- `ckm:design`, `ckm:brand`, `ckm:design-system`, `ckm:ui-styling`

**Stitch (Google) — capa de mockups/iteración visual:**
- `stitch::extract-design-md` — extraer DS actual desde el código
- `stitch::extract-static-html` — snapshot HTML autocontenido
- `stitch::upload-to-stitch` — subir assets
- `stitch::code-to-design` — código → Stitch
- `stitch::generate-design` — generar pantallas con prompts
- `stitch::manage-design-system` — CRUD DS en Stitch
- `stitch::taste-design` — DESIGN.md anti-slop premium
- `stitch::design-md` — sintetizar DESIGN.md desde Stitch
- `stitch::enhance-prompt` — optimizar prompts para Stitch
- `stitch::stitch-loop` — loop autónomo de generación
- `react:components` — Stitch → JSX modular con AST validation
- `shadcn-ui` — guía integración shadcn

**21st Magic MCP — componentes premium puntuales:**
- `mcp__magic__21st_magic_component_builder`
- `mcp__magic__21st_magic_component_inspiration`
- `mcp__magic__21st_magic_component_refiner`
- `mcp__magic__logo_search`

### MCPs configurados (post-fix de esta sesión)

- `magic` ✅ (global)
- `shadcn` ⚠️ (configurado, requiere restart de Claude Code para cargar)
- `stitch` ⚠️ (configurado, requiere restart de Claude Code para cargar)
- `postgres` ✅ (vía `.mcp.json` del repo)

**Backup de claude.json antes del fix**: `C:\Users\Dell\.claude.json.bak-20260523-211954`

---

## Las 7 fases

### FASE 0 — Baseline y contexto (1-2 días)
- `impeccable teach` → `PRODUCT.md` (Andrés, vendedores, tono, anti-referencias, principios)
- `stitch::extract-design-md` + `extract-static-html` → baseline visual actual
- `impeccable audit` → lista priorizada de anti-patterns existentes
- **Deliverables**: `PRODUCT.md`, `DESIGN.md` (baseline), `AUDIT.md`

### FASE 1 — Information Architecture nueva (2-3 días)
- Agrupar los 17 tabs actuales por dominio:
  - **Operación diaria**: Resumen, VentasRapidas, Caja, Inventario
  - **Gestión**: Clientes, Compras, Proveedores, Gastos
  - **Reportes**: Historial, HistoricoVentas, Resultados, Kardex, TopProductos
  - **Fiscal**: Facturacion, FacturasElectronicasRecibidas, LibroIVA, ComprasFiscal
- Decidir patrón de navegación (sidebar agrupado vs command palette vs top-nav)
- Replantear `TabResumen` como cockpit/home con bento de KPIs + quick actions
- **Deliverables**: `IA.md` con sitemap + wireframes de bajo nivel

### FASE 2 — Dirección visual por evidencia (2-3 días) ⭐ PUNTO DE DECISIÓN
- Configurar proyecto Stitch, subir assets actuales
- `stitch::taste-design` → DESIGN.md anti-slop (tipo extremo, color calibrado desde `#C8200E`, layout asimétrico, micro-motion)
- Generar **3-4 mockups exploratorios** (TabResumen + TabVentasRapidas + TabCaja):
  - A: Bento minimalista (Linear-style)
  - B: Industrial denso (Bloomberg-style POS)
  - C: Glassmorphism + motion
  - D: Editorial/serio (banking-style)
- **Revisión con Andrés → elegir dirección → consolidar DESIGN.md final**
- **Deliverables**: 4 mockups + `DESIGN.md` definitivo

### FASE 3 — Design System en código (2-3 días)
- `npx shadcn@latest init` con tokens del DESIGN.md elegido
- Tokens 3 capas (primitive → semantic → component) en `tailwind.config.js`
- CSS vars en `dashboard/src/index.css`
- Tipografía nueva (font pairing + `@fontsource` o `<link>`)
- Instalar base shadcn: Button, Input, Select, Dialog, DropdownMenu, Table, Tabs, Toast, Tooltip, Card, Badge, Avatar, Command + Toaster global
- **Adapter pattern**: `shared.jsx` mantiene exports, delega a shadcn internamente
- **Deliverables**: shadcn instalado, tokens en código, `shared.jsx` como adapter

### FASE 4 — Migración por waves (8-10 días)

**Wave 1 — Bajo riesgo (2 días)**: TabResumen, TabTopProductos, TabResultados

**Wave 2 — Medio riesgo (3 días)**: TabInventario, TabClientes, TabKardex, TabHistorial, TabHistoricoVentas

**Wave 3 — Alto riesgo POS (3 días)**: TabVentasRapidas, TabCaja, TabGastos
- Testing manual exhaustivo con datos reales
- Verificar SSE (`useRealtime.js` no se toca)

**Wave 4 — Fiscal (2 días)**: TabFacturacion, TabLibroIVA, TabComprasFiscal, TabCompras, TabProveedores, FacturasElectronicasRecibidas

**Por cada tab**: `21st_magic_component_inspiration` → `react:components` o `21st_magic_component_builder` → `impeccable craft` → verificar SSE → smoke test

### FASE 5 — Componentes especiales (2-3 días)
- `ChatWidget.jsx` (refinar con `21st_magic_component_refiner`)
- `AnimatedBackground.jsx` (alinear con DS nuevo)
- Login Telegram Widget (rebranding)
- Modales globales (confirmaciones, form largos de cliente)
- Estados vacíos / loading / errores (anti-pattern actual: pantallas blancas)

### FASE 6 — Polish y audit (2 días)
- `impeccable audit` completo (6 pilares)
- `impeccable live` iteración en navegador real
- WCAG AA, responsive móvil, dark mode (si está en DS), Lighthouse > 90

### FASE 7 (opcional) — Demo (0.5 día)
- `remotion` walkthrough en video del dashboard nuevo

---

## Riesgos

| Severidad | Riesgo | Mitigación |
|---|---|---|
| CRITICAL | Romper flujo POS (TabVentasRapidas) en producción | Migración por waves; testing manual Wave 3; feature flag para volver atrás |
| HIGH | Romper SSE durante migración | `useRealtime.js` y `events.py` intocables; verificar eventos en cada tab migrado |
| HIGH | Diseño bonito pero menos productivo para Andrés | Validar mockups Fase 2 con Andrés; mantener atajos teclado; no ocultar acciones |
| HIGH | Convivencia shared.jsx + shadcn rota visualmente | Adapter pattern (Fase 3.4) garantiza coherencia |
| MEDIUM | Stitch genera diseños genéricos pese a `taste-design` | `enhance-prompt` + iteración manual del DESIGN.md |
| MEDIUM | shadcn rompe estilos custom (`AnimatedBackground`) | Migrar componentes raros al final, después de DS estable |
| MEDIUM | Bundle size crece | Tree-shaking shadcn (copy-paste, no bundle), code-splitting por tab |
| LOW | Discrepancia diseño Stitch ↔ código generado | `react:components` con AST + revisión manual |

---

## Métricas de éxito

- Lighthouse Performance > 90, Accessibility = 100
- Andrés puede registrar una venta en ≤ los clics actuales
- Cero regresiones en flujos críticos (suite manual)
- DESIGN.md vivo y mantenible
- Coherencia visual: cualquier tab nuevo hereda DS automáticamente

---

## Complejidad

**ALTA** — ~3-4 semanas trabajo enfocado
- Fase 0-2: ~5-8 días
- Fase 3: ~2-3 días
- Fase 4: ~8-10 días
- Fase 5-6: ~4-5 días

---

## Siguiente paso al retomar

Ver `NEXT-STEPS.md` en este mismo directorio.
