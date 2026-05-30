# Prompts Stitch — Fase 2 (Cockpit HOY × 4 direcciones × 2 viewports)

**Estado**: redactados 2026-05-23. Stitch MCP no respondió en la sesión de generación (10 timeouts, 0 screens persistidos en proyecto `12113492557069924495`). Reutilizar estos prompts cuando Stitch vuelva a responder, o portarlos a otra herramienta (frontend-design skill, v0, etc.).

**Contexto compartido a todos los prompts**:
- Dashboard de ferretería colombiana FerreBot Punto Rojo. Cockpit HOY = landing.
- Contenido viene de `.planning/dashboard-redesign/IA.md` (wireframe ASCII bajo nivel).
- Anti-references de `PRODUCT.md`: nada de Bootstrap/Material genérico, nada de SAP gris, nada de crypto neón.
- Ancla de marca: rojo `#C8200E` (calibrado, no decoración invasiva).
- Datos mockeados consistentes en todos: ventas $2.450.000 (17 ventas, ticket prom $144.117), caja abierta $850.000 desde 08:14 con Δ +$1.450k, gastos $120.000 (4 gastos), semana $14.200.000 ▲12%, mes $48.900.000 ▲4%, métodos pago Efectivo 62% / Transferencia 28% / Fiado 10% / Tarjeta 0%, 3 alertas stock (Cemento 50kg 2und, Drywall 1/2" 8lám, Tornillo 3/8" 12und), fiados vigentes $380.000 / vencidos $90.000.

---

## A — Bento minimalista (Linear/Vercel)

### A-desktop (1440px)

Cockpit "HOY" — landing del dashboard de una ferretería colombiana (FerreBot Punto Rojo). En español. Vista desktop 1440px.

DIRECCIÓN VISUAL: **A — Bento minimalista estilo Linear/Vercel**. Mucho whitespace, jerarquía por tipografía (no por color), borders sutiles 1px, radios 12-16px, sin gradientes, sin shadows pesados. Background gris muy claro #FAFAFA con cards blancas. Tipografía sans geométrica moderna (Geist, Inter, o similar). Acento de marca #C8200E SOLO en estados activos y el item de sidebar activo — nunca como fill de cards. Numbers tabular-nums. Sensación: producto SaaS premium, calmo, confiado.

LAYOUT (sidebar izq 240px + contenido):
Sidebar: logo "FERRE · PUNTO ROJO v5", item activo "Hoy" con pill rojo y border-left 3px, grupos uppercase 11px: OPERACIÓN (Ventas Rápidas, Caja, Inventario), GESTIÓN (Clientes, Compras, Proveedores, Gastos), REPORTES (Resumen, Historial, Resultados, Kárdex), FISCAL (colapsado). Abajo: "⌘K Buscar".

Header sticky: "HOY · martes 23 may" + chips a la derecha [Vendedor ▾] [Bot ●] [⌘K] [Avatar Andrés AC]

Bento de 3 columnas, primera fila 3 cards iguales:
- VENTAS HOY: $2.450.000 grande, "17 ventas · ticket prom. $144.117"
- CAJA: "Abierta · $850.000" + "desde 08:14" + "Δ +$1.450k" + botón ghost "Cerrar caja →"
- GASTOS HOY: $120.000 + "4 gastos" + botón ghost "+ Gasto"

Fila 2 (dos cards):
- ACUMULADOS: "Semana $14.200.000 ▲12%" "Mes $48.900.000 ▲4%" + sparkline 30 días minimalista
- MÉTODOS DE PAGO HOY: barras horizontales finas — Efectivo 62%, Transferencia 28%, Fiado 10%, Tarjeta 0%

Fila 3 ancho completo: tabla "ÚLTIMAS 8 VENTAS" densa tabular: #2045 · 14:28 · Andrés · $32.400 · efectivo (8 filas), header con botón "+ Nueva venta"

