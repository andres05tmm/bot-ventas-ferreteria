# PLAN V3 — Reescritura fiel al mockup Gemini

**Branch**: `feat/dashboard-polish` (continuar, revertir cambios si hace falta)
**Referencia**: `C:\Users\Dell\Downloads\Gemini_Generated_Image_lowx9ilowx9ilowx.png` → copiar a `.planning/dashboard-redesign/mockups/reference-gemini-final.png`
**Modelo de planning**: Opus 4.7
**Creado**: 2026-05-26

---

## Diagnóstico — por qué V2 no aterrizó

El PLAN-V2 asumió que **un solo patrón** (3px top-accent strip + ícono filled + heroValue) podía describir todos los KPIs. El mockup de Gemini en realidad usa **dos arquetipos visuales distintos**, y los confundir produjo cards uniformes sin la jerarquía que el mockup mostraba.

### Arquetipo A — "Tarjeta hero blanca" (KPIs principales: Ventas/Caja/Gastos)
- Fondo blanco puro, **sin top accent strip**.
- Label uppercase pequeño arriba-izquierda (gris medio).
- Cifra **muy grande** (≈32-36px), negro brand, no coloreada del tone.
- Subtexto pequeño debajo.
- **Cuadrado coloreado del tone arriba-derecha** con ícono blanco dentro (rounded-md, ~36px).
- Sparkline (cuando aplica, sólo Ventas Hoy) en esquina inferior derecha.

### Arquetipo B — "Tarjeta con banda de color" (KPIs secundarios: Pedidos/Ticket/Semana/Mes)
- Card blanca, pero la **mitad superior es una franja sólida coloreada** (~35-40px alto, tone primary/info/success/warning).
- Label uppercase **en blanco dentro de la franja** + ícono blanco a la derecha.
- Cuerpo blanco abajo con cifra grande negra (tabular, no coloreada).
- Subtexto debajo de la cifra.
- Es el "move distintivo" que faltó implementar. No es topAccent, es **headerBand**.

### Caso especial — CAJA cerrada
La card "CAJA" mezcla los dos arquetipos:
- Estructura del Arquetipo A (fondo blanco, label arriba, ícono coloreado arriba-derecha).
- Cuerpo: **rectángulo amarillo horizontal** (~25-32px) con pill "CERRADA" en rojo + texto "Pendiente de apertura" a la derecha.
- Cuando abierta: el rectángulo amarillo pasa a verde con badge "ABIERTA" + hora de apertura.

---

## Deltas precisos del mockup vs. estado actual

| Elemento | Estado actual (post-V2) | Target Gemini | Acción |
|---|---|---|---|
| Row 1 KPIs (Ventas/Caja/Gastos) | 3px topAccent + iconStyle=filled + heroValue (text-2xl) | Arquetipo A: sin accent, text-3xl/4xl, ícono cuadrado coloreado | Quitar topAccent, bump font size, simplificar |
| Card CAJA cuando cerrada | Badge "Cerrada" inline en value | Banda amarilla horizontal con pill "CERRADA" + texto a la derecha | Custom render, no usar `value` prop |
| Sparkline Ventas Hoy | Spark a la derecha del sub, 56x20px | Spark más prominente, alineado abajo-derecha | Mover spark fuera del row sub, mismo tamaño OK |
| Row 2 KPIs (Pedidos/Ticket/Semana/Mes) | 3px topAccent en card compact | Arquetipo B: banda completa coloreada con label blanco dentro | Nueva prop `headerBand`, refactor |
| Tones row 2 | primary/info/success/warning | red/blue/green/orange (mismos mapeos, OK) | Sin cambio |
| Chart "Evolución de ventas" | Label + total pequeño | Total **grande** ($1.418.000 en text-2xl) + acumulado/prom inline | Reordenar header del chart |
| Últimas ventas | Lista texto sin thumbnails | Misma lista + bloque inferior con thumbnails de productos | Añadir sección "productos vendidos" abajo |
| Top Productos Hoy | Lista con # y barra | Lista con **thumbnail cuadrado** + barra | Reemplazar # por thumbnail |
| Métodos de pago bars | 1px thin | 2-3px más visibles, gradiente rojo sólido | Bump altura barras |
| Sidebar | Grupos OK, logo OK | OK (ya implementado) | Sin cambio |
| HeaderBar | Caja pill + bot pill OK | OK (ya implementado) | Sin cambio |

---

## Plan ejecutable por fases

Cada fase se commitea por separado para rollback granular. Build verde obligatorio entre fases.

### FASE 1 — `KpiCard.jsx`: añadir variante `headerBand` (el patrón faltante)

**Archivo**: `dashboard/src/components/KpiCard.jsx`

