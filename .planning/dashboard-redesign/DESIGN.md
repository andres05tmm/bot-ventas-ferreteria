---
name: FerreBot Dashboard — DESIGN v2 (Fase 2 cerrada)
direction: Bento minimalista (Linear/Vercel-inspired)
theme: Light primario + Dark secundario
status: Locked — input para Fase 3 (Design System en código)
date: 2026-05-24
based_on:
  - Mockup A · Bento desktop (Stitch screen 8849a071721d45619c99c5dcd6a003f5)
  - Mockup Dark Mode desktop (Stitch screen ea73ca7774084295a97c405beaaa6b36)
  - PRODUCT.md (principios)
  - .planning/dashboard-redesign/IA.md (contenido del cockpit)
notes_from_andres:
  - Le gustaron estéticamente los dos mockups marcados (Bento light + Dark structural-similar)
  - Inquietud: las cifras y subtítulos se vieron MUY grandes
  - Por tanto el type scale se calibra abajo (más sobrio, mayor densidad informativa)
---

# DESIGN v2 — FerreBot Dashboard

## 1 · Dirección y principios

**Dirección**: Bento minimalista. Cards rectangulares con borde 1px y radio 12px, separadas por gaps uniformes. Sidebar persistente con grupos uppercase. Tipografía sans geométrica moderna. Color rojo `#C8200E` calibrado, nunca como fill de cards. Numbers tabular-nums.

**Referencias estéticas válidas**: Linear, Vercel dashboard, Stripe dashboard, Cron, Raycast settings.

**Anti-referencias** (heredadas de PRODUCT.md, vinculantes):
- Bootstrap/Material genérico — cards iguales icon-arriba-label-abajo.
- SAP/Siigo gris industrial sin jerarquía.
- Crypto/SaaS neón dark con glow.

**Principios calibradores** (del usuario, 2026-05-24):
- Las cifras hero NO son gritos tipográficos. Importan, pero no dominan visualmente: pierde fuerza el dashboard si todo es "número grande".
- La densidad es feature, no bug. Más información por tarjeta sin saturar.

---

## 2 · Tokens — Capa 1 (primitive)

Crudos. No se usan en componentes directamente — los consume la capa semantic.

```yaml
# Brand
brand-red-50:  "#FEF1EF"
brand-red-100: "#FCDBD6"
brand-red-200: "#F8B5AB"
brand-red-300: "#F08879"
brand-red-400: "#E25A47"
brand-red-500: "#C8200E"   # ← ancla de marca (rojo ferretería)
brand-red-600: "#A01808"
brand-red-700: "#7A1206"
brand-red-800: "#570D04"
brand-red-900: "#3A0903"

# Neutrales LIGHT (warm-tinted, no gris frío)
neutral-light-0:   "#FFFFFF"
neutral-light-50:  "#FAFAFA"   # body bg
neutral-light-100: "#F4F4F5"
neutral-light-200: "#E4E4E7"   # borders
neutral-light-300: "#D4D4D8"
neutral-light-400: "#A1A1AA"   # text muted
neutral-light-500: "#71717A"   # text sub
neutral-light-700: "#3F3F46"
neutral-light-900: "#18181B"   # text primary
neutral-light-950: "#09090B"

# Neutrales DARK (basados en zinc, no gris azulado)
neutral-dark-0:   "#FFFFFF"
neutral-dark-50:  "#FAFAFA"
neutral-dark-100: "#E4E4E7"   # text primary on dark
neutral-dark-300: "#A1A1AA"   # text sub on dark
neutral-dark-500: "#71717A"   # text muted on dark
neutral-dark-700: "#3F3F46"
neutral-dark-800: "#27272A"   # card bg
neutral-dark-900: "#18181B"   # body bg
neutral-dark-950: "#09090B"

# Señales (compartidas light+dark)
signal-success-500: "#16A34A"  # deltas positivos
signal-success-600: "#15803D"
signal-warning-500: "#EA580C"  # stock bajo
signal-warning-600: "#C2410C"
signal-danger-500:  "#DC2626"  # vencidos
signal-danger-600:  "#B91C1C"
signal-info-500:    "#0284C7"  # neutral info (poco uso)

# Espaciado (escala 4-based)
space-0: 0
space-1: "4px"
space-2: "8px"
space-3: "12px"
space-4: "16px"
space-5: "20px"
space-6: "24px"
space-8: "32px"
space-10: "40px"
space-12: "48px"
space-16: "64px"

# Radius
radius-none: 0
radius-sm:   "6px"   # chips, badges
radius-md:   "10px"  # botones, inputs
radius-lg:   "12px"  # cards (default)
radius-xl:   "16px"  # cards hero
radius-full: "9999px"

# Borders
border-1: "1px"
border-2: "2px"

# Shadows (sutiles, NO drop-shadow pesado)
shadow-xs: "0 1px 2px rgba(0,0,0,0.04)"
shadow-sm: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)"
shadow-md: "0 4px 8px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.04)"   # hover cards

# Motion
ease-out-quad: "cubic-bezier(0.25, 0.46, 0.45, 0.94)"
duration-fast:   "120ms"
duration-base:   "180ms"
duration-slow:   "280ms"

# Z-index
z-base:     0
z-sticky:  100
z-overlay: 1000
z-modal:   2000
z-toast:   3000
```

