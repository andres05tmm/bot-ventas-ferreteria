# Audit — Dashboard FerreBot (baseline pre-rediseño)

**Fecha**: 2026-05-23
**Branch**: `feat/dashboard-redesign`
**Scope**: `dashboard/src/` — capa de presentación únicamente
**Método**: `impeccable audit` (5 dimensiones, escala 0-4)

---

## Audit Health Score

| # | Dimensión | Score | Hallazgo crítico |
|---|---|---|---|
| 1 | Accessibility | **1/4** | Cero atributos ARIA en todo el proyecto. Inputs sin labels. SVGs sin `<title>`. |
| 2 | Performance | **2/4** | Sin lazy-loading (17 tabs en bundle inicial). `@import` de fuente en runtime. AnimatedBackground O(n²). |
| 3 | Theming | **2/4** | 4 temas paralelos con tokens duplicados. Cero CSS variables. Algunos hex hard-coded fuera de THEMES. |
| 4 | Responsive | **2/4** | `useIsMobile` ad-hoc en cada componente. Portrait lock fuerza una sola orientación. Targets <44×44. |
| 5 | Anti-Patterns | **1/4** | KPI bento idéntico, emojis + SVG mezclados, `index.css` corrupto, Tailwind en deps sin uso. |
| **Total** | | **8/20** | **Poor — overhaul mayor** (es justo el rediseño que ya está planeado) |

---

## Anti-Patterns Verdict

**No parece AI-slop genérico**, pero acumula **anti-patterns concretos** que se sienten al usar el producto. La paleta cálida + el rojo `#C8200E` con su drift por tema le dan algo de carácter (no es "Bootstrap default"), y los iconos SVG del nav son intencionales. Pero:

**Tells visibles:**
1. **KPI bento de 6 cards idénticos** en TabResumen — el patrón "icon-arriba / valor-grande / label-uppercase" repetido. Es exactamente lo que el principio 4 de PRODUCT.md prohíbe.
2. **Emojis decorativos** (⚠️ en ErrorMsg, 📭 en EmptyState, 🔥/🌙/☀️/◆ en labels de temas) chocan con los SVG vectoriales del nav. Inconsistencia tonal.
3. **Side-accent vertical** en KpiCard (gradiente `${c}00 → ${c} → ${c}00` a la izquierda) — esto sí es un *side-stripe border*, uno de los bans absolutos del skill `impeccable`.
4. **Glass effect translúcido decorativo** en `GlassCard` y header caramelo (`backdropFilter: blur(20px)`) — usado por estética, no por función. Otro tell.
5. **Card de hover-lift + shadow-amplify** universal — el gesto "translateY(-2px) + shadowHov" se aplica a todo, dilución de jerarquía.

**Veredicto: 1/4** — distintivo en intención (rojo ferretería, temas con nombre) pero ejecuta varios anti-patterns reconocibles. El rediseño tiene base para subir esto a 3-4.

---

## Executive Summary

- **Health: 8/20** (Poor).
- **Issues: 32 totales** — P0: 4, P1: 13, P2: 10, P3: 5.
- **Top 5 críticos**:
  1. [P0] `dashboard/src/index.css` contiene HTML en vez de CSS — el import del CSS global está roto.
  2. [P0] Cero atributos ARIA en componentes interactivos — bloquea screen-readers por completo.
  3. [P0] 17 tabs en bundle inicial sin code-splitting — first-paint penalizado.
  4. [P0] `KpiCard` aplica `whileHover scale` ignorando `prefers-reduced-motion`.
  5. [P1] 4 temas mantenidos en paralelo con tokens hex duplicados (no CSS vars) — cualquier cambio visual se replica 4 veces.
- **Recomendación**: el rediseño ya planeado (PLAN.md, 7 fases) ataca los issues sistémicos. Las P0 deberían arreglarse al final de Fase 0 o inicio de Fase 3, no esperar a Wave 4.

---

## Detailed Findings by Severity

