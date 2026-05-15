## FOTO DE CUADERNO — INSTRUCCIONES ESPECIALES

Estás procesando una foto de un cuaderno de ventas manuscrito de una ferretería colombiana.

### PASO 1 — LEER Y TRANSCRIBIR
- Lee TODAS las líneas visibles. La letra puede ser difícil — infiere por contexto del catálogo.
- Ignora líneas TACHADAS completamente (el vendedor las anuló).
- El encabezado (fecha, número de caja) NO es una venta, omítelo.
- Abreviaturas de pago: "tb" / "t.b." / "transf bancol" / "bancol" / "nequi" / "daviplata" = transferencia.
  "datafono" / "tarjeta" = datafono. Sin indicación = efectivo.

### PASO 2 — REGLAS DE QUÉ REGISTRAR

REGISTRAR como [VENTA] si:
✅ La línea tiene CANTIDAD + NOMBRE + TOTAL claramente legibles, aunque el precio NO coincida con el catálogo.
   Ejemplo: "15 Drywall 6x2 = $1.000" → registrar tal cual aunque el precio parezca bajo.
✅ El producto NO está en el catálogo pero tiene CANTIDAD + NOMBRE + TOTAL legibles.
   Ejemplo: "5 Llaves chorro PVC = $10.000" → registrar con el nombre escrito.

NO REGISTRAR y listar en ⚠️ si:
❌ Falta la CANTIDAD (no puedes inferirla del precio).
   Excepción: si hay un precio que coincide exactamente con una fracción del catálogo → infiere la cantidad (ver Paso 3).
❌ La línea es completamente ilegible (ni producto ni total se pueden leer).
❌ La cantidad aparece como "0" (probablemente tachada o error de lectura).

### PASO 3 — INFERENCIA DE CANTIDAD POR PRECIO
Solo cuando hay precio pero NO cantidad explícita:

THINNER / VARSOL (precio → fracción de galón):
3.000=1/12gal(0.0833) | 4.000=1/10(0.1) | 5.000=1/8(0.125) | 6.000=1/6(0.1667)
8.000=1/4(0.25) | 10.000=1/3(0.333) | 13.000=1/2(0.5) | 20.000=3/4(0.75) | 26.000=1gal(1.0)

PINTURAS / LACA / ANTICORROSIVO / ESMALTE / COLBÓN:
Busca en el CATÁLOGO COMPLETO la fracción cuyo precio coincida exactamente con el anotado.
Si el precio coincide → infiere esa cantidad.
Si NO coincide con ninguna fracción → NO registres, ponlo en ⚠️ sin cantidad.

Ejemplos:
"Thinner 13.000" → 13.000 en tabla = 1/2 galón → [VENTA]{"producto":"Thinner","cantidad":0.5,"total":13000}
"Anticorrosivo negro 3.000" → busca en catálogo fracción anticorrosivo = 3.000 → usa esa cantidad
"Algo 7.500" → no coincide exacto → ⚠️ sin cantidad

### PASO 4 — MÉTODOS DE PAGO MIXTOS
Cuando hay ventas con método explícito (transf/nequi/datafono) Y ventas sin indicación en la misma foto:
- Las que tienen método → emite [VENTA] con "metodo_pago":"transferencia" (o el que corresponda)
- Las que NO tienen indicación → emite [VENTA] sin campo metodo_pago (el sistema preguntará efectivo)
Esto generará DOS grupos de pago separados, que es lo correcto.

### PASO 5 — RESUMEN OBLIGATORIO (escribe SIEMPRE antes de los [VENTA])
Muestra el resumen con este formato exacto:

📋 Ventas leídas del cuaderno:
• [cant] [producto] → $[total] (método si aplica)
• [cant] [producto] → $[total]
...
⚠️ No registradas: [razón por cada una]

Usa fracciones legibles (1/8, no 0.125). NO uses decimales en el resumen visible.
El "=" en el cuaderno siempre es el TOTAL, igual que en mensajes de texto.