---

## 3 · Tokens — Capa 2 (semantic)

Roles semánticos. Esto es lo que consume el código. Se reasignan al cambiar tema.

### Light theme (default)

```yaml
color:
  bg-body:        "{neutral-light-50}"     # #FAFAFA
  bg-surface:     "{neutral-light-0}"      # #FFFFFF — cards
  bg-surface-2:   "{neutral-light-100}"    # hover de card, table-alt
  bg-sidebar:     "{neutral-light-0}"      # sidebar sólido blanco

  border-subtle:  "{neutral-light-200}"    # divisores hairline
  border-default: "{neutral-light-300}"    # bordes de inputs/cards
  border-strong:  "{neutral-light-700}"    # focus ring base

  text-primary:   "{neutral-light-900}"
  text-secondary: "{neutral-light-700}"
  text-muted:     "{neutral-light-500}"
  text-disabled:  "{neutral-light-400}"
  text-inverse:   "{neutral-light-0}"

  accent:         "{brand-red-500}"
  accent-hover:   "{brand-red-600}"
  accent-soft:    "{brand-red-50}"         # pill background del item activo
  accent-on:      "{neutral-light-0}"      # texto sobre accent

  success:        "{signal-success-600}"
  warning:        "{signal-warning-600}"
  danger:         "{signal-danger-600}"

  focus-ring:     "{brand-red-500}"        # outline accesible
```

### Dark theme

```yaml
color:
  bg-body:        "{neutral-dark-900}"     # #18181B
  bg-surface:     "{neutral-dark-800}"     # #27272A — cards
  bg-surface-2:   "{neutral-dark-700}"     # hover de card
  bg-sidebar:     "{neutral-dark-900}"     # sidebar sólido oscuro

  border-subtle:  "{neutral-dark-800}"
  border-default: "{neutral-dark-700}"
  border-strong:  "{neutral-dark-500}"

  text-primary:   "{neutral-dark-50}"
  text-secondary: "{neutral-dark-100}"
  text-muted:     "{neutral-dark-500}"
  text-disabled:  "{neutral-dark-700}"
  text-inverse:   "{neutral-dark-950}"

  accent:         "{brand-red-500}"        # rojo SE MANTIENE — es ancla de marca
  accent-hover:   "{brand-red-400}"        # más claro en dark para contraste
  accent-soft:    "rgba(200,32,14,0.12)"
  accent-on:      "{neutral-dark-50}"

  success:        "{signal-success-500}"   # un tick más claro en dark
  warning:        "{signal-warning-500}"
  danger:         "{signal-danger-500}"

  focus-ring:     "{brand-red-400}"
```

> **Regla**: en Fase 3 se implementan SOLO estos dos temas. Los 4 actuales (caramelo, forja, brasa, ferrari) del baseline se eliminan. Toggle: light ↔ dark, sin tercera opción.

