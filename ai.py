"""
Integracion con Claude AI:
- Construccion del system prompt con contexto del negocio
- Llamada a la API de Claude (async via executor)
- Parseo y ejecucion de acciones embebidas en la respuesta ([VENTA]...[/VENTA], etc.)
"""

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
)
from excel import (
    obtener_todos_los_datos, obtener_resumen_ventas,
    generar_excel_personalizado, guardar_cliente_nuevo,
    inicializar_excel, buscar_clientes_multiples, _normalizar,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────

def _construir_system_prompt(mensaje_usuario: str, nombre_usuario: str) -> str:
    memoria       = cargar_memoria()
    resumen = obtener_resumen_ventas()
    resumen_excel_total    = resumen["total"]     if resumen else 0
    resumen_excel_cantidad = resumen["num_ventas"] if resumen else 0

    # Sumar ventas del dia actual desde el Sheets (aun no pasadas al Excel)
    resumen_sheets_total    = 0
    resumen_sheets_cantidad = 0
    if config.SHEETS_ID and config.SHEETS_DISPONIBLE:
        try:
            from sheets import sheets_leer_ventas_del_dia
            ventas_hoy = sheets_leer_ventas_del_dia()
            for v in ventas_hoy:
                try:
                    resumen_sheets_total += float(v.get("total", 0) or 0)
                    resumen_sheets_cantidad += 1
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass

    total_combinado    = resumen_excel_total + resumen_sheets_total
    cantidad_combinada = resumen_excel_cantidad + resumen_sheets_cantidad

    if cantidad_combinada > 0:
        resumen_texto = (
            f"${total_combinado:,.0f} en {cantidad_combinada} ventas este mes "
            f"(hoy: ${resumen_sheets_total:,.0f} en {resumen_sheets_cantidad} ventas)"
        )
    else:
        resumen_texto = "Sin ventas este mes"

    # Cargar datos historicos solo si el mensaje parece un analisis
    palabras_analisis = ["cuanto", "vendimos", "reporte", "analiz", "total",
                         "resumen", "estadistica", "top", "mas vendido"]
    if any(p in mensaje_usuario.lower() for p in palabras_analisis):
        try:
            todos = obtener_todos_los_datos()
            datos_texto = json.dumps(todos[-100:], ensure_ascii=False, default=str) if todos else "Sin datos aun"
        except Exception:
            datos_texto = "Sin datos aun"
    else:
        datos_texto = "(no cargado)"

    # Stopwords (se usa mas abajo en candidatos y clientes)
    stopwords = {"que", "del", "los", "las", "una", "uno", "con", "por", "para", "como",
                 "fue", "son", "precio", "vale", "cuesta", "cuanto", "la", "el", "de", "en"}

    # Info de fracciones si el mensaje las menciona
    info_fracciones_extra = ""
    palabras_frac = ["1/4", "1/2", "3/4", "1/8", "1/16", "cuarto", "medio", "mitad", "octavo"]
    if any(p in mensaje_usuario.lower() for p in palabras_frac):
        palabras_msg = mensaje_usuario.lower().split()
        for largo in [4, 3, 2]:
            encontrado = False
            for i in range(len(palabras_msg) - largo + 1):
                fragmento = " ".join(palabras_msg[i:i + largo])
                prod = buscar_producto_en_catalogo(fragmento)
                if prod and prod.get("precios_fraccion"):
                    info = obtener_info_fraccion_producto(prod["nombre_lower"])
                    if info:
                        info_fracciones_extra = f"\nPRECIOS POR FRACCION DEL PRODUCTO MENCIONADO:\n{info}"
                    encontrado = True
                    break
            if encontrado:
                break

    # Candidatos del catalogo para el mensaje actual
    info_candidatos_extra = ""
    palabras_clave = [p for p in mensaje_usuario.lower().split() if p not in stopwords]
    if palabras_clave:
        termino    = " ".join(palabras_clave[:5])
        candidatos = buscar_multiples_en_catalogo(termino, limite=8)

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

        if len(candidatos) > 1:
            lineas = [_linea_candidato(p) for p in candidatos]
            info_candidatos_extra = (
                "\nPRODUCTOS DEL CATALOGO QUE COINCIDEN CON EL MENSAJE (con precios de fraccion):\n"
                + "\n".join(lineas)
            )
        elif len(candidatos) == 1:
            info_candidatos_extra = (
                "\nPRODUCTO ENCONTRADO EN CATALOGO:\n" + _linea_candidato(candidatos[0])
            )

    # ── CLIENTES RECIENTES: si el mensaje lo pide ──
    clientes_recientes_texto = ""
    palabras_recientes = ["ultimo", "ultimos", "reciente", "recientes", "nuevo", "nuevos", "anadido", "anadidos", "agregado", "agregados", "registrado", "registrados"]
    _msg_norm = _normalizar(mensaje_usuario)
    if any(p in _msg_norm for p in palabras_recientes) and "cliente" in _msg_norm:
        try:
            from excel import obtener_clientes_recientes
            recientes = obtener_clientes_recientes(5)
            if recientes:
                lineas = []
                for c in recientes:
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificacion", "") or c.get("Identificación", "")
                    tipo   = c.get("Tipo de identificacion", "") or c.get("Tipo de identificación", "")
                    fecha  = c.get("Fecha registro", "Sin fecha")
                    lineas.append(f"  - {nombre} ({tipo}: {id_c}) — registrado: {fecha}")
                clientes_recientes_texto = (
                    "ULTIMOS 5 CLIENTES REGISTRADOS EN EL SISTEMA:\n" + "\n".join(lineas)
                )
        except Exception as e:
            print(f"Error clientes recientes: {e}")
            clientes_recientes_texto = ""

    # ── CLIENTES: buscar si el mensaje menciona alguno ──
    clientes_texto = ""
    try:
        from excel import buscar_cliente_con_resultado
        palabras_cliente = [p for p in mensaje_usuario.lower().split()
                            if len(p) > 3 and p not in stopwords]
        if palabras_cliente:
            termino_cliente = " ".join(palabras_cliente[:4])
            cliente_unico, candidatos = buscar_cliente_con_resultado(termino_cliente)

            if len(candidatos) == 1:
                # Un solo cliente encontrado — mostrarlo directamente
                c      = candidatos[0]
                nombre = c.get("Nombre tercero", "")
                id_c   = c.get("Identificación", "")
                tipo   = c.get("Tipo de identificación", "")
                clientes_texto = (
                    f"CLIENTE ENCONTRADO EN EL SISTEMA (usar este directamente):\n"
                    f"  - {nombre} ({tipo}: {id_c})"
                )
            elif len(candidatos) > 1:
                # Varios candidatos — el bot debe preguntar cual es
                lineas_cli = []
                for c in candidatos:
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificación", "")
                    tipo   = c.get("Tipo de identificación", "")
                    lineas_cli.append(f"  - {nombre} ({tipo}: {id_c})")
                clientes_texto = (
                    "MULTIPLES CLIENTES ENCONTRADOS — pregunta al usuario cual es:\n"
                    + "\n".join(lineas_cli)
                    + "\nEjemplo: '¿Te refieres a NOMBRE1 (CC: 123) o NOMBRE2 (CC: 456)?'"
                )
    except Exception:
        clientes_texto = ""

    aviso_drive = ""
    if not config.DRIVE_DISPONIBLE:
        aviso_drive = "\n⚠️ AVISO: Google Drive no disponible. Los datos se guardan localmente."

    # Inventario: solo si el mensaje lo menciona
    palabras_inv = ["inventario", "stock", "queda", "quedan", "hay", "cuanto hay", "existencia"]
    if any(p in mensaje_usuario.lower() for p in palabras_inv):
        inventario_texto = f"INVENTARIO ACTUAL:\n{json.dumps(cargar_inventario(), ensure_ascii=False)}"
    else:
        inventario_texto = ""

    # Caja y gastos: solo si el mensaje los menciona
    palabras_caja = ["caja", "gasto", "gastos", "apertura", "cierre", "efectivo", "cuanto hay en caja"]
    if any(p in mensaje_usuario.lower() for p in palabras_caja):
        caja_texto   = f"ESTADO CAJA:\n{obtener_resumen_caja()}"
        gastos_texto = f"GASTOS DE HOY:\n{json.dumps(cargar_gastos_hoy(), ensure_ascii=False, default=str)}"
    else:
        caja_texto   = ""
        gastos_texto = ""


    # ── CATALOGO: carga inteligente segun el mensaje ──
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

    palabras_precio = ["precio", "vale", "cuesta", "cuanto", "catalogo", "productos", "lista", "precios"]
    palabras_no_catalogo = ["caja", "gasto", "gastos", "apertura", "cierre", "reporte", "excel",
                            "cliente", "clientes", "inventario", "vendimos", "resumen", "analiz"]
    msg_lower = mensaje_usuario.lower()

    pide_catalogo_completo = any(p in msg_lower for p in palabras_precio)
    no_necesita_catalogo   = any(p in msg_lower for p in palabras_no_catalogo) and not pide_catalogo_completo
    # Si ya tenemos candidatos especificos y no pide el catalogo completo, no lo mandamos
    tiene_candidatos = bool(info_candidatos_extra)

    if no_necesita_catalogo:
        # Mensaje de caja/gastos/reportes — no necesita catalogo
        precios_texto = ""
    elif tiene_candidatos and not pide_catalogo_completo:
        # Mensaje de venta con producto especifico — los candidatos ya estan en info_candidatos_extra
        precios_texto = ""
    elif catalogo:
        # Catalogo completo: cuando pide precios genericos o mensaje ambiguo
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

    # Construir seccion catalogo solo si hay contenido
    if precios_texto:
        catalogo_seccion = (
            "CATALOGO DE PRODUCTOS (precios por fraccion incluidos):\n"
            "Formato: 1=galon | 3/4 | 1/2 | 1/4 | 1/8 | 1/16\n"
            + precios_texto
            + "\n\n" + precios_fraccion_texto
        )
    elif precios_fraccion_texto and "ninguno" not in precios_fraccion_texto:
        catalogo_seccion = precios_fraccion_texto
    else:
        catalogo_seccion = ""

    return f"""Eres FerreBot, asistente inteligente de una ferreteria colombiana.

CAPACIDADES: ventas[VENTA] excel[EXCEL] precios[PRECIO] inventario[INVENTARIO] caja[CAJA] gastos[GASTO] borrar_cliente[BORRAR_CLIENTE]. Memoria permanente de precios.

REGLAS CRITICAS DE FRACCIONES Y PRECIOS:
- Muchos productos se venden en fracciones: 1/4, 1/2, 3/4, 1/8 de galon/unidad.
- Los precios de fraccion NO se calculan matematicamente. Son precios independientes.
- NUNCA calcules ni asumas el precio de una fraccion multiplicando el precio de unidad.
- Si el usuario menciona una fraccion Y dice el precio: registra la venta y guarda el precio.
- Si el usuario menciona una fraccion pero NO dice el precio: busca en PRECIOS DE FRACCION CONOCIDOS.
  Si no lo tienes: pregunta antes de registrar.
- En el campo "cantidad" pon el decimal: 1/4=0.25, 1/2=0.5, 3/4=0.75, 1/8=0.125
- En el campo "precio_unitario" pon el precio TOTAL de esa fraccion (lo que pago el cliente)
{info_fracciones_extra}
{info_candidatos_extra}

INFORMACION DEL NEGOCIO:
{json.dumps(memoria.get('negocio', {}), ensure_ascii=False)}
{clientes_recientes_texto}
{clientes_texto}

{catalogo_seccion}

RESUMEN VENTAS DEL MES:
{resumen_texto}

DATOS HISTORICOS (analisis):
{datos_texto}

{inventario_texto}
{caja_texto}
{gastos_texto}
{aviso_drive}

REGLA CRITICA — PREGUNTAS VS ORDENES:
NUNCA ejecutes una accion si el usuario esta PREGUNTANDO como funciona algo.
Palabras que indican pregunta (NO actuar): "como hago", "como se hace", "como funciona",
"como abro", "como cierro", "como registro", "para que sirve", "que pasa si", "y si quiero".
Solo actua cuando el mensaje es una orden directa: "abre caja", "cierra caja", "registra venta".
Ejemplos:
  - "y como hago cuando la quiera abrir?" → SOLO explicar, NO abrir caja
  - "abre la caja con 50000" → SI abrir caja
  - "como se registra un gasto?" → SOLO explicar, NO registrar nada
  - "registra un gasto de 5000" → SI registrar gasto

INSTRUCCIONES DE FORMATO:
1. Responde en español, natural y amigable. Sin markdown con ** ni #.
   Mensajes cortos y directos, SIN lineas en blanco entre frases ni parrafos.
   Cuando confirmes una venta CON cliente ya registrado en el sistema, usa UNA sola frase corta:
   Ejemplo correcto (cliente existente): "Listo, registro a Patricia Hernandez. ¿Metodo de pago?"
   Cuando confirmes una venta CON cliente NUEVO (emites [INICIAR_CLIENTE]), NO preguntes
   el metodo de pago — el sistema lo hara automaticamente despues de crear el cliente:
   Ejemplo correcto (cliente nuevo): "Detecto la venta y el cliente nuevo. Voy a registrar todo junto."
   Ejemplo INCORRECTO (cliente nuevo): "Listo, registro a Alberto Trujillo. ¿Metodo de pago?"
   CRITICO: Si el mensaje incluye "PRODUCTOS DEL CATALOGO QUE COINCIDEN" o
   "PRODUCTO ENCONTRADO EN CATALOGO", SIEMPRE usa esa informacion para responder precios.

2. Venta detectada — incluye al FINAL uno por producto:
   [VENTA]{{"producto": "nombre completo", "cantidad": 1, "precio_unitario": 40000}}[/VENTA]
   - Si el usuario NO menciona cliente en ninguna parte del mensaje: NO preguntes, registra directo sin campo "cliente".
   - Si el usuario menciona un cliente: agrega "cliente": "nombre del cliente".
   - Si el usuario menciona el metodo DE PAGO EN ESTE MISMO MENSAJE: agrega "metodo_pago": "efectivo|transferencia|datafono".
   - Si NO dijo el metodo EN ESTE MENSAJE: NO pongas metodo_pago (el sistema preguntara con botones).
   CRITICO: NUNCA preguntes "a nombre de quien" si el usuario no menciono un cliente explícitamente.
   CRITICO: El metodo de pago solo se incluye si el usuario lo dijo EXPLICITAMENTE en el mensaje actual.
   CRITICO: NUNCA repitas [VENTA] para el mismo producto.
   CRITICO: Si el usuario esta RESPONDIENDO una pregunta tuya, NO emitas [VENTA] de nuevo.

   REGLA DE PRECIO TOTAL VS UNITARIO — CRITICA:
   En una ferreteria colombiana, cuando el usuario dice "X producto PRECIO" sin palabras especiales,
   el PRECIO es siempre el TOTAL cobrado, NO el precio por unidad.
   precio_unitario = PRECIO / cantidad

   EJEMPLOS DE PRECIO TOTAL (sin palabras especiales → dividir):
   - "12 tornillos drywall 2000" → precio_unitario=166.67, cantidad=12 (2000 es el total)
   - "12 tornillos 2000" → precio_unitario=166.67, cantidad=12
   - "5 brochas 10000" → precio_unitario=2000, cantidad=5
   - "vendio 3 galones vinilo 120000" → precio_unitario=40000, cantidad=3
   - "50 tornillos 5000" → precio_unitario=100, cantidad=50 (5000 es el total)

   EJEMPLOS DE PRECIO UNITARIO (con palabras especiales → multiplicar):
   - "12 tornillos a 2000" → precio_unitario=2000, total=24000
   - "12 tornillos a 2000 cada uno" → precio_unitario=2000, total=24000
   - "12 tornillos c/u 2000" → precio_unitario=2000, total=24000
   - "5 brochas a 3000 cada una" → precio_unitario=3000, total=15000
   Palabras que indican precio UNITARIO: "a X", "c/u", "cada uno", "cada una", "por unidad".
   Si NO aparece ninguna de esas palabras: el precio es el TOTAL, divide entre cantidad.

   REGLA DE FRACCIONES EN VENTAS (MUY IMPORTANTE):
   Cuando el usuario diga "un cuarto", "un octavo", "medio", "un tercio" etc, convierte asi:
   - "un cuarto" o "1/4" → cantidad: 0.25
   - "un octavo" o "1/8" → cantidad: 0.125
   - "medio" o "media" o "1/2" → cantidad: 0.5
   - "tres cuartos" o "3/4" → cantidad: 0.75
   - "un dieciseisavo" o "1/16" → cantidad: 0.0625

   REGLA THINNER — MUY IMPORTANTE:
   Cuando el usuario diga "X pesos de thinner/tiner/tinner" el precio es el TOTAL pagado.
   La cantidad (fraccion de galon) se determina SEGUN ESTA TABLA OFICIAL:
   $3.000 → cantidad:0.083333 | $10.000 → cantidad:0.333333
   $15.000 → cantidad:0.5     | $20.000 → cantidad:0.75

   REGLA DE PINTURAS SIN COLOR (MUY IMPORTANTE):
   Si el usuario dice "vinilo t1", "esmalte", etc SIN especificar color:
   → SIEMPRE pregunta el color primero: "¿De qué color?" y NO registres hasta saberlo.

2b. Cliente en una venta — REGLAS CRITICAS:
   FLUJO SEGUN LO QUE APARECE EN EL SISTEMA:

   A) Si el usuario NO MENCIONÓ a ningún cliente:
      → NO uses [INICIAR_CLIENTE]. NUNCA preguntes el nombre.
      → Registra la [VENTA] directamente sin el campo "cliente".
      → El sistema usará "Consumidor Final" automáticamente.

   B) Si aparece "CLIENTE ENCONTRADO EN EL SISTEMA":
      → Usa ese cliente DIRECTAMENTE en el campo "cliente" del [VENTA].
      → NO preguntes identificacion. NO uses [INICIAR_CLIENTE].

   C) Si aparece "MULTIPLES CLIENTES ENCONTRADOS":
      → Pregunta al usuario cual es antes de registrar la venta.

   D) Si el usuario MENCIONÓ un cliente explícitamente pero NO aparece en el sistema:
      → El cliente no existe y hay que crearlo. USA SIEMPRE [INICIAR_CLIENTE].
      → NUNCA uses [CLIENTE_NUEVO] a menos que el usuario haya dado EXPLICITAMENTE
        en ese mismo mensaje: nombre completo + numero de cedula/NIT + tipo de documento.
      → Ejemplo normal: [INICIAR_CLIENTE]{{"nombre":"nombre del cliente"}}[/INICIAR_CLIENTE]

   METODO DE PAGO CUANDO HAY CLIENTE NUEVO — CRITICO:
   Cuando emites [INICIAR_CLIENTE], el sistema pausa las ventas. NO preguntes metodo de pago.
   Ejemplo correcto: "Detecto la venta y el cliente nuevo. Voy a registrar todo junto."
   + [INICIAR_CLIENTE]{{"nombre":"Alberto Trujillo"}}[/INICIAR_CLIENTE]
   + [VENTA]...[/VENTA]

3. Precio nuevo: [PRECIO]{{"producto": "nombre", "precio": 50000}}[/PRECIO]
3c. Codigo producto: [CODIGO_PRODUCTO]{{"producto": "nombre exacto del producto", "codigo": "COD123"}}[/CODIGO_PRODUCTO]
3b. Precio fraccion: [PRECIO_FRACCION]{{"producto": "nombre completo", "fraccion": "1/4", "precio": 15000}}[/PRECIO_FRACCION]
4. Info negocio: [NEGOCIO]{{"clave": "valor"}}[/NEGOCIO]
5. Excel: [EXCEL]{{"titulo": "Titulo", "encabezados": ["Col1"], "filas": [["dato"]]}}[/EXCEL]
6. Apertura caja: [CAJA]{{"accion": "apertura", "monto": 50000}}[/CAJA]
7. Cierre caja: [CAJA]{{"accion": "cierre"}}[/CAJA]
8. Gasto: [GASTO]{{"concepto": "nombre", "monto": 50000, "categoria": "varios", "origen": "caja"}}[/GASTO]
9. Inventario: [INVENTARIO]{{"producto": "nombre", "cantidad": 10, "minimo": 2, "unidad": "galones", "accion": "actualizar"}}[/INVENTARIO]
10. Borrar cliente: [BORRAR_CLIENTE]{{"nombre": "nombre o identificacion del cliente"}}[/BORRAR_CLIENTE]
11. Para borrar ventas: /borrar numero
12. Usuario actual: {nombre_usuario}"""


# ─────────────────────────────────────────────
# LLAMADA A CLAUDE
# ─────────────────────────────────────────────

async def procesar_con_claude(mensaje_usuario: str, nombre_usuario: str, historial_chat: list) -> str:
    system_prompt = _construir_system_prompt(mensaje_usuario, nombre_usuario)

    messages = []
    for msg in historial_chat[-6:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
    messages.append({"role": "user", "content": str(mensaje_usuario)})

    loop = asyncio.get_event_loop()
    respuesta = await loop.run_in_executor(
        None,
        lambda: config.claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            system=system_prompt,
            messages=messages,
        )
    )
    return respuesta.content[0].text


# ─────────────────────────────────────────────
# PARSEO Y EJECUCION DE ACCIONES
# ─────────────────────────────────────────────

def procesar_acciones(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    from ventas_state import ventas_pendientes, registrar_ventas_con_metodo, _estado_lock

    acciones:      list[str] = []
    archivos_excel: list[str] = []
    texto_limpio = texto_respuesta

    # ── Ventas ──
    ventas_con_metodo = []
    ventas_sin_metodo = []

    with _estado_lock:
        esperando_pago = bool(ventas_pendientes.get(chat_id))

    ventas_nuevas = re.findall(r'\[VENTA\](.*?)\[/VENTA\]', texto_respuesta, re.DOTALL)

    for venta_json in ventas_nuevas:
        try:
            if esperando_pago:
                print(f"[VENTA] ignorado — esperando seleccion de pago para chat {chat_id}")
            else:
                venta = json.loads(venta_json.strip())
                if venta.get("metodo_pago"):
                    ventas_con_metodo.append(venta)
                else:
                    ventas_sin_metodo.append(venta)
        except Exception as e:
            print(f"Error parseando venta: {e}")
        texto_limpio = texto_limpio.replace(f'[VENTA]{venta_json}[/VENTA]', '')

    if esperando_pago and ventas_con_metodo:
        ventas_con_metodo.clear()

    if ventas_con_metodo:
        grupos: dict = {}
        for venta in ventas_con_metodo:
            metodo = venta.get("metodo_pago", "efectivo").lower()
            grupos.setdefault(metodo, []).append(venta)

        for metodo, grupo in grupos.items():
            conf  = registrar_ventas_con_metodo(grupo, metodo, vendedor, chat_id)
            emoji = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
            acciones.append(f"✅ Venta registrada — {emoji} {metodo.capitalize()}\n" + "\n".join(conf))

    if ventas_sin_metodo:
        if esperando_pago:
            acciones.append("PAGO_PENDIENTE_AVISO")
        else:
            with _estado_lock:
                ventas_pendientes[chat_id] = ventas_sin_metodo
            acciones.append("PEDIR_METODO_PAGO")

    # ── Cliente nuevo ──
    for cli_json in re.findall(r'\[CLIENTE_NUEVO\](.*?)\[/CLIENTE_NUEVO\]', texto_respuesta, re.DOTALL):
        try:
            datos  = json.loads(cli_json.strip())
            nombre = datos.get("nombre", "").strip()
            id_num = str(datos.get("identificacion", "")).strip()
            if nombre and id_num:
                ok = guardar_cliente_nuevo(
                    nombre, datos.get("tipo_id", "Cédula de ciudadanía"), id_num,
                    datos.get("tipo_persona", "Natural"),
                    datos.get("correo", ""), datos.get("telefono", ""),
                )
                acciones.append(
                    f"👤 Cliente creado: {nombre.upper()} — {datos.get('tipo_id','')}: {id_num}"
                    if ok else f"⚠️ No pude guardar el cliente {nombre}. Intenta de nuevo."
                )
            else:
                acciones.append("⚠️ Para crear el cliente necesito al menos el nombre y el número de identificación.")
        except Exception as e:
            print(f"Error cliente nuevo: {e}")
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
            else:
                acciones.append("⚠️ No se especifico el cliente a borrar.")
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
                acciones.append(f"🧠 Precio de fraccion guardado: {producto} {fraccion} = ${precio:,.0f}")
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
            acciones.append(f"🧠 Precio guardado: {datos['producto']} = ${float(datos['precio']):,.0f}")
        except Exception as e:
            print(f"Error precio: {e}")
        texto_limpio = texto_limpio.replace(f'[PRECIO]{precio_json}[/PRECIO]', '')

    # ── Codigo producto ──
    for cp_json in re.findall(r'\[CODIGO_PRODUCTO\](.*?)\[/CODIGO_PRODUCTO\]', texto_respuesta, re.DOTALL):
        try:
            datos   = json.loads(cp_json.strip())
            nombre  = datos.get("producto", "").strip()
            codigo  = datos.get("codigo", "").strip()
            if nombre and codigo:
                mem      = cargar_memoria()
                catalogo = mem.get("catalogo", {})
                from memoria import buscar_producto_en_catalogo
                prod = buscar_producto_en_catalogo(nombre)
                if prod:
                    for k, v in catalogo.items():
                        if v.get("nombre_lower") == prod.get("nombre_lower"):
                            catalogo[k]["codigo"] = codigo
                            break
                    mem["catalogo"] = catalogo
                    guardar_memoria(mem)
                    acciones.append(f"🏷️ Código guardado: {nombre} = {codigo}")
                else:
                    acciones.append(f"⚠️ Producto '{nombre}' no encontrado en el catálogo.")
        except Exception as e:
            print(f"Error codigo producto: {e}")
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
                    "fecha": datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d"),
                    "monto_apertura": float(datos.get("monto", 0)),
                    "efectivo": 0, "transferencias": 0, "datafono": 0,
                })
                from memoria import guardar_caja
                guardar_caja(caja)
                acciones.append(f"✅ Caja abierta con ${float(datos.get('monto', 0)):,.0f}")
            elif datos.get("accion") == "cierre":
                acciones.append(f"🔒 Caja cerrada.\n{obtener_resumen_caja()}")
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
            acciones.append(f"💸 Gasto registrado: {gasto['concepto']} — ${gasto['monto']:,.0f} ({gasto['origen']})")
        except Exception as e:
            print(f"Error gasto: {e}")
        texto_limpio = texto_limpio.replace(f'[GASTO]{gasto_json}[/GASTO]', '')

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
                acciones.append(f"📦 Inventario: {datos['producto']} — {decimal_a_fraccion_legible(cantidad)} {unidad}")
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
            datos    = json.loads(excel_json.strip())
            nombre   = f"reporte_{datetime.now(config.COLOMBIA_TZ).strftime('%Y%m%d_%H%M%S')}.xlsx"
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
# EDICION DE EXCEL CON CLAUDE
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

Genera SOLO el codigo Python necesario para modificar el archivo usando openpyxl.
- El archivo ya esta cargado, usa: wb = openpyxl.load_workbook('{ruta_excel}')
- Al final guarda con: wb.save('{ruta_excel}')
- Usa colores en formato hex sin # (ej: 'FF0000' para rojo)
- Solo tienes disponibles: openpyxl y json. NO uses os, sys, subprocess ni ninguna otra libreria.
- Solo el codigo, sin explicaciones ni comentarios ni bloques ```
- Si la instruccion no tiene sentido para un Excel, devuelve solo la palabra: IMPOSIBLE"""

    loop = asyncio.get_event_loop()
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
