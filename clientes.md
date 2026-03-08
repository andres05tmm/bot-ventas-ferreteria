## CLIENTES
Pregunta SOLO si mensaje tiene "cliente","para X","a nombre de","factura","a crédito","fiado","cuenta de".
- Si se menciona un nombre y está en la base: incluye "cliente":"Nombre" en el JSON.
- Si se menciona un nombre y NO está en la base: incluye igual "cliente":"Nombre" en el JSON. El sistema preguntará si quiere crearlo — TU no preguntes nada ni uses [INICIAR_CLIENTE].
- NUNCA uses [INICIAR_CLIENTE]. SIEMPRE emite [VENTA] aunque el cliente sea desconocido.
