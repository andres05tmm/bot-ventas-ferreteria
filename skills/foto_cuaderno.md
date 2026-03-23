## FOTO DE CUADERNO — INSTRUCCIONES ESPECIALES

Estás procesando una foto de un cuaderno de ventas manuscrito de una ferretería colombiana.
Aplica ESTAS reglas en lugar de las reglas normales de silencio.

### PASO 1 — LEER Y TRANSCRIBIR
- Transcribe TODAS las líneas visibles, incluso si la letra es difícil. Infiere por contexto del catálogo.
- Ignora líneas TACHADAS (el vendedor las anuló).
- El encabezado (fecha, nombre de caja) NO es una venta, omítelo.
- Abreviaturas comunes: "tb" / "t.b." / "transf bancol" / "bancol" = transferencia bancaria.
- Si una línea es completamente ilegible, anótala como "⚠️ ilegible".

### PASO 2 — RESUMEN OBLIGATORIO (escribe esto SIEMPRE antes de los [VENTA])
Escribe un resumen legible con este formato exacto:

📋 Ventas del cuaderno:
• [cantidad] [producto] → $[total]
• [cantidad] [producto] → $[total]
...
⚠️ No pude leer: [línea] (solo si las hay)

Usa fracciones legibles: 1/8, 1/4, 1/2. No uses decimales en el resumen.
Separa las que tienen método de pago conocido: agrega "(transf)" o "(efectivo)" al final de la línea.

### PASO 3 — INFERENCIA DE CANTIDAD POR PRECIO
Cuando hay PRECIO pero NO cantidad explícita (ej: "Thinner 13000"), infiere la cantidad:
Divide el precio anotado entre los precios del catálogo para encontrar la fracción exacta.

TABLA THINNER / VARSOL (precios → fracción de galón):
3.000 = 1/12 gal (cant=0.0833) | 4.000 = 1/10 gal (cant=0.1) | 5.000 = 1/8 gal (cant=0.125)
6.000 = 1/6 gal (cant=0.1667) | 8.000 = 1/4 gal (cant=0.25) | 10.000 = 1/3 gal (cant=0.333)
13.000 = 1/2 gal (cant=0.5)   | 20.000 = 3/4 gal (cant=0.75) | 26.000 = 1 galón (cant=1.0)

Para PINTURAS, LACA, ANTICORROSIVO, ESMALTE: busca en el catálogo la fracción cuyo precio coincida.
Si el precio no coincide exactamente con ninguna fracción → usa el total como está, cantidad=1, y anota ⚠️.

Ejemplos:
"Thinner 13000" → sin cantidad → INFIERE: 13000 en tabla = 1/2 galón → [VENTA]{"producto":"Thinner","cantidad":0.5,"total":13000}
"Anticorrosivo negro 3000" → busca en catálogo fracciones de anticorrosivo → si 1/8=3000 → cantidad=0.125
"Colbón 5000" → busca fracción en catálogo → emite con la fracción encontrada

### PASO 4 — EMITIR [VENTA] NORMALES
Después del resumen, emite un [VENTA] por cada línea válida encontrada.
Aplica las mismas reglas de siempre: nombre limpio del catálogo, fracción en cantidad no en nombre.
Para líneas con "tb/transf bancol": agrega "metodo_pago":"transferencia".

### IMPORTANTE
- El "=" en el cuaderno (ej: "1/8 colbon = 5000") ES el total, igual que en mensajes de texto.
- Si hay múltiples ventas en la foto, registra TODAS con sus respectivos [VENTA].
- Las líneas donde no puedes leer el producto: NO emitas [VENTA], solo menciónalas en ⚠️.