Fila 4 (dos cards):
- ALERTAS DE STOCK (3): Cemento 50kg 2 und, Drywall 1/2" 8 lám, Tornillo 3/8" 12 und, badge naranja "⚠"
- FIADOS POR COBRAR: "Total vigente $380.000" "Vencidos $90.000 ⚠" link "Ver fiados →"

Quick actions abajo: chips inline [+ Venta] [+ Gasto] [+ Compra] [+ Cliente] [Cierre caja]

PROHIBIDO: gradientes neón, glassmorphism, dark mode, side-stripes verticales de color en cards (eso es un anti-patrón), icon-arriba-label-abajo en KPIs, plantilla admin tipo Bootstrap. Ningún elemento debe gritar.

### A-móvil (390px)

Cockpit "HOY" móvil — versión 390px del dashboard de ferretería FerreBot Punto Rojo.

DIRECCIÓN: **A — Bento minimalista estilo Linear/Vercel**. Whitespace generoso, cards blancas borde 1px sobre #FAFAFA, radios 12-16px, tipografía sans geométrica (Geist/Inter), tabular-nums en cifras. Acento rojo marca #C8200E solo en estado activo de bottom nav e indicadores críticos. Sin gradientes, sin glass, sin shadows pesados.

Header sticky: "HOY · mar 23 may" izquierda, [⌘K icon] [Avatar AC] derecha. Subline pequeño: "Andrés · 14:32".

Stack vertical, una columna:
1. VENTAS HOY (card hero): $2.450.000 muy grande, "17 ventas · prom $144.117"
2. CAJA (card): "Abierta · $850.000" "desde 08:14" "Δ +$1.450k" botón "Cerrar caja →"
3. GASTOS HOY: $120.000 · 4 gastos · botón "+ Gasto" inline
4. ACUMULADOS card: Semana $14.200.000 ▲12% / Mes $48.900.000 ▲4% + sparkline mini
5. MÉTODOS DE PAGO: barras horizontales finas (Efectivo 62%, Transferencia 28%, Fiado 10%, Tarjeta 0%)
6. ÚLTIMAS VENTAS (5 visibles): #2045 · 14:28 · $32.400 · efectivo. Link "Ver todas (17) →"
7. ALERTAS STOCK (3 items con badge ⚠ naranja)
8. FIADOS: total vigente + vencidos

FAB rojo #C8200E flotante esquina inferior derecha "+ Venta" (mostrador-first).

Bottom nav 5 items con iconos minimalistas: Hoy (activo), Ventas, Caja, Inventario, Más. Estado activo: ícono coloreado #C8200E + label visible, los demás solo ícono. Altura 64px, área táctil 44×44px mínimo. Safe area iOS respetada.

PROHIBIDO: glassmorphism, gradientes neón, dark mode, side-stripes, plantilla admin genérica.

---

## B — Industrial denso (Bloomberg/POS)

### B-desktop (1440px)

Cockpit "HOY" desktop 1440px — dashboard ferretería colombiana FerreBot Punto Rojo.

DIRECCIÓN VISUAL: **B — Industrial denso estilo Bloomberg/POS profesional**. Información maximizada, tipografía monoespaciada para todas las cifras (JetBrains Mono, IBM Plex Mono), sans condensada para labels (Inter Tight, Söhne Mono). Paleta: blanco roto #FCFBF8 fondo, líneas finas grises #E5E2DD, texto casi negro #0B0B0B. Acento marca rojo #C8200E para señales críticas (deltas negativos, stock crítico, vendor pill activo). Verde militar #1E5A3A para deltas positivos. Sin radios redondos (radius 4px máximo, varios elementos sharp 0px). Sin shadows. Sensación: terminal financiera, mostrador profesional, "cada pixel paga renta".

LAYOUT: sidebar izquierdo 220px denso + header tipo barra de estado superior + contenido cuadriculado.

Sidebar: tipografía 13px regular, items en una línea, grupos en mayúsculas 10px tracking ancho. Item activo: fondo rojo #C8200E texto blanco, sin radio.