Nueva prop **`headerBand: boolean`** (default `false`). Cuando `true`:
- Render un `<div>` superior de altura `~36px` con `background: t.color` (sólido, no opacity).
- Dentro de la banda: label uppercase blanco (`text-[11px] font-semibold tracking-wider text-white`) + ícono blanco a la derecha (`size-3.5`).
- El cuerpo de la card (cifra + sub) va **debajo** de la banda, no comparte fila con el label.
- Padding: la banda usa `px-3 py-2`, el cuerpo usa `px-3 py-2.5`.
- La cifra del cuerpo es **negra/foreground**, no coloreada del tone (`color: hsl(var(--text-primary))`).
- Cuando `headerBand=true`, ignorar `topAccent` (mutuamente excluyentes).

**Spec visual completa** (ver mockup):
```
┌────────────────────────────────────┐
│ PEDIDOS                      📅   │  ← banda 36px, bg = t.color, todo blanco
├────────────────────────────────────┤
│                                    │
│  2                                 │  ← número text-2xl negro, tabular
│  de $649.500                       │  ← sub muted text-xs
│                                    │
└────────────────────────────────────┘
```

Tests rápidos:
- `headerBand + tone=primary` → banda roja brand
- `headerBand + tone=info` → banda azul
- `headerBand + tone=success` → banda verde
- `headerBand + tone=warning` → banda naranja (NO amarillo — el mockup usa naranja saturado `#C8682E` para Total Mes)

**Nota tones**: el mapeo `warning → naranja` en row 2 es contextual. El TONES map sigue: success=verde, info=azul, warning=naranja, primary=rojo. El `--accent-orange` ya existe en tokens — usar `tone="warning"` y verificar que renderiza naranja, o crear nuevo tone `orange` si hace falta.

**Acceptance**: `<KpiCard headerBand tone="primary" label="PEDIDOS" value={2} sub="de $649.500" icon={CalendarDays} />` produce visualmente la card de PEDIDOS del mockup.

**Commit**: `feat(dashboard-v3): fase1 KpiCard variante headerBand`

---

### FASE 2 — TabHoy Row 1: Arquetipo A (Ventas/Caja/Gastos)

**Archivo**: `dashboard/src/tabs/TabHoy.jsx`

Quitar `topAccent` de las 3 cards principales. Bump cifra a **text-3xl** (extender `KpiCard` con `heroValue='2xl' | '3xl'` o pasar a `text-3xl` por defecto cuando `heroValue=true` — preferir lo segundo, menos churn).

Cambios concretos:

#### Ventas Hoy
```jsx
<KpiCard
  tone="primary"
  label="Ventas hoy"
  value={cop(totalHoy)}
  icon={ShoppingCart}
  sub={`${pedidosHoy} ${pedidosHoy === 1 ? 'venta' : 'ventas'}`}
  spark={historico7d}
  iconStyle="filled"
  heroValue
/>
```
- **Sin `topAccent`**.
- Color del número: **`hsl(var(--accent))` (rojo brand)**, igual que el mockup.
- Spark: ya está en posición abajo-derecha, OK.

#### Gastos Hoy
```jsx
<KpiCard
  tone="danger"
  label="Gastos hoy"
  value={cop(totalGastos)}
  icon={Receipt}
  onClick={() => navigate('/gastos')}
  actionLabel="Registrar gasto"
  sub={`${numGastos} ${numGastos === 1 ? 'registro' : 'registros'}`}
  iconStyle="filled"
  heroValue
/>
```
- Sin `topAccent`. Número en text-3xl `hsl(var(--danger))`.

#### Caja (caso especial — necesita custom render)
La banda amarilla horizontal **no la puede renderizar `KpiCard` standard**. Dos opciones:

**Opción A** (recomendada): añadir a `KpiCard` una prop nueva `stateBand: { tone, pill: string, text: string }` que renderiza dentro del cuerpo (debajo del label, en vez del `value` numérico) un rectángulo coloreado de la altura del bloque value.

**Opción B**: implementar la card de CAJA como componente custom local en TabHoy (no usar `KpiCard`).

Optar por **Opción B** porque es un caso único; no contaminamos el API del `KpiCard` con un slot.

```jsx
<CajaCard
  abierta={cajaAbierta}
  apertura={aperturaCaja}
  horaApertura={horaApertura}
  numMovs={numMovs}
  onClick={() => navigate('/caja')}
/>
```

`CajaCard` (componente local, ~40 LOC):
- Estructura del Arquetipo A: white card, label "CAJA" arriba, ícono Wallet en cuadrado coloreado top-right (rojo si cerrada para urgencia, verde si abierta).
- Cuerpo: rectángulo de altura ~52px con `bg-warning/20 border border-warning/30` (cerrada) o `bg-success/15 border border-success/30` (abierta).
- Dentro del rectángulo: badge "CERRADA" / "ABIERTA" + texto descriptivo a la derecha.

