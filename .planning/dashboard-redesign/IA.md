# Information Architecture — Dashboard FerreBot (Fase 1)

**Fecha**: 2026-05-23
**Estado**: Aprobado por Andrés
**Fase**: 1 — IA nueva (precede a Stitch mockups en Fase 2)

---

## Decisiones de Andrés (esta sesión)

| Decisión | Valor |
|---|---|
| Navegación primaria | **Sidebar persistente agrupado + Cmd+K** como acelerador global |
| Home / landing | **Cockpit "HOY"** con foco en plata (ventas, caja, gastos, totales, métodos, ticket promedio). Stock como sección secundaria abajo. |
| Dark mode | **Light + dark desde Fase 3** (tokens semánticos paralelos) |
| Agrupamiento | **4 grupos del PLAN.md**: Operación / Gestión / Reportes / Fiscal |
| Cleanup tabs | Top10 → sección de Resultados · Cablear `FacturasElectronicasRecibidas` (hoy huérfano) · Unificar `Historial` + `Histórico` en uno solo |

---

## Sitemap nuevo

```
/                         → redirect a /hoy
/hoy                      → Cockpit operativo (NUEVO — reemplaza TabResumen como landing)
/login                    → ya existe

OPERACIÓN
  /ventas                 → TabVentasRapidas (siempre montada para preservar carrito)
  /caja                   → TabCaja
  /inventario             → TabInventario

GESTIÓN
  /clientes               → TabClientes
  /compras                → TabCompras
  /proveedores            → TabProveedores
  /gastos                 → TabGastos

REPORTES
  /resumen                → TabResumen (KPIs históricos — degradado de landing a sub-tab)
  /historial              → TabHistorial unificado (fusiona Historial + HistoricoVentas)
  /resultados             → TabResultados
    └── tab interno: Top 10 productos (era TabTopProductos)
  /kardex                 → TabKardex

FISCAL
  /facturacion            → TabFacturacion
  /facturas-recibidas     → FacturasElectronicasRecibidas (HOY HUÉRFANO — se cablea ahora)
  /libro-iva              → TabLibroIVA
  /compras-fiscal         → TabComprasFiscal

ATAJOS GLOBALES (sin ruta)
  Cmd+K / Ctrl+K          → command palette (busca tab, cliente, producto, acción)
  Cmd+N / Ctrl+N          → nueva venta rápida (atajo a /ventas)
```

**Resumen numérico**:
- Antes: 16 tabs activos + 1 huérfano (`FacturasElectronicasRecibidas`)
- Después: **15 destinos** en sidebar + Top10 como sección interna de Resultados + Hoy como landing
- Tabs eliminados como destinos propios: `TabTopProductos`, `TabHistoricoVentas` (mergeado)
- Tabs nuevos: `Hoy` (cockpit)
- Tabs rescatados: `FacturasElectronicasRecibidas`

---

## Cockpit "HOY" — wireframe de bajo nivel

Prioridad de la mirada (orden de protagonismo según Andrés): **plata primero, stock al final**.

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ HOY · martes 23 may              [Vendedor ▾]  Bot ●  🕐 14:32              │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌───────────────────────┬───────────────────────┬───────────────────────┐    │
│  │ VENTAS HOY            │ CAJA                  │ GASTOS HOY            │    │
│  │                       │                       │                       │    │
│  │  $ 2.450.000          │  Abierta · $ 850.000  │  $ 120.000            │    │
│  │  17 ventas · ticket   │  desde 08:14          │  4 gastos             │    │
│  │  prom. $144.117       │  Δ +$1.450k           │                       │    │
│  │                       │  [Cerrar caja →]      │  [+ Gasto]            │    │
│  └───────────────────────┴───────────────────────┴───────────────────────┘    │
│                                                                               │
│  ┌─────────────────────────────────────┬─────────────────────────────────┐    │
│  │ ACUMULADOS                          │ MÉTODOS DE PAGO (hoy)           │    │
│  │  Semana   $ 14.200.000  ▲ 12%      │  Efectivo    62%  ████████░░░    │    │
│  │  Mes      $ 48.900.000  ▲ 4%       │  Transferenc 28%  ████░░░░░░░    │    │
│  │  [sparkline 30 días]                │  Fiado       10%  █░░░░░░░░░    │    │
│  │                                     │  Tarjeta      0%                │    │
│  └─────────────────────────────────────┴─────────────────────────────────┘    │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐      │
│  │ ÚLTIMAS 8 VENTAS                                      [+ Nueva venta]      │
│  │ #2045 · 14:28 · Andrés · $32.400 · efectivo                         │      │
│  │ #2044 · 14:15 · Andrés · $145.000 · transferencia                   │      │
│  │ ...                                                                  │      │
│  └─────────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  ┌─────────────────────────────────────┬─────────────────────────────────┐    │
│  │ ALERTAS DE STOCK (3)                │ FIADOS POR COBRAR               │    │
│  │  • Cemento 50kg     2 und  ⚠        │  Total vigente   $ 380.000      │    │
│  │  • Drywall 1/2      8 lám  ⚠        │  Vencidos        $ 90.000  ⚠    │    │
│  │  • Tornillo 3/8     12 und ⚠        │  [Ver fiados →]                 │    │
│  │  [Ver inventario →]                 │                                 │    │
│  └─────────────────────────────────────┴─────────────────────────────────┘    │
│                                                                               │
│  Quick actions: [+ Venta] [+ Gasto] [+ Compra] [+ Cliente] [Cierre caja]      │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Densidad por zona** (principio PRODUCT.md "densidad calibrada"):
- **Fila 1** (cifras del día): tipografía grande, alto contraste, 3 cards iguales.
- **Fila 2** (acumulados + métodos): densidad media, soporta sparkline y barras horizontales.
- **Fila 3** (últimas ventas): tabla densa, 7-8 filas, tipografía pequeña tabular-nums.
- **Fila 4** (stock + fiados): densidad baja, badges de severidad, links a tabs completos.
- **Quick actions**: fijo arriba del fold en móvil, abajo en desktop.

