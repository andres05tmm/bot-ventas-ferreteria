# PLAN V2 — Rediseño Dashboard "Punto Rojo Style"

**Branch**: `feat/dashboard-polish` (extender) o nuevo `feat/dashboard-v2-punto-rojo`
**Creado**: 2026-05-25
**Referencia visual**: Gemini mockup aprobado por Andrés (`.planning/dashboard-redesign/mockups/reference-gemini.png` — pendiente de guardar).
**Logo**: `C:\Users\Dell\Downloads\Gemini_Generated_Image_3vemaf3vemaf3vem.png` (a copiar a `dashboard/public/logo-punto-rojo.png`).

---

## Direccion de diseño (locked)

**Estilo**: Bento minimalista evolucionado con saturación táctica.
- Fondo: **blanco hueso** `#F8F5EE` (cálido, no pastel).
- Brand red `#C8200E` como ancla **operativa**, no como wash.
- **Top accent strips** sólidos en cards y mini-metrics (red/blue/green/orange/yellow) = move distintivo del sistema.
- **Estado pills** con color funcional (amarillo = pending/warning, rojo = abierto, verde = ok).
- Tipografía: Inter sans (ya cargada), pesos 500/600/700 para jerarquía.
- Cero gradient mesh, cero blur, cero glassmorphism (mantiene los bans de impeccable).

**Test AI-slop**:
- First-order: no aurora ni soft gradient. ✅ pasa.
- Second-order: el "top accent strip" es un move distintivo (no es el border-left lazy ni el card uniforme). ✅ pasa.

---

## Mapa de fases

### **FASE 0 — Foundation (preparación)**
*Sin código, sólo prep.*

- [ ] **0.1** Copiar logo PNG a `dashboard/public/logo-punto-rojo.png`.
- [ ] **0.2** Guardar screenshot de referencia Gemini en `mockups/reference-gemini.png`.
- [ ] **0.3** Decidir: ¿optimizar logo a SVG con vectorización manual, o usar PNG @ 2x? Por ahora PNG `@2x` (decisión por defecto, no bloquea).
- [ ] **0.4** Definir tokens nuevos en `tailwind.config.js` + `index.css`:
  - `--bg-body: #F8F5EE` (blanco hueso, reemplaza el actual).
  - `--bg-body-strong: #F1ECE3` (variante para hover/elevation).
  - `--accent-red: #C8200E` (sin cambios).
  - `--accent-yellow: #E8A53A` (warning, más sólido que el current).
  - `--accent-blue: #2C5F8A` (info, saturado para top accents).
  - `--accent-green: #4A9B5C` (success, calibrado al brand).
  - `--accent-orange: #C8682E` (orange para "Total mes").
  - Mantener tokens semantic existentes — solo añadir los `accent-*` para top strips.

**Salida**: branch creado, logo en assets, tokens listos. Cero regresión visual.

---

### **FASE 1 — Background flat + Logo**
*Eliminar aurora, plantar la nueva base.*

- [ ] **1.1** Revertir el `body::before` en `dashboard/src/index.css`: eliminar el linear-gradient + radials del fondo Aurora. Reemplazar por `background: hsl(var(--bg-body));`.
- [ ] **1.2** Eliminar (o conservar deshabilitado) `AnimatedBackground.jsx`. Decision: eliminarlo del árbol completamente, queda en git history.
- [ ] **1.3** Sidebar (`Sidebar.jsx`): reemplazar header actual ("F PUNTO ROJO / DASHBOARD V5") por:
  - Imagen del logo (40x40 round + texto "Ferretería" thin / "Punto Rojo" bold).
  - Layout horizontal compacto en sidebar de 240px, vertical compacto si colapsada.
  - Quitar el bg semitransparente del sidebar (`bg-surface-sidebar/55`) → volver a `bg-surface-sidebar` sólido sobre blanco hueso.
- [ ] **1.4** Ajustar scrollbar Aurora si conflictúa con el nuevo fondo (probable: cambiar `--accent / 0.22` a `--accent / 0.18` para mantener contraste).
- [ ] **1.5** Quitar el `bg-surface/40 backdrop-blur` del HeaderBar (ya no hay aurora que atravesar). Volver a `bg-surface` sólido + borde inferior.

**Salida**: dashboard funciona con fondo blanco hueso, logo nuevo arriba-izquierda. Hace falta polish en KPIs (siguiente fase).

---

### **FASE 2 — KpiCard con Top Accent**
*El move distintivo del sistema.*

- [ ] **2.1** Extender `components/KpiCard.jsx` con dos nuevas props:
  - `topAccent: boolean` — renderiza una barra sólida coloreada arriba (3-4px height).
  - `iconStyle: 'subtle' | 'filled'` — `subtle` (actual) o `filled` (cuadrado sólido del tone con ícono blanco, como el ejemplo).
- [ ] **2.2** Ajustar `TONES` para que el top accent use el color saturado (no el `[0.05]` actual). Mantener bg ligero `[0.02]` para el cuerpo de la card.
- [ ] **2.3** En TabHoy, los 3 KPI principales se renderizan con `topAccent + iconStyle='filled'`:
  - Ventas hoy: tone=`danger`/`primary` (rojo brand), spark integrado, hero number rojo grande.
  - Caja: tone=`warning` (amarillo) cuando cerrada, `success` (verde) cuando abierta.
  - Gastos hoy: tone=`danger` (rojo).
