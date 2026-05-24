---
name: FerreBot Dashboard — Baseline (pre-rediseño)
colors:
  # Identidad — rojo ferretería
  brand-red: "#C8200E"
  brand-red-hover: "#A01808"
  ferrari-red: "#DA291C"
  brasa-red: "#F03418"
  forja-red: "#E83020"

  # Tema "caramelo" (light, default)
  light-bg: "#F8F5F1"
  light-card: "#FFFFFF"
  light-card-hover: "#FEFCF9"
  light-border: "#EAE4DC"
  light-border-soft: "#F0EBE3"
  light-text: "#1C1410"
  light-text-sub: "#4A3F35"
  light-text-muted: "#9C8E82"
  light-table-alt: "#FDFAF6"

  # Tema "forja" (dark, GitHub-like)
  forja-bg: "#0D1117"
  forja-card: "#161B22"
  forja-card-hover: "#1C2128"
  forja-border: "#21262D"
  forja-text: "#E6EDF3"
  forja-text-sub: "#8B949E"
  forja-text-muted: "#484F58"

  # Tema "brasa" (dark warm)
  brasa-bg: "#100C08"
  brasa-card: "#1C1714"
  brasa-text: "#F0E8DC"
  brasa-text-sub: "#C0A890"

  # Tema "ferrari" (editorial b/n + rojo)
  ferrari-bg: "#FFFFFF"
  ferrari-header: "#000000"
  ferrari-border: "#CCCCCC"
  ferrari-text: "#181818"

  # Estados funcionales (caramelo)
  success: "#1A7A3C"
  warning: "#C47A10"
  info: "#2056C8"
  error: "#C8200E"
---

# Design System: FerreBot Dashboard — Baseline

**Estado**: snapshot del dashboard ANTES del rediseño (fase 0). Este documento captura lo que existe hoy, no lo que queremos. La dirección visual definitiva se decide en Fase 2 vía Stitch mockups.

**Branch**: `feat/dashboard-redesign`
**Fecha extracción**: 2026-05-23

---

## 1. Visual Theme & Atmosphere

El dashboard actual vive bajo un sistema de **cuatro temas alternables** (Caramelo claro por defecto, Forja oscuro GitHub-like, Brasa carbón cálido, Ferrari editorial b/n + rojo Rosso Corsa). Cada tema es un objeto JS de tokens en `dashboard/src/components/shared.jsx` (`THEMES`), inyectado por `ThemeContext`. No hay variables CSS, no hay Tailwind activo (está en `package.json` pero ningún componente usa clases utility — todo es `style={{...}}` inline).

El tema por defecto **caramelo** apuesta por arena cálida (`#F8F5F1`), texto chocolate (`#1C1410`), tarjetas blancas con sombras suaves y un acento rojo ladrillo (`#C8200E`) que también es el `theme-color` del manifest PWA. Hay un fondo animado opcional (`AnimatedBackground.jsx`): blobs CSS con gradiente radial (rojo + ámbar + azul acero) + partículas canvas interactivas con `repel` al cursor — solo activas en caramelo, solo desktop, respetando `prefers-reduced-motion`. Los temas oscuros desactivan el fondo animado por completo.

La atmósfera resultante es **cálida-profesional-amistosa** en caramelo (legible, sin agresividad, con presencia de marca discreta), **técnico-confiable** en forja (palette GitHub), **dramática-cálida** en brasa (carbón con destellos naranjas) y **editorial-rigurosa** en ferrari (negro/blanco con rojo Rosso Corsa, sin sombras, radius=2px — el más distintivo del set).

---

## 2. Color Palette & Roles

### Primary Foundation (tema caramelo — default)

| Color | Hex | Rol |
|---|---|---|
| Arena cálida | `#F8F5F1` | Fondo de página |
| Blanco puro | `#FFFFFF` | Tarjetas, modales |
| Beige hover | `#FEFCF9` | Card en hover |
| Crema borde | `#EAE4DC` | Borde estándar |
| Crema borde suave | `#F0EBE3` | Borde sutil |

### Accent & Interactive

| Color | Hex | Rol |
|---|---|---|
| **Rojo Punto Rojo** | `#C8200E` | Acento de marca, CTAs, foco activo |
| Rojo hover | `#A01808` | Estado hover del acento |
| Acento sutil (8% α) | `rgba(200,32,14,0.08)` | Fondos de pill/badge con marca |
| Acento glow (15% α) | `rgba(200,32,14,0.15)` | Halo de foco |

Variantes por tema: Ferrari usa Rosso Corsa `#DA291C`, Forja usa `#E83020`, Brasa usa `#F03418`. Todas son **familias del mismo rojo ferretería** ajustadas al contraste de cada fondo.

### Typography & Text Hierarchy

