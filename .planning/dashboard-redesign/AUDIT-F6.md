# AUDIT-F6 — Polish y audit del dashboard

**Fecha**: 2026-05-25
**Estado entrada**: 10.18 KB css gz · 506.16 KB js gz · 1.823 MB js sin minificar
**Estado salida**: 10.18 KB css gz · 292.82 KB js gz inicial (−42%) · tabs en chunks separados
**Build**: verde
**Cobertura**: 18 tabs migrados (Waves 1-4 + Fase 5) · `useTheme` legacy eliminado · `shared.jsx` 651→142 LOC

---

## Resumen ejecutivo

El dashboard está visualmente coherente: todos los tabs consumen tokens semantic (light/dark via `data-theme`), focus-visible global y `prefers-reduced-motion` ya están cableados en `index.css`. Las brechas de la Fase 6 se concentran en **3 ejes**:

1. **Performance** — sin code-splitting por tab. El bundle entero (1.8 MB sin gz) se descarga en el primer load aunque el usuario solo entre a HOY.
2. **ChatWidget** — 1342 LOC con paleta hex hardcoded y 0 `aria-label`. No participa del DS ni es navegable por teclado.
3. **Accesibilidad** — apenas 3 archivos usan `aria-label`/`role`. Botones icon-only repartidos por todos los tabs no tienen nombre accesible.

Riesgos visuales menores y pulido están en MEDIUM/LOW.

---

## Findings priorizados

### 🔴 HIGH

| # | Pillar | Finding | Evidencia | Fix propuesto |
|---|---|---|---|---|
| H1 | Performance | Sin code-splitting: `App.jsx` importa los 17 tabs eagerly → chunk único de 1.8 MB (506 KB gz) | `App.jsx:12-28`, build log `index-*.js 1,823.77 kB` | `React.lazy()` + `<Suspense>` por tab. Estimación: -60% TTI en primer load, chunks ~30-80 KB por tab |
| H2 | Accesibilidad | `ChatWidget` (1342 LOC) tiene 0 `aria-label`. Botones de envío, toggle de modelo, expand/collapse no son anunciados por lectores de pantalla | `grep aria-label dashboard/src/components/ChatWidget.jsx` → 0 | Etiquetar botones icon-only, agregar `role="log"` al stream y `aria-live="polite"` |
| H3 | Visual coherence | `ChatWidget` usa scoped CSS `.fw-*` con 57 valores hex hardcoded. No reacciona a `data-theme="dark"` | `ChatWidget.jsx` (grep hex: 57 ocurrencias) | Tokenizar con `hsl(var(--*))` reemplazando los `.fw-*` clave. Mantener identidad brand red pero hereda dark mode |
| H4 | Accesibilidad | Solo 3 archivos en `dashboard/src` (MobileNav, Sidebar, ui/table) usan `aria-label`/`role`. Botones icon-only en tabs (acordeones, descarga PDF, anular) carecen de nombre accesible | Grep global → 3 matches | Barrido: agregar `aria-label` a todo `<Button>` con solo icono `lucide` |

### 🟡 MEDIUM

| # | Pillar | Finding | Evidencia | Fix propuesto |
|---|---|---|---|---|
| M1 | Visual coherence | Paletas de charts con hex hardcoded (`#0284C7`, `#a78bfa`, `#94a3b8`) | `TabResultados.jsx:212-244`, `TabResumen.jsx:26`, `TabCompras.jsx:41-42`, `TabComprasFiscal.jsx:43-44` | Definir `--chart-1..5` en `index.css` y consumir con `hsl(var(--chart-N))`. Light + dark |
| M2 | Visual coherence | `bg-white` en switches/badges y `bg-black/45-70` en overlays escapan tokens | `TabCompras.jsx:192`, `TabComprasFiscal.jsx:173`, `TabVentasRapidas.jsx:1558,2221,2258`, `TabProveedores.jsx:242`, `MobileNav.jsx:38`, `ui/dialog.jsx:15` | Para overlays mantener `bg-black/X` (DialogOverlay shadcn estándar). Para switches usar `bg-card` o `bg-background` |
| M3 | DX/Mantenibilidad | 4 `console.log/warn` quedan en producción | `ChatWidget.jsx:2`, `Login.jsx:1`, `TabHistorial.jsx:1` | Remover o sustituir por `log()` debug condicional |
| M4 | Performance | `recharts` se importa estáticamente en 5 tabs y vive en el chunk principal | Sin grep, deducido del bundle size | Code-splitting de H1 lo resuelve indirectamente (cada tab con chart trae su recharts en chunk propio) |
| M5 | Visual hierarchy | `TabVentasRapidas.jsx` aún tiene 11 `style={{` inline (más que cualquier otro tab) | Grep counts | Auditar uno por uno; mover a tailwind donde sea estilo estático |

### 🟢 LOW

