# Product

## Register

product

## Users

**Andrés (dueño / admin)** — Lo usa todo el día entre escritorio (oficina) y celular (en la calle, en el carro). Necesita vista completa: ventas de todos los vendedores, caja, fiados, fiscal, decisiones de negocio. Telegram ID `1831034712`, sembrado como admin en `migrations/004_usuarios_auth.py`.

**Vendedores (mostrador)** — Ritmo rápido, cliente esperando, manos posiblemente sucias. Solo ven sus propias ventas (RBAC `rol=vendedor`). Tablet y celular son escenarios probables. La fricción en TabVentasRapidas y TabCaja se paga en clientes molestos.

**Contador externo (ocasional)** — Entra a TabFacturacion, TabLibroIVA, TabComprasFiscal, FacturasElectronicasRecibidas. Uso esporádico, no diario.

## Product Purpose

Convertir el caos diario de una ferretería colombiana — ventas en efectivo, fiados a clientes, facturación electrónica DIAN, inventario que se mueve por fracciones (puntillas por peso, drywall por hoja o por caja), gastos de caja chica — en operación visible, rastreable y rápida.

Éxito = (1) el vendedor registra una venta con menos clics que hoy y (2) Andrés sabe el estado real de la ferretería (caja del día, deudas, stock crítico, IVA del mes) de un vistazo desde el celular.

## Brand Personality

Rápido, confiable, con carácter.

Una herramienta de mostrador que también tiene voz propia: distinta del software contable gris colombiano, pero sin gritar. Cálida sin ser infantil. Decisión visual deliberada en cada pantalla, no plantilla.

## Anti-references

- **Bootstrap / Material genérico.** Cards idénticos, azul corporativo, plantilla admin AI-slop. Si parece una demo de template, falló.
- **SAP / Siigo / software contable colombiano viejo.** Densidad infernal sin jerarquía, modales sobre modales, gris industrial sin gracia. Trabajar ahí es castigo.
- **Crypto / SaaS dark con neon.** Terminal-hacker, gráficas exageradas con glow, dark mode forzado como personalidad. No somos un exchange.

## Design Principles

1. **La velocidad operativa manda.** El vendedor con un cliente esperando es el peor caso de uso. Ningún adorno justifica un clic extra en TabVentasRapidas, TabCaja o el bypass de productos. Atajos de teclado son ciudadanos de primera.

2. **Carácter sin grito.** Lo distintivo vive en la tipografía y la composición, no en el color. El rojo `#C8200E` (ya usado en `AnimatedBackground.jsx`) es ancla de marca, no decoración invasiva. Saturación calibrada, no genérica.

3. **Densidad calibrada por zona.** POS (TabVentasRapidas, TabCaja) e inventario son densos por necesidad: el operador quiere ver mucho a la vez. Resumen, login y onboarding son aireados. No se aplica el mismo ritmo a todo el dashboard.

4. **Cero gestos genéricos.** Prohibido: bento de 6 KPIs iguales con icon-arriba-label-abajo, "big number + gradient label", card-grids repetidos, side-stripe borders, modales como primera opción. Cada vez que aparezca esa tentación, romper el patrón.

5. **Mostrador-first responsive.** Tablet y celular no son afterthought. El vendedor lo usa con el pulgar, posiblemente con una mano. Andrés revisa desde el carro. Si solo funciona bien en desktop 1440px, falló.

## Accessibility & Inclusion

WCAG AA mínimo en contraste, foco visible, navegación por teclado.

- **Light mode primero.** Dark mode opcional, solo si emerge natural del DS — no es feature obligatorio.
- **Teclado completo en POS.** Andrés y vendedores expertos teclean sin mirar. Tab, Enter, atajos numéricos para métodos de pago.
- **Reduced motion respetado.** `prefers-reduced-motion: reduce` desactiva animaciones decorativas. El AnimatedBackground se congela.
- **Sin dependencia de color** para estados (un fiado vencido no se distingue solo por color rojo — usar también ícono o texto).
- **Tamaños táctiles** mínimos 44×44px en cualquier acción de POS (vendedor con dedos grandes / guantes ligeros).