Header: barra superior 48px con divisores verticales tipo Bloomberg. Bloques: [HOY · MAR 23 MAY 14:32:08] [VENDEDOR: ANDRÉS C ▾] [BOT ●LIVE] [REFRESH 00:04s] [⌘K] [AC]

Bento alta densidad — grid 4 columnas:
Fila 1 (4 cards estrechas): VENTAS HOY $2.450.000 / TICKET PROM $144.117 / CAJA ABIERTA $850.000 / GASTOS $120.000 — cada una con label uppercase pequeño arriba, número mono grande, sub-línea micro abajo con delta vs ayer (verde/rojo).

Fila 2 (3+1):
- Card ancha (3 col) tabla LIBRO DE VENTAS HOY (12 filas): cols # / HORA / VENDEDOR / CLIENTE / TOTAL / MÉTODO / EST. Hover row highlight gris. Numbers tabular alineadas derecha.
- Card lateral (1 col) MÉTODOS PAGO: lista vertical con porcentaje + barra horizontal cuadrada fina.

Fila 3 (2+2):
- Card ACUMULADOS: tabla 3 filas (SEMANA / MES / AÑO) con monto, delta vs anterior, sparkline ASCII estilo barra
- Card FIADOS: tabla 4 filas (CLIENTE / SALDO / VENC / DÍAS), última roja con "VENCIDO -12d"

Fila 4 (2+2):
- Card STOCK CRÍTICO: tabla 5 filas (SKU / DESC / EXIST / MIN / DIFF) con badge cuadrado naranja "BAJO" o rojo "CERO"
- Card CAJA / MOVIMIENTOS: ingresos/egresos del día, balance corriente

Footer barra inferior: status [BD: ONLINE] [SSE: STREAMING 1 cliente] [ÚLT. SYNC 00:02s] [VER LOG]

PROHIBIDO: cards aireados estilo SaaS, KPIs con icon-arriba-label-abajo, gradientes, glass, radios grandes, espacios vacíos decorativos. Esto es información-primero. Pero NO gris industrial sin gracia tipo Siigo/SAP: tiene que tener carácter (tipografía deliberada, micro-detalles en deltas, jerarquía clara, color rojo marca presente).

### B-móvil (390px)

Cockpit "HOY" móvil 390px — dashboard ferretería FerreBot Punto Rojo, dirección Industrial denso.

DIRECCIÓN: **B — Industrial denso Bloomberg/POS**. Tipografía mono para cifras (JetBrains Mono / IBM Plex Mono), sans condensada para labels uppercase. Paleta blanco roto #FCFBF8, líneas finas #E5E2DD, texto #0B0B0B. Acento rojo marca #C8200E para alertas críticas y deltas negativos, verde militar #1E5A3A para positivos. Radios 0-4px máximo. Sin gradientes, sin shadows. Estética: terminal portátil del operador, no SaaS aireado.

Header 56px: línea 1 "HOY · MAR 23 MAY 14:32" + Avatar AC derecha. Línea 2 chips densos: [BOT ●LIVE] [VEND: ANDRÉS ▾] [⌘K]

Stack vertical denso, separadores horizontales 1px en vez de gaps grandes:

Bloque 1 — strip de KPIs 2×2 sin gaps (4 cuadrantes divididos por líneas): VENTAS HOY $2.450.000 / TICKET $144.117 / CAJA $850.000 / GASTOS $120.000. Cada cuadrante: label uppercase 10px tracking ancho arriba, número mono medio centro, delta verde/rojo abajo.

Bloque 2 tabla LIBRO VENTAS HOY: 8 filas mono, cols compactas #/HORA/TOTAL/MÉT abreviadas (E=efectivo, T=transfer, F=fiado). Link "VER 17 →"

Bloque 3 ACUMULADOS: 3 filas mono SEMANA $14.200.000 ▲12% / MES $48.900.000 ▲4% / AÑO $X ▲X%

Bloque 4 STOCK CRÍTICO (3 filas): SKU / DESC truncada / EXIST badge cuadrado naranja "BAJO"