### P0 — Blocking

#### [P0] `index.css` corrupto contiene HTML
- **Location**: `dashboard/src/index.css` (36 líneas)
- **Category**: Build / Theming
- **Impact**: `main.jsx:4` importa `./index.css`. Vite parsea HTML como CSS y silenciosamente lo descarta — el dashboard funciona porque no depende del archivo, pero la convención `index.css = estilos globales` está totalmente rota. Cualquier intento futuro de añadir CSS global se pierde.
- **Recommendation**: en Fase 3, reescribir `index.css` con `@tailwind base/components/utilities` (o el reset elegido) + variables CSS de los tokens del DESIGN.md definitivo. Verificar con DevTools que el bundle inyecta las reglas.

#### [P0] Cero ARIA en todo el árbol
- **Location**: búsqueda `aria-` en `App.jsx` + `shared.jsx` → 0 matches. Idem para `role=`.
- **Category**: Accessibility (WCAG 2.1 — 4.1.2 Name/Role/Value)
- **Impact**: Screen readers no leen estados de las KpiCard (no son nodos accesibles), no anuncian el Spinner como `status`, no anuncian ErrorMsg como `alert`, los `StyledInput` no se asocian con label. Para el contador externo que use lector de pantalla = inutilizable.
- **Recommendation**: en Fase 3 (cuando se montan shadcn primitives), `Spinner` → `role="status" aria-live="polite"`; `ErrorMsg` → `role="alert"`; `StyledInput` → recibir `label` prop obligatorio y wrappear `<label>`; iconos del nav → `aria-label={name}`. Documentar en CONTRIBUTING.md.

#### [P0] Sin code-splitting — 17 tabs en bundle inicial
- **Location**: `App.jsx:9-25` (todos los `import Tab*`)
- **Category**: Performance
- **Impact**: Primera carga descarga TabFacturacion, TabLibroIVA, TabComprasFiscal (uso esporádico de contador) aunque el vendedor mostrador solo abra TabVentasRapidas. `jspdf` + `html2canvas` + `recharts` engordan el chunk inicial sin necesidad.
- **Recommendation**: en Fase 4 cada wave migra sus tabs a `React.lazy()` + `<Suspense>`. Wave 4 (fiscal) es el más obvio — esos 4 tabs deben ser chunks independientes.

#### [P0] `KpiCard` y hover-lift ignoran `prefers-reduced-motion`
- **Location**: `shared.jsx:341` (`whileHover={isFerrari ? undefined : { scale: 1.025, y: -3 }}`) y `shared.jsx:253` (`transform: translateY(-2px)`).
- **Category**: Accessibility (WCAG 2.3.3 Animation from Interactions)
- **Impact**: Para usuarios con vestibular issues / migrañas, el efecto al pasar el cursor sobre 6 KPIs es disparador. `AnimatedBackground` sí lo respeta — incoherente.
- **Recommendation**: hook `useReducedMotion()` (`framer-motion` ya lo expone) → `whileHover` queda `undefined`. Card hover transform condicionado. Aplica a todos los componentes de `shared.jsx`.

### P1 — Major

#### [P1] 4 temas con tokens hex duplicados, sin CSS vars
- **Location**: `shared.jsx:34-170` (THEMES object).
- **Category**: Theming
- **Impact**: Para cambiar el rojo de marca hay que tocar 4 lugares (`#C8200E`, `#DA291C`, `#E83020`, `#F03418`). Algunos componentes hard-codean valores fuera del tema (`'#fef2f2'` en `ErrorMsg`, `'#f87171'` para texto rojo en dark).
- **Recommendation**: Fase 3 colapsa a 1-2 temas (caramelo + opcional forja) con CSS variables. Las variantes de rojo se derivan vía OKLCH lightness shift, no hex paralelos.