| Color | Hex | Uso |
|---|---|---|
| Chocolate primario | `#1C1410` | Cuerpo principal, números KPI |
| Cacao secundario | `#4A3F35` | Texto de soporte |
| Beige apagado | `#9C8E82` | Etiquetas, captions, muted |

### Functional States (caramelo)

| Estado | Hex | Uso |
|---|---|---|
| Éxito (verde bosque) | `#1A7A3C` | Pagos confirmados, stock OK |
| Advertencia (ámbar) | `#C47A10` | Stock bajo, fiados próximos a vencer |
| Info (azul cobalto) | `#2056C8` | Notas informativas, filtros activos |
| Error (rojo marca) | `#C8200E` | Errores, anulaciones — comparte hue con el acento (atención: puede confundirse) |

### Tablas

`tableAlt` `#FDFAF6` (filas zebra) y `tableFoot` `#F5F0E8` (pie con totales). Diferencia muy sutil — funciona pero pierde fuerza en tablas largas.

---

## 3. Typography Rules

### Familia tipográfica

**Una sola familia: Inter** (Google Fonts), pesos 400/500/600/700/800. Cargada vía `@import url(...)` dentro de un `<style>` en `App.jsx` línea 732. No usa `<link>` en `<head>` ni `@fontsource` — el import en runtime cuesta un FOUT en la primera carga.

Stack: `'Inter', Arial, Helvetica, sans-serif`. `font-family: inherit` para botones e inputs (todo el árbol hereda Inter).

### Hierarchy & Weights

| Elemento | Tamaño | Peso | Letter-spacing | Notas |
|---|---|---|---|---|
| Logo "PUNTO ROJO" | ~h*0.41 (varía con prop `size`) | 800 | -0.025em | SVG con texto incrustado |
| "FERRETERÍA" (label sobre logo) | h*0.225 | 500 | 0.16em | Caps tracking abierto |
| KPI valor (número grande) | 24px | 700 | -0.03em | `font-variant-numeric: tabular-nums`, line-height 1.1 |
| KPI label | 10px | 600 | 0.06em | Uppercase, color muted |
| KPI sub | 11px | 500 | normal | Color del KPI, opacity 0.85 |
| Section title (h2) | 13px (11px en Ferrari) | 700 (400 en Ferrari) | 0.04em (1px en Ferrari) | Uppercase, borde inferior |
| Table header (Th) | 10px | 700 | 0.06em | Uppercase, color muted |
| Badge | 10px | 700 (400 en Ferrari) | 0.04em (1px en Ferrari) | Uppercase opcional |
| Input | 12px desktop / **16px móvil** | 400 | normal | El 16px móvil evita el zoom iOS |
| Periodo botón | 11px | 400 / 700 si activo | normal | Píldora |
| Spinner texto | 12px | 400 | 0.04em | "Cargando..." |

### Spacing & Hierarchy Principles

- **No hay escala formal de tipo**. Cada tamaño aparece literal en cada componente (`fontSize: 24`, `fontSize: 13`). Sin tokens compartidos = inconsistencias inevitables al crecer.
- Uppercase + letter-spacing es el patrón dominante para metadatos (labels KPI, section titles, badges, table headers, periodo activo en Ferrari). Funciona pero satura cuando hay 4-5 títulos en pantalla.
- `tabular-nums` solo se aplica al valor de KPI. Las demás cifras en tablas usan números proporcionales — los totales bailan.
- El tema Ferrari rompe el patrón general: pesos más livianos (400 en lugar de 700), letter-spacing más extremo (1px), radius=2 — quiere personalidad editorial pero solo se aplica a un subset de componentes.

---

## 4. Component Stylings

### Cards (`Card`, `GlassCard`, `KpiCard` en `shared.jsx`)

- **Radius**: 16 por defecto, override por tema (`t.radius`). Ferrari = 2. Caramelo / Forja / Brasa = 16.
- **Padding interno**: 20px en Card, 16-18-22 asimétrico en KpiCard (más a la izquierda por la barra de acento).
- **Border**: 1px sólido `t.border`; en hover cambia a `t.accent + '30'` (alpha hex). GlassCard en caramelo usa borde 0.5px rojo translúcido.
- **Sombras**: 3 niveles definidos por tema (`shadow`, `shadowHov`, `shadowCard`). En Ferrari todas son `'none'`. En caramelo son sutiles (1-3px blur). En oscuros son más fuertes y agregan halo de acento en hover.
- **Hover lift**: `translateY(-2px)` con transición 0.22s ease — desactivado en Ferrari.
- **Línea de acento horizontal** arriba (`Card`): gradiente lineal `transparent → t.accent → transparent`, 2px de alto, márgenes 16px izq/der. Ausente en Ferrari.
- **Glass effect** (`GlassCard`): `backdropFilter: blur(16px)` solo en caramelo; los demás temas reutilizan el card sólido.