Bloque 5 FIADOS: total + vencidos con barra fina roja

Bottom nav 5 items densos, sin labels (solo iconos pequeños mono-line), label inline solo en activo. Altura 56px. Touch target 44×44px. Activo: fondo rojo #C8200E. Items: HOY/VENTAS/CAJA/INV/MÁS

NO usar glassmorphism, no dark, no SaaS aireado. Densidad es la feature.

---

## C — Editorial serio (banking premium)

### C-desktop (1440px)

Cockpit "HOY" desktop 1440px — dashboard ferretería FerreBot Punto Rojo.

DIRECCIÓN VISUAL: **C — Editorial serio estilo banking premium / Monzo / Mercury / The Browser Company**. Sensación: producto financiero serio pero con alma editorial. Tipografía: serif elegante para títulos y cifras hero (GT Sectra, Tiempos Headline, o similar), sans humanista para body (Söhne, Inter Display). Paleta: crema warm #F5F1EB de fondo, paneles blanco puro, texto negro tinta #111111, dorado oxidado/cobre #B45B2E como acento secundario, rojo marca #C8200E reservado para alertas y CTA primario. Líneas hairline 1px. Mucho whitespace asimétrico. Cifras grandes tipográficamente impecables con número OldStyle o tabular según contexto. Sensación: anuario corporativo, balance bancario premium, no SaaS genérico.