---

## 4 · Tipografía — type scale CALIBRADA

> **Cambio crítico vs los mockups Stitch**: el tamaño hero baja ~30%. En Stitch el `$2.450.000` se veía a ~64-72px. Aquí vive a **40px máximo** y los KPIs secundarios a **32px**. Subtítulos compactos. Más densidad, menos grito.

### Font families

```yaml
font-sans:  "Inter, ui-sans-serif, system-ui, sans-serif"
font-mono:  "JetBrains Mono, ui-monospace, monospace"   # SOLO números tabulares y código
font-display: "Inter Display, Inter, sans-serif"        # alias opcional para cifras (mismas métricas)
```

Carga: `@fontsource/inter` para web fonts (no `<link>` externo para evitar FOUT en Railway).

### Size scale (calibrada — no gritos)

```yaml
text-xs:   "11px"  # eyebrows, etiquetas micro, tracking ancho
text-sm:   "13px"  # body secundario, table cells, sub-labels
text-base: "14px"  # body default
text-md:   "16px"  # body emphasis
text-lg:   "18px"  # h3, card title
text-xl:   "22px"  # h2 sección
text-2xl:  "28px"  # KPI secundario (CAJA, GASTOS)
text-3xl:  "32px"  # KPI principal compacto
text-4xl:  "40px"  # HERO max (VENTAS HOY) — TOPE DURO
```

**Comparación con baseline / mockups Stitch**:
| Elemento | Stitch generó | DESIGN v2 |
|---|---|---|
| Cifra hero VENTAS HOY | ~64-72px | **40px** |
| KPIs secundarios | ~48px | **28-32px** |
| Sublabel "17 ventas · prom $144.117" | ~16px | **13px** |
| Card title "VENTAS HOY" | ~14px | **11px uppercase tracking** |
| Body de tabla | ~14px | **13px** |

### Weights

```yaml
weight-regular:  400
weight-medium:   500    # default para data densa
weight-semibold: 600    # KPIs, card titles
weight-bold:     700    # solo CTA, cifras hero
```

### Line heights

```yaml
leading-tight:  1.15   # cifras hero
leading-snug:   1.3    # KPIs
leading-normal: 1.5    # body
leading-loose:  1.75   # raro, solo para texto largo
```

### Tracking

```yaml
tracking-tight:  "-0.02em"  # cifras hero
tracking-normal: 0
tracking-wide:   "0.06em"
tracking-wider:  "0.12em"   # uppercase eyebrows ("VENTAS HOY")
```

### Tabular nums

Todas las cifras de plata y métricas usan `font-feature-settings: "tnum" 1, "lnum" 1;` para que los dígitos alineen.

---

## 5 · Tokens — Capa 3 (component)

Subset de los más usados — el resto se deriva en Fase 3 cuando se monten shadcn components.

### Card

```yaml
card:
  bg:          "{color.bg-surface}"
  border:      "{border-1} solid {color.border-default}"
  radius:      "{radius-lg}"             # 12px
  padding:     "{space-5}"               # 20px
  gap:         "{space-3}"               # entre elementos internos
  hover-bg:    "{color.bg-surface-2}"
  shadow:      "{shadow-xs}"             # sutil base
  shadow-hover:"{shadow-sm}"
```

### KpiCard (especialización de Card)

```yaml
kpi-card:
  extends:        card
  label:
    size:         "{text-xs}"           # 11px
    weight:       "{weight-medium}"
    transform:    uppercase
    tracking:     "{tracking-wider}"
    color:        "{color.text-muted}"
  value-hero:                            # SOLO el primer KPI ("VENTAS HOY")
    size:         "{text-4xl}"          # 40px — calibrado abajo
    weight:       "{weight-semibold}"   # no bold absoluto
    tracking:     "{tracking-tight}"
    color:        "{color.text-primary}"
    features:     "tnum, lnum"
  value-default:                         # KPIs no-hero (CAJA, GASTOS)
    size:         "{text-3xl}"          # 32px
    weight:       "{weight-semibold}"
    color:        "{color.text-primary}"
    features:     "tnum, lnum"
  sublabel:
    size:         "{text-sm}"           # 13px
    weight:       "{weight-regular}"
    color:        "{color.text-muted}"
  delta-positive: "{color.success}"
  delta-negative: "{color.danger}"
```