**Spec visual exacta CAJA cerrada**:
```
┌────────────────────────────────────┐
│ CAJA                          📋   │
│                                    │
│ ┌────────────────────────────────┐ │
│ │ ⓒERRADA  Pendiente de apertura │ │  ← banda amarilla horizontal
│ └────────────────────────────────┘ │
└────────────────────────────────────┘
```

**Commit**: `feat(dashboard-v3): fase2 TabHoy row1 arquetipo hero + CajaCard especial`

---

### FASE 3 — TabHoy Row 2: aplicar `headerBand` (Pedidos/Ticket/Semana/Mes)

**Archivo**: `dashboard/src/tabs/TabHoy.jsx`

Reemplazar los 4 `<KpiCard ... compact topAccent iconStyle="filled" />` por la variante `headerBand`. Ajustar tones para que correspondan a los colores del mockup:

```jsx
<KpiCard headerBand tone="primary" label="Pedidos"       value={num(pedidosHoy)} sub={`de ${cop(totalHoy)}`} icon={CalendarDays}  />
<KpiCard headerBand tone="info"    label="Ticket prom."  value={cop(ticketProm)} sub="últimos 7 días"        icon={CalendarDays}  />
<KpiCard headerBand tone="success" label="Total semana"  value={cop(totalSemana)} sub="últimos 7 días"       icon={CalendarDays}  />
<KpiCard headerBand tone="warning" label="Total mes"     value={cop(totalMes)}   sub="mes en curso"          icon={CalendarDays}  />
```

Importante: el mockup usa ícono **calendar / agenda** en las 4 — no listOrdered/calculator/calendarRange/calendarDays mixtos. Unificar al ícono `CalendarDays` o similar.

Quitar prop `compact` — el card con headerBand tiene su propia altura natural (~110px) que matchea el mockup.

**Commit**: `feat(dashboard-v3): fase3 TabHoy row2 headerBand colorido`

---

### FASE 4 — Chart "Evolución de ventas": número grande prominente

**Archivo**: `dashboard/src/tabs/TabHoy.jsx`, componente `EvolucionChart`

Cambio mínimo al header del chart. Actual:
```
EVOLUCIÓN DE VENTAS              [7d][30d]
$XXX acumulado · prom. $XX/día
```

Target:
```
EVOLUCIÓN DE VENTAS                              [7d][30d]
$1.418.000  acumulado - prom. $202.571/dia
↑text-2xl    ↑text-[11px] text-muted
```

Subir el tamaño del total a `text-2xl font-semibold` (era `text-xl`). El "acumulado · prom." va inline pequeño a su derecha.

**Commit**: `feat(dashboard-v3): fase4 chart hero number bump`

---

### FASE 5 — Thumbnails de producto en Últimas Ventas + Top Productos

**Archivo**: `dashboard/src/tabs/TabHoy.jsx`

#### Backend check (5.0)
Verificar si `productos` o `inventario` tiene columna `imagen_url` / `thumbnail_url`. Si NO existe:
- Por ahora usar **placeholder generativo**: cuadrado `bg-surface-2` con iniciales del producto en `text-muted-foreground font-semibold`. ~32x32px rounded-sm.
- TODO en plan: añadir columna `imagen_url` a productos en migración futura. No bloqueante.

Helper compartido (extraer a `dashboard/src/components/shared.jsx`):
```js
export function ProductThumb({ src, nombre, size = 32 }) {
  const iniciales = String(nombre || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase()).join('')
  if (src) return <img src={src} alt={nombre} className="rounded-sm object-cover" style={{ width: size, height: size }} />
  return (
    <span
      className="grid place-items-center rounded-sm bg-surface-2 text-muted-foreground font-semibold"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
      aria-hidden="true"
    >{iniciales}</span>
  )
}
```

#### FeedLive (Últimas Ventas) — añadir bloque "productos vendidos"
El mockup muestra 2 secciones en la card derecha:
1. **Lista de ventas con hora + monto + método** (ya implementado, OK).
2. **Lista de productos vendidos** (nueva): thumbnail + nombre + cantidad. Es esencialmente un agregado de productos del día.

Implementación: añadir al final del `<FeedLive>` un divider + segunda lista con `topProductos` (ya calculado), limit 3-4, mostrando thumbnail + nombre + "X ud".

#### TopProductos — reemplazar # por thumbnail
Cambiar el `<span className="text-muted-foreground tabular w-4 shrink-0">{i + 1}</span>` por `<ProductThumb nombre={p.nombre} src={p.imagen_url} size={28} />`. El resto de la card queda igual.

