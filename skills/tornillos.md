## TORNILLOS Y PUNTILLAS — PRECIOS POR CANTIDAD

### Precio mayorista (umbral: 50 unidades)
Todos los tornillos drywall tienen DOS precios: normal (<50) y mayorista (≥50).
Ejemplos: TORNILLO DRYWALL 8x1: normal=$38, mayorista=$35
Aplicar precio mayorista cuando cantidad_total ≥ 50, sin importar cómo se exprese.

### UNIDADES DE CONVERSIÓN (aplicar ANTES de evaluar precio)
1 docena = 12 unidades | 1 media docena = 6 unidades | 1 gruesa = 144 unidades
"7 docenas" = 84 unidades → 84 ≥ 50 → precio mayorista
"3 docenas" = 36 unidades → 36 < 50 → precio normal
"2 gruesas" = 288 unidades → precio mayorista

### PRECIOS POR CANTIDAD — TORNILLOS DRYWALL (precio_bajo_umbral/precio_sobre_umbral × umbral=50)
6x1/2=25 | 6x3/4=58/30 | 6x1=38/35 | 6x1-1/4=42/40 | 6x1-1/2=58/55 | 6x2=67/60 | 6x2-1/2=75/70 | 6x3=83/80 | 6 x 3=83/80
8x1=38/35 | 8x3/4=33/30 | 8x1-1/2=58/55 | 8x 2=67/60 | 8x3=83/80
10x1=83/70 | 10x1-1/2=125/100 | 10x2=150/120 | 10x2-1/2=167/160 | 10x3=167/160 | 10x4=208/200

### PUNTILLAS — precio por libra (precio_unidad fijo, sin mayorista)
Venta por libra. "2 libras puntilla 2"" = 2 × precio_libra.

### ACTUALIZAR PRECIOS DE TORNILLOS
Cuando el usuario pida actualizar precios de tornillos, usa el tag [PRECIO_MAYORISTA]:
- Si da un solo precio: úsalo como precio_unidad y precio_mayorista igual
- Si da dos precios ("unidad / mayorista" o "normal y mayorista"): sepáralos correctamente
- umbral siempre = 50

Ejemplos de instrucciones del usuario:
  "tornillo drywall 6x1 = 40 / 35"          → precio_unidad=40, precio_mayorista=35
  "tornillo drywall 8x1 unidad 42 mayor 38"  → precio_unidad=42, precio_mayorista=38
  "tornillo 10x3 = 170"                      → precio_unidad=170, precio_mayorista=170

Formato del tag:
[PRECIO_MAYORISTA]{"producto": "Tornillo Drywall 6X1", "precio_unidad": 40, "precio_mayorista": 35, "umbral": 50}[/PRECIO_MAYORISTA]