### KpiCard (el patrón más usado del dashboard)

- Barra vertical de acento izquierda: gradiente vertical en temas no-Ferrari (`${c}00 → ${c} → ${c}00`), sólida 2px en Ferrari. Ocupa el 60% central de la altura.
- Animación `framer-motion`: entrada `opacity 0→1, y +20→0` (0.35s easeOut). Hover scale 1.025 + y -3 (excepto Ferrari).
- Count-up cúbico ease-out (800ms) en el valor numérico — parsea `$`, separadores de miles, decimales (`useCountUp` hook).
- Icon opcional en cuadro 36×36 con radius 10, fondo `${c}12` (hex alpha).

### Badge

- Pill `padding: 3px 10px`, radius 99 (full round excepto Ferrari = 2px).
- Background `color + '18'` (alpha hex), borde `color + '35'`, texto color sólido.
- Uppercase + tracking en Ferrari; en otros temas mantiene case del contenido.

### PeriodBtn (filtro de período: Hoy / Semana / Mes / Año)

- Inactivo: background transparent, borde 1px `t.border`, texto muted.
- Activo: background `t.accent` sólido, texto `#fff`, peso 700.
- Hover (inactivo): borde + texto suben a `t.accent`/`t.text`.
- Padding `5px 14px`, fontSize 11, radius 8 (2 en Ferrari).

### StyledInput

- `padding: 8px 12px`, radius 9 (2 en Ferrari).
- Focus: borde a `t.accent + '80'`, box-shadow `0 0 0 3px ${t.accent}15` (halo 15% alpha) — patrón de **focus ring** consistente.
- **fontSize móvil 16px** intencional (evita zoom iOS), 12px desktop. Detecta con `screen.width < 768`.
- Sin label asociado en muchas instancias — depende de placeholder.

### Th (table header)

- Padding `10px 14px`, fontSize 10, peso 700, uppercase, tracking 0.06em, color muted, borde inferior 1px.
- No hay sticky header definido a nivel base; cada tabla lo implementa por separado.

### Spinner

Loop CSS `spin` 0.65s linear infinite. Círculo 28×28, borde 2px, top-color = accent. Texto "Cargando..." 12px. Padding generoso 48px.

### ErrorMsg / EmptyState

- ErrorMsg: fondo `t.accent + '10'` (oscuros) o `#fef2f2` (caramelo, hard-coded), borde `t.accent + '40'`. Icono `⚠️` emoji.
- EmptyState: solo texto centrado + icono `📭` emoji opacity 0.4.
- **Anti-pattern**: emojis en lugar de iconos vectoriales — choca con los SVG limpios del nav.

### Iconos del nav

SVG inline en `App.jsx`, 24×24 viewBox, `strokeWidth: 1.75`, `strokeLinecap/Linejoin: round`. Estilo consistente, único set bien hecho del dashboard.

### Logo

SVG vectorial paramétrico (`Logo({ size, themeId })`). Círculo rojo con gradiente lineal + drop shadow, llave inglesa estilizada blanca rotada -40°, texto "FERRETERÍA / PUNTO ROJO" + barra roja decorativa. Variante de color por tema.

---

## 5. Layout Principles

### Grid & Structure

- Sin sistema de grid formal. Layouts ad-hoc con flex y `gridTemplateColumns` inline (`'repeat(auto-fit, minmax(160, 1fr))'` aparece como patrón en TabResumen).
- KpiCard pide `flex: 1, minWidth: 160` — define implícitamente una fila de KPIs que se acomoda.
- Sin `max-width` global de contenido — el dashboard ocupa todo el viewport.

### Whitespace Strategy

- No hay escala formal de espaciado. Valores comunes que se repiten: 8, 10, 12, 14, 16, 20, 24, 32, 48 — coherente con un grid de 4-8px pero no enforzado.
- Padding de Card: 20. Padding de KpiCard: 16/18/22 (asimétrico para acomodar barra de acento izquierda).
- Section spacing: `marginBottom: 16` + `paddingBottom: 10` con borde inferior.

### Alignment & Visual Balance

- Layout dominante: header fijo + contenido scrollable + tabs como navegación principal.
- Tabs: 17 tabs en navegación plana sin agrupación. Sobrepasa la regla 7±2 — uno de los problemas que motivan el rediseño.
- KPIs en TabResumen: 6 KpiCards en fila — el patrón "bento de KPIs idénticos" identificado como anti-pattern en PRODUCT.md principio 4.

### Responsive Behavior & Touch