**Commit**: `feat(dashboard-v3): fase5 thumbnails de producto en feed y top`

---

### FASE 6 — Polish bars y refinamientos finales

**Archivo**: `dashboard/src/tabs/TabHoy.jsx`

#### Métodos de pago — bars más gruesas
- `h-1` → `h-2` (8px) en la barra de progreso.
- Mantener gradiente de color por método (rojo brand para Transferencia, verde para Efectivo, etc.).
- Quitar el `%` text del lado derecho (el mockup no lo muestra prominente, ya está implícito en la longitud de la barra). Opcional: dejar `%` muy pequeño debajo.

#### Top Productos — bars también `h-2`
Bump de `h-1` a `h-2`. Color de la barra: ya es `bg-primary/80`, OK.

**Commit**: `feat(dashboard-v3): fase6 polish bars y refinamientos`

---

### FASE 7 (opcional, post-MVP) — propagar `headerBand` a otros tabs

Sólo si tras Fase 1-6 el TabHoy queda igual al mockup y Andrés aprueba. NO ejecutar hasta confirmación.

Tabs a propagar (mismo patrón Row 2):
- TabLibroIVA: 3 KPIs → headerBand
- TabFacturacion: 3 KPIs → headerBand
- TabComprasFiscal: 5 KPIs → headerBand (o mantener compact, decisión por densidad)
- TabResultados (MiniKpi): 4 KPIs → headerBand
- TabCompras: 4 KPIs → headerBand
- TabProveedores: 4 KPIs → headerBand
- TabGastos: 3 KPIs → headerBand
- TabCaja: 4 KPIs → headerBand
- historial/VistaDia: 4 KPIs → headerBand

Los **Tabs cockpit** (TabHoy) usan **mezcla** de arquetipos (A para los 3 hero, B para los 4 secundarios).
Los **Tabs operativos** (resto) usan **Arquetipo B (headerBand)** uniformemente — son grids de métricas, no cockpits.

---

## Riesgos y mitigaciones

| Severidad | Riesgo | Mitigación |
|---|---|---|
| MEDIUM | `headerBand` en dark mode puede saturar/cegar | Probar con `--accent` saturado en dark — el banda usa color sólido OK, mientras texto sea blanco hay contraste AAA |
| MEDIUM | Thumbnails sin `imagen_url` en DB → todos iniciales | Aceptable como degradación elegante. Crear migración futura para añadir URLs reales con Cloudinary |
| MEDIUM | CajaCard custom rompe consistencia con el sistema | Aceptable — el patrón "state band" es genuinamente único en el mockup, no merece abstracción prematura |
| LOW | text-3xl en mobile puede romper layout de 3 cards en row | Verificar en breakpoint sm/md, usar `text-2xl md:text-3xl` si necesario |
| LOW | Cambio de tone warning a naranja en row 2 | El `--accent-orange` ya existe en tokens. Verificar si `tone="warning"` mapea a naranja o crear `tone="orange"` |

---

## Métricas de éxito

- Andrés mira el dashboard y dice "**sí, así**" — sin necesidad de aclaraciones.
- Captura del dashboard vs. captura del mockup Gemini: **diferenciables solo por datos reales, no por estilo**.
- Cero regresiones funcionales (toda la lógica de derivación de datos intacta).
- Build verde tras cada commit.
- Net LOC ≤ +200 (FASE 1 añade ~30 LOC, FASE 2 añade ~50 LOC para CajaCard, resto es refactor).

---

## Complejidad y tiempo

**MEDIA-ALTA** — 3-5 horas con foco. Distribución:
- FASE 1: 30 min (KpiCard headerBand variant)
- FASE 2: 60 min (Row 1 simplificar + CajaCard custom)
- FASE 3: 20 min (Row 2 swap a headerBand)
- FASE 4: 15 min (chart header bump)
- FASE 5: 60 min (helper ProductThumb + integrar en 2 lugares)
- FASE 6: 20 min (polish bars)
- FASE 7: condicional, +90 min

---

## Plan de validación visual

Después de FASE 2, 3 y 5, screenshot del dashboard y comparar lado-a-lado con `reference-gemini-final.png`. Si hay delta visible, parar y ajustar antes de continuar.

**No tocar otras pestañas (TabCaja, TabLibroIVA, etc.) hasta que TabHoy quede ≈100% match con el mockup.**

---

## Siguiente paso (waiting for Andrés)

1. ¿Plan aprobado? ¿Falta algo?
2. ¿Ejecutamos Fase 1-6 secuencialmente sin checkpoints, o paro tras FASE 3 para que valides?
3. ¿Borramos los commits de V2 (`refactor(dashboard): KpiCard compartido…`) y rebaseamos limpio sobre `main`, o seguimos acumulando en `feat/dashboard-polish`?