#### [P1] Sin escala formal de espaciado ni tipo
- **Location**: cada `fontSize:` y `padding:` literal en `shared.jsx`, `App.jsx`, y los 17 tabs.
- **Category**: Theming / Maintainability
- **Impact**: Tres componentes tienen `fontSize: 10`, `11`, `12` — no se sabe cuál es la "etiqueta", cuál es "caption", cuál es "small body". Crecimiento futuro inevitable de inconsistencias.
- **Recommendation**: Fase 3 define escala de tipo (xs/sm/base/lg/xl con ratio 1.25) y espaciado (4/8/12/16/24/32/48) como tokens. Tailwind ya viene con ellas — se usa.

#### [P1] Tailwind en deps pero no usado
- **Location**: `dashboard/package.json` (`tailwindcss`, `autoprefixer`, `postcss`); cero `className=` con utilities en `dashboard/src/tabs/*.jsx` (verificado con grep).
- **Category**: Performance / Anti-pattern
- **Impact**: Pipeline PostCSS corre en cada build sin output útil. Confunde a contributors nuevos ("¿uso Tailwind o style inline?").
- **Recommendation**: Fase 3 — o usar Tailwind real (shadcn lo requiere) o desinstalar. Dado que el plan migra a shadcn, **usar Tailwind real** desde Fase 3, configurado contra los tokens del DESIGN definitivo.

#### [P1] StyledInput sin label asociado
- **Location**: `shared.jsx:544-575`.
- **Category**: Accessibility (WCAG 1.3.1, 3.3.2)
- **Impact**: Inputs sin `<label htmlFor>` ni `aria-label` — screen readers solo leen el placeholder, que desaparece al escribir. Atajos por teclado (`alt+letter` a labels) no funcionan.
- **Recommendation**: API rota — `label` se hace prop requerida, render como `<label>` envolvente o asociado por id.

#### [P1] PeriodBtn debajo del mínimo táctil 44×44
- **Location**: `shared.jsx:521-541` — `padding: '5px 14px', fontSize: 11` → ~24×60px.
- **Category**: Responsive / Accessibility (WCAG 2.5.5)
- **Impact**: En móvil (Andrés desde el carro, vendedor con dedos sucios) errar el tap del filtro de período → frustra.
- **Recommendation**: en móvil padding `12px 16px` mínimo. shadcn `Button` size variants ya lo resuelven.

#### [P1] `@import` de Inter en runtime dentro de `<style>`
- **Location**: `App.jsx:732` — `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');`
- **Category**: Performance
- **Impact**: FOUT en cada primera carga. El navegador descubre la URL después de parsear el JS. `display=swap` mitiga pero no elimina.
- **Recommendation**: mover a `<link rel="preconnect" href="https://fonts.gstatic.com">` + `<link rel="stylesheet" href="...">` en `index.html` o instalar `@fontsource/inter`.

#### [P1] 17 tabs sin agrupación en navegación principal
- **Location**: `App.jsx:9-25` y nav rendering (alrededor de líneas 700+).
- **Category**: Responsive / IA (overlap con Fase 1)
- **Impact**: Sobrepasa Miller (7±2). En móvil ya hay overflow horizontal. El contador entra 1× al mes y tiene que filtrar entre 17 opciones para llegar a Libro IVA.
- **Recommendation**: **Fase 1** del rediseño — agrupar por dominio (Operación / Gestión / Reportes / Fiscal). Sidebar agrupado o command palette.

#### [P1] Portrait lock móvil congela el dashboard en landscape
- **Location**: `dashboard/index.html:31-38` — `@media landscape and (max-device-width: 900px)` muestra mensaje "Gira el teléfono".
- **Category**: Responsive / UX
- **Impact**: Decisión arquitectónica fuerte — el dashboard renuncia a una orientación. Si Andrés está en el carro con un soporte de celular landscape, ve la pantalla bloqueada. POS con tablet horizontal también bloqueado.
- **Recommendation**: revisar en Fase 4 si el rediseño hace que landscape funcione bien (probable). Si sí, eliminar el lock.

