## TINTES — VENTAS POR MILILITROS (MENUDEO)

Los tintes se venden menudiados: el cliente puede pedir cualquier cantidad en pesos o en ml.

PRECIO EN CATÁLOGO = precio del TARRO COMPLETO (1 litro = 1000 ml).
precio_por_ml = precio_tarro ÷ 1000

Ejemplo con Tinte Caoba (precio_tarro = $26.000):
  precio_por_ml = 26.000 ÷ 1000 = $26 por ml

NUNCA uses el precio del catálogo directamente para ml — siempre divide entre 1000.
Unidad DIAN: MLT. Inventario en tarros (1 tarro = 1000 ml).

─────────────────────────────────────────
CASO 1 — CLIENTE PIDE TARRO(S) COMPLETO(S)
─────────────────────────────────────────
Frases: "un tinte rojo", "un tarro", "un litro de tinte", "1 tinte", "2 tintes"

Fórmula:
  ml      = N × 1000
  total   = N × precio_tarro   (precio_tarro = precio_unidad del catálogo)

Ejemplos:
  "1 tinte caoba"    → cantidad=1000, total=26000
  "2 tarros de miel" → cantidad=2000, total=52000
  "medio tarro"      → cantidad=500,  total=13000
  "1/4 de tarro"     → cantidad=250,  total=6500

─────────────────────────────────────────
CASO 2 — CLIENTE PIDE POR PESOS (menudeo)
─────────────────────────────────────────
Número redondo sin unidad = PESOS que el cliente va a pagar.
Frases: "2000 de tinte caoba", "cinco mil de tinte negro", "mil de tinte miel"

Fórmula:
  precio_por_ml = precio_unidad ÷ 1000
  ml            = pesos_pedidos ÷ precio_por_ml   (redondear a 1 decimal)
  total         = pesos_pedidos   ← NO calcular, tomar literal lo que dijo el cliente

Ejemplo — "2000 de tinte caoba" (precio_unidad=26000):
  precio_por_ml = 26000 ÷ 1000 = 26
  ml            = 2000 ÷ 26    = 76.9 ml
  → [VENTA]{"producto":"Tinte Caoba","cantidad":76.9,"total":2000}[/VENTA]

Ejemplo — "5000 de tinte negro":
  ml = 5000 ÷ 26 = 192.3 ml
  → [VENTA]{"producto":"Tinte Negro","cantidad":192.3,"total":5000}[/VENTA]

─────────────────────────────────────────
CASO 3 — CLIENTE DICE ML EXPLÍCITAMENTE
─────────────────────────────────────────
Frases: "500ml de tinte rojo", "200 mililitros de tinte negro"

Fórmula:
  precio_por_ml = precio_unidad ÷ 1000
  total         = ml × precio_por_ml

Ejemplo — "500ml de tinte caoba":
  total = 500 × 26 = 13000
  → [VENTA]{"producto":"Tinte Caoba","cantidad":500,"total":13000}[/VENTA]

─────────────────────────────────────────
TABLA RESUMEN (P = precio_unidad del catálogo = precio del tarro)
─────────────────────────────────────────
Pedido                   → cantidad (ml)   total
1 tarro completo         → 1000            P
N tarros                 → N × 1000        N × P
medio tarro              → 500             P ÷ 2
1/4 de tarro             → 250             P ÷ 4
X pesos de tinte         → X ÷ (P÷1000)   X          ← total = lo que dijo el cliente
Y ml de tinte            → Y              Y × (P÷1000)

─────────────────────────────────────────
CÓMO DISTINGUIR LOS 3 CASOS
─────────────────────────────────────────
1. "tarro","litro","un tinte", número entero de tintes/tarros → CASO 1
2. Número redondo sin unidad (500, 1000, 2000, 5000...)       → CASO 2 (pesos)
3. "ml","mililitros","cc" explícito                           → CASO 3

Ambigüedad "500 de tinte" → siempre CASO 2 (pesos).
"500ml" o "500 mililitros" → siempre CASO 3.

─────────────────────────────────────────
INVENTARIO DE TINTES
─────────────────────────────────────────
El inventario se lleva en TARROS. Convertir siempre a ml al registrar:
  "hay 5 tarros de tinte caoba"
  → [INVENTARIO]{"producto":"Tinte Caoba","cantidad":5000,"unidad":"MLT","accion":"actualizar"}[/INVENTARIO]

Si dice ml directamente: usar ese valor sin conversión.
Si dice unidades sin especificar: asumir tarros → × 1000.

─────────────────────────────────────────
COLORES DISPONIBLES (verificar en catálogo con MATCH)
─────────────────────────────────────────
Tinte Caoba, Tinte Caramelo, Tinte Miel, Tinte Negro, Tinte Rojo Inglés
