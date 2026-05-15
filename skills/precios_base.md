## PRECIOS BASE
Número al final ES el total, NUNCA multipliques por defecto.
"2 brochas 8000"->8000 | "15 tornillos 14000"->14000 | "1/2 vinilo 21000"->21000
Multiplica SOLO si dice "c/u","cada uno/a","por unidad".

## FORMATO "CANTIDAD PRODUCTO= TOTAL"
"=" después de cantidad+producto = TOTAL de la venta. Ejemplos:
"348 tornillos 6x3/4= 17000" → cantidad=348, total=17000 (NO es precio unitario)
"48 tornillos 6x1= 2000" → cantidad=48, total=2000
"1 espatula= 6000" → cantidad=1, total=6000
NUNCA interpretar como cambio de precio si hay cantidad antes.

## FRACCIONES
1/4=0.25 | 1/2=0.5 | 3/4=0.75 | 1/8=0.125 | 1/16=0.0625. Precio=total.
ALIAS FRACCIONES para [PRECIO_FRACCION]: litro=1/4 | botella=1/8 | media botella=1/16 | mayorista=usa precio_por_cantidad no fraccion.

## CANTIDADES MIXTAS — REGLA CRITICA
Cantidades como "2 y 1/2", "1-1/4", "3 y medio" = enteros + fraccion.
PASO 1: Identificar parte entera y fraccion (2-1/2 = 2 enteros + 1/2)
PASO 2: Buscar precio en MATCH (MATCH siempre tiene prioridad sobre el catálogo estático)
PASO 3: total = (enteros × precio_1) + precio_fraccion
NUNCA multiplicar decimal por precio_unidad.
Ejemplos:
- "2-1/2 vinilo T2"(1=40000,1/2=21000): 2×40000=80000 + 21000 = 101000 ✓
- "1 y 1/4 esmalte"(1=65000,1/4=17000): 1×65000=65000 + 17000 = 82000 ✓

## DOCENAS
1 docena=12 | media=6 | ciento=100. cantidad=docenas*12, total=cantidad*precio_u.

## UNIDAD SUELTA
CRITICO — si el MATCH de CUALQUIER producto tiene "unidad_suelta" y el mensaje NO dice "kilo/kilos/kg/medio kilo" → usar precio unidad_suelta × cantidad. NUNCA usar precio_unidad(kilo).
Ejemplos: "2 wayper blanco"(unidad_suelta=700)→1400 | "3 wayper de color"(unidad_suelta=500)→1500 | "1 kilo wayper"→precio_unidad.

## BISAGRA/SELLADOR/AEROSOL
BISAGRA 3x3 sin material=PAR $4500 (INOX solo si dice "inox"/"inoxidable").
SELLADOR=Corriente. AEROSOL=normal $9000 ("alta temperatura" solo si lo dice).

## MULTI-PRODUCTO (3+)
Registra TODO sin preguntar. Sin color->total:0,indica pendiente.