LAYOUT: sidebar izq 240px tipográfico (no iconos cuadrados, items con tipografía elegante, sin pills agresivos — item activo subrayado con regla #C8200E 2px) + contenido editorial asimétrico (NO bento simétrico de 6 cards iguales).

Header generoso 80px: izquierda título serif grande "Hoy." en cursiva o regular, subline pequeña sans "martes, 23 de mayo · 14:32 · Andrés". Derecha discreta: [⌘K] [Vendedor] [Avatar AC]

Sección 1 — hero asimétrico (col izq 60% + col der 40%):
- Izq: "Ventas del día" eyebrow uppercase letterspaced, debajo cifra hero serif gigante $2.450.000, debajo metadata sans pequeña "17 ventas · ticket promedio $144.117 · 62% efectivo". Línea hairline divisoria abajo.
- Der: dos mini-paneles apilados — CAJA (estado: Abierta desde 08:14, balance $850.000, Δ +$1.450k, link "Cerrar caja") y GASTOS HOY ($120.000, 4 movimientos, link "+ Gasto").

Sección 2 — banda de acumulados, full width: 3 columnas separadas por hairlines verticales. SEMANA $14.200.000 ▲12% / MES $48.900.000 ▲4% / SPARKLINE 30 DÍAS con etiqueta editorial "Tendencia mensual" en cursiva.

Sección 3 — "Diario de ventas" (estilo periódico): tabla editorial 8 filas, tipografía generosa, columnas: # / Hora / Vendedor / Cliente / Monto / Método. Sin background alterno tipo zebra — solo hairlines. Botón "Registrar venta" arriba a la derecha, estilo CTA serio con rojo marca.

Sección 4 (2 col asimétrico 70/30):
- Izq: "Métodos de pago hoy" — barras horizontales con label tipográfico al lado, no porcentaje arriba sino al final de la barra como en un balance.
- Der: dos paneles verticales — "Stock crítico" (3 items en lista editorial, badge dorado oxidado #B45B2E) + "Fiados" (total vigente + vencidos con regla roja).

Footer editorial: línea hairline + "FerreBot Punto Rojo · v5 · datos al 14:32" tipografía serif pequeña centrada.

PROHIBIDO: cards bento simétricos genéricos, gradientes, glass, dark mode, neón, plantilla SaaS admin, iconos decorativos por todos lados (los iconos son raros y pesados, no constantes). Tipografía hace todo el trabajo, no el color.

### C-móvil (390px)

Cockpit "HOY" móvil 390px — dashboard ferretería FerreBot Punto Rojo, dirección Editorial.

DIRECCIÓN: **C — Editorial serio banking premium Monzo/Mercury**. Tipografía serif para títulos y cifras hero (GT Sectra/Tiempos), sans humanista para body (Söhne/Inter). Paleta crema #F5F1EB, paneles blanco puro, texto tinta #111111, cobre oxidado #B45B2E para acentos secundarios, rojo marca #C8200E solo alertas/CTA primario. Hairlines 1px. Whitespace generoso. Sensación editorial seria, no SaaS.

Header 72px: título serif grande "Hoy." izquierda + pequeña metadata "mar 23 may · 14:32" debajo. Avatar AC discreto derecha. Sin barra de chips agresiva.

Stack vertical editorial:

1. HERO: eyebrow uppercase letterspaced "Ventas del día" + cifra serif gigante $2.450.000 + sub sans "17 ventas · prom $144.117". Hairline divisor.

2. Dos mini paneles lado a lado 50/50 separados por hairline vertical: CAJA "Abierta · $850.000" "08:14 · Δ +$1.450k" link "Cerrar →" / GASTOS $120.000 "4 movimientos" link "+ Gasto"

3. Banda ACUMULADOS: 2 filas con label cursiva y monto serif (SEMANA $14.2M ▲12% / MES $48.9M ▲4%) + sparkline mini debajo titulado "Tendencia mensual".

4. "Diario de ventas" (5 visibles) tabla editorial hairlines: #2045 · 14:28 · $32.400 · ef. Link "Ver las 17 →"

5. MÉTODOS PAGO: barras horizontales con label tipográfico al final (estilo balance contable).

6. STOCK CRÍTICO (3 items lista editorial badge cobre oxidado).

7. FIADOS: total vigente + vencidos con regla hairline roja.

CTA flotante NO tipo FAB redondo neon: pill rectangular discreta abajo "Registrar venta" con borde rojo #C8200E texto rojo fondo blanco, ancho 60% centrada con safe-area.

Bottom nav editorial: 5 items con label visible siempre tipografía sans condensada pequeña, separados por hairlines verticales. Activo: subrayado rojo #C8200E 2px bajo el label. Items: Hoy/Ventas/Caja/Inv/Más. Sin iconos saturados.

PROHIBIDO: glass, gradientes, dark mode, bento genérico, plantilla SaaS, FAB rojo neón saturado, iconos por todos lados. Tipografía hace el trabajo.

---

## D — Glassmorphism disciplinado (visionOS/Arc)

### D-desktop (1440px)

Cockpit "HOY" desktop 1440px — dashboard ferretería FerreBot Punto Rojo.

DIRECCIÓN VISUAL: **D — Glassmorphism contemporáneo + micro-motion (Apple-influenced, no genérico)**. Atención: glassmorphism aplicado con disciplina — NO el típico AI-slop con blobs neon y blur exagerado. Hablamos de capas translúcidas calibradas sobre un fondo dinámico tinted, jerarquía clara, profundidad real. Inspiración: visionOS, Linear ambient, Arc browser, Apple system UI moderno.

Fondo: superficie warm #F4EFE8 con DOS blobs de color muy difuminados — uno rojo marca #C8200E muy diluido (10% opacity) abajo-izquierda, uno cobre #B45B2E (8% opacity) arriba-derecha. Blur 200px. Sin nada más decorativo en el fondo.

Cards: superficie translúcida (frosted glass) con backdrop-filter blur(40px), background rgba blanco 65% + saturación, borde hairline blanco 50% arriba (highlight), shadow muy sutil para flotar. Radios 20px. Tipografía sans moderna geométrica (SF Pro Display / Inter Display / Geist). Numbers tabular-nums. Sutil micro-motion en hover: scale 1.01, sombra crece.

LAYOUT sidebar izq 240px también glass (translúcido) + contenido bento generoso.

Sidebar glass: logo FERRE · PUNTO ROJO v5, item activo "Hoy" con fill glass más opaco + border-left rojo #C8200E 3px. Grupos uppercase tracking ancho.

Header glass sticky 64px: "Hoy" grande izquierda + "martes 23 may · 14:32" sub. Derecha: chips glass [Vendedor ▾] [Bot ●] [⌘K] [AC].

Fila 1 — 3 cards glass equal:
- VENTAS HOY $2.450.000 enorme, "17 ventas · prom $144.117"
- CAJA "Abierta $850.000" + "desde 08:14 · Δ +$1.450k" botón glass "Cerrar caja →"
- GASTOS HOY $120.000, "4 gastos", botón glass "+ Gasto"

Fila 2 — 2 cards glass:
- ACUMULADOS: Semana $14.200.000 ▲12% / Mes $48.900.000 ▲4% + sparkline animada sutil
- MÉTODOS DE PAGO: barras horizontales con fill semi-translúcido degradado muy sutil rojo→cobre (no neón, calibrado).

Fila 3 ancho completo: ÚLTIMAS 8 VENTAS tabla sobre superficie glass + botón "+ Nueva venta" CTA glass acentuado.

Fila 4 — 2 cards glass:
- STOCK CRÍTICO (3 alertas badge naranja translúcido)
- FIADOS: total $380.000 + vencidos $90.000 ⚠ con barra roja translúcida

Quick actions pill bar glass abajo: [+ Venta] [+ Gasto] [+ Compra] [+ Cliente] [Cierre caja].

PROHIBIDO: glass exagerado AI-slop con blobs neon saturados, gradientes púrpura-azul crypto, dark mode (este es light glass), neumorphism rosado, shadows pesadas estilo skeumorphism, plantillas dribbble genéricas. La transparencia es estructura, no decoración.

### D-móvil (390px)

Cockpit "HOY" móvil 390px — dashboard ferretería FerreBot Punto Rojo, dirección Glassmorphism.

DIRECCIÓN: **D — Glassmorphism disciplinado visionOS/Arc/Apple system**. NO AI-slop con neon blobs. Fondo warm #F4EFE8 con dos blobs muy difuminados (rojo marca #C8200E 10% abajo-izq, cobre #B45B2E 8% arriba-der, blur 200px). Cards glass: backdrop-filter blur(40px), rgba blanco 65%, hairline blanco 50% top, shadow sutil para flotar, radios 20px. Sans geométrica moderna (SF Pro Display/Inter Display/Geist). Tabular-nums.

Header glass sticky 64px: título "Hoy" grande + sub "mar 23 may · 14:32 · Andrés". Avatar AC chip glass derecha. Sin chips agresivos.

Stack glass con gaps generosos 16px:

1. Card hero glass VENTAS HOY: $2.450.000 gigante + "17 ventas · prom $144.117"
2. Card glass CAJA: "Abierta · $850.000" "08:14 · Δ +$1.450k" botón glass "Cerrar caja →"
3. Card glass GASTOS HOY: $120.000 · 4 gastos · botón glass "+ Gasto"
4. Card glass ACUMULADOS: Semana $14.2M ▲12% / Mes $48.9M ▲4% + sparkline mini
5. Card glass MÉTODOS PAGO: barras horizontales con fill translúcido sutil (rojo→cobre calibrado, no neón)
6. Card glass ÚLTIMAS VENTAS (5 visibles + "Ver las 17 →")
7. Card glass STOCK CRÍTICO (3 alertas badge naranja translúcido)
8. Card glass FIADOS: total + vencidos barra roja translúcida

FAB glass rojo #C8200E (no neón, calibrado, con backdrop-filter sutil) flotante esquina inf der "+ Venta" para mostrador.

Bottom nav glass blur fuerte fondo translúcido, 5 items: Hoy (activo, rojo fill glass), Ventas, Caja, Inventario, Más. Iconos line-weight medio. Touch 44×44. Safe area iOS.

PROHIBIDO: AI-slop glass con neon, dark mode, gradientes crypto, neumorphism rosa, shadows skeumorphism, plantilla dribbble. Glass como estructura, no decoración.