**Datos requeridos** (endpoints ya existentes — no se toca backend):
- `GET /caja/estado-hoy` — apertura + ventas + total
- `GET /ventas?desde=hoy` — ventas hoy + ticket promedio
- `GET /gastos?desde=hoy` — gastos hoy
- `GET /resultados?rango=semana` y `mes` — acumulados
- `GET /ventas/metodos-pago?rango=hoy` — distribución (puede requerir endpoint nuevo si no existe)
- `GET /inventario/alertas` — stock bajo
- `GET /fiados/resumen` — fiados pendientes

> Acción Fase 4 Wave 1: verificar endpoints disponibles. Si `metodos-pago` no existe, derivarlo en el cliente desde `/ventas?desde=hoy` (cada venta trae `metodo_pago`).

---

## Shell con sidebar — wireframe de bajo nivel

### Desktop (≥1024px)

```
┌───────────────┬───────────────────────────────────────────────────────────────┐
│  FERRE        │  HEADER (sticky)                                              │
│  PUNTO ROJO   │   [Vendedor ▾] [Tema] [Refresh ↻] [Bot ●] [⌘K] [Avatar Andrés]│
│  v5           ├───────────────────────────────────────────────────────────────┤
│               │                                                               │
│  ◉ Hoy        │                                                               │
│               │                                                               │
│  OPERACIÓN    │                                                               │
│  · Ventas R.  │                                                               │
│  · Caja       │             CONTENIDO DEL TAB                                 │
│  · Inventario │                                                               │
│               │                                                               │
│  GESTIÓN  ▾   │                                                               │
│  · Clientes   │                                                               │
│  · Compras    │                                                               │
│  · Proveed.   │                                                               │
│  · Gastos     │                                                               │
│               │                                                               │
│  REPORTES ▾   │                                                               │
│  · Resumen    │                                                               │
│  · Historial  │                                                               │
│  · Resultados │                                                               │
│  · Kárdex     │                                                               │
│               │                                                               │
│  FISCAL   ▸   │  (colapsado por defecto — uso menos frecuente)               │
│               │                                                               │
│  ─────────    │                                                               │
│  ⌘K Buscar    │                                                               │
└───────────────┴───────────────────────────────────────────────────────────────┘
   240px ancho
```

**Reglas del sidebar**:
- Ancho fijo `240px` desktop. Colapsable a `64px` (solo iconos) con shortcut `[`.
- Grupos con header pequeño `font-size: 11px, letter-spacing: .12em, text-transform: uppercase`.
- "Hoy" siempre top-level (sin grupo) — es el destino más visitado.
- "Fiscal" inicia **colapsado** por defecto (uso esporádico). El resto inicia expandido.
- Item activo: pill de `accent` (rojo `#C8200E`) con borde izquierdo de 3px.
- Persistir estado expandido/colapsado en `localStorage` (`ferrebot_sidebar_state`).
- Sticky en scroll, scrollable internamente si el viewport no alcanza.

### Móvil (<768px)

Mantener el **BottomNav actual** (bottom tabs con grupos + drawer) — ya funciona bien según AUDIT.md. Cambios mínimos:
- Reemplazar grupos por los 4 nuevos (Operación / Gestión / Reportes / Fiscal).
- Añadir "Hoy" como botón FAB centrado (estilo TikTok/Instagram) o como primer item.
- Cmd+K se vuelve un icono de búsqueda en el header móvil.

### Tablet (768-1023px)

Sidebar **colapsado por defecto** (solo iconos, 64px). Click en grupo abre flyout temporal con los items.

---

## Command Palette (Cmd+K / Ctrl+K)

Componente: shadcn `Command` (sobre Radix).

**Categorías que indexa**:
1. **Navegación** — todos los items del sidebar
2. **Acciones** — nueva venta, abrir caja, cerrar caja, nuevo gasto, nueva compra, nuevo cliente
3. **Clientes** — buscar por nombre (top 50 cargados, fetch on-demand)
4. **Productos** — buscar por nombre/código (top 100 cargados, fetch on-demand)
5. **Configuración** — cambiar tema, cambiar vendedor (admin), logout