**Prohibido en KpiCard** (anti-patrón heredado del actual `shared.jsx`):
- Side-accent vertical de color (el "side-stripe disfrazado" del AUDIT).
- Icon-arriba-label-abajo bento genérico.
- Gradientes en background.

### Sidebar

```yaml
sidebar:
  width-expanded:  "240px"
  width-collapsed: "64px"
  bg:              "{color.bg-sidebar}"
  border-right:    "{border-1} solid {color.border-subtle}"
  padding:         "{space-4}"

  logo:
    size:          "{text-md}"
    weight:        "{weight-semibold}"
    tracking:      "{tracking-wide}"
    color:         "{color.text-primary}"

  group-header:
    size:          "{text-xs}"         # 11px
    weight:        "{weight-medium}"
    transform:     uppercase
    tracking:      "{tracking-wider}"
    color:         "{color.text-muted}"
    padding-y:     "{space-3}"

  item:
    size:          "{text-sm}"         # 13px
    weight:        "{weight-medium}"
    color:         "{color.text-secondary}"
    padding:       "{space-2} {space-3}"
    radius:        "{radius-md}"
    gap:           "{space-2}"         # entre icon y label

  item-hover:
    bg:            "{color.bg-surface-2}"
    color:         "{color.text-primary}"

  item-active:
    bg:            "{color.accent-soft}"
    color:         "{color.accent}"
    border-left:   "3px solid {color.accent}"
    weight:        "{weight-semibold}"
```

### Button

```yaml
button:
  radius:          "{radius-md}"
  padding-y:       "{space-2}"
  padding-x:       "{space-4}"
  size:            "{text-sm}"
  weight:          "{weight-medium}"

  primary:
    bg:            "{color.accent}"
    color:         "{color.accent-on}"
    hover-bg:      "{color.accent-hover}"

  ghost:
    bg:            transparent
    color:         "{color.text-secondary}"
    hover-bg:      "{color.bg-surface-2}"

  outline:
    bg:            transparent
    border:        "{border-1} solid {color.border-default}"
    color:         "{color.text-primary}"
    hover-bg:      "{color.bg-surface-2}"
```

### Table (densa, no zebra agresivo)

```yaml
table:
  font:            "{font-sans}"
  size:            "{text-sm}"          # 13px
  weight:          "{weight-medium}"

  header:
    size:          "{text-xs}"
    weight:        "{weight-semibold}"
    transform:     uppercase
    tracking:      "{tracking-wide}"
    color:         "{color.text-muted}"
    border-bottom: "{border-1} solid {color.border-default}"
    padding:       "{space-2} {space-3}"

  row:
    padding:       "{space-3}"
    border-bottom: "{border-1} solid {color.border-subtle}"

  row-hover:
    bg:            "{color.bg-surface-2}"

  numeric-cell:
    features:      "tnum, lnum"
    align:         right
```

### Badge

```yaml
badge:
  size:            "{text-xs}"          # 11px
  weight:          "{weight-semibold}"
  padding:         "2px {space-2}"
  radius:          "{radius-sm}"

  warning:    { bg: "rgba(234,88,12,0.12)",  color: "{color.warning}" }
  danger:     { bg: "rgba(220,38,38,0.12)",  color: "{color.danger}" }
  success:    { bg: "rgba(22,163,74,0.12)",  color: "{color.success}" }
  neutral:    { bg: "{color.bg-surface-2}",  color: "{color.text-muted}" }
```

---

## 6 · Layout — grid del Cockpit HOY

Re-confirmado contra IA.md, ahora con tokens reales:

