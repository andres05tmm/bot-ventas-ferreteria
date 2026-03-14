## TINTES — VENTAS POR MILILITROS

Los tintes se venden por mililitro (ml). El precio en catálogo es el precio POR 1 ML.
El precio por tarro completo = precio_unidad × 1000.
NUNCA uses un precio fijo — siempre consulta precio_unidad del catálogo con MATCH.
Unidad DIAN: MLT. Inventario en tarros (1 tarro = 1000 ml).

─────────────────────────────────────────
CASO 1 — CLIENTE PIDE TARRO COMPLETO
─────────────────────────────────────────
Frases que significan 1 tarro (1000 ml):
  "un tinte rojo", "un tarro de tinte", "un litro de tinte",
  "1 tinte rojo", "1 tarro", "1 litro"
→ cantidad = 1000
→ total = precio_unidad × 1000

Múltiples tarros:
  "2 tintes rojo", "2 tarros", "dos litros"
→ cantidad = N × 1000
→ total = precio_unidad × N × 1000

Fracciones de tarro:
  "medio tinte / tarro / litro"  → 500 ml  → total = precio_unidad × 500
  "1/4 de tarro / litro"         → 250 ml  → total = precio_unidad × 250

─────────────────────────────────────────
CASO 2 — CLIENTE DICE PESOS
─────────────────────────────────────────
Número redondo sin unidad = PESOS a cobrar.
  "2000 de tinte rojo", "cinco mil de tinte negro"
→ ml = pesos_pedidos / precio_unidad  (redondear a 1 decimal)
→ total = los pesos que dijo el cliente (NO calcular, tomar literal)
→ [VENTA]{"producto":"Tinte X","cantidad":ml_calculado,"total":pesos_pedidos}[/VENTA]

─────────────────────────────────────────
CASO 3 — CLIENTE DICE ML EXPLÍCITAMENTE
─────────────────────────────────────────
  "500ml de tinte rojo", "200 mililitros de tinte negro"
→ cantidad = ml dichos
→ total = ml × precio_unidad

─────────────────────────────────────────
FÓRMULAS (P = precio_unidad del catálogo)
─────────────────────────────────────────
un tarro completo     → cantidad=1000,    total= P × 1000
N tarros              → cantidad=N×1000,  total= P × N × 1000
medio tarro           → cantidad=500,     total= P × 500
1/4 de tarro          → cantidad=250,     total= P × 250
X pesos de tinte      → cantidad=X/P,     total= X
Y ml de tinte         → cantidad=Y,       total= P × Y

─────────────────────────────────────────
CÓMO DISTINGUIR LOS 3 CASOS
─────────────────────────────────────────
1. "tarro","litro","un tinte", número entero de tintes → CASO 1 (tarros × 1000 ml)
2. Número redondo sin unidad (típico de pesos)         → CASO 2 (pesos ÷ precio_unidad)
3. "ml","mililitros","cc"                              → CASO 3 (ml directo × precio_unidad)

Ambigüedad "500 de tinte" → CASO 2 (pesos). "500ml" → siempre CASO 3.

─────────────────────────────────────────
INVENTARIO DE TINTES
─────────────────────────────────────────
Inventario se lleva en TARROS (1 tarro = 1000 ml). Convertir siempre a ml:
  "hay 5 tarros de tinte rojo"
  → [INVENTARIO]{"producto":"Tinte Rojo Inglés","cantidad":5000,"unidad":"MLT","accion":"actualizar"}[/INVENTARIO]
Si dice ml directamente: usar ese valor sin conversión.
Si dice unidades sin especificar: asumir tarros → × 1000.

─────────────────────────────────────────
COLORES COMUNES (verificar en catálogo con MATCH)
─────────────────────────────────────────
Tinte Rojo Inglés, Tinte Negro, Tinte Miel, Tinte Caoba,
Tinte Caramelo, Tinte Amarillo, Tinte Azul, Tinte Verde.
