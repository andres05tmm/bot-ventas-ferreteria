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
    inicializar_excel,
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
    stopwords = {"que", "del", "los", "las", "una", "uno", "con", "por", "para", "como",
                 "fue", "son", "precio", "vale", "cuesta", "cuanto", "la", "el", "de", "en"}
    palabras_clave = [p for p in mensaje_usuario.lower().split() if p not in stopwords]
    if palabras_clave:
        termino    = " ".join(palabras_clave[:5])
        candidatos = buscar_multiples_en_catalogo(termino, limite=8)
        if len(candidatos) > 1:
            lineas = [f"  - {p['nombre']}: ${p['precio_unidad']:,}" for p in candidatos]
            info_candidatos_extra = (
                "\nPRODUCTOS DEL CATALOGO QUE COINCIDEN CON EL MENSAJE:\n" + "\n".join(lineas)
            )
        elif len(candidatos) == 1:
            p = candidatos[0]
            info_candidatos_extra = f"\nPRODUCTO ENCONTRADO EN CATALOGO: {p['nombre']} — ${p['precio_unidad']:,}"

    aviso_drive = ""
    if not config.DRIVE_DISPONIBLE:
        aviso_drive = "\n⚠️ AVISO: Google Drive no disponible. Los datos se guardan localmente."

    # Catalogo agrupado por categoria
    catalogo = memoria.get("catalogo", {})
    if catalogo:
        categorias: dict = {}
        for prod in catalogo.values():
            cat = prod.get("categoria", "Otros")
            tiene_frac = bool(prod.get("precios_fraccion"))
            categorias.setdefault(cat, []).append(
                f"  - {prod['nombre']}: ${prod['precio_unidad']:,}" + (" [fraccionable]" if tiene_frac else "")
            )
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

CATALOGO DE PRODUCTOS (precio de unidad completa):
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

INSTRUCCIONES DE FORMATO:
1. Responde en español, natural y amigable. Sin markdown con ** ni #.
   CRITICO: Si el mensaje incluye "PRODUCTOS DEL CATALOGO QUE COINCIDEN" o
   "PRODUCTO ENCONTRADO EN CATALOGO", SIEMPRE usa esa informacion para responder precios.
2. Venta detectada — incluye al FINAL uno por producto:
   [VENTA]{{"producto": "nombre completo", "cantidad": 1, "precio_unitario": 40000}}[/VENTA]
   - Si hay cliente: agrega "cliente": "nombre del cliente"
   - Si el usuario ya dijo el metodo: agrega "metodo_pago": "efectivo|transferencia|datafono"
   - Si NO dijo el metodo: NO pongas metodo_pago (el sistema preguntara con botones)
   CRITICO: NUNCA repitas [VENTA] para el mismo producto.
2b. Cliente nuevo — REGLAS CRITICAS:
   - Si el usuario pide crear un cliente y YA dio todos los datos en el mensaje
     (nombre, tipo documento, numero, tipo persona, correo), usa el tag directamente:
     [CLIENTE_NUEVO]{{"nombre":"NOMBRE COMPLETO","tipo_id":"Cédula de ciudadanía","identificacion":"123456","tipo_persona":"Natural","correo":"correo@ejemplo.com"}}[/CLIENTE_NUEVO]
   - Si el usuario pide crear un cliente pero NO dio todos los datos, NO uses el tag.
     En cambio responde con este tag especial para iniciar el flujo paso a paso:
     [INICIAR_CLIENTE]{{"nombre":"nombre si ya lo dijo o vacio"}}[/INICIAR_CLIENTE]
     El sistema se encargara de preguntar cada dato con botones.
   - Los valores validos de tipo_id son: "Cédula de ciudadanía", "NIT", "Cédula de extranjería"
   - Los valores validos de tipo_persona son: "Natural", "Juridica"
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
        for venta in ventas_con_metodo:
            metodo = venta.get("metodo_pago", "efectivo").lower()
            conf   = registrar_ventas_con_metodo([venta], metodo, vendedor, chat_id)
            emoji  = {"efectivo": "💵", "transferencia": "📱", "datafono": "💳"}.get(metodo, "✅")
            acciones.append(f"✅ Venta registrada — {emoji} {metodo.capitalize()}\n" + "\n".join(conf))

    if ventas_sin_metodo:
        import threading
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
            from ventas_state import clientes_en_proceso, _estado_lock as _lock
            with _lock:
                clientes_en_proceso[chat_id] = {
                    "nombre":       nombre,
                    "tipo_id":      None,
                    "identificacion": None,
                    "tipo_persona": None,
                    "correo":       None,
                    "paso":         "nombre" if not nombre else "tipo_id",
                }
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
            datos     = json.loads(inv_json.strip())
            inventario = cargar_inventario()
            producto  = datos.get("producto", "").lower()
            accion    = datos.get("accion", "actualizar")
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