- **Portrait lock activo en móvil** (`index.html` línea 35 — bloquea landscape ≤900px de ancho, muestra mensaje "Gira el teléfono"). Decisión fuerte: el dashboard **no responde a landscape móvil**.
- `useIsMobile` hook (`shared.jsx:597`) detecta `max-width: 767px`. Algunos componentes lo consultan, otros no.
- StyledInput salta a fontSize 16px en móvil (evita zoom iOS). Buena práctica.
- **Sin targets táctiles auditados a 44×44**. Algunos botones de filtro (PeriodBtn 24px de alto) están por debajo del mínimo.
- ServiceWorker registrado (`/sw.js`) — es PWA installable (`manifest.json`, `apple-touch-icon`).

### Motion

- Transiciones estándar: `transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease`. Easing CSS `ease` (no ease-out-quart como recomienda impeccable).
- `framer-motion` se usa solo en `KpiCard` (entrada + hover scale) y posiblemente en otros lugares puntuales — no es sistémico.
- AnimatedBackground: blobs con `transform: translate + scale`, keyframes 30-44s, infinite. Particles canvas con repel al cursor. Solo en caramelo + desktop. Respeta `prefers-reduced-motion`.
- Count-up cúbico ease-out (`1 - Math.pow(1 - progress, 3)`) — consistente con la guía de motion (curvas exponenciales).

---

## 6. Design System Notes for Stitch Generation

### Language to use (para prompts de mockups)

- "warm sand background, ferretería red accent, GitHub-like density"
- "humanist sans (Inter alternative — Söhne, General Sans, Geist)"
- "muted chocolate text, beige borders, asymmetric KPI accent bar on the left"
- "industrial-warm — not crypto-dark, not banking-navy, not bootstrap-blue"
- "data-dense without SAP feeling, breathable without SaaS-cream feeling"

### Color references

- Marca primaria: `#C8200E` (no `#FF0000`, no rojo crayón). Calibrar al fondo de cada tema.
- Neutrales cálidos tintados (`#F8F5F1`, `#EAE4DC`) — nunca `#fff` puro como fondo, nunca `#000` puro como texto.
- Acentos secundarios (verde `#1A7A3C`, ámbar `#C47A10`, azul `#2056C8`) son funcionales, no decorativos — solo aparecen en estados.

### Component prompts (para Fase 2 mockups)

- **TabResumen**: "executive dashboard for a Colombian hardware store, 4-6 KPIs in editorial layout (not equal-sized cards), a Caja del Día card with the day's deltas, a Top Productos list, a Fiados Próximos a Vencer alert section. Warm sand background, chocolate text, ferretería red accent. Mobile-first."
- **TabVentasRapidas**: "point-of-sale screen with a fast product search bar, recent customers, payment method shortcuts (efectivo / transferencia / fiado), big tabular numbers for totals, keyboard-shortcut hints visible. Density over decoration."
- **TabCaja**: "cash drawer screen with apertura/cierre state, day's transactions in a dense table, expense entry form inline, real-time balance. Calm but information-rich."

### Incremental iteration

- Empezar el rediseño desde **caramelo** (default). Los otros 3 temas se reducen o eliminan en Fase 3 (decisión pendiente: ¿mantener dark mode? ¿matar Ferrari/Brasa?).
- El acento rojo `#C8200E` es no-negociable. Todo lo demás está en revisión.
- Los SVG icons del nav son lo único que ya está al nivel del rediseño objetivo — preservarlos.

---

## Anti-patterns identificados en el baseline (input para AUDIT.md)

Ver `AUDIT.md` (Fase 0 task 4) para la lista priorizada con remedios. Snapshot rápido aquí:

- **Tailwind en deps pero no usado** — ~5MB de CSS en bundle que nadie consume.
- **Estilos 100% inline** (`style={{...}}`) — sin escala de espaciado, sin tokens compartidos en runtime, cada componente reinventa sus tamaños.
- **`index.css` está corrupto** — contiene HTML en lugar de CSS. `main.jsx:4` lo importa de todos modos.
- **4 temas mantenidos en paralelo** — duplica el costo de cualquier cambio visual; el rediseño debería colapsar a 1-2 (light + dark opcional).
- **Emojis (⚠️, 📭) mezclados con SVG icons** — incoherencia visual.
- **17 tabs sin agrupación** en la navegación principal (motivación principal del rediseño — ver `IA.md` en Fase 1).
- **`window.matchMedia` y `screen.width` consultados ad-hoc** en lugar de hook único — duplica lógica de breakpoints.
- **Sin targets táctiles auditados a 44×44** — Andrés y vendedores usan mucho móvil.
- **Portrait lock en móvil** — decisión arquitectónica fuerte, puede revisarse en rediseño.
- **`@import` de Inter en runtime** — debería ser `<link rel="preconnect">` + `<link>` en `<head>` o `@fontsource` para evitar FOUT.
- **Sin escala formal de espaciado/tipo** — cada `fontSize:` y `padding:` es un valor literal.
- **Hover scale + translateY** en KpiCard no respeta `prefers-reduced-motion`.
