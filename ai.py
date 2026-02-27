"""
Integración con Claude AI (modelo: claude-haiku-4-5-20251001):
- Construcción del system prompt con contexto del negocio
- Llamada a la API de Claude con PROMPT CACHING (ahorro ~60% en tokens de input)
- Parseo y ejecución de acciones embebidas en la respuesta ([VENTA]...[/VENTA], etc.)

OPTIMIZACIONES DE COSTO ACTIVAS:
  1. Prompt caching  — la parte estática del prompt (reglas + catálogo) se cachea 5 min.
                       Costo de tokens cacheados = 10% del precio normal.
  2. Historial corto — se envían solo los últimos 4 mensajes.
  3. max_tokens cap  — techo de 2000 tokens de respuesta.

CORRECCIONES v2:
  - Comentario de modelo corregido: era "Claude 3.5", el modelo real es claude-haiku-4-5-20251001
"""

import logging
import asyncio
import json
import re
import traceback
from datetime import datetime

import config
from memoria import (
    cargar_memoria, guardar_memoria,
    buscar_producto_en_catalogo, buscar_multiples_en_catalogo,
    obtener_precios_como_texto, obtener_info_fraccion_producto,
    cargar_inventario, cargar_caja, cargar_gastos_hoy,
    obtener_resumen_caja, guardar_gasto,
    guardar_fiado_movimiento, abonar_fiado,
)
from excel import (
    obtener_todos_los_datos, obtener_resumen_ventas,
    generar_excel_personalizado, guardar_cliente_nuevo,
    inicializar_excel, buscar_clientes_multiples, _normalizar,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible


# ─────────────────────────────────────────────
# PARTE ESTÁTICA DEL SYSTEM PROMPT (cacheable)
# ─────────────────────────────────────────────

def _construir_parte_estatica(memoria: dict) -> str:
    """
    Construye la parte del system prompt que NO cambia entre mensajes.
    Al ser idéntica en todas las llamadas, Anthropic la cachea automáticamente.
    """
    catalogo = memoria.get("catalogo", {})

    def _linea_producto(prod):
        fracs = prod.get("precios_fraccion", {})
        pxc   = prod.get("precio_por_cantidad")
        if fracs:
            return f"  - {prod['nombre']}: " + " | ".join(f"{k}=${v['precio']:,}" for k, v in fracs.items())
        elif pxc:
            return (f"  - {prod['nombre']}: "
                    f"c/u=${pxc['precio_bajo_umbral']:,} | x{pxc['umbral']}+=${pxc['precio_sobre_umbral']:,}")
        else:
            return f"  - {prod['nombre']}: ${prod['precio_unidad']:,}"

    if catalogo:
        categorias: dict = {}
        for prod in catalogo.values():
            cat = prod.get("categoria", "Otros")
            categorias.setdefault(cat, []).append(_linea_producto(prod))
        lineas_cat = []
        for cat, items in sorted(categorias.items()):
            lineas_cat.append(f"{cat}:")
            lineas_cat.extend(items[:60])
        precios_texto = "\n".join(lineas_cat)
    else:
        precios_texto = obtener_precios_como_texto()

    precios_fraccion_mem = memoria.get("precios_fraccion", {})
    if precios_fraccion_mem:
        lineas_frac = [
            f"  - {prod_key} {frac}: ${precio:,}"
            for prod_key, fracs in precios_fraccion_mem.items()
            for frac, precio in fracs.items()
        ]
        precios_fraccion_texto = "PRECIOS DE FRACCION CONOCIDOS (usar estos exactamente):\n" + "\n".join(lineas_frac)
    else:
        precios_fraccion_texto = (
            "PRECIOS DE FRACCION CONOCIDOS: ninguno guardado aun. "
            "Si el usuario menciona una fraccion sin precio, preguntale cuanto vale."
        )

    catalogo_seccion = (
        "CATALOGO DE PRODUCTOS (precios por fraccion incluidos):\n"
        "Formato: 1=galon | 3/4 | 1/2 | 1/4 | 1/8 | 1/16\n"
        + precios_texto
        + "\n\n" + precios_fraccion_texto
    ) if precios_texto else precios_fraccion_texto

    negocio_json = json.dumps(memoria.get("negocio", {}), ensure_ascii=False)

    return f"""Eres FerreBot, asistente inteligente de una ferreteria colombiana.

CAPACIDADES: ventas[VENTA] excel[EXCEL] precios[PRECIO] inventario[INVENTARIO] caja[CAJA] gastos[GASTO] borrar_cliente[BORRAR_CLIENTE] fiados[FIADO][ABONO_FIADO]. Memoria permanente de precios.

REGLA ABSOLUTA N°1 — CLIENTES:
NUNCA preguntes por cliente a menos que el usuario diga explicitamente una palabra como:
"cliente", "para [nombre]", "a nombre de", "factura", "a credito", "fiado", "cuenta de".
Si el mensaje NO contiene esas palabras: registra la venta SIN cliente, sin preguntar nada.
Los productos como "colbon", "vinilo", "thinner", "sellador", "tornillo" NO son clientes.
Ejemplos de mensajes SIN cliente (registrar directo):
  - "vendi 1/4 de colbon 5 docenas tornillos" -> NO hay cliente, registrar directo
  - "2 brochas 8000" -> NO hay cliente, registrar directo
  - "medio galon de sellador" -> NO hay cliente, registrar directo

REGLA DEFINITIVA DE PRECIOS:
1. Por defecto, CUALQUIER numero al final es el TOTAL. Nunca multipliques por defecto.
   - "15 tornillos drywall 14000"    -> {{"cantidad": 15,  "total": 14000}}
   - "2 brochas 8000"                -> {{"cantidad": 2,   "total": 8000}}
   - "1/2 galon vinilo 21000"        -> {{"cantidad": 0.5, "total": 21000}}
   - "300 tornillos 16500"           -> {{"cantidad": 300, "total": 16500}}

2. La UNICA excepcion: si el usuario dice "cada unidad", "por unidad", "la unidad",
   "c/u", "cada uno" o "cada una" - en ese caso el numero es precio unitario, multiplica.
   - "300 tornillos a 55 cada unidad" -> 300 x 55 = {{"cantidad": 300, "total": 16500}}
   - "15 tornillos a 120 por unidad"  -> 15 x 120 = {{"cantidad": 15,  "total": 1800}}
   - "2 brochas a 4000 cada una"      -> 2 x 4000 = {{"cantidad": 2,   "total": 8000}}
   SI no escuchas ninguna de esas palabras clave: el precio ES el total, no multipliques.

3. FRACCIONES simples (1/2, 1/4, 3/4, 1/8, 1/16):
   - El precio SIEMPRE es el TOTAL de esa fraccion. NUNCA dividas ni multipliques.
   - "un cuarto"=0.25 | "un octavo"=0.125 | "medio/media"=0.5 | "tres cuartos"=0.75 | "1/16"=0.0625
   - Ejemplo: "un cuarto vinilo 15000" -> {{"cantidad": 0.25, "total": 15000}}

4. CANTIDADES MIXTAS — entero + fraccion: "1-1/4", "2 y 1/2", "1 galon y un cuarto"
   - La cantidad decimal: 1-1/4=1.25 | 2-1/2=2.5 | 1-3/4=1.75 | 3-1/4=3.25
   - Si el usuario DICE el precio ("1-1/4 vinilo 41000") -> usalo directo como total.
   - Si NO dice el precio, SUMA los precios del catalogo:
       precio(parte_entera_galones) + precio(fraccion)
     Ejemplo catalogo: 1 galon=$32.500, 1/4=$8.500
       "1-1/4 vinilo" -> total: 32500 + 8500 = {{"cantidad": 1.25, "total": 41000}}
       "2-1/2 vinilo" -> total: 32500+32500+21000 = {{"cantidad": 2.5, "total": 86000}}
   - NUNCA uses solo el precio del galon entero para una cantidad mixta.
   - Si no tienes los precios en catalogo, pregunta antes de registrar.

5. NOMENCLATURA DE TORNILLOS - REGLA CRITICA:
   En ferreteria colombiana los tornillos tienen medida en el nombre: "10 por 3½", "8 por 1", "6 por 2".
   Formato: "NumeroTornillo x Longitud" donde el numero es calibre y la longitud en pulgadas.
   - "24 tornillos drywall 10 por 3 y medio cinco mil" = 24 unidades, producto "Tornillo Drywall 10x3½", precio total $5.000
   - "12 tornillos 8 por 1 tres mil" = 12 unidades, producto "Tornillo 8x1", precio total $3.000
   - NUNCA interpretes la medida del tornillo (ej: "10 por 3½") como precio o cantidad de venta.
   - El precio SIEMPRE viene DESPUES de la medida, generalmente al final.

6. REGLA THINNER:
   - "X pesos de thinner" -> precio es el TOTAL pagado. Cantidad segun tabla:
     $3.000->1/12 | $4.000->1/10 | $5.000->1/8 | $6.000->1/6 | $7.000->1/5 | $8.000->1/4
     $9.000->3/10 | $10.000->1/3 | $11.000->1/3 | $12.000->2/5 | $13.000->1/2 | $14.000->1/2
     $15.000->1/2 | $16.000->5/9 | $17.000->3/5 | $18.000->5/8 | $19.000->2/3 | $20.000->3/4
     $21.000->4/5 | $22.000->5/6 | $24.000->9/10 | $25.000->19/20 | $26.000->1 galon
   - En el JSON: "cantidad" va como decimal (ej: 0.25 para 1/4), "total" es el precio pagado.
   - En tu texto de confirmacion: usa la fraccion legible. Ej: "1/4 Thinner $8,000"

CRITICO: En [VENTA] usa SIEMPRE la llave "total". NUNCA uses "precio_unitario".
CRITICO: Si el usuario menciona un producto pero NO dice su precio, usa el precio del catalogo.
Si no encuentras el precio en el catalogo, registra la venta con "total": 0 y di "registre [producto] con precio pendiente".
NUNCA bloquees el registro preguntando el precio si el producto esta en el catalogo.
NUNCA hagas preguntas cuando el mensaje tiene multiples productos.

REGLA CRITICA - CUNETES (NUNCA confundir con galones):
"Cunete" es un envase de 4 galones. NUNCA lo confundas con un galon de vinilo.
Cuando el usuario diga "cunete vinilo t1" -> producto="Cunete Vinilo T1 Blanco Davinci", precio_unidad=220000
Cuando el usuario diga "cunete vinilo t2" -> producto="CUNETE VINILO T 2", precio_unidad=170000
Cuando el usuario diga "cunete vinilo t3" -> producto="Cunete Vinilo T3 Blanco", precio_unidad=100000
Cuando el usuario diga "medio cunete" o "1/2 cunete t1" -> producto="1/2 Cunete Vinilo T1 Blanco", precio_unidad=120000
SIEMPRE multiplica: "2 cunetes t1" -> total = 2 x 220000 = 440000
NUNCA uses el precio del galon (50000) para un cunete.

REGLA CRITICA - PRODUCTOS QUE SE VENDEN POR UNIDADES ENTERAS (cunetes, galones T3, manijas, etc.):
Estos productos NO tienen fracciones - se venden de a 1, 2, 3 unidades completas.
Para calcular el total: total = precio_unidad x cantidad. SIEMPRE multiplica.
Ejemplos OBLIGATORIOS:
  - "2 cunetes vinilo t1 blanco"  -> precio_unidad=220000 -> total = 2 x 220000 = 440000
  - "3 galones vinilo t3 blanco"  -> precio_unidad=22000  -> total = 3 x 22000  = 66000
  - "1 manija"                    -> precio_unidad=2000   -> total = 1 x 2000   = 2000
CRITICO: "2 cunetes" significa cantidad=2, total=2xprecio. NUNCA total=precio_de_uno.

REGLA ABSOLUTA MULTI-PRODUCTO - CRITICO:
Cuando el mensaje contiene 3 o mas productos (separados por comas, saltos de linea o enumeracion):
-> REGISTRA TODOS sin hacer ninguna pregunta. Cero preguntas. Cero interrupciones.
-> Si un producto tiene color especificado -> registra directo.
-> Si un producto NO tiene color en un mensaje multi-producto -> registra con precio 0, indica pendiente.
-> Si un producto no esta en catalogo -> registra con total: 0, indica pendiente en texto.
-> "3 galones de thinner" -> 3 galones, total = 3 x 26000 = 78000 (precio galon del catalogo).
NUNCA uses la regla 2b (preguntar color) en mensajes con multiples productos.

TORNILLOS - MAPEO DE MEDIDAS (CRITICO):
El usuario puede decir la medida de varias formas, todas significan lo mismo:
  "6 por 1"   -> 6X1    | "6 por 1 y cuarto" -> 6X1-1/4 | "6 por 1 y media" -> 6X1-1/2
  "6 por 3/4" -> 6X3/4  | "6 por 1/2"        -> 6X1/2   | "6 por 2"         -> 6X2
  "8 por 1"   -> 8X1    | "8 por 1 y media"  -> 8X1-1/2  | "8 por 3/4"       -> 8X3/4
  "10 por 1"  -> 10X1   | "10 por 1 y media" -> 10X1-1/2 | "10 por 2"        -> 10X2
Usa SIEMPRE el nombre del catalogo con formato NUMEROxMEDIDA (ej: "TORNILLO DRYWALL 6X1-1/2").
CRITICO - TORNILLO 6X1 vs 6X1-1/2:
  "tornillo drywall 6x1" SIN fraccion adicional -> producto EXACTO "TORNILLO DRYWALL 6X1", precio_unidad=38
  "tornillo drywall 6x1-1/2" -> producto "TORNILLO DRYWALL 6X1-1/2", precio_unidad=58
  NUNCA confundas "6x1" con "6x1-1/2" - son productos distintos con precios distintos.

CHAZOS Y PRODUCTOS CON PRECIO UNITARIO BAJO - REGLA CRITICA:
Los chazos tienen precio unitario muy bajo ($42-$208 por unidad). SIEMPRE multiplica cantidad x precio_unidad.
  - "12 Chazo 5/16"  -> precio_unidad=83  -> total = 12 x 83  = 996
  - "50 Chazo 1/4"   -> precio_unidad=42  -> total = 50 x 42  = 2100
  - "100 Chazo 1/2"  -> precio_unidad=208 -> total = 100 x 208 = 20800

DOCENAS Y OTRAS UNIDADES DE CONTEO:
  "1 docena"  = 12 unidades  | "media docena" = 6 unidades
  "2 docenas" = 24 unidades  | "5 docenas"    = 60 unidades
  "1 ciento"  = 100 unidades | "medio ciento" = 50 unidades
  Para tornillos vendidos por docena: cantidad = docenas x 12, total = cantidad x precio_unitario_catalogo
  Si el usuario dice "5 docenas tornillo drywall 8x2":
    - cantidad = 5 x 12 = 60, precio unitario = 67, total = 60 x 67 = 4020
    - JSON: {{"producto": "TORNILLO DRYWALL 8X 2", "cantidad": 60, "total": 4020}}

INFORMACION DEL NEGOCIO:
{negocio_json}

{catalogo_seccion}

INSTRUCCIONES DE FORMATO Y RESPUESTA:
1. Responde en espanol, natural y amigable. Sin markdown con ** ni #. NUNCA uses asteriscos para nada.

2. ORDEN DE RESPUESTA EN TEXTO PARA VENTAS (CRITICO):
   - Cuando confirmes o listes una venta en tu respuesta de texto, usa SIEMPRE este orden: 1. Cantidad, 2. Producto, 3. Valor Total.
   - Para cantidades fraccionarias usa la fraccion legible, NUNCA el decimal.
   - Para cantidades enteras usa SIEMPRE numero, NUNCA palabras. "1 Manija" NO "Una Manija".
   - Ejemplo correcto entero: "12 Tornillo Drywall $6,000"
   - Ejemplo correcto fraccion: "1/4 Thinner $8,000" (NO "0.25 Thinner $8,000")
   - Ejemplo correcto fraccion: "1/2 Vinilo Blanco T1 $21,000" (NO "2 Vinilo $21,000")

2b. PINTURAS SIN COLOR - REGLA CRITICA:
   Si el usuario dice "vinilo t1", "laca catalizada", "esmalte" etc SIN especificar color:
   -> PREGUNTA el color primero: "De que color?"
   -> NUNCA registres una pintura sin color.
   -> Una vez tengas el color, registra con el precio del catalogo sin preguntar.

2c. BROCHAS SIN MEDIDA - REGLA CRITICA:
   Si el usuario dice "brochas" o "una brocha" SIN especificar la medida:
   -> PREGUNTA la medida primero: "De que medida son las brochas?"
   Precios del catalogo: 1"=$2,000 | 1.5"=$3,000 | 2"=$4,000 | 2.5"=$5,000 | 3"=$6,000 | 4"=$8,000

2d. SELLADOR - REGLA CRITICA:
   -> "sellador [color]" o solo "sellador" -> usar siempre "Sellador Corriente" con sus precios del catalogo.
   -> "sellador catalizado [color]" -> usar "Sellador Catalizado" con sus precios.
   -> NUNCA preguntes si es corriente o catalizado - por defecto es Corriente.
   Precios Sellador Corriente: galon=$65,000 | 3/4=$50,000 | 1/2=$33,000 | 1/4=$17,000 | 1/8=$9,000 | 1/16=$5,000

2e. AEROSOLES - REGLA CRITICA:
   -> Si el usuario NO menciona "alta temperatura": usar el aerosol normal de $9,000.
   -> Si menciona "alta temperatura": usar el de alta temperatura con su precio.

3. Venta detectada - incluye al FINAL uno por producto:
   [VENTA]{{"producto": "nombre completo", "cantidad": 1, "total": 21000}}[/VENTA]
   - USA SIEMPRE y UNICAMENTE la llave "total" con el valor final pagado.
   - NUNCA uses "precio_unitario", "precio", "monto", "valor" ni ninguna otra llave para el dinero.
   - METODO DE PAGO - CRITICO:
     Si el usuario menciona el metodo de pago en su mensaje, DEBES incluirlo en el JSON como "metodo_pago".
       "efectivo" / "cash" / "en plata" / "billetes"        -> "efectivo"
       "transferencia" / "nequi" / "daviplata" / "bancolombia" -> "transferencia"
       "datafono" / "tarjeta" / "credito" / "debito"         -> "datafono"
     Si el usuario NO menciona el metodo: NO pongas "metodo_pago" en el JSON.
   - Si NO menciona cliente: NO preguntes, registra directo sin campo "cliente".
   - Si menciona cliente y esta en la base: incluye "cliente": "Nombre" en el JSON.
   - Si menciona cliente y NO esta en la base:
     NO registres la venta todavia. Pregunta primero:
     "El cliente [Nombre] no esta en la base. Quieres crearlo antes de registrar la venta? (si / no)"
     -> Si el usuario responde "si": emite [INICIAR_CLIENTE]{{"nombre": "Nombre"}}[/INICIAR_CLIENTE] y NO emitas [VENTA] todavia. La venta se registrara automaticamente despues de crear el cliente.
     -> Si el usuario responde "no": registra la venta normalmente con el nombre tal cual sin datos de cliente.
   FORMATO JSON ESTRICTO:
   CORRECTO: {{"producto": "Vinilo T1 Blanco", "cantidad": 0.25, "total": 15000, "metodo_pago": "efectivo"}}
   CORRECTO: {{"producto": "Vinilo T1 Blanco", "cantidad": 0.25, "total": 15000}}
   INCORRECTO: {{"producto": "Vinilo T1 Blanco", "cantidad": 0.25, "precio_unitario": 15000}}
   NUNCA incluyas el simbolo $ ni comas en los numeros.

4. Precio nuevo: [PRECIO]{{"producto": "nombre", "precio": 50000}}[/PRECIO]
5. Codigo producto: [CODIGO_PRODUCTO]{{"producto": "nombre exacto del producto", "codigo": "COD123"}}[/CODIGO_PRODUCTO]
6. Precio fraccion: [PRECIO_FRACCION]{{"producto": "nombre completo", "fraccion": "1/4", "precio": 15000}}[/PRECIO_FRACCION]
7. Info negocio: [NEGOCIO]{{"clave": "valor"}}[/NEGOCIO]
8. Excel: [EXCEL]{{"titulo": "Titulo", "encabezados": ["Col1"], "filas": [["dato"]]}}[/EXCEL]
9. Apertura caja: [CAJA]{{"accion": "apertura", "monto": 50000}}[/CAJA]
10. Cierre caja: [CAJA]{{"accion": "cierre"}}[/CAJA]
11. Gasto: [GASTO]{{"concepto": "nombre", "monto": 50000, "categoria": "varios", "origen": "caja"}}[/GASTO]
12. Fiado: [FIADO]{{"cliente": "Nombre Cliente", "concepto": "descripcion productos", "cargo": 50000, "abono": 0}}[/FIADO]
    - "cargo" = monto que quedo debiendo | "abono" = monto que SI pago ahora
    - SIEMPRE emite tambien los [VENTA] normales para registrar los productos vendidos.
13. Abono a fiado: [ABONO_FIADO]{{"cliente": "Nombre Cliente", "monto": 50000}}[/ABONO_FIADO]
14. Inventario: [INVENTARIO]{{"producto": "nombre", "cantidad": 10, "minimo": 2, "unidad": "galones", "accion": "actualizar"}}[/INVENTARIO]
15. Borrar cliente: [BORRAR_CLIENTE]{{"nombre": "nombre o identificacion del cliente"}}[/BORRAR_CLIENTE]"""


# ─────────────────────────────────────────────
# PARTE DINÁMICA DEL SYSTEM PROMPT (por mensaje)
# ─────────────────────────────────────────────

def _construir_parte_dinamica(mensaje_usuario: str, nombre_usuario: str, memoria: dict) -> str:
    """
    Construye la parte del system prompt que SÍ cambia entre mensajes:
    candidatos del catálogo, cliente encontrado, ventas del día, inventario, caja, etc.
    """
    # ── Resumen de ventas ──
    resumen_sheets_total    = 0
    resumen_sheets_cantidad = 0
    if config.SHEETS_ID and config.SHEETS_DISPONIBLE:
        try:
            from sheets import sheets_leer_ventas_del_dia
            ventas_hoy = sheets_leer_ventas_del_dia()
            for v in ventas_hoy:
                try:
                    resumen_sheets_total    += float(v.get("total", 0) or 0)
                    resumen_sheets_cantidad += 1
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass

    resumen               = obtener_resumen_ventas()
    resumen_excel_total   = resumen["total"]      if resumen else 0
    resumen_excel_cantidad = resumen["num_ventas"] if resumen else 0

    total_mes    = resumen_excel_total
    cantidad_mes = resumen_excel_cantidad

    resumen_texto = (
        f"${total_mes:,.0f} en {cantidad_mes} ventas este mes "
        f"(hoy: ${resumen_sheets_total:,.0f} en {resumen_sheets_cantidad} ventas)"
    ) if cantidad_mes > 0 else "Sin ventas este mes"

    # ── Datos históricos (solo si piden análisis) ──
    palabras_analisis = ["cuanto", "vendimos", "reporte", "analiz", "total",
                         "resumen", "estadistica", "top", "mas vendido"]
    if any(p in mensaje_usuario.lower() for p in palabras_analisis):
        try:
            todos       = obtener_todos_los_datos()
            datos_texto = json.dumps(todos[-100:], ensure_ascii=False, default=str) if todos else "Sin datos aun"
        except Exception:
            datos_texto = "Sin datos aun"
    else:
        datos_texto = "(no cargado)"

    stopwords = {"que", "del", "los", "las", "una", "uno", "con", "por", "para", "como",
                 "fue", "son", "precio", "vale", "cuesta", "cuanto", "la", "el", "de", "en"}

    # ── Info de fracciones del producto mencionado ──
    info_fracciones_extra = ""
    palabras_frac = ["1/4", "1/2", "3/4", "1/8", "1/16", "cuarto", "medio", "mitad", "octavo"]
    if any(p in mensaje_usuario.lower() for p in palabras_frac):
        palabras_msg = mensaje_usuario.lower().split()
        for largo in [4, 3, 2]:
            encontrado = False
            for i in range(len(palabras_msg) - largo + 1):
                fragmento = " ".join(palabras_msg[i:i + largo])
                prod      = buscar_producto_en_catalogo(fragmento)
                if prod and prod.get("precios_fraccion"):
                    info = obtener_info_fraccion_producto(prod["nombre_lower"])
                    if info:
                        info_fracciones_extra = f"PRECIOS POR FRACCION DEL PRODUCTO MENCIONADO:\n{info}"
                    encontrado = True
                    break
            if encontrado:
                break

    # ── Candidatos del catálogo para este mensaje específico ──
    info_candidatos_extra = ""
    palabras_clave        = [p for p in mensaje_usuario.lower().split() if p not in stopwords]

    def _linea_candidato(p: dict) -> str:
        fracs = p.get("precios_fraccion", {})
        pxc   = p.get("precio_por_cantidad")
        if fracs:
            precios_str = " | ".join(f"{k}=${v['precio']:,}" for k, v in fracs.items())
            return f"  - {p['nombre']}: {precios_str}"
        elif pxc:
            return (f"  - {p['nombre']}: "
                    f"c/u=${pxc['precio_bajo_umbral']:,} | "
                    f"x{pxc['umbral']}+=${pxc['precio_sobre_umbral']:,}")
        else:
            return f"  - {p['nombre']}: ${p['precio_unidad']:,}"

    if palabras_clave:
        todos_candidatos = {}
        for largo in [4, 3, 2, 1]:
            for i in range(len(palabras_clave) - largo + 1):
                fragmento = " ".join(palabras_clave[i:i + largo])
                if len(fragmento) < 4:
                    continue
                for prod in buscar_multiples_en_catalogo(fragmento, limite=3):
                    todos_candidatos[prod["nombre_lower"]] = prod

        candidatos = list(todos_candidatos.values())[:12]
        if candidatos:
            lineas = [_linea_candidato(p) for p in candidatos]
            info_candidatos_extra = (
                "PRODUCTOS DEL CATALOGO QUE COINCIDEN CON EL MENSAJE (con precios):\n"
                + "\n".join(lineas)
            )

    # ── Clientes recientes ──
    clientes_recientes_texto = ""
    palabras_recientes = ["ultimo", "ultimos", "reciente", "recientes", "nuevo", "nuevos",
                          "anadido", "anadidos", "agregado", "agregados", "registrado", "registrados"]
    _msg_norm = _normalizar(mensaje_usuario)
    if any(p in _msg_norm for p in palabras_recientes) and "cliente" in _msg_norm:
        try:
            from excel import obtener_clientes_recientes
            recientes = obtener_clientes_recientes(5)
            if recientes:
                lineas = []
                for c in recientes:
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificacion", "") or c.get("Identificacion", "")
                    tipo   = c.get("Tipo de identificacion", "") or c.get("Tipo de identificacion", "")
                    fecha  = c.get("Fecha registro", "Sin fecha")
                    lineas.append(f"  - {nombre} ({tipo}: {id_c}) — registrado: {fecha}")
                clientes_recientes_texto = (
                    "ULTIMOS 5 CLIENTES REGISTRADOS EN EL SISTEMA:\n" + "\n".join(lineas)
                )
        except Exception as e:
            print(f"Error clientes recientes: {e}")

    # ── Búsqueda de cliente si el mensaje lo indica ──
    clientes_texto      = ""
    _indicadores_cliente = [
        "cliente", "para ", "de parte", "a nombre", "factura", "facturar",
        "a credito", "fiado", "cuenta de",
    ]
    _menciona_cliente = any(ind in mensaje_usuario.lower() for ind in _indicadores_cliente)
    if _menciona_cliente:
        try:
            from excel import buscar_cliente_con_resultado
            palabras_cliente = [p for p in mensaje_usuario.lower().split()
                                if len(p) > 3 and p not in stopwords]
            if palabras_cliente:
                termino_cliente = " ".join(palabras_cliente[:4])
                cliente_unico, candidatos_cli = buscar_cliente_con_resultado(termino_cliente)

                if len(candidatos_cli) == 1:
                    c      = candidatos_cli[0]
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificacion", "")
                    tipo   = c.get("Tipo de identificacion", "")
                    clientes_texto = (
                        f"CLIENTE ENCONTRADO EN EL SISTEMA (usar este directamente):\n"
                        f"  - {nombre} ({tipo}: {id_c})"
                    )
                elif len(candidatos_cli) > 1:
                    lineas_cli = []
                    for c in candidatos_cli:
                        nombre = c.get("Nombre tercero", "")
                        id_c   = c.get("Identificacion", "")
                        tipo   = c.get("Tipo de identificacion", "")
                        lineas_cli.append(f"  - {nombre} ({tipo}: {id_c})")
                    clientes_texto = (
                        "MULTIPLES CLIENTES ENCONTRADOS — pregunta al usuario cual es:\n"
                        + "\n".join(lineas_cli)
                        + "\nEjemplo: 'Te refieres a NOMBRE1 (CC: 123) o NOMBRE2 (CC: 456)?'"
                    )
        except Exception:
            clientes_texto = ""

    # ── Inventario, caja y gastos ──
    palabras_inv     = ["inventario", "stock", "queda", "quedan", "hay", "cuanto hay", "existencia"]
    inventario_texto = (
        f"INVENTARIO ACTUAL:\n{json.dumps(cargar_inventario(), ensure_ascii=False)}"
        if any(p in mensaje_usuario.lower() for p in palabras_inv) else ""
    )

    palabras_caja_kw = ["caja", "gasto", "gastos", "apertura", "cierre", "efectivo", "cuanto hay en caja"]
    if any(p in mensaje_usuario.lower() for p in palabras_caja_kw):
        caja_texto   = f"ESTADO CAJA:\n{obtener_resumen_caja()}"
        gastos_texto = f"GASTOS DE HOY:\n{json.dumps(cargar_gastos_hoy(), ensure_ascii=False, default=str)}"
    else:
        caja_texto   = ""
        gastos_texto = ""

    aviso_drive = (
        "AVISO: Google Drive no disponible. Los datos se guardan localmente."
        if not config.DRIVE_DISPONIBLE else ""
    )

    partes = [
        p for p in [
            info_fracciones_extra,
            info_candidatos_extra,
            clientes_recientes_texto,
            clientes_texto,
            f"RESUMEN VENTAS DEL MES:\n{resumen_texto}",
            f"DATOS HISTORICOS (analisis):\n{datos_texto}",
            inventario_texto,
            caja_texto,
            gastos_texto,
            aviso_drive,
            f"Usuario actual: {nombre_usuario}",
        ] if p
    ]
    return "\n\n".join(partes)


# ─────────────────────────────────────────────
# LLAMADA A CLAUDE CON PROMPT CACHING
# ─────────────────────────────────────────────

async def procesar_con_claude(mensaje_usuario: str, nombre_usuario: str, historial_chat: list) -> str:
    memoria        = cargar_memoria()
    parte_estatica = _construir_parte_estatica(memoria)
    parte_dinamica = _construir_parte_dinamica(mensaje_usuario, nombre_usuario, memoria)

    messages = []
    for msg in historial_chat[-4:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
    messages.append({"role": "user", "content": str(mensaje_usuario)})

    num_lineas = mensaje_usuario.count("\n") + mensaje_usuario.count(",") + 1
    max_tokens = min(2000, max(1000, num_lineas * 200))

    loop = asyncio.get_event_loop()
    try:
        respuesta = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: config.claude_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": parte_estatica,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": parte_dinamica,
                        },
                    ],
                    messages=messages,
                )
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        raise RuntimeError("La IA tardó demasiado en responder (>30s). Intenta de nuevo.")

    return respuesta.content[0].text