- [ ] **2.4** Refactor del `MiniMetric` (strip de 4) → mismo patrón `topAccent + iconStyle='filled'`. Tones: red/blue/green/orange.
- [ ] **2.5** Hero number en KPI principal: subir tamaño a `2xl` (32-36px), color matches tone.

**Salida**: TabHoy se parece muy fuerte al mockup target. Otros tabs no cambian aún (van en fase 4).

---

### **FASE 3 — Estado pills + Payment badges**
*State clarity siguiendo ui-ux-pro-max §4.*

- [ ] **3.1** `HeaderBar.jsx`: `CajaStatusPill` cuando cerrada → fondo amarillo `bg-warning/15`, borde `border-warning/40`, ícono Wallet. Cuando abierta → ya es verde (mantener).
- [ ] **3.2** `TabHoy` feed "Últimas ventas": payment method badges con colores funcionales:
  - Efectivo → `bg-success/15 text-success`
  - Transferencia → `bg-warning/15 text-warning`
  - Nequi → `bg-info/15 text-info`
  - Datáfono / Tarjeta → `bg-accent/15 text-accent`
  - Fiado → `bg-destructive/15 text-destructive`
- [ ] **3.3** Verificar pill "Bot activo" del header: ya está verde, solo confirmar que no rompe.

**Salida**: Estados visualmente diferenciables sin leer texto. Mejora a11y (color + ícono + texto, no solo color).

---

### **FASE 4A — topAccent en todos los KPIs (decisión Andrés 2026-05-26)**

**Regla actualizada**: TODOS los KPIs principales de cada tab llevan `topAccent`. Es la firma visual del nuevo sistema. La saturación se controla con:
- Tones contrastantes consecutivos (no 3 rojos seguidos).
- Strip 3px (no 4-5px) en tabs no-cockpit.
- Reducir cifras a UN solo KPI hero con número grande; el resto con número estándar.

#### 4A.1 — TabCaja (4 KPIs, todos con topAccent)
| KPI | Tone |
|---|---|
| Apertura | muted (gris neutro, pero con strip) |
| Ventas hoy | success |
| Gastos | danger |
| Efectivo esperado | primary (rojo brand, hero) |

#### 4A.2 — TabLibroIVA (3 KPIs, todos con topAccent)
| KPI | Tone |
|---|---|
| IVA generado (FE) | primary |
| IVA descontable | success |
| IVA neto del período | warning/success dinámico según `a_favor` |

#### 4A.3 — TabFacturacion (3 KPIs, todos con topAccent)
| KPI | Tone |
|---|---|
| Facturas emitidas | success |
| $ Total facturado | primary |
| Con errores | danger (si >0), muted (si 0) |

#### 4A.4 — TabComprasFiscal (5 KPIs, todos con topAccent)
| KPI | Tone |
|---|---|
| Total invertido | primary |
| IVA descontable | success |
| Compras fiscales | info |
| Con factura | warning |
| Enviadas a almacén | muted/success |

#### 4A.5 — TabResultados — MiniKpi (4 KPIs, todos con topAccent)
**Cambio importante**: ahora SÍ migra a topAccent (rectificación). MiniKpi wrapper extiende `KpiCard` con `topAccent=true`.
| KPI | Tone |
|---|---|
| Ventas | success |
| CMV | danger |
| Utilidad bruta | primary |
| Utilidad neta | success/danger dinámico según signo |

#### 4A.6 — TabCompras (4 KPIs, todos con topAccent)
Sin cambios estructurales — solo aplicar topAccent a los 4 existentes (Total invertido, Compras, Proveedores, Productos).

#### 4A.7 — historial/VistaMes — sin cambios desde plan anterior (4 KPIs principales + 3 métodos, todos con topAccent).

#### 4A.8 — historial/VistaDia — ver fase 4B (reestructura).

---

### **FASE 4B — Reestructuras de KPIs y filtros**
*Cambios funcionales, no solo visuales.*

#### 4B.1 — TabHistorial / VistaDia
**KPIs (cambio total)**:
- Antes: Total hoy / Registros / Pagados / Sin método
- Después: **Total hoy** (primary) / **Efectivo** (success) / **Transferencia** (warning) / **Datáfono** (info)
- Cálculo: en cliente desde `todasVentas` agrupando por `v.metodo` (normalizar variantes: efect/transf/dataf/tarj).
- Todos con topAccent.

**Filtros (cambio total)**:
- Antes: Todos / Pagados / Pendientes
- Después: **Todos / Efectivo / Transferencia / Datáfono**
- Lógica: `filtro` ahora filtra por `v.metodo` matching, no por `estado`.
- Aplicar el mismo cambio a TODOS los filtros del flujo (search, dropdown export, etc.) que actualmente usen pagado/pendiente.

