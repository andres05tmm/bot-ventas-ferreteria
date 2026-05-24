# Comparativa de mockups — Fase 2

**Fecha**: 2026-05-24
**Estado**: 8 mockups generados (4 direcciones × 2 viewports) + 5 extras. Pendiente decisión de Andrés.

## Cómo revisar

**Opción rápida (todo en uno)** — abre el proyecto Stitch y navega visualmente:
👉 https://stitch.withgoogle.com/projects/12113492557069924495

**Opción detallada** — abre cada dirección por separado (links abajo).

---

## Las 4 direcciones

### A · Bento minimalista (Linear/Vercel)

Calmo, whitespace generoso, jerarquía por tipografía. Cards blancas sobre #FAFAFA. Rojo `#C8200E` solo en estados activos.

- **Desktop** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/8849a071721d45619c99c5dcd6a003f5) — "Cockpit HOY - FerreBot Punto Rojo (Bento Style)" (2560×2048)
- **Móvil** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/e7df3c05864d403c86214374a00da3e5) — "Dashboard HOY - FerreBot Punto Rojo" (780×2232)

**Encaja con PRODUCT.md si**: quieres "carácter sin grito" sobrio, escalable, pero no muy distintivo respecto a SaaS del mundo (Linear, Vercel, Stripe son referentes obvios).
**Riesgo**: puede sentirse "ya lo vi antes" — el carácter de marca queda diluido.

### B · Industrial denso (Bloomberg/POS)

Densidad alta, tipografía mono para cifras, rojo `#C8200E` en alertas, sin radios redondos. Tipo terminal financiera.

- **Desktop** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/400ff574a3be461ebbe21b9fcef9a737) — "Cockpit Industrial - FerreBot Punto Rojo" (2560×2048)
- **Móvil** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/dd25616b9bdb43f990f092462db7b9ef) — "Cockpit HOY - Industrial Denso Mobile" (780×1768)

**Encaja con PRODUCT.md si**: "velocidad operativa manda" y "densidad calibrada por zona" se interpretan como protagonistas. POS pro de mostrador.
**Riesgo**: puede inclinarse a "Siigo/SAP gris industrial" si no se calibra bien. Móvil denso puede ser duro para vendedor con dedos grandes.

### C · Editorial serio (banking premium)

Tipografía serif + sans humanista, paleta crema, cobre oxidado, hairlines. Tipo Monzo/Mercury/anuario corporativo.

- **Desktop** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/a84350d7645946de97e8ffce7f4398e1) — "Dashboard HOY - Editorial Banking Style" (2560×3546)
- **Móvil** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/8fc2bb45da4e4416895ee62fa2237c38) — "Cockpit HOY - Editorial Edition" (780×2374)

**Encaja con PRODUCT.md si**: "cero gestos genéricos" + carácter en tipografía son las apuestas más fuertes. Más distintivo del mercado de software contable.
**Riesgo**: serif puede sentirse "lento" para POS rápido. Densidad menor que B. El desktop salió largo (3546px alto) — posible scroll vertical alto.

### D · Glassmorphism disciplinado (visionOS/Arc)

Capas translúcidas calibradas sobre fondo warm con blobs muy difuminados. Inspiración Apple system / Arc browser. **NO** AI-slop neón.

- **Desktop** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/89733415639245d7a10de1711c414719) — "Cockpit HOY - Glassmorphism Edition" (2560×2902)
- **Móvil** · [Stitch](https://stitch.withgoogle.com/projects/12113492557069924495/screens/dd8fe99b5bd3474d9788b5574843f453) — "Cockpit HOY - Glassmorphism Edition" (780×1824)

**Encaja con PRODUCT.md si**: quieres romper más fuerte con la estética de software colombiano. Llama la atención por profundidad/material.
**Riesgo**: glass puede envejecer mal, performance en celulares de mostrador (backdrop-filter es caro), legibilidad en luz fuerte (mostrador con sol). El más arriesgado del lote.

---

## Extras (no son las 4 direcciones — se generaron de bonus)

- [Dashboard HOY - Dark Mode](https://stitch.withgoogle.com/projects/12113492557069924495/screens/ea73ca7774084295a97c405beaaa6b36) (desktop)
- [Cockpit HOY - Dark Mode Mobile](https://stitch.withgoogle.com/projects/12113492557069924495/screens/8ebe3cf96fa24116b2b7370546cb3c20)
- [Dashboard HOY - FerreBot Punto Rojo (genérico)](https://stitch.withgoogle.com/projects/12113492557069924495/screens/33be91d9e82140ab9bd9c07f278e81b6) (desktop)
- [Cockpit HOY - FerreBot Punto Rojo (variante)](https://stitch.withgoogle.com/projects/12113492557069924495/screens/760301b2e46e4f0ca0b67bb8e9f95c25) (desktop)
- [Cockpit HOY - FerreBot Punto Rojo (variante)](https://stitch.withgoogle.com/projects/12113492557069924495/screens/d6ff7fcddd434432a95361bf2c88970d) (desktop)

> Las versiones dark mode contradicen el principio "Light mode primero" de PRODUCT.md. Útiles solo si decides activar dark desde Fase 3 como hipotético.

---

## Filtros para tu decisión (rápidos)

Cuando los abras, pregúntate por cada uno:

1. **¿Lo veo y digo "esto es FerreBot, no es un template"?** → si la respuesta es "podría ser cualquier SaaS", descártalo.
2. **¿El rojo `#C8200E` aparece calibrado, no decorativo?** → si grita o si se pierde, es señal.
3. **¿La cifra de ventas hoy `$2.450.000` es el primer foco al entrar?** → ese es el contrato del cockpit.
4. **¿Imagino a un vendedor con cliente esperando usándolo en 5 segundos?** → si dudas, problema de velocidad.
5. **¿La densidad cambia entre zonas (KPIs aireados vs tabla densa)?** → si todo es uniforme, falla "densidad calibrada por zona".

---

## Decisión esperada

Andrés elige **1 dirección** (o pide ajustes a una específica con `generate_variants`). Esa dirección consolida el `DESIGN.md` definitivo y abre Fase 3 (Design System en código).

Si ninguna convence, opciones:
- Iterar la más cercana con `generate_variants` (1-2 rounds máximo).
- Combinar: ej. "estructura de A + tipografía de C".
- Generar una 5ª dirección híbrida.

---

## Para retomar

Cuando confirmes elección, escribe el nombre de la dirección elegida (A/B/C/D) y procedemos a:
1. Consolidar `DESIGN.md` final con tokens (color/tipografía/espaciado/radius) extraídos de la dirección ganadora.
2. Cerrar Fase 2 en `NEXT-STEPS.md`.
3. Abrir Fase 3 (instalar shadcn + tokens en código).