**Atajos secundarios**:
- `Cmd+N` → nueva venta (lleva a `/ventas` con foco en input)
- `Cmd+/` → abrir ChatWidget IA del dashboard
- `Esc` → cierra palette / modals
- `g h` → go to Hoy (estilo Linear/GitHub)
- `g v` → go to Ventas Rápidas

> Decisión Fase 2: si los atajos `g h` se sienten over-engineered para el contexto ferretería, los removemos. Cmd+K + Cmd+N son suficientes en MVP.

---

## Mapeo tab → ruta → componente

| Sidebar item | Ruta nueva | Componente actual | Cambio en Fase 4 |
|---|---|---|---|
| Hoy | `/hoy` | (no existe) | **Crear `TabHoy.jsx` nuevo** |
| Ventas Rápidas | `/ventas` | `TabVentasRapidas` | Solo restyle |
| Caja | `/caja` | `TabCaja` | Solo restyle |
| Inventario | `/inventario` | `TabInventario` | Solo restyle |
| Clientes | `/clientes` | `TabClientes` | Solo restyle |
| Compras | `/compras` | `TabCompras` | Solo restyle |
| Proveedores | `/proveedores` | `TabProveedores` | Solo restyle |
| Gastos | `/gastos` | `TabGastos` | Solo restyle |
| Resumen | `/resumen` | `TabResumen` | Degradado de landing |
| Historial | `/historial` | `TabHistorial` + `TabHistoricoVentas` | **Fusionar en uno** |
| Resultados | `/resultados` | `TabResultados` + `TabTopProductos` | **Top10 entra como tab interno** |
| Kárdex | `/kardex` | `TabKardex` | Solo restyle |
| Facturación | `/facturacion` | `TabFacturacion` | Solo restyle |
| Facturas recibidas | `/facturas-recibidas` | `FacturasElectronicasRecibidas` | **Cablear (hoy huérfano)** |
| Libro IVA | `/libro-iva` | `TabLibroIVA` | Solo restyle |
| Compras Fiscal | `/compras-fiscal` | `TabComprasFiscal` | Solo restyle |

**Migración de URL**: el dashboard actual no usa rutas reales (tab en `useState`). Fase 4 introduce `react-router` con rutas reales para que `Cmd+K` pueda navegar por URL y `back/forward` del browser funcione.

---

## Cambios de fusión (Historial + Histórico)

`TabHistorial` y `TabHistoricoVentas` hoy duplican concepto: ambas listan ventas. Fusión en Fase 4 Wave 2:

**`/historial` unificado** — un solo componente con:
- Filtro de rango persistente: **Hoy** (default) / Semana / Mes / Personalizado
- Filtros adicionales: vendedor, cliente, método de pago, estado (anulada/activa)
- Tabla densa con paginación lazy
- Acciones por fila: ver detalle, anular, imprimir, generar factura electrónica

**Estado de las páginas viejas**:
- `TabHistorial.jsx` → renombrar a `TabHistorialUnificado.jsx` (lleva la mayor parte de la lógica actual)
- `TabHistoricoVentas.jsx` → eliminar. Su único valor único era el filtro por rangos largos — se absorbe en el filtro "Personalizado".

---

## Cambios de jerarquía (Top 10 dentro de Resultados)

`TabResultados.jsx` pasa a tener tabs internos (con shadcn `Tabs`):
- **Resultados** (default) — P&L del rango, márgenes, gráficas
- **Top productos** — el actual `TabTopProductos`
- **Top clientes** (futuro, no en Fase 4)

`TabTopProductos.jsx` se mueve a `dashboard/src/tabs/resultados/TopProductos.jsx` o se inline en `TabResultados.jsx`. Decisión exacta en Fase 4.

---

## Reglas de la Fase 1 (cierre)

1. **Nada de código de UI en Fase 1** — esto es solo IA y wireframes ASCII. Los wireframes pixel-perfect salen de Stitch en Fase 2.
2. **El cockpit "Hoy" se diseña visualmente en Fase 2** — aquí solo se acuerda contenido y prioridad.
3. **Las fusiones de tabs (Historial, Top10) se ejecutan en Fase 4 Wave 1/2** — no antes, para no introducir riesgo durante el rediseño visual.
4. **`useRealtime.js` sigue intocable**. Los nuevos endpoints que requiera el cockpit (si `metodos-pago` no existe) son **derivados en cliente** desde `/ventas?desde=hoy`.
5. **Backend no se toca en este rediseño**. Si un dato del cockpit no tiene endpoint, se computa en el cliente o se posterga.

---

## Deliverables Fase 1

- ✅ Este documento (`IA.md`)
- ⏸️ Cleanup P0 opcional (`dashboard/src/index.css` vacío + viewport sin `maximum-scale`)
- ⏸️ Actualización `NEXT-STEPS.md` cerrando Fase 1

## Siguiente paso

Fase 2 — Dirección visual por evidencia con Stitch. Los wireframes ASCII de este documento son el input semántico; Stitch produce las 3-4 variantes visuales para decidir estética.
