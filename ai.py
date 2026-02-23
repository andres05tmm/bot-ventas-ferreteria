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
    inicializar_excel, buscar_clientes_multiples,
)
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────

def _construir_system_prompt(mensaje_usuario: str, nombre_usuario: str) -> str:
    memoria       = cargar_memoria()
    resumen       = obtener_resumen_ventas()
    resumen_texto = (
        f"${resumen['total']:,.0f} en {resumen['num_ventas']} ventas este mes"
        if resumen else "Sin ventas este mes"
    )

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

    # Catalogo agrupado por categoria
    catalogo = memoria.get("catalogo", {})
    if catalogo:
        categorias: dict = {}
        for prod in catalogo.values():
            cat = prod.get("categoria", "Otros")
            fracs = prod.get("precios_fraccion", {})
            pxc   = prod.get("precio_por_cantidad")
            if fracs:
                precios_frac_str = " | ".join(
                    f"{k}=${v['precio']:,}" for k, v in fracs.items()
                )
                linea = f"  - {prod['nombre']}: {precios_frac_str}"
            elif pxc:
                linea = (f"  - {prod['nombre']}: "
                         f"c/u=${pxc['precio_bajo_umbral']:,} | "
                         f"x{pxc['umbral']}+=${pxc['precio_sobre_umbral']:,}")
            else:
                linea = f"  - {prod['nombre']}: ${prod['precio_unidad']:,}"
            categorias.setdefault(cat, []).append(linea)
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

    return f"""Eres FerreBot, asistente inteligente de una ferreteria colombiana.

==================================================
TUS CAPACIDADES - NUNCA LAS OLVIDES
==================================================
- SI PUEDES registrar ventas con [VENTA]...[/VENTA]
- SI PUEDES crear Excel con [EXCEL]...[/EXCEL]
- SI PUEDES guardar precios con [PRECIO]...[/PRECIO]
- SI PUEDES controlar inventario con [INVENTARIO]...[/INVENTARIO]
- SI PUEDES manejar caja con [CAJA]...[/CAJA]
- SI PUEDES registrar gastos con [GASTO]...[/GASTO]
- TIENES memoria permanente de precios y productos
==================================================

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
{clientes_texto}

CATALOGO DE PRODUCTOS (con precios por fraccion incluidos):
IMPORTANTE: Los precios de fraccion YA estan en el catalogo. Usaelos directamente.
Formato: 1=galon completo | 3/4 | 1/2 | 1/4 | 1/8 | 1/16
{precios_texto}

{precios_fraccion_texto}

RESUMEN VENTAS DEL MES:
{resumen_texto}

DATOS HISTORICOS (analisis):
{datos_texto}

INVENTARIO ACTUAL:
{json.dumps(cargar_inventario(), ensure_ascii=False)}

ESTADO CAJA:
{obtener_resumen_caja()}

GASTOS DE HOY:
{json.dumps(cargar_gastos_hoy(), ensure_ascii=False, default=str)}
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
   Cuando confirmes una venta, usa UNA sola frase corta sin listar los productos
   (el sistema ya los muestra automaticamente en la confirmacion de pago).
   Ejemplo correcto: "Listo, registro a Patricia Hernandez. ¿Metodo de pago?"
   Ejemplo incorrecto: frase + salto de linea + lista detallada de productos.
   CRITICO: Si el mensaje incluye "PRODUCTOS DEL CATALOGO QUE COINCIDEN" o
   "PRODUCTO ENCONTRADO EN CATALOGO", SIEMPRE usa esa informacion para responder precios.

2. Venta detectada — incluye al FINAL uno por producto:
   [VENTA]{{"producto": "nombre completo", "cantidad": 1, "precio_unitario": 40000}}[/VENTA]
   - Si hay cliente: agrega "cliente": "nombre del cliente"
   - Si el usuario ya dijo el metodo: agrega "metodo_pago": "efectivo|transferencia|datafono"
   - Si NO dijo el metodo: NO pongas metodo_pago (el sistema preguntara con botones)
   CRITICO: NUNCA repitas [VENTA] para el mismo producto.

   REGLA DE FRACCIONES EN VENTAS (MUY IMPORTANTE):
   Cuando el usuario diga "un cuarto", "un octavo", "medio", "un tercio" etc, convierte asi:
   - "un cuarto" o "1/4" → cantidad: 0.25
   - "un octavo" o "1/8" → cantidad: 0.125
   - "medio" o "media" o "1/2" → cantidad: 0.5
   - "tres cuartos" o "3/4" → cantidad: 0.75
   - "un dieciseisavo" o "1/16" → cantidad: 0.0625
   NUNCA registres un octavo como cantidad 1. NUNCA registres un cuarto como cantidad 1.

   REGLA ESPECIAL — THINNER (conversion automatica precio a fraccion de galon):
   Cuando el usuario diga "X pesos de thinner", "tiner por X" o "vendio thinner por X",
   convierte automaticamente usando esta tabla:
     3000=0.0833  4000=0.1    5000=0.125  6000=0.1667  7000=0.2
     8000=0.25    9000=0.3    10000=0.3333  11000=0.3333  12000=0.4
     13000=0.5    14000=0.5   15000=0.5   16000=0.5556  17000=0.6
     18000=0.625  19000=0.6667  20000=0.75  21000=0.8   22000=0.8333
     24000=0.9    25000=0.95  26000=1.0
   El precio_unitario es el valor en pesos que pago el cliente.
   Ejemplo: "15000 de tiner" → cantidad: 0.5, precio_unitario: 15000

   REGLA DE PRODUCTOS AMBIGUOS:
   Si dicen "esmalte negro", "esmalte blanco" etc SIN especificar tipo, asume el corriente basico.
   NO preguntes el tipo ni el color si ya lo dijeron.
   Solo pregunta si mencionan expresamente "3 en 1" o "anticorrosivo".

2b. Cliente en una venta — REGLAS CRITICAS:
   FLUJO SEGUN LO QUE APARECE EN EL SISTEMA:

   A) Si aparece "CLIENTE ENCONTRADO EN EL SISTEMA":
      → Usa ese cliente DIRECTAMENTE en el campo "cliente" del [VENTA].
      → NO preguntes identificacion. NO uses [INICIAR_CLIENTE]. NO uses [CLIENTE_NUEVO].
      → Ejemplo: [VENTA]{{"producto":"...", "cantidad":1, "precio_unitario":50000, "cliente":"ALBERTO TRUJILLO"}}[/VENTA]

   B) Si aparece "MULTIPLES CLIENTES ENCONTRADOS":
      → Pregunta al usuario cual es antes de registrar la venta.
      → Ejemplo: "¿Te refieres a ALBERTO TRUJILLO (CC: 123) o ALBERTO TRUJILLO GOMEZ (CC: 456)?"

   C) Si NO aparece ningun cliente en el sistema (campo vacio):
      → El cliente no existe y hay que crearlo. USA SIEMPRE [INICIAR_CLIENTE].
      → NUNCA uses [CLIENTE_NUEVO] a menos que el usuario haya dado EXPLICITAMENTE
        en ese mismo mensaje: nombre completo + numero de cedula/NIT + tipo de documento.
        Si falta CUALQUIERA de esos tres datos, usa [INICIAR_CLIENTE].
      → En la practica casi siempre usaras [INICIAR_CLIENTE], porque los usuarios
        raramente dan la cedula de una sola vez.
      → [INICIAR_CLIENTE]{{"nombre":"nombre del cliente"}}[/INICIAR_CLIENTE]
      → [CLIENTE_NUEVO] solo cuando tienes nombre+identificacion+tipo_id juntos:
        [CLIENTE_NUEVO]{{"nombre":"NOMBRE","tipo_id":"Cédula de ciudadanía","identificacion":"123","tipo_persona":"Natural","correo":""}}[/CLIENTE_NUEVO]
      → tipo_id validos: "Cédula de ciudadanía", "NIT", "Cédula de extranjería"
      → tipo_persona validos: "Natural", "Juridica"

   NUNCA pidas identificacion si el cliente ya esta en el sistema.
   NUNCA uses [INICIAR_CLIENTE] si el cliente ya esta en el sistema.

   METODO DE PAGO CUANDO HAY CLIENTE NUEVO — CRITICO:
   Cuando emites [INICIAR_CLIENTE], el sistema pausa las ventas hasta completar
   el registro del cliente. NO preguntes metodo de pago en ese mismo mensaje.
   NO emitas "metodo_pago" en los [VENTA] cuando hay [INICIAR_CLIENTE].
   El metodo de pago se pedira automaticamente DESPUES de crear el cliente.
   Ejemplo correcto cuando hay cliente nuevo:
     "Listo, registro a Alberto Trujillo con los 4 productos."
     + [INICIAR_CLIENTE]{{"nombre":"Alberto Trujillo"}}[/INICIAR_CLIENTE]
     + [VENTA]...[/VENTA] x4  (SIN metodo_pago)
   Ejemplo INCORRECTO: pedir metodo de pago antes de crear el cliente.

   ORDEN FLEXIBLE — CRITICO:
   El usuario puede mencionar el cliente y los productos en CUALQUIER orden.
   Debes detectar AMBAS cosas en el mismo mensaje y emitir TODAS las acciones juntas.
   Ejemplos de ordenes validas:
     "anota a Juan Mendoza (nuevo) 2 galones de vinilo y un cuarto de colbon"
     → emite [INICIAR_CLIENTE] + [VENTA] + [VENTA] en el mismo mensaje
     "vendi 2 galones de vinilo y un cuarto de colbon... a Juan Mendoza (nuevo)"
     → emite [VENTA] + [VENTA] + [INICIAR_CLIENTE] en el mismo mensaje
   El sistema se encarga de pausar las ventas hasta que se cree el cliente
   y luego las registra automaticamente. Tu solo emite todo junto.

   NOMBRES DE PRODUCTOS — REGLA CRITICA:
   El nombre del producto NUNCA debe incluir la cantidad ni la fraccion.
   Correcto: "producto":"Vinilo Davinci T1 Azul Concentrado", "cantidad":0.5
   Incorrecto: "producto":"Vinilo Davinci T1 Azul Concentrado x1/2"
   La cantidad va SOLO en el campo "cantidad", nunca en el nombre del producto.

3. Precio nuevo: [PRECIO]{{"producto": "nombre", "precio": 50000}}[/PRECIO]
3b. Precio fraccion: [PRECIO_FRACCION]{{"producto": "nombre completo", "fraccion": "1/4", "precio": 15000}}[/PRECIO_FRACCION]
4. Info negocio: [NEGOCIO]{{"clave": "valor"}}[/NEGOCIO]
5. Excel: [EXCEL]{{"titulo": "Titulo", "encabezados": ["Col1"], "filas": [["dato"]]}}[/EXCEL]
6. Apertura caja: [CAJA]{{"accion": "apertura", "monto": 50000}}[/CAJA]
7. Cierre caja: [CAJA]{{"accion": "cierre"}}[/CAJA]
8. Gasto: [GASTO]{{"concepto": "nombre", "monto": 50000, "categoria": "varios", "origen": "caja"}}[/GASTO]
9. Inventario: [INVENTARIO]{{"producto": "nombre", "cantidad": 10, "minimo": 2, "unidad": "galones", "accion": "actualizar"}}[/INVENTARIO]
10. Para borrar: /borrar numero
11. Usuario actual: {nombre_usuario}"""