| # | Pillar | Finding | Evidencia | Fix propuesto |
|---|---|---|---|---|
| L1 | DX | Comentario de `shared.jsx` referencia `useTheme` que ya no existe | `shared.jsx:6` | Limpiar comentario obsoleto |
| L2 | Motion | `index.css` ya respeta `prefers-reduced-motion` global. `AnimatedBackground` no consume — verificar | `AnimatedBackground.jsx` | Confirmar que `requestAnimationFrame` se pausa con `matchMedia('prefers-reduced-motion')` |
| L3 | Responsive | `useIsMobile` se usa en pocos tabs. Validar que el sidebar colapsa correctamente en <768px y que tablas se hacen scrolleables | QA manual | Test en dev tools 375px / 768px / 1280px |

---

## Lighthouse — no medido aún

No corrí Lighthouse en este pass; requiere build + serve + chromium. Antes de medir conviene aplicar **H1** (lazy loading) porque cambiará drásticamente Performance/TTI. Medir después.

**Target PLAN.md**:
- Performance > 90
- Accessibility = 100

Estimación post-fixes: Performance 85→95 (lazy loading + tree-shake), Accessibility 80→100 (H2+H4).

---

## Plan de fixes — APLICADO

| Fix | Estado | Commit | Notas |
|---|---|---|---|
| H1 — Lazy loading tabs | ✅ | `a05857d` | Bundle inicial −42% gz; cada tab on-demand |
| H2 — ChatWidget aria-labels | ✅ | `e0aa433` | role="dialog/log/menu/radiogroup", aria-label en todos los icon-only |
| H3 — ChatWidget tokens semantic | ✅ | `e0aa433` | Surfaces y text con `hsl(var(--*))`. Brand red intacto |
| H4 — Aria-labels icon-only en tabs | ✅ | `817aa1b` | 6 tabs (Compras/ComprasFiscal/Facturacion/HistoricoVentas/Inventario/Proveedores) |
| M1 — Tokens `--chart-1..6` + `--info` | ✅ | `edd5f3f` | Light/dark/system; hex de charts eliminados |
| M2 — Overlays `bg-black/X` | ✅ parcial | `817aa1b` | TabProveedores → `bg-foreground/70`. Resto (DialogOverlay shadcn, modales bottom-sheet) son patrones estándar — se mantienen |
| M3 — Consoles residuales | ✅ no-op | — | Los 4 `console.error` viven en `catch` blocks; son logging legítimo en JS frontend (sin `logger` idiomático). Se mantienen |
| M5 — Inline styles TabVentasRapidas | ✅ no-op | — | Los 11 `style={{` son legítimos: `gridTemplateColumns` dinámico, `WebkitOverflowScrolling`, `env(safe-area-inset-*)`, posición de switches, keyframes inline. Tailwind no cubre |
| L1 — Comentario shared.jsx | ✅ no-op | — | El comentario describe el cambio histórico, no referencia un símbolo vigente. Correcto |
| L2 — AnimatedBackground reduced-motion | ✅ no-op | — | Ya cumplía: `noMotion` cancela canvas (l.31-32) + CSS `@media (prefers-reduced-motion: reduce) { animation: none }` (l.192-194) |

**Tiempo real**: ~2.5 horas. Dentro del budget de "2 días" del PLAN.

---

## Lighthouse — MEDIDO

Servido `dist/` con `npx serve -s dist -l 5050` y corrido `npx lighthouse http://localhost:5050/hoy` (desktop + mobile preset).

| Categoría | Desktop | Mobile | Target PLAN.md |
|---|---|---|---|
| **Performance** | **100** | **91** | > 90 ✅ |
| **Accessibility** | **100** | **100** | = 100 ✅ |
| Best Practices | 77 | 77 | — |
| SEO | 82 | 82 | — |

**Core Web Vitals — Desktop**:
- FCP 0.5s · LCP 0.5s · TBT 0ms · CLS 0 · SI 0.5s · TTI 0.5s

**Core Web Vitals — Mobile**:
- FCP 2.5s · LCP 3.1s · TBT 60ms · CLS 0 · SI 2.5s · TTI 3.2s

**Fix adicional aplicado** (commit `ec0ea82`) para llegar a A11y 100 en mobile:
- `Login.jsx`: `<div>` raíz → `<main aria-labelledby="login-title">` (faltaba landmark)
- `MutationObserver` que inyecta `title="Iniciar sesión con Telegram"` al `<iframe>` que crea el widget de Telegram (el script no acepta el atributo en sus opts)

**Best Practices 77 y SEO 82 — no se accionan**:
- "Uses third-party cookies" — necesarias por OAuth Telegram
- "Missing source maps for first-party JS" — Vite no emite sourcemaps en prod por default; se podría activar (`build.sourcemap: true`) pero infla el bundle subido
- "robots.txt is not valid" + "meta description" — dashboard interno, no se indexa

Reportes completos: `.planning/dashboard-redesign/lighthouse/{desktop,mobile}.report.html`

---

## Fuera de scope (NEXT-STEPS)

- Fase 7 (Remotion walkthrough) — opcional
- Test E2E formal — no hay CI, queda manual
- Medición Lighthouse en producción Railway (post-merge)