#### 4B.2 — TabGastos
**KPIs**:
- Antes: Total gastos / Promedio diario / Categorías / Registros
- Después: **Total gastos** (danger) / **Promedio diario** (warning) / **Registros** (muted)
- Eliminar el KPI "Categorías" (no aporta señal operativa).
- Los 3 con topAccent.

#### 4B.3 — TabProveedores
KPIs ya existen exactamente como pides — solo añadir topAccent:
- **Deuda total** (primary) / **Total pagado** (success) / **Pendientes** (danger) / **En proceso** (warning).

#### 4B.4 — TabVentasRapidas — Carrito rojo
- Panel del carrito (desktop right-aligned): cambiar `bg-card` por `bg-accent-soft` y borde `border-accent/40`.
- FAB móvil bottom bar: fondo brand red `#C8200E` con texto blanco (en vez del actual estilo neutral).
- Items en carrito con left-tint suave rojo.
- Botón "Cerrar venta" / "Checkout": variant primary (ya está).

---

### **FASE 4C — Wrappers MiniKpi / KpiSmall**
Ambos wrappers de `KpiCard` deben aceptar y pasar `topAccent`:
- `MiniKpi` (TabResultados): por defecto `topAccent=true` ahora.
- `KpiSmall` (historial/VistaDia): se reemplaza por uso directo de `KpiCard` con `compact + topAccent`.

**Salida**: dashboard completo con topAccent en todos los KPIs, jerarquía por **tamaño de cifra hero** y **contraste de tones**, no por presencia/ausencia de strip.

---

### **FASE 5 — Polish global y verificación**
*Auditar todos los detalles del mockup.*

- [ ] **5.1** Chart "Evolución de ventas" en TabHoy: verificar que el área usa `--accent` rojo brand con fill `rgba(200,32,14,0.15)` translúcido (el actual ya está cerca).
- [ ] **5.2** "Top productos hoy" con product thumbnails: validar que existen avatares o usar placeholder. (El mockup muestra mini-imágenes — si no las tenemos en DB, usar inicial del producto).
- [ ] **5.3** "Stock bajo" empty state: ícono AlertTriangle warning + texto "Stock sin alertas." centrado.
- [ ] **5.4** Verificar que el sidebar collapse mantiene el logo (versión cuadrada del logo, solo el ícono).
- [ ] **5.5** Dark mode: revisar que el blanco hueso se mapea correctamente a un cream-dark (ej. `#1F1B16`). Top accents en dark mode mantienen los mismos colores (high-contrast).
- [ ] **5.6** Build verde + Lighthouse > 90 + screenshots de antes/después en `mockups/after-implementation/`.

**Salida**: dashboard completo en el nuevo estilo Punto Rojo, todos los tabs auditados, listo para PR.

---

## Riesgos

| Severidad | Riesgo | Mitigación |
|---|---|---|
| MEDIUM | Top strips coloreados saturan si todos los KPIs los llevan | TabHoy main 3 + mini-strip 4 llevan topAccent (cockpit). En el resto de tabs solo el KPI **hero** lo lleva (1-2 por tab); KPIs de contexto siguen sin strip. Jerarquía explícita en el plan |
| MEDIUM | Logo PNG @2x se ve pixelado en displays Retina | Vectorizar a SVG si Andrés tiene tiempo; alternativa: PNG @3x. Aceptable como PNG por ahora |
| MEDIUM | El blanco hueso choca con dark mode | Definir token `--bg-body` con dos variantes (light=#F8F5EE, dark=#1F1B16) en Fase 0 |
| LOW | El mascot del mockup (esquina inferior derecha) no se va a implementar | Ignorar — era artefacto de Gemini; el ChatWidget actual cumple esa función |
| LOW | Cambio rompe expectativa del usuario en sesión activa | Aplicar en una sola sesión continua, commit por fase para rollback granular |

---

## Métricas de éxito

- ✅ Andrés mira el dashboard y dice "sí, así". Sin necesidad de aclaraciones.
- ✅ Lighthouse Perf ≥ 90, A11y = 100 (no regresar de Fase 6 anterior).
- ✅ Cero regresiones funcionales — todos los flujos POS/Caja/Facturación intactos.
- ✅ Net LOC ≤ +200 (extensión del KpiCard + nuevos tokens). El resto es refactor.
- ✅ Build verde tras cada fase (commit por fase).

---

## Complejidad estimada

**MEDIA** — 4-6 horas de trabajo enfocado dividido en 6 commits.

- Fase 0: 15 min (prep + tokens)
- Fase 1: 30 min (background + logo)
- Fase 2: 60 min (KpiCard extended)
- Fase 3: 30 min (pills + badges)
- Fase 4: 60-90 min (propagar a 6 tabs)
- Fase 5: 30-60 min (polish + audit)

---

## Siguiente paso

1. Andrés confirma este plan (o pide ajustes).
2. Si OK → ejecutamos Fase 0 → 1 → 2 → 3 → 4 → 5 secuencialmente, con commit por fase.
3. Andrés revisa el dashboard tras cada fase si quiere checkpoint, o esperamos al final.

**WAITING FOR CONFIRMATION**: ¿Plan aprobado? ¿Algún ajuste? ¿Empezamos por Fase 0?
