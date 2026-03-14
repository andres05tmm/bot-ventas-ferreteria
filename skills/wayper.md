## WAYPER — VENTAS POR KILO Y POR UNIDAD

El Wayper se vende de DOS formas según cómo pida el cliente.
NUNCA asumas precio — consulta siempre el catálogo con MATCH.

─────────────────────────────────────────
PRODUCTOS EN CATÁLOGO
─────────────────────────────────────────
Por kilo   → "Wayper Blanco"        precio_unidad = precio por 1 kg
Por kilo   → "Wayper Color"         precio_unidad = precio por 1 kg
Por unidad → "Wayper Blanco Unidad" precio_unidad = precio por 1 und
Por unidad → "Wayper Color Unidad"  precio_unidad = precio por 1 und

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
→ [VENTA]{"producto":"Wayper Blanco","cantidad":1,"total":P×1}[/VENTA]

"medio kilo wayper blanco"
→ [VENTA]{"producto":"Wayper Blanco","cantidad":0.5,"total":P×0.5}[/VENTA]

"3 waypers blancos" (unidades)
→ [VENTA]{"producto":"Wayper Blanco Unidad","cantidad":3,"total":P×3}[/VENTA]

"2 kilos wayper color"
→ [VENTA]{"producto":"Wayper Color","cantidad":2,"total":P×2}[/VENTA]

"5 waypers color" (unidades)
→ [VENTA]{"producto":"Wayper Color Unidad","cantidad":5,"total":P×5}[/VENTA]

─────────────────────────────────────────
VARIANTES DE NOMBRE QUE PUEDE DECIR EL CLIENTE
─────────────────────────────────────────
"wayper","guayper","papel industrial","papel wayper"
Blanco = blanco, white, normal (si no dice color → preguntar)
Color  = de color, de colores, de rayas, de cuadros

Si no especifica color → preguntar: "¿Wayper blanco o de color?"
