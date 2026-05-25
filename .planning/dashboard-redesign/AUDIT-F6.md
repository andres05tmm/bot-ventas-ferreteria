# AUDIT-F6 — Polish y audit del dashboard

**Fecha**: 2026-05-25
**Estado entrada**: 10.18 KB css gz · 506.16 KB js gz · 1.823 MB js sin minificar
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

## Plan de fixes propuesto (orden sugerido)

1. **H1** — Lazy loading de tabs (~30 min, biggest win)
2. **H2 + H3** — ChatWidget: tokenizar + aria-labels (~1h, ambos juntos)
3. **H4** — Barrido aria-labels en botones icon-only de tabs (~45 min)
4. **M1** — Tokens `--chart-1..5` y reemplazo en 4 archivos (~30 min)
5. **M2 + M3** — Limpieza overlays + remove consoles (~20 min)
6. **M5 + L1 + L2** — Pulido final (~30 min)
7. **Lighthouse + Axe** — medición y captura de score (~15 min)

**Total estimado**: 3.5-4 horas. Encaja en el budget de "2 días" del PLAN si Andrés solo prioriza HIGH + M1.

---

## Fuera de scope (NEXT-STEPS)

- Fase 7 (Remotion walkthrough) — opcional
- Test E2E formal — no hay CI, queda manual