#### [P1] `AnimatedBackground` particles O(n²) en `drawConnections`
- **Location**: `AnimatedBackground.jsx:80-96` — doble loop 42×42 = 861 pair checks/frame @ 60fps = ~52k/seg.
- **Category**: Performance
- **Impact**: En laptops modestos / batería baja se nota como drop a 30-40fps. Solo afecta caramelo + desktop, pero ese es el default.
- **Recommendation**: spatial hashing (grid 4×4) — solo comparar partículas en celdas adyacentes. O bajar `MAX_DIST` a 80px → menos pares conectables.

#### [P1] Cero alt text / `<title>` en SVGs
- **Location**: `App.jsx` `Icon` (línea 49) y `Logo` (línea 73) — sin `<title>`, sin `role="img"`, sin `aria-label`.
- **Category**: Accessibility (WCAG 1.1.1)
- **Impact**: Screen readers anuncian "image" sin contexto. El logo y los 17 iconos del nav son invisibles para a11y.
- **Recommendation**: `Icon` recibe `name` ya — usarlo como `<title>{name}</title>`. Logo lleva `<title>Ferretería Punto Rojo</title>`.

#### [P1] Contraste muted `#9C8E82` sobre `#F8F5F1` en small text
- **Location**: tema caramelo, `textMuted` aplicado en `Th` (fontSize 10), KpiCard label (fontSize 10), Spinner texto (fontSize 12).
- **Category**: Accessibility (WCAG 1.4.3 — 4.5:1 mínimo small text)
- **Impact**: Ratio ≈ 3.4:1 — falla AA. Aplica a metadatos de tablas, etiquetas KPI, "Cargando..." — texto frecuente.
- **Recommendation**: oscurecer a `#6B5E54` (4.7:1) o subir fontSize de esos elementos a 14px (umbral large-text = 3:1).

#### [P1] ErrorMsg y EmptyState usan emojis decorativos
- **Location**: `shared.jsx:472, 487`.
- **Category**: Anti-pattern / Consistency
- **Impact**: Choca con SVG icons del nav. Emojis renderan distinto por OS (⚠️ amarillo en Android, naranja en macOS, blanco-y-rojo en Windows).
- **Recommendation**: Fase 5 reemplaza por iconos `lucide-react` (ya en deps): `AlertTriangle`, `Inbox`.

#### [P1] Hover scale + translateY universal en Cards
- **Location**: `shared.jsx:253, 302, 341`.
- **Category**: Anti-pattern
- **Impact**: Todos los cards "saltan" al hover. Diluye jerarquía — si todo se eleva, nada se eleva. KPIs (no clicables) saltan igual que cards clicables.
- **Recommendation**: hover-lift solo en elementos interactivos. KpiCard estático.

#### [P1] `index.html` `viewport` permite `maximum-scale=1.0, user-scalable=no`
- **Location**: `dashboard/index.html:5`.
- **Category**: Accessibility (WCAG 1.4.4 Resize Text)
- **Impact**: Usuarios con baja visión no pueden hacer pinch-zoom para leer mejor.
- **Recommendation**: remover `maximum-scale` y `user-scalable=no`. iOS ya respeta el zoom de input via fontSize 16px (que ya está aplicado).

### P2 — Minor

#### [P2] `useIsMobile` consultado ad-hoc, lógica duplicada
- **Location**: `shared.jsx:546` (StyledInput consulta `window.screen` directo), `AnimatedBackground.jsx:16` (idem). El hook `useIsMobile` existe pero no es de uso obligatorio.
- **Recommendation**: enforcer hook único en Fase 3.

#### [P2] `tableAlt` y `tableFoot` muy sutiles en caramelo (`#FDFAF6` vs `#F8F5F1` y `#F5F0E8` vs `#FFFFFF`)
- **Recommendation**: aumentar contraste a 5-6% de luminosidad en Fase 3.