# ─────────────────────────────────────────────
# PARSEO Y EJECUCIÓN DE ACCIONES
# ─────────────────────────────────────────────

def procesar_acciones(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    from ventas_state import ventas_pendientes, registrar_ventas_con_metodo, _estado_lock, mensajes_standby

    acciones:       list[str] = []
    archivos_excel: list[str] = []
    texto_limpio = texto_respuesta

    # ── Ventas ──
    ventas_con_metodo = []
    ventas_sin_metodo = []

    with _estado_lock:
        esperando_pago = bool(ventas_pendientes.get(chat_id))

    for venta_json in re.findall(r'\[VENTA\](.*?)\[/VENTA\]', texto_respuesta, re.DOTALL):
        try:
            if esperando_pago:
                print(f"[VENTA] ignorado — esperando selección de pago para chat {chat_id}")
            else:
                venta = json.loads(venta_json.strip())
                logging.getLogger("ferrebot.ai").debug(f"[VENTA] JSON recibido: {venta}")
                if venta.get("metodo_pago"):
                    ventas_con_metodo.append(venta)
                else:
                    ventas_sin_metodo.append(venta)
        except Exception as e:
            logging.getLogger("ferrebot.ai").error(f"Error parseando venta: {e} | JSON raw: {repr(venta_json.strip())}")
        texto_limpio = texto_limpio.replace(f'[VENTA]{venta_json}[/VENTA]', '')

    if esperando_pago and ventas_con_metodo:
        ventas_con_metodo.clear()

    def _tiene_cliente_desconocido(ventas: list) -> str | None:
        from excel import buscar_cliente_con_resultado
        for v in ventas:
            nombre_cliente = v.get("cliente", "").strip()
            if not nombre_cliente or nombre_cliente.lower() in ("consumidor final", "cf", ""):
                continue
            try:
                _, candidatos = buscar_cliente_con_resultado(nombre_cliente)
                if not candidatos:
                    return nombre_cliente
            except Exception:
                pass
        return None

    todas_las_ventas_nuevas = ventas_con_metodo + ventas_sin_metodo
    cliente_desconocido     = _tiene_cliente_desconocido(todas_las_ventas_nuevas) if todas_las_ventas_nuevas else None

    if cliente_desconocido and not esperando_pago:
        with _estado_lock:
            ventas_pendientes[chat_id] = todas_las_ventas_nuevas
        acciones.append(f"CLIENTE_DESCONOCIDO:{cliente_desconocido}")
        ventas_con_metodo.clear()
        ventas_sin_metodo.clear()

    if ventas_con_metodo:
        metodo_conocido = ventas_con_metodo[0].get("metodo_pago", "efectivo").lower()
        with _estado_lock:
            ventas_pendientes[chat_id] = ventas_con_metodo
        acciones.append(f"PEDIR_CONFIRMACION:{metodo_conocido}")

    ventas_ignoradas = esperando_pago and bool(
        re.findall(r'\[VENTA\](.*?)\[/VENTA\]', texto_respuesta, re.DOTALL)
    )
    if ventas_ignoradas or (ventas_sin_metodo and esperando_pago):
        acciones.append("PAGO_PENDIENTE_AVISO")
    elif ventas_sin_metodo:
        with _estado_lock:
            ventas_pendientes[chat_id] = ventas_sin_metodo
        acciones.append("PEDIR_METODO_PAGO")

    # ── Cliente nuevo (datos completos) ──
    for cli_json in re.findall(r'\[CLIENTE_NUEVO\](.*?)\[/CLIENTE_NUEVO\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(cli_json.strip())
            nombre = datos.get("nombre", "").strip()
            id_num = str(datos.get("identificacion", "")).strip()
            if nombre and id_num:
                ok = guardar_cliente_nuevo(
                    nombre, datos.get("tipo_id", "Cedula de ciudadania"), id_num,
                    datos.get("tipo_persona", "Natural"),
                    datos.get("correo", ""), datos.get("telefono", ""),
                )
                acciones.append(
                    f"Cliente creado: {nombre.upper()} — {datos.get('tipo_id','')}: {id_num}"
                    if ok else f"No pude guardar el cliente {nombre}."
                )
        except Exception as e:
            logging.getLogger("ferrebot.ai").error(f"Error cliente nuevo: {e}")
        texto_limpio = texto_limpio.replace(f'[CLIENTE_NUEVO]{cli_json}[/CLIENTE_NUEVO]', '')

    # ── Iniciar flujo paso a paso de cliente ──
    for ini_json in re.findall(r'\[INICIAR_CLIENTE\](.*?)\[/INICIAR_CLIENTE\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(ini_json.strip())
            nombre = datos.get("nombre", "").strip()
            from ventas_state import clientes_en_proceso, ventas_esperando_cliente, _estado_lock as _lock
            with _lock:
                clientes_en_proceso[chat_id] = {
                    "nombre":         nombre,
                    "tipo_id":        None,
                    "identificacion": None,
                    "tipo_persona":   None,
                    "correo":         None,
                    "paso":           "nombre" if not nombre else "tipo_id",
                    "vendedor":       vendedor,
                }
                if chat_id in ventas_pendientes and ventas_pendientes[chat_id]:
                    ventas_esperando_cliente[chat_id] = {
                        "ventas":   ventas_pendientes.pop(chat_id),
                        "metodo":   None,
                        "vendedor": vendedor,
                    }
                elif ventas_sin_metodo:
                    ventas_esperando_cliente[chat_id] = {
                        "ventas":   list(ventas_sin_metodo),
                        "metodo":   None,
                        "vendedor": vendedor,
                    }
                    ventas_sin_metodo.clear()
            acciones.append("INICIAR_FLUJO_CLIENTE")
        except Exception as e:
            print(f"Error iniciando flujo cliente: {e}")
        texto_limpio = texto_limpio.replace(f'[INICIAR_CLIENTE]{ini_json}[/INICIAR_CLIENTE]', '')

    # ── Borrar cliente ──
    for bc_json in re.findall(r'\[BORRAR_CLIENTE\](.*?)\[/BORRAR_CLIENTE\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(bc_json.strip())
            nombre = datos.get("nombre", "").strip()
            if nombre:
                from excel import borrar_cliente
                exito, msg = borrar_cliente(nombre)
                acciones.append(msg)
        except Exception as e:
            print(f"Error borrando cliente: {e}")
        texto_limpio = texto_limpio.replace(f'[BORRAR_CLIENTE]{bc_json}[/BORRAR_CLIENTE]', '')

    # ── Precio fraccion ──
    for pf_json in re.findall(r'\[PRECIO_FRACCION\](.*?)\[/PRECIO_FRACCION\]', texto_respuesta, re.DOTALL):
        try:
            datos    = json.loads(pf_json.strip())
            producto = datos.get("producto", "").strip()
            fraccion = datos.get("fraccion", "").strip()
            precio   = float(datos.get("precio", 0))
            if producto and fraccion and precio:
                mem = cargar_memoria()
                mem.setdefault("precios_fraccion", {}).setdefault(producto.lower(), {})[fraccion] = round(precio)
                guardar_memoria(mem)
                acciones.append(f"Precio de fracción guardado: {producto} {fraccion} = ${precio:,.0f}")
        except Exception as e:
            print(f"Error precio fraccion: {e}")
        texto_limpio = texto_limpio.replace(f'[PRECIO_FRACCION]{pf_json}[/PRECIO_FRACCION]', '')

    # ── Precio ──
    for precio_json in re.findall(r'\[PRECIO\](.*?)\[/PRECIO\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(precio_json.strip())
            mem   = cargar_memoria()
            mem["precios"][datos["producto"].lower()] = float(datos["precio"])
            guardar_memoria(mem)
            acciones.append(f"Precio guardado: {datos['producto']} = ${float(datos['precio']):,.0f}")
        except Exception as e:
            print(f"Error precio: {e}")
        texto_limpio = texto_limpio.replace(f'[PRECIO]{precio_json}[/PRECIO]', '')

    # ── Código producto ──
    for cp_json in re.findall(r'\[CODIGO_PRODUCTO\](.*?)\[/CODIGO_PRODUCTO\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(cp_json.strip())
            nombre = datos.get("producto", "").strip()
            codigo = datos.get("codigo", "").strip()
            if nombre and codigo:
                mem      = cargar_memoria()
                catalogo = mem.get("catalogo", {})
                prod     = buscar_producto_en_catalogo(nombre)
                if prod:
                    for k, v in catalogo.items():
                        if v.get("nombre_lower") == prod.get("nombre_lower"):
                            catalogo[k]["codigo"] = codigo
                            break
                    mem["catalogo"] = catalogo
                    guardar_memoria(mem)
                    acciones.append(f"Código guardado: {nombre} = {codigo}")
        except Exception as e:
            print(f"Error código producto: {e}")
        texto_limpio = texto_limpio.replace(f'[CODIGO_PRODUCTO]{cp_json}[/CODIGO_PRODUCTO]', '')

    # ── Negocio ──
    for neg_json in re.findall(r'\[NEGOCIO\](.*?)\[/NEGOCIO\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(neg_json.strip())
            mem   = cargar_memoria()
            mem["negocio"].update(datos)
            guardar_memoria(mem)
        except Exception as e:
            print(f"Error negocio: {e}")
        texto_limpio = texto_limpio.replace(f'[NEGOCIO]{neg_json}[/NEGOCIO]', '')

    # ── Caja ──
    for caja_json in re.findall(r'\[CAJA\](.*?)\[/CAJA\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(caja_json.strip())
            caja  = cargar_caja()
            if datos.get("accion") == "apertura":
                caja.update({
                    "abierta": True,
                    "fecha":   datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
                    "monto_apertura": float(datos.get("monto", 0)),
                    "efectivo": 0, "transferencias": 0, "datafono": 0,
                })
                from memoria import guardar_caja
                guardar_caja(caja)
                acciones.append(f"Caja abierta con ${float(datos.get('monto', 0)):,.0f}")
            elif datos.get("accion") == "cierre":
                acciones.append(f"Caja cerrada.\n{obtener_resumen_caja()}")
                caja["abierta"] = False
                from memoria import guardar_caja
                guardar_caja(caja)
        except Exception as e:
            print(f"Error caja: {e}")
        texto_limpio = texto_limpio.replace(f'[CAJA]{caja_json}[/CAJA]', '')

    # ── Gastos ──
    for gasto_json in re.findall(r'\[GASTO\](.*?)\[/GASTO\]', texto_respuesta, re.DOTALL):
        try:
            datos = json.loads(gasto_json.strip())
            gasto = {
                "concepto":  datos.get("concepto", ""),
                "monto":     float(datos.get("monto", 0)),
                "categoria": datos.get("categoria", "varios"),
                "origen":    datos.get("origen", "externo"),
                "hora":      datetime.now(config.COLOMBIA_TZ).strftime("%H:%M"),
            }
            guardar_gasto(gasto)
            acciones.append(f"Gasto registrado: {gasto['concepto']} — ${gasto['monto']:,.0f} ({gasto['origen']})")
        except Exception as e:
            print(f"Error gasto: {e}")
        texto_limpio = texto_limpio.replace(f'[GASTO]{gasto_json}[/GASTO]', '')

    # ── Fiado ──
    for fiado_json in re.findall(r'\[FIADO\](.*?)\[/FIADO\]', texto_respuesta, re.DOTALL):
        try:
            datos    = json.loads(fiado_json.strip())
            cliente  = datos.get("cliente", "").strip()
            concepto = datos.get("concepto", "")
            cargo    = float(datos.get("cargo", 0))
            abono    = float(datos.get("abono", 0))
            if cliente and cargo > 0:
                saldo = guardar_fiado_movimiento(cliente, concepto, cargo, abono)
                from excel import registrar_fiado_en_excel
                registrar_fiado_en_excel(cliente, concepto, cargo, abono, saldo)
                acciones.append(f"Fiado registrado: {cliente} debe ${saldo:,.0f}")
        except Exception as e:
            print(f"Error fiado: {e}")
        texto_limpio = texto_limpio.replace(f'[FIADO]{fiado_json}[/FIADO]', '')

    # ── Abono fiado ──
    for abono_json in re.findall(r'\[ABONO_FIADO\](.*?)\[/ABONO_FIADO\]', texto_respuesta, re.DOTALL):
        try:
            datos   = json.loads(abono_json.strip())
            cliente = datos.get("cliente", "").strip()
            monto   = float(datos.get("monto", 0))
            if cliente and monto > 0:
                ok, msg = abonar_fiado(cliente, monto)
                if ok:
                    from excel import registrar_fiado_en_excel
                    from memoria import cargar_fiados
                    fiados      = cargar_fiados()
                    cliente_key = next((k for k in fiados if k.lower() in cliente.lower() or cliente.lower() in k.lower()), cliente)
                    saldo       = fiados.get(cliente_key, {}).get("saldo", 0)
                    registrar_fiado_en_excel(cliente_key, "Abono", 0, monto, saldo)
                acciones.append(msg)
        except Exception as e:
            print(f"Error abono fiado: {e}")
        texto_limpio = texto_limpio.replace(f'[ABONO_FIADO]{abono_json}[/ABONO_FIADO]', '')

    # ── Inventario ──
    for inv_json in re.findall(r'\[INVENTARIO\](.*?)\[/INVENTARIO\]', texto_respuesta, re.DOTALL):
        try:
            datos      = json.loads(inv_json.strip())
            inventario = cargar_inventario()
            producto   = datos.get("producto", "").lower()
            accion     = datos.get("accion", "actualizar")
            if accion == "actualizar":
                cantidad = convertir_fraccion_a_decimal(datos.get("cantidad", 0))
                minimo   = convertir_fraccion_a_decimal(datos.get("minimo", 0.5))
                unidad   = datos.get("unidad", "unidades")
                inventario[producto] = {
                    "cantidad": cantidad, "minimo": minimo, "unidad": unidad,
                    "nombre_original": datos.get("producto", producto),
                }
                from memoria import guardar_inventario as _guardar_inv
                _guardar_inv(inventario)
                acciones.append(f"Inventario: {datos['producto']} — {decimal_a_fraccion_legible(cantidad)} {unidad}")
            elif accion == "descontar" and producto in inventario:
                descuento = convertir_fraccion_a_decimal(datos.get("cantidad", 0))
                inventario[producto]["cantidad"] = max(0, inventario[producto]["cantidad"] - descuento)
                from memoria import guardar_inventario as _guardar_inv
                _guardar_inv(inventario)
            from memoria import verificar_alertas_inventario
            acciones.extend(verificar_alertas_inventario())
        except Exception as e:
            print(f"Error inventario: {e}")
        texto_limpio = texto_limpio.replace(f'[INVENTARIO]{inv_json}[/INVENTARIO]', '')

    # ── Excel personalizado ──
    for excel_json in re.findall(r'\[EXCEL\](.*?)\[/EXCEL\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(excel_json.strip())
            nombre = f"reporte_{datetime.now(config.COLOMBIA_TZ).strftime('%Y%m%d_%H%M%S')}.xlsx"
            generar_excel_personalizado(
                datos.get("titulo", "Reporte"),
                datos.get("encabezados", []),
                datos.get("filas", []),
                nombre,
            )
            archivos_excel.append(nombre)
        except Exception as e:
            print(f"Error generando Excel: {e}")
        texto_limpio = texto_limpio.replace(f'[EXCEL]{excel_json}[/EXCEL]', '')

    return texto_limpio.strip(), acciones, archivos_excel


# ─────────────────────────────────────────────
# EDICIÓN DE EXCEL CON CLAUDE
# ─────────────────────────────────────────────

async def editar_excel_con_claude(instruccion: str, ruta_excel: str, nombre_excel: str,
                                   vendedor: str, chat_id: int) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(ruta_excel)
    info_hojas = []
    for hoja_nombre in wb.sheetnames:
        ws = wb[hoja_nombre]
        encabezados   = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        filas_ejemplo = []
        for fila in ws.iter_rows(
            min_row=config.EXCEL_FILA_DATOS,
            max_row=min(config.EXCEL_FILA_DATOS + 2, ws.max_row),
            values_only=True,
        ):
            filas_ejemplo.append(list(fila))
        info_hojas.append({
            "hoja": hoja_nombre, "encabezados": encabezados,
            "ejemplo_filas": filas_ejemplo, "total_filas": ws.max_row - 1,
        })

    prompt = f"""Eres un experto en Python y openpyxl. El usuario tiene un archivo Excel llamado '{nombre_excel}' con esta estructura:

{json.dumps(info_hojas, ensure_ascii=False, default=str)}

El usuario quiere: {instruccion}

Genera SOLO el código Python necesario para modificar el archivo usando openpyxl.
- El archivo ya está cargado, usa: wb = openpyxl.load_workbook('{ruta_excel}')
- Al final guarda con: wb.save('{ruta_excel}')
- Usa colores en formato hex sin # (ej: 'FF0000' para rojo)
- Solo tienes disponibles: openpyxl y json. NO uses os, sys, subprocess ni ninguna otra librería.
- Solo el código, sin explicaciones ni comentarios ni bloques ```
- Si la instrucción no tiene sentido para un Excel, devuelve solo la palabra: IMPOSIBLE"""

    loop     = asyncio.get_event_loop()
    respuesta = await loop.run_in_executor(
        None,
        lambda: config.claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
    )
    codigo = respuesta.content[0].text.strip()
    if "```python" in codigo:
        codigo = codigo.split("```python")[1].split("```")[0].strip()
    elif "```" in codigo:
        codigo = codigo.split("```")[1].split("```")[0].strip()
    return codigo
