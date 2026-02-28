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
    cargar_memoria, guardar_memoria, invalidar_cache_memoria,
    buscar_producto_en_catalogo, buscar_multiples_en_catalogo,
    obtener_precios_como_texto, obtener_info_fraccion_producto,
    cargar_inventario, cargar_caja, cargar_gastos_hoy,
    obtener_resumen_caja, guardar_gasto,
    guardar_fiado_movimiento, abonar_fiado,
    actualizar_precio_en_catalogo,
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
        # En el catálogo completo solo mostramos precio base para ahorrar tokens.
        # Las fracciones llegan via info_candidatos_extra cuando el producto es mencionado.
        pxc = prod.get("precio_por_cantidad")
        if pxc:
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

    return f"""Eres FerreBot, asistente de ferreteria colombiana.

CAPACIDADES: ventas[VENTA] excel[EXCEL] precios[PRECIO] inventario[INVENTARIO] caja[CAJA] gastos[GASTO] borrar_cliente[BORRAR_CLIENTE] fiados[FIADO][ABONO_FIADO].

CLIENTES: Pregunta solo si el mensaje tiene: "cliente","para [nombre]","a nombre de","factura","a credito","fiado","cuenta de". Si no, registra SIN cliente, sin preguntar.

PRECIOS — el numero al final ES el total. NUNCA multipliques por defecto.
- "2 brochas 8000"->total:8000 | "15 tornillos 14000"->total:14000 | "1/2 vinilo 21000"->total:21000
- EXCEPCION: solo si dice "c/u","cada uno/a","por unidad","cada unidad" -> multiplica.
- FRACCIONES: 1/4=0.25|1/2=0.5|3/4=0.75|1/8=0.125|1/16=0.0625. Precio siempre es el total.
- MIXTAS (1-1/4, 2 y 1/2...): total = suma de precios por fraccion del catalogo, NUNCA precio_unidad x decimal.

- DOCENAS: 1 docena=12|media=6|1 ciento=100. Tornillos por docena: cantidad=docenas*12, total=cantidad*precio_unitario.

TORNILLOS DRYWALL — formato "TORNILLO DRYWALL CALIBRExMEDIDA". Total = cantidad x precio_unitario.
Voz: "por 1"->X1|"por 1 y cuarto"->X1-1/4|"por 1 y medio"->X1-1/2|"por 2"->X2|"por 3"->X3
TABLA (A=precio si cantidad<100 / B=precio si cantidad>=100, usa A o B segun corresponda):
  6: 1/2 A25 B25|3/4 A58 B30|1 A38 B35|1-1/4 A42 B40|1-1/2 A58 B55|2 A67 B60|2-1/2 A75 B70|3 A83 B80
  8: 3/4 A33 B30|1 A38 B35|1-1/2 A58 B55|2 A67 B60|3 A83 B80
  10: 1 A83 B70|1-1/2 A125 B100|2 A150 B120|2-1/2 A167 B160|3 A167 B160|3-1/2 A208 B200|4 A208 B200
CRITICO: 10X3 (sin "medio") != 10X3-1/2 (con "medio"/"y medio"). Son productos distintos.

THINNER: el precio pagado determina la fraccion. Tabla precio=fraccion:
$3000=1/12 | $4000=1/10 | $5000=1/8 | $6000=1/6 | $8000=1/4 | $10000=1/3 | $13000=1/2 | $16000=5/9 | $20000=3/4 | $26000=1galon
JSON: cantidad=decimal (0.25 para 1/4), total=precio pagado. Texto: fraccion legible. Ej: "6000 de thinner"->cantidad:1/6(0.167),total:6000

CUNETES (4 galones, NO confundir con galon): T1=220000|T2=170000|T3=100000. Multiplica: "2 cunetes t1"->440000.
MEDIO CUNETE: cantidad=1 (NO 0.5), nombre="1/2 Cunete Vinilo TX". T1=120000|T2=85000|T3=55000.

CHAZOS: multiplica siempre cantidad x precio_unitario del catalogo.

SOLDADURA: fracciones en el nombre (60/11,1/32,7018) son especificacion tecnica, NO cantidad/precio.
Cantidad=kilos: "medio kilo"->0.5|"kilo y medio"->1.5. Precio al final es el total.

GRANEL precio/kg: Cemento Blanco=2500|Yeso=1500|Talco=1500|Marmolina=1500|Granito N1=1000.
Carbonato: solo bolsa completa 25kg=18000, NUNCA kilos sueltos.

PINTURAS sin color -> preguntar "De que color?" (NUNCA registres sin color).
BROCHAS sin medida -> preguntar medida. Precios: 1"=2000|1.5"=3000|2"=4000|2.5"=5000|3"=6000|4"=8000.
SELLADOR sin calificar = Corriente. AEROSOL sin "alta temperatura" = normal $9000.

MULTI-PRODUCTO (3+): registra TODO sin preguntar. Sin color en multi-producto->total:0, indica pendiente.

INFORMACION DEL NEGOCIO: {negocio_json}

{catalogo_seccion}

RESPUESTA: espanol natural, sin markdown ni asteriscos.
Texto ventas: Cantidad + Producto + Total. Fracciones legibles (1/4 no 0.25). Multi-producto: 1 linea resumen + JSONs, sin calculos en texto.

ACCIONES al final, una por producto:
[VENTA]{{"producto":"nombre","cantidad":1,"total":21000}}[/VENTA]
- USA SOLO "total". NUNCA "precio_unitario","precio","monto","valor". Sin $ ni comas en numeros.
- metodo_pago si mencionado: efectivo|transferencia|datafono. Si no, omitir.
  efectivo/cash/en plata -> "efectivo" | transferencia/nequi/daviplata/bancolombia -> "transferencia" | datafono/tarjeta/credito/debito -> "datafono"
- cliente si mencionado (aunque sea desconocido). Si no se menciona, NO preguntes ni uses [INICIAR_CLIENTE].
- Fiado con metodo_pago: el metodo indica como pagara al cancelar. cargo=total, abono=0.

[PRECIO]{{"producto":"nombre","precio":50000}}[/PRECIO]  <- cambio permanente, NUNCA junto con [VENTA].
[PRECIO]{{"producto":"nombre","precio":15000,"fraccion":"1/4"}}[/PRECIO]  <- fraccion especifica.
[PRECIO_FRACCION]{{"producto":"nombre","fraccion":"1/4","precio":15000}}[/PRECIO_FRACCION]
[CAJA]{{"accion":"apertura","monto":50000}}[/CAJA]  o  [CAJA]{{"accion":"cierre"}}[/CAJA]
[GASTO]{{"concepto":"x","monto":50000,"categoria":"varios","origen":"caja"}}[/GASTO]
[FIADO]{{"cliente":"X","concepto":"x","cargo":50000,"abono":0}}[/FIADO]  + siempre emitir [VENTA].
[ABONO_FIADO]{{"cliente":"X","monto":50000}}[/ABONO_FIADO]
[INVENTARIO]{{"producto":"x","cantidad":10,"minimo":2,"unidad":"galones","accion":"actualizar"}}[/INVENTARIO]
[BORRAR_CLIENTE]{{"nombre":"x"}}[/BORRAR_CLIENTE]
[EXCEL]{{"titulo":"x","encabezados":["Col1"],"filas":[["dato"]]}}[/EXCEL]
[NEGOCIO]{{"clave":"valor"}}[/NEGOCIO]
[CODIGO_PRODUCTO]{{"producto":"nombre","codigo":"COD123"}}[/CODIGO_PRODUCTO]"""

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

                    # Calcular total mixto en Python para no depender de Claude
                    fracs = prod.get("precios_fraccion", {})
                    msg_lower = mensaje_usuario.lower()
                    map_frac = {
                        "un cuarto": "1/4", "1/4": "1/4",
                        "medio": "1/2", "media": "1/2", "1/2": "1/2",
                        "tres cuartos": "3/4", "3/4": "3/4",
                        "un octavo": "1/8", "1/8": "1/8",
                        "1/16": "1/16",
                    }
                    map_enteros = {"un ": 1, "uno ": 1, "1 ": 1, "dos ": 2, "2 ": 2, "tres ": 3, "3 ": 3}
                    frac_key   = next((v for k, v in map_frac.items() if k in msg_lower), None)
                    n_enteros  = next((v for k, v in map_enteros.items() if k in msg_lower), None)
                    if frac_key and n_enteros and frac_key in fracs and "1" in fracs:
                        p_galon   = fracs["1"]["precio"] if isinstance(fracs.get("1"), dict) else fracs.get("1", 0)
                        p_frac    = fracs[frac_key]["precio"] if isinstance(fracs.get(frac_key), dict) else fracs.get(frac_key, 0)
                        total_calc = p_galon * n_enteros + p_frac
                        dec_map   = {"1/4": 0.25, "1/2": 0.5, "3/4": 0.75, "1/8": 0.125, "1/16": 0.0625}
                        cantidad_calc = n_enteros + dec_map.get(frac_key, 0)
                        info_fracciones_extra += (
                            f"\nTOTAL YA CALCULADO: cantidad={cantidad_calc}, total={total_calc}"
                            f" ({n_enteros}x${p_galon:,} + {frac_key}=${p_frac:,})"
                            f"\nUSA EXACTAMENTE estos valores en el [VENTA], no calcules de nuevo."
                        )

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
    max_tokens = min(4000, max(1500, num_lineas * 250))

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
            datos    = json.loads(precio_json.strip())
            producto = datos["producto"]
            precio   = float(datos["precio"])
            fraccion = datos.get("fraccion")  # opcional: "1/4", "1/2", etc.

            # Actualizar en catálogo (permanente)
            en_catalogo = actualizar_precio_en_catalogo(producto, precio, fraccion)

            # Limpiar precio viejo de precios simples para que no haya conflicto
            mem = cargar_memoria()
            precios_simples = mem.get("precios", {})
            # Borrar cualquier variante del nombre del producto en precios simples
            from memoria import buscar_producto_en_catalogo as _bpc
            prod_encontrado = _bpc(producto)
            if prod_encontrado:
                nombre_lower = prod_encontrado.get("nombre_lower", "")
                claves_borrar = [k for k in precios_simples if k == nombre_lower or nombre_lower in k or k in nombre_lower]
                for k in claves_borrar:
                    del precios_simples[k]
            # Guardar precio nuevo también en simples como referencia actualizada
            precios_simples[producto.lower()] = precio
            mem["precios"] = precios_simples
            guardar_memoria(mem)
            invalidar_cache_memoria()  # Forzar recarga inmediata

            if fraccion:
                acciones.append(f"🧠 Precio actualizado: {producto} {fraccion} = ${precio:,.0f}")
            else:
                acciones.append(f"🧠 Precio actualizado: {producto} = ${precio:,.0f}")
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

# ─────────────────────────────────────────────
# VERSIÓN ASYNC DE PROCESAR_ACCIONES
# ─────────────────────────────────────────────

async def procesar_acciones_async(texto_respuesta: str, vendedor: str, chat_id: int) -> tuple[str, list, list]:
    """
    Wrapper async de procesar_acciones para compatibilidad con handlers async.
    Ejecuta procesar_acciones en un executor para no bloquear el event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: procesar_acciones(texto_respuesta, vendedor, chat_id)
    )