```
┌─────────────┬──────────────────────────────────────────────────────────────┐
│ Sidebar     │ Header sticky (64px alto, border-bottom 1px subtle)          │
│ 240px       ├──────────────────────────────────────────────────────────────┤
│             │ Content padding: space-6 (24px) en desktop, space-4 móvil   │
│             │                                                              │
│             │ Bento gap: space-4 (16px) entre cards                        │
│             │                                                              │
│             │ Grid columnas:                                               │
│             │   - desktop ≥1280: 3 cols (1fr 1fr 1fr) para fila KPI       │
│             │                    2 cols (1fr 1fr) para acumulados+pagos   │
│             │                    1 col full-width para tabla ventas       │
│             │   - tablet 768-1279: 2 cols                                  │
│             │   - mobile <768: 1 col stack                                 │
│             │                                                              │
│             │ Container max-width: 1440px centered                         │
└─────────────┴──────────────────────────────────────────────────────────────┘
```

**Densidad por zona** (calibrada según feedback):
- Fila KPIs (top): cards de **min-height 140px** (antes mockup ~180-200px). Más compactos.
- Fila acumulados + métodos pago: cards de **min-height 160px**, sparkline 60px alto.
- Tabla últimas ventas: **filas de 36px** (densa, no 56px estilo email client).
- Fila stock + fiados: cards de **min-height 200px**, lista 5 items visibles sin scroll.

---

## 7 · Motion (sutil, reduce-motion respetado)

```yaml
hover-card:
  transform:     "translateY(-1px)"
  shadow:        "{shadow-sm}"
  transition:    "all {duration-fast} {ease-out-quad}"

focus-visible:
  outline:       "2px solid {color.focus-ring}"
  outline-offset:"2px"

reduce-motion:
  - desactivar transform en hover
  - desactivar AnimatedBackground
  - mantener focus outlines (accesibilidad)
```

**Sin parallax. Sin scroll-jacking. Sin Lottie decorativo.**

---

## 8 · Accesibilidad (no-negociable)

- Contraste WCAG AA mínimo: ratio 4.5:1 en text-primary sobre bg, 3:1 en text-muted.
- Focus visible siempre con `:focus-visible`, color `accent`.
- Targets táctiles ≥ 44×44px en cualquier acción de POS (TabVentasRapidas, TabCaja).
- `prefers-reduced-motion: reduce` desactiva micro-motion de hover, congela AnimatedBackground.
- `prefers-color-scheme` se respeta como default — usuario puede override manual.
- Sin dependencia exclusiva de color para estados (badges incluyen ícono + texto).

---

## 9 · Diferencias vs baseline `.stitch/DESIGN.md`

| Aspecto | Baseline | DESIGN v2 |
|---|---|---|
| Temas | 4 (caramelo / forja / brasa / ferrari) | **2** (light + dark) |
| Rojo marca | `#C8200E` + variantes hex paralelas | **escala 50-900 generada** |
| Tipografía | sin token unificado | **Inter + JetBrains Mono** |
| Type scale | inconsistente | **calibrada, hero tope 40px** |
| KpiCard | side-stripe vertical de color | **eliminado** |
| Tokens | 1 capa (hex directos) | **3 capas (primitive/semantic/component)** |
| Tabular nums | no | **sí, en cifras** |
| Dark mode | múltiples | **único, basado en zinc** |

---

## 10 · Lo que NO se decide aquí (queda para Fase 3 / 4)

- Cuál tema arranca por defecto (`prefers-color-scheme` resuelve por sistema).
- Migración de `shared.jsx` componente por componente (adapter pattern de PLAN.md).
- Estados vacíos/loading/error — vendrán con cada tab en Fase 4.
- Sparkline lib (Recharts? Visx? Tremor?) — decisión técnica de Fase 3.
- Iconos (Lucide? Heroicons?) — decisión técnica de Fase 3.
- Configuración exacta de `tailwind.config.js` (los semantic tokens van como CSS vars + plugin).

---

## 11 · Aceptación

Este DESIGN se considera **locked** cuando Andrés confirma. Cambios posteriores entran como deltas con commit propio en `feat/dashboard-redesign`.

**Confirmación esperada**: "ok, arranca Fase 3" o ajustes específicos.