# ─────────────────────────────────────────────
# LLAMADA A CLAUDE
# ─────────────────────────────────────────────

async def procesar_con_claude(mensaje_usuario: str, nombre_usuario: str, historial_chat: list) -> str:
    system_prompt = _construir_system_prompt(mensaje_usuario, nombre_usuario)

    messages = []
    for msg in historial_chat[-10:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
    messages.append({"role": "user", "content": str(mensaje_usuario)})

    loop = asyncio.get_event_loop()
    respuesta = await loop.run_in_executor(
        None,
        lambda: config.claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system=system_prompt,
            messages=messages,
        )
    )
    return respuesta.content[0].text


# ─────────────────────────────────────────────
# PARSEO Y EJECUCION DE ACCIONES
# ─────────────────────────────────────────────

def procesar_acciones(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    """
    Extrae y ejecuta todas las acciones del mensaje de Claude.
    Retorna (texto_limpio, acciones, archivos_excel).
    """
    from ventas_state import ventas_pendientes, registrar_ventas_con_metodo, _estado_lock

    acciones:      list[str] = []
    archivos_excel: list[str] = []
    texto_limpio = texto_respuesta

    # ── Ventas ──
    ventas_con_metodo = []
    ventas_sin_metodo = []

    for venta_json in re.findall(r'\[VENTA\](.*?)\[/VENTA\]', texto_respuesta, re.DOTALL):
        try:
            venta = json.loads(venta_json.strip())
            if venta.get("metodo_pago"):
                ventas_con_metodo.append(venta)
            else:
                ventas_sin_metodo.append(venta)
        except Exception as e:
            print(f"Error parseando venta: {e}")
        texto_limpio = texto_limpio.replace(f'[VENTA]{venta_json}[/VENTA]', '')

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
        with _estado_lock:
            ventas_pendientes[chat_id] = ventas_sin_metodo
        acciones.append("PEDIR_METODO_PAGO")

    # ── Cliente nuevo (datos completos dados de una vez) ──
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
                # Si habia ventas sin metodo pendientes, guardarlas para
                # registrarlas automaticamente cuando se cree el cliente
                if chat_id in ventas_pendientes and ventas_pendientes[chat_id]:
                    ventas_esperando_cliente[chat_id] = {
                        "ventas":   ventas_pendientes.pop(chat_id),
                        "metodo":   None,
                        "vendedor": vendedor,
                    }
                # Si habia ventas con metodo ya confirmado, guardarlas tambien
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
