## TINTES — VENTAS POR MILILITROS

Los tintes se venden por mililitro (ml). El precio en catálogo es el precio POR ML.
Ejemplo: Tinte Rojo Inglés precio_unidad=26 → $26 por 1 ml → $26.000 por 1000 ml.

### REGLA PRINCIPAL: cuando el cliente dice un número de pesos

"2000 de tinte rojo" → el 2000 son PESOS, NO mililitros.
Cantidad en ml = pesos_pedidos / precio_por_ml
Ejemplo: 2000 / 26 = 76.9 ml → [VENTA]{"producto":"Tinte Rojo Inglés","cantidad":76.9,"total":2000}[/VENTA]

Redondear cantidad a máximo 1 decimal. El total siempre es lo que dijo el cliente (los pesos).

### REGLA SECUNDARIA: cuando el cliente dice ml explícitamente

"500ml de tinte rojo" → cantidad=500, total = 500 × precio_por_ml
Ejemplo: 500 × 26 = 13000 → [VENTA]{"producto":"Tinte Rojo Inglés","cantidad":500,"total":13000}[/VENTA]

### CÓMO DISTINGUIR si dice pesos o ml

- Dice un número redondo pequeño (500, 1000, 2000, 5000) SIN decir "ml" → son PESOS
- Dice un número con "ml", "mililitros", "cc" → son MILILITROS
- Dice "medio tinte", "1/4 de tinte" → fracción del litro base (1000ml):
  medio = 500ml → total = 500 × precio_por_ml
  1/4   = 250ml → total = 250 × precio_por_ml

### REFERENCIA RÁPIDA (si precio_por_ml = 26)

| Cliente dice        | Cantidad (ml) | Total ($) |
|---------------------|---------------|-----------|
| 1000 de tinte       | 38.5 ml       | $1.000    |
| 2000 de tinte       | 76.9 ml       | $2.000    |
| 5000 de tinte       | 192.3 ml      | $5.000    |
| 10000 de tinte      | 384.6 ml      | $10.000   |
| 26000 de tinte      | 1000 ml       | $26.000   |
| 500ml de tinte      | 500 ml        | $13.000   |
| 1 litro de tinte    | 1000 ml       | $26.000   |
| medio tinte         | 500 ml        | $13.000   |

### TINTES COMUNES (verificar precio real en catálogo con MATCH)

Los tintes pueden llamarse: "tinte [color] inglés", "tinte [color]", "colorante [color]".
Colores: Rojo, Azul, Amarillo, Negro, Verde, Naranja, Violeta, Café, Blanco, Gris.
SIEMPRE buscar en catálogo con MATCH antes de registrar — nunca asumir el precio.

### UNIDAD DIAN

Registrar con unidad_medida="MLT" (código DIAN oficial para mililitro).
