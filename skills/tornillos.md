## TORNILLOS Y PUNTILLAS — REGLAS DE PRECIO

### REGLA DE ORO: USA SIEMPRE LOS PRECIOS DEL MATCH
Los precios de tornillos cambian. NUNCA uses precios memorizados.
Usa EXACTAMENTE los precios del bloque MATCH que recibes en cada mensaje.
Formato del MATCH: `NOMBRE:precio_normal/precio_mayorista×umbral`
Ejemplo recibido: `TORNILLO DRYWALL 6X1:42/40x50` → normal=$42, mayorista=$40, umbral=50

### REGLA MAYORISTA
Aplica precio mayorista cuando cantidad_total ≥ umbral (normalmente 50).
Si la cantidad es menor al umbral → precio normal.
Si la cantidad es mayor o igual al umbral → precio mayorista.

### CONVERSIÓN DE UNIDADES (aplicar ANTES de evaluar precio)
1 docena = 12 unidades
1 media docena = 6 unidades  
1 gruesa = 144 unidades
Ejemplo: "7 docenas tornillo 6x1" = 84 unidades → ≥50 → precio mayorista

### PUNTILLAS — precio por libra
Venta por libra. Usa siempre precio_unidad del MATCH.
"2 libras puntilla 2" = 2 × precio_libra del MATCH.

### ACTUALIZAR PRECIOS DE TORNILLOS
Cuando el usuario pida actualizar precios, usa el tag [PRECIO_MAYORISTA]:
- Si da un solo precio: úsalo como precio_unidad y precio_mayorista igual
- Si da dos precios ("unidad / mayorista"): sepáralos correctamente
- umbral siempre = 50

Formato:
[PRECIO_MAYORISTA]{"producto": "TORNILLO DRYWALL 6X1", "precio_unidad": 42, "precio_mayorista": 40, "umbral": 50}[/PRECIO_MAYORISTA]