#### [P2] Error de tema caramelo: `'#fef2f2'` hard-coded en ErrorMsg
- **Location**: `shared.jsx:466`.
- **Recommendation**: token `t.errorBg`.

#### [P2] Animaciones usan `ease` CSS en lugar de `ease-out-quart`
- **Location**: `shared.jsx` transitions múltiples (`transition: 'transform 0.22s ease'`).
- **Recommendation**: curva `cubic-bezier(0.25, 1, 0.5, 1)` (ease-out-quart) en Fase 3.

#### [P2] `THEMES.caramelo.bgPattern` se define pero no se aplica (revisar)
- **Recommendation**: verificar uso en App.jsx; si no, eliminar.

#### [P2] Spinner sin `aria-busy` / `aria-live`
- **Location**: `shared.jsx:441`.
- **Recommendation**: `role="status" aria-live="polite"`.

#### [P2] EmptyState sin role
- **Recommendation**: `role="status"` o estructural sin role pero con heading.

#### [P2] Logo SVG sin `<title>` ni `aria-label`
- (overlap con P1 SVG general, pero el logo es identidad — separable).

#### [P2] `framer-motion` import completo
- **Location**: `shared.jsx:3` — `import { motion } from 'framer-motion'`.
- **Recommendation**: en Fase 3, evaluar `framer-motion/dom` (versión mini, ~20KB en lugar de ~60KB).

#### [P2] `radius: 99` en Badge para "pill" — magic number repetido
- **Recommendation**: token `t.radius.pill = 9999`.

### P3 — Polish

#### [P3] Comentarios en español, código en inglés — convención no enforzada
- Aceptable, alineado con CLAUDE.md.

#### [P3] `keepalive.py` mencionado en docs pero no en frontend
- No aplica al dashboard.

#### [P3] Falta favicon SVG (solo PNG en `/icons/`)
- **Recommendation**: añadir `<link rel="icon" type="image/svg+xml" href="/icon.svg">`.

#### [P3] PWA manifest no auditado — sin manifest validator output
- **Recommendation**: pasar `https://pwabuilder.com` antes de Fase 6.

#### [P3] No hay test visual (Chromatic, Percy, Playwright snapshots)
- **Recommendation**: opcional para Fase 6.

---

## Patterns & Systemic Issues

1. **Estilos inline sin tokens compartidos**. ~95% del CSS del dashboard es `style={{...}}` literal. Cualquier cambio sistémico (oscurecer todos los muted, subir todos los radius, etc.) requiere edits en N archivos. **Causa raíz de 4 P1**.

2. **Cero accesibilidad estructural**. No es solo "le falta ARIA aquí o allá" — la decisión de no usar primitives accesibles fue sistémica. shadcn (Radix) resuelve esto por defecto. **Justifica la migración entera**.

3. **Tema-driven con código-driven mezcla**. Los temas declaran tokens, pero los componentes a veces los usan, a veces hard-codean, a veces inventan. La inconsistencia se nota en oscuros (algunas pantallas funcionan, otras tienen "huecos" de color).

4. **Móvil pensado pero no priorizado**. Hay señales de pensar en móvil (`fontSize: 16px` en input, `useIsMobile` hook, manifest PWA, portrait lock) pero también señales de no haberlo probado (PeriodBtn, hover-only states, 17 tabs sin colapsar).

5. **Anti-patterns desplegados sin caer en AI-slop**. El proyecto evita lo más obvio (no usa `#000`, tiene un rojo de marca calibrado, los SVGs nav son intencionales) pero acumula side-stripe borders, KPI bento, hover-lift universal y emojis decorativos. El rediseño debe ser quirúrgico, no destructivo.

---

## Positive Findings

