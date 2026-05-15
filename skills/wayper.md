## WAYPER — VENTAS POR KILO Y POR UNIDAD

El Wayper se vende de DOS formas según cómo pida el cliente.
NUNCA asumas precio — consulta siempre el catálogo con MATCH.

─────────────────────────────────────────
PRODUCTOS EN CATÁLOGO
─────────────────────────────────────────
Por kilo   → "WAYPER BLANCO"        precio_unidad = precio por 1 kg
Por kilo   → "WAYPER DE COLOR"      precio_unidad = precio por 1 kg
Por unidad → "WAYPER BLANCO UNIDAD" precio_unidad = precio por 1 und
Por unidad → "WAYPER DE COLOR UNIDAD" precio_unidad = precio por 1 und

INVENTARIO: siempre se lleva en UNIDADES. 1 kg = 12 unidades.
El sistema convierte automáticamente al descontar inventario.
NO mezcles blanco con color — son inventarios completamente separados.

─────────────────────────────────────────
CÓMO DISTINGUIR KILO VS UNIDAD
─────────────────────────────────────────
→ KILO: menciona "kilo","kilos","kg","medio kilo","libra"
  o dice un número con unidad de peso: "2 kilos de wayper"

→ UNIDAD: menciona "uno","unidad","unidades","waypers" sin peso
  o dice número entero sin unidad de peso: "3 waypers","un wayper"

Ambigüedad "2 wayper blanco" sin contexto de peso → preguntar:
  "¿Los 2 wayper son por kilo o por unidad?"

─────────────────────────────────────────
FRACCIONES DE KILO
─────────────────────────────────────────
"medio kilo de wayper blanco"  → cantidad=0.5, total=precio_unidad × 0.5
"un cuarto de kilo"            → cantidad=0.25, total=precio_unidad × 0.25
"2 kilos y medio"              → cantidad=2.5, total=precio_unidad × 2.5

─────────────────────────────────────────
EJEMPLOS DE REGISTRO (P = precio_unidad del catálogo)
─────────────────────────────────────────
"1 kilo wayper blanco"
→ [VENTA]{"producto":"WAYPER BLANCO","cantidad":1,"total":P×1}[/VENTA]
→ (sistema descuenta 12 unidades del inventario de WAYPER BLANCO UNIDAD)

"medio kilo wayper blanco"
→ [VENTA]{"producto":"WAYPER BLANCO","cantidad":0.5,"total":P×0.5}[/VENTA]
→ (sistema descuenta 6 unidades del inventario de WAYPER BLANCO UNIDAD)

"3 waypers blancos" (unidades)
→ [VENTA]{"producto":"WAYPER BLANCO UNIDAD","cantidad":3,"total":P×3}[/VENTA]
→ (sistema descuenta 3 unidades directamente)

"2 kilos wayper color"
→ [VENTA]{"producto":"WAYPER DE COLOR","cantidad":2,"total":P×2}[/VENTA]
→ (sistema descuenta 24 unidades del inventario de WAYPER DE COLOR UNIDAD)

"5 waypers color" (unidades)
→ [VENTA]{"producto":"WAYPER DE COLOR UNIDAD","cantidad":5,"total":P×5}[/VENTA]
→ (sistema descuenta 5 unidades directamente)

─────────────────────────────────────────
VARIANTES DE NOMBRE QUE PUEDE DECIR EL CLIENTE
─────────────────────────────────────────
"wayper","guayper","papel industrial","papel wayper"
Blanco = blanco, white, normal (si no dice color → preguntar)
Color  = de color, de colores, de rayas, de cuadros

Si no especifica color → preguntar: "¿Wayper blanco o de color?"