- **Iconografía vectorial del nav** — único set bien hecho, conservar y extender en Fase 3.
- **Rojo de marca calibrado por tema** — la familia (`C8200E / DA291C / E83020 / F03418`) muestra intención, no es un único hex pegado en todos lados.
- **Detección de móvil consciente** — `fontSize 16px` en input evita zoom iOS, `useIsMobile` existe.
- **`prefers-reduced-motion` respetado en AnimatedBackground** — el patrón existe en la base de código, falta extenderlo a más componentes.
- **`tabular-nums` en KPI** — pequeño detalle pero correcto.
- **Spinner simple y rápido** — no overengineered.
- **Theming arquitectura clara** — context + tokens objeto, fácil de migrar a CSS vars sin big-bang.
- **Logo paramétrico SVG** — escala bien sin imágenes raster, listo para rediseño minor.

---

## Recommended Actions (mapeo a fases del PLAN.md)

Ordenadas por severidad y momento de fase, **no como comandos `/impeccable craft` sueltos** sino integradas al plan que ya existe:

### Antes de iniciar Fase 1 (cleanup mínimo, 1-2h)

1. **[P0] Arreglar `index.css`** — vaciar el archivo o ponerle `/* placeholder — Fase 3 lo llena con Tailwind */` para no acarrear el HTML basura al rediseño.
2. **[P0] Remover `maximum-scale=1.0, user-scalable=no`** del viewport en `index.html` — fix de a11y barato (1 línea).

### Durante Fase 3 (Design System en código)

3. **[P0] CSS variables + tokens 3 capas** — colapsa los 4 temas a 1-2, reescribe `index.css`.
4. **[P0] Lazy-load de tabs** — `React.lazy` + `Suspense` por tab, mínimo Wave 4 (fiscal).
5. **[P1] Reemplazar `@import` Inter por `<link>` o `@fontsource`.**
6. **[P1] Tailwind activado de verdad** (requisito shadcn) — tokens del DESIGN nuevo via `tailwind.config.js`.
7. **[P1] Adapter pattern en `shared.jsx`** — los componentes (`Card`, `KpiCard`, `Badge`, `StyledInput`, etc.) delegan a primitives shadcn que ya traen ARIA. Resuelve **9 issues de a11y de un solo golpe**.

### Durante Fase 4 (migración por waves)

8. **[P0] `useReducedMotion`** aplicado a todo `motion.*` y transitions.
9. **[P1] Side-accent vertical de KpiCard** — eliminar o reemplazar (no es un side-stripe `border-left` técnico, pero visualmente lo es).
10. **[P1] Hover-lift solo en cards interactivos.**
11. **[P1] Emojis → `lucide-react`** (ya en deps).
12. **[P1] Contraste muted** subido en caramelo.
13. **[P1] Touch targets 44×44** mínimo en POS (Wave 3 lo audita explícito).

### Durante Fase 5 (componentes especiales)

14. **[P1] `AnimatedBackground` spatial hashing** o reducción de `MAX_DIST`.
15. **[P1] Eliminar portrait lock** si Fase 4 demostró que landscape funciona.

### Durante Fase 6 (polish y audit)

16. **[P2-P3]** Issues cosméticos restantes — tabla zebra, errorBg token, ease-out-quart, favicon SVG, manifest validator.

---

## Conclusión

El dashboard actual saca **8/20** — categoría "Poor". Pero las causas son **3 sistémicas** (sin tokens compartidos, sin a11y estructural, 4 temas paralelos) más que **30 issues individuales**. Atacar las 3 sistémicas durante Fase 3 (Design System en código) hace caer en cascada **~70% de los issues P0/P1** automáticamente.

El plan de rediseño ya existente (`PLAN.md`) **es** la respuesta a este audit. Este documento sirve como:
- **Checklist por fase** — al cerrar cada wave verificar qué issues quedaron resueltos.
- **Baseline numérico** — re-correr `impeccable audit` al final de Fase 6, target ≥ **17/20** (Good).
- **Justificación** para las decisiones del PLAN (migrar a shadcn no es capricho — es la única forma realista de subir el score a11y de 1 a 3+).

> Re-run `/impeccable audit` después de Fase 3, Fase 4 Wave 4, y al cierre de Fase 6.
