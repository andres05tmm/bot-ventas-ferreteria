"""
Integración con Claude AI (modelo: claude-haiku-4-5-20251001):
- Construcción del system prompt con contexto del negocio
- Llamada a la API de Claude con PROMPT CACHING (ahorro ~60% en tokens de input)
- Parseo y ejecución de acciones embebidas en la respuesta ([VENTA]...[/VENTA], etc.)

OPTIMIZACIONES DE COSTO ACTIVAS:
  1. Prompt caching  — la parte estática del prompt (reglas + catálogo) se cachea 5 min.
                       Costo de tokens cacheados = 10% del precio normal.
  2. Historial corto — se envían solo los últimos 1-4 mensajes (adaptativo).
  3. max_tokens cap  — techo adaptativo de respuesta.
  4. Catálogo simplificado — parte estática solo precio base, fracciones vía MATCH dinámico (~26% menos tokens cacheados).

CORRECCIONES v3:
  - Eliminado código muerto (_frac_por_producto, loop vacío en _linea_candidato)
  - Historial adaptativo más agresivo (1-4 mensajes según contexto)
  - Instrucción de JSON compacto para reducir output tokens
"""

import logging
import os
import asyncio
import json
import re
import traceback
from datetime import datetime

import config
from memoria import (
    cargar_memoria, guardar_memoria, invalidar_cache_memoria,
    buscar_producto_en_catalogo, buscar_multiples_en_catalogo,
    buscar_multiples_con_alias,
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
# ALIAS DE FERRETERÍA (pre-procesamiento)
# ─────────────────────────────────────────────

_ALIAS_FERRETERIA = [
    # (patrón regex, reemplazo)
    (r'\b(\d+)?\s*botellas?\s+de\s+thinner\b', r'\g<1> thinner 4000'.replace('None', '1')),
    (r'\b(\d+)?\s*botellas?\s+de\s+varsol\b', r'\g<1> varsol 4000'),
    (r'\b(\d+)?\s*litros?\s+de\s+thinner\b', r'\g<1> thinner 8000'),
    (r'\b(\d+)?\s*litros?\s+de\s+varsol\b', r'\g<1> varsol 8000'),
    (r'\b(\d+)?\s*botellas?\s+thinner\b', r'\g<1> thinner 4000'),
    (r'\b(\d+)?\s*botellas?\s+varsol\b', r'\g<1> varsol 4000'),
    (r'\b(\d+)?\s*litros?\s+thinner\b', r'\g<1> thinner 8000'),
    (r'\b(\d+)?\s*litros?\s+varsol\b', r'\g<1> varsol 8000'),
]

def aplicar_alias_ferreteria(mensaje: str) -> str:
    """Transforma alias comunes antes de enviar a Claude."""
    resultado = mensaje
    for patron, reemplazo in _ALIAS_FERRETERIA:
        # Manejar caso sin número (ej: "botella de thinner" -> "1 thinner 4000")
        def _reemplazo(m):
            num = m.group(1) if m.group(1) else "1"
            return reemplazo.replace(r'\g<1>', num).strip()
        resultado = re.sub(patron, _reemplazo, resultado, flags=re.IGNORECASE)
    return resultado
  
# ─────────────────────────────────────────────
# PARTE ESTÁTICA DEL SYSTEM PROMPT (cacheable)
# ─────────────────────────────────────────────

def _construir_parte_estatica(memoria: dict) -> str:
    """
    Construye la parte del system prompt que NO cambia entre mensajes.
    Al ser idéntica en todas las llamadas, Anthropic la cachea automáticamente.
    """
    catalogo = memoria.get("catalogo", {})

    def _linea_producto_simple(prod):
        # Solo nombre:precio_unidad — las fracciones llegan via MATCH en la parte dinámica
        # Ahorra ~1960 tokens cacheados vs incluir fracciones completas
        pxc = prod.get("precio_por_cantidad")
        if pxc:
            return f"{prod['nombre']}:{pxc['precio_bajo_umbral']}/{pxc['precio_sobre_umbral']}x{pxc['umbral']}"
        else:
            return f"{prod['nombre']}:{prod['precio_unidad']}"

    if catalogo:
        # Catálogo simplificado: precio_unidad solamente (sin fracciones)
        # Las fracciones completas se inyectan en la parte dinámica via MATCH
        # cuando el producto es mencionado en el mensaje
        categorias: dict = {}
        for prod in catalogo.values():
            cat = prod.get("categoria", "Otros")
            categorias.setdefault(cat, []).append(_linea_producto_simple(prod))
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
            f"{prod_key} {frac}:{precio}"
            for prod_key, fracs in precios_fraccion_mem.items()
            for frac, precio in fracs.items()
        ]
        precios_fraccion_texto = "FRACCIONES EXTRA:\n" + "\n".join(lineas_frac)
    else:
        precios_fraccion_texto = ""

    # En MODO_MATCH_ONLY: catálogo se omite del estático — llega dinámicamente via MATCH
    # o como fallback completo si MATCH no encuentra nada. Cache estable con ~1235 tokens (reglas).
    # En modo normal: catálogo simplificado (solo precio base, sin fracciones) → 26% menos tokens
    _match_only = os.getenv("MODO_MATCH_ONLY", "false").lower() == "true"

    if _match_only:
        # Solo fracciones extra si las hay — el catálogo llega en la parte dinámica
        catalogo_seccion = precios_fraccion_texto
    else:
        catalogo_seccion = (
            "CATALOGO(nombre:precio_galon_o_unidad. Fracciones exactas en MATCH):\n"
            + precios_texto
            + ("\n" + precios_fraccion_texto if precios_fraccion_texto else "")
        ) if precios_texto else precios_fraccion_texto

    negocio_json = json.dumps(memoria.get("negocio", {}), ensure_ascii=False)

    return f"""FerreBot — asistente ferreteria colombiana.
Acciones:[VENTA][EXCEL][PRECIO][PRECIO_FRACCION][INVENTARIO][GASTO][FIADO][ABONO_FIADO][BORRAR_CLIENTE][NEGOCIO][CODIGO_PRODUCTO]

CLIENTES: pregunta SOLO si mensaje tiene "cliente","para X","a nombre de","factura","a credito","fiado","cuenta de".
- Si se menciona un nombre y está en la base: incluye "cliente":"Nombre" en el JSON.
- Si se menciona un nombre y NO está en la base: incluye igual "cliente":"Nombre" en el JSON. El sistema preguntará si quiere crearlo — TU no preguntes nada ni uses [INICIAR_CLIENTE].
- NUNCA uses [INICIAR_CLIENTE]. SIEMPRE emite [VENTA] aunque el cliente sea desconocido.

PRECIOS: numero al final ES el total, NUNCA multipliques por defecto.
"2 brochas 8000"->8000|"15 tornillos 14000"->14000|"1/2 vinilo 21000"->21000
Multiplica SOLO si dice "c/u","cada uno/a","por unidad".
FRACCIONES: 1/4=0.25|1/2=0.5|3/4=0.75|1/8=0.125|1/16=0.0625. Precio=total.
MIXTAS — REGLA CRITICA:
Cantidades como "2 y 1/2", "1-1/4", "3 y medio" = enteros + fraccion.
PASO 1: Identificar parte entera y fraccion (2-1/2 = 2 enteros + 1/2)
PASO 2: Buscar precio de 1 galon y precio de fraccion en MATCH
PASO 3: total = (enteros × precio_galon) + precio_fraccion
NUNCA multiplicar decimal por precio_unidad.
Ejemplos:
- "2-1/2 vinilo T2"(1=40000,1/2=21000): 2×40000=80000 + 21000 = 101000 ✓
- "1 y 1/4 esmalte"(1=65000,1/4=17000): 1×65000=65000 + 17000 = 82000 ✓
- "3 y medio acronal"(kg=13000,1/2=7000): 3×13000=39000 + 7000 = 46000 ✓
DOCENAS: 1 docena=12|media=6|ciento=100. cantidad=docenas*12, total=cantidad*precio_u.

TORNILLOS DRYWALL: "TORNILLO DRYWALL CALIBRExMEDIDA". Total=cantidad*precio_u.
Voz: "por 1"=X1|"y cuarto"=+1/4|"y medio"=+1/2|"por 2"=X2|"por 3"=X3
<50uds=precio1,>=50=precio2:
6:X1/2=25/25|X3/4=58/30|X1=38/35|X1-1/4=42/40|X1-1/2=58/55|X2=67/60|X2-1/2=75/70|X3=83/80
8:X3/4=33/30|X1=38/35|X1-1/2=58/55|X2=67/60|X3=83/80
10:X1=83/70|X1-1/2=125/100|X2=150/120|X2-1/2=167/160|X3=167/160|X3-1/2=208/200|X4=208/200
CRITICO: 10X3(sin "medio") != 10X3-1/2(con "medio"/"y medio"). Productos distintos.

THINNER y VARSOL: mismos precios por fraccion de galon.
precio->fraccion: 3000=1/12|4000=1/10|5000=1/8|6000=1/6|8000=1/4|10000=1/3|13000=1/2|16000=5/9|20000=3/4|26000=1g
cantidad=decimal, total=precio pagado.
Ej: "varsol 8000"->cantidad=0.25,total=8000|"thinner 13000"->cantidad=0.5,total=13000

CUNETES(4gal,NO galon): T1=220000|T2=170000|T3=100000. "2 cunetes t1"->440000.
MEDIO CUNETE: cantidad=1(NO 0.5),nombre="1/2 Cunete Vinilo TX",T1=120000|T2=90000|T3=60000.

MEDIDAS EN NOMBRE no son cantidad: chazos(3/8),puntillas(2"),arandelas(1/2),soldadura(60/11,7018). Total=cantidad*precio_u catalogo.
LIJA ESMERIL: se vende por centimetros. Precio en catalogo = 100cm.
Calculo: total = cantidad_cm × (precio/100)
N°36=20000|N°60=18000|N°80=18000|N°100=18000 (x100cm)
Ej: "10cm esmeril 36"=10×200=2000|"50cm esmeril 60"=50×180=9000
En [VENTA] poner cantidad=centimetros y producto="cm Lija Esmeril N°X"
Ej: {{"producto":"cm Lija Esmeril N°36","cantidad":15,"total":3000}}
Asi se muestra: "15 cm Lija Esmeril N°36 $3,000"

GRANEL/kg: CementoBlanco=2500|Yeso=1500|Talco=1500|Marmolina=1500|GranitoN1=1000|Acronal(kg=13000,1/2kg=7000). Carbonato=bolsa25kg=18000,NUNCA kilos sueltos.
Cantidad kilos: "medio kilo"=0.5|"kilo y medio"=1.5.

PINTURAS sin color->preguntar "De que color?". BROCHAS sin medida->preguntar. Precios:1"=2000|1.5"=3000|2"=4000|2.5"=5000|3"=6000|4"=8000.
RODILLO: "rodillo" o "rodillos" SIN medida = Rodillo Convencional $7000. 
"3 rodillos"=3 x Rodillo Convencional = 21000. "1 rodillo"=7000.
SOLO usar Rodillo de X" si dice EXPLICITAMENTE la medida: "rodillo de 3", "rodillo 4 pulgadas", "rodillo de 2"".
NUNCA interpretar "3 rodillos" como "Rodillo de 3"" — el 3 es CANTIDAD, no medida.
BISAGRA 3x3 sin material=PAR$4500(INOX solo si dice "inox"/"inoxidable").
SELLADOR=Corriente. AEROSOL=normal$9000("alta temperatura" solo si lo dice).
MULTI-PRODUCTO(3+): registra TODO sin preguntar. Sin color->total:0,indica pendiente.

INFORMACION DEL NEGOCIO: {negocio_json}

{catalogo_seccion}

RESPUESTA: espanol, sin markdown. Fracciones legibles (1/4 no 0.25).
SILENCIO TOTAL si es registro de venta sin ambiguedades: emite SOLO los JSON [VENTA], cero texto antes ni despues. El sistema ya muestra el resumen al cliente automaticamente.
Texto SOLO en: (1) falta dato obligatorio como color o medida, (2) producto no encontrado en catalogo, (3) precio contradictorio, (4) el usuario hace una pregunta explicita.

ACCIONES al final (una por producto, JSON compacto sin espacios):
[VENTA]{{"producto":"nombre","cantidad":1,"total":21000}}[/VENTA]
- Solo campo "total" (NUNCA precio_unitario/precio/monto). Sin $ ni comas.
- "producto" = nombre limpio del catalogo SIN fraccion. La fraccion va SOLO en "cantidad".
  CORRECTO: {{"producto":"Laca Miel Catalizada","cantidad":0.25,"total":17000}}
  INCORRECTO: {{"producto":"Laca Miel Catalizada 1/4","cantidad":0.25,"total":17000}}
  INCORRECTO: {{"producto":"1/4 Laca Miel Catalizada","cantidad":0.25,"total":17000}}
- metodo_pago si se menciona: efectivo|transferencia|datafono
  cash/plata=efectivo | nequi/daviplata/transfer=transferencia | tarjeta/datafono=datafono
- cliente si se menciona. Fiado+metodo: cargo=total,abono=0.
[PRECIO]{{"producto":"nombre","precio":50000}}[/PRECIO]
[PRECIO]{{"producto":"nombre","precio":15000,"fraccion":"1/4"}}[/PRECIO]
USA [PRECIO] SOLO si el usuario dice explicitamente "el precio es X","cuesta X","vale X","cambia el precio a X". NUNCA si solo pregunta "precio del X" o "cuanto vale X" — eso es consulta, responde SOLO con los precios base del catalogo en una linea corta. NO calcules combinaciones ni variantes.
[GASTO]{{"concepto":"x","monto":50000,"categoria":"varios","origen":"caja"}}[/GASTO]
[FIADO]{{"cliente":"X","concepto":"x","cargo":50000,"abono":0}}[/FIADO]
[ABONO_FIADO]{{"cliente":"X","monto":50000}}[/ABONO_FIADO]
[INVENTARIO]{{"producto":"x","cantidad":10,"minimo":2,"unidad":"galones","accion":"actualizar"}}[/INVENTARIO]
[BORRAR_CLIENTE]{{"nombre":"x"}}[/BORRAR_CLIENTE]
[EXCEL]{{"titulo":"x","encabezados":["Col1"],"filas":[["dato"]]}}[/EXCEL]
[NEGOCIO]{{"clave":"valor"}}[/NEGOCIO]
[CODIGO_PRODUCTO]{{"producto":"n","codigo":"COD123"}}[/CODIGO_PRODUCTO]"""

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
                 "fue", "son", "precio", "vale", "cuesta", "cuanto", "la", "el", "de", "en",
                 "galon", "litro", "kilo", "metro", "pulgada", "pulgadas", "unidad", "unidades",
                 "vendi", "vendo", "vendimos", "dame", "quiero", "necesito", "par"}

    def _es_keyword_relevante(p: str) -> bool:
        """Determina si una palabra debe incluirse como keyword de búsqueda."""
        if p in stopwords:
            return False
        if len(p) > 2:
            return True
        if p.isdigit():
            return True
        # Incluir códigos de variante de 2 chars: t1, t2, t3, x1, 6x, 8x, etc.
        if len(p) == 2 and any(c.isdigit() for c in p):
            return True
        return False

    palabras_clave = [p for p in mensaje_usuario.lower().split() if _es_keyword_relevante(p)]
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
    # palabras_clave ya definida arriba con _es_keyword_relevante (incluye t1/t2/t3)

    # Detectar fracciones y cantidades mixtas mencionadas en el mensaje
    _fracs_mencionadas = set()
    _msg_lower = mensaje_usuario.lower()
    _mapa_palabras = {
        "cuarto": "1/4", "un cuarto": "1/4",
        "medio": "1/2",  "media": "1/2",  "un medio": "1/2",
        "octavo": "1/8", "un octavo": "1/8",
        "tres cuartos": "3/4",
    }
    for palabra, frac in _mapa_palabras.items():
        if palabra in _msg_lower:
            _fracs_mencionadas.add(frac)
    for token in _msg_lower.split():
        if token in ("1/4","1/2","3/4","1/8","1/16","3/8"):
            _fracs_mencionadas.add(token)

    # Tokenizar mensaje para detectar fracciones adyacentes a productos
    _tokens = mensaje_usuario.lower().replace(",","").split()
    _fracs_set = {"1/4","1/2","3/4","1/8","1/16","3/8"}

    def _linea_candidato(p: dict) -> str:
        # Formato comprimido: sin "  - ", sin "$", sin comas, fraccion relevante marcada con *
        fracs = p.get("precios_fraccion", {})
        pxc   = p.get("precio_por_cantidad")
        if fracs:
            nl = p.get("nombre_lower", "")
            palabras_prod = [w for w in nl.split() if len(w) > 3]
            frac_este_prod = None
            _tok = _msg_lower.replace(",","").split()
            for idx_t, tok in enumerate(_tok):
                if tok in _fracs_set:
                    ventana = " ".join(_tok[idx_t:idx_t+5])
                    if any(pp in ventana for pp in palabras_prod):
                        frac_este_prod = tok
                        break
            lineas_frac = []
            for k, v in fracs.items():
                precio = v['precio'] if isinstance(v, dict) else v
                marca = "*" if k == frac_este_prod else ""
                lineas_frac.append(f"{k}={precio}{marca}")
            return f"{p['nombre']}:" + "|".join(lineas_frac)
        elif pxc:
            return f"{p['nombre']}:{pxc['precio_bajo_umbral']}/{pxc['precio_sobre_umbral']}x{pxc['umbral']}"
        else:
            return f"{p['nombre']}:{p['precio_unidad']}"

    if palabras_clave:
        # FIX MULTI-PRODUCTO: segmentar el mensaje por producto para que cada uno
        # tenga garantizado su candidato, sin que unos "aplasten" a otros.
        # Ej: "1/4 vinilo blanco, 1/2 laca miel, 3/4 thinner" → 3 segmentos independientes
        import re as _re
        _segmentos_raw = _re.split(r',\s*|(?<!\w)\s+y\s+(?=\d)', mensaje_usuario.lower())
        _segmentos = []
        for seg in _segmentos_raw:
            seg = seg.strip()
            # Quitar fracciones y números del inicio para quedarnos con el nombre
            seg_limpio = _re.sub(r'^[\d\-/\.\s]+', '', seg).strip()
            if len(seg_limpio) > 3:
                _segmentos.append(seg_limpio)

        combinados = {}
        _candidatos_garantizados = {}  # nl → prod: el mejor hit por segmento, siempre incluido

        # Familias donde hay múltiples tallas/variantes — necesitamos límite más alto
        _familias_con_tallas = {"brocha", "rodillo", "lija", "disco", "tornillo", "chazo",
                                 "tuerca", "arandela", "bisagra", "candado", "manguera",
                                 "lampara", "foco", "cable", "codo", "tee", "reduccion"}

        # Palabras de acción al inicio del mensaje que no son producto
        _palabras_accion = {"vendi", "vende", "vendí", "vender", "cobré", "cobre", "cobrar",
                             "dame", "deme", "dar", "quiero", "necesito", "compre", "compré"}

        # Stemming mínimo: quitar 's' final para que "lijas"→"lija", "discos"→"disco"
        def _stem(w):
            return w[:-1] if w.endswith("s") and len(w) > 4 else w

        # 1. Buscar candidato por cada segmento de producto (garantiza uno por producto)
        for seg in _segmentos:
            # Quitar palabras de acción y cantidades iniciales del segmento
            palabras_raw = seg.split()
            # Saltar palabras de acción al inicio
            while palabras_raw and palabras_raw[0] in _palabras_accion:
                palabras_raw = palabras_raw[1:]
            # Saltar números/fracciones iniciales (cantidades como "3", "1/2", "50")
            while palabras_raw and _re.match(r'^[\d/\.]+$', palabras_raw[0]):
                palabras_raw = palabras_raw[1:]
            # Saltar palabras de volumen/unidad inmediatas tras la cantidad
            _unidades_volumen = {"galon", "galones", "cuarto", "cuartos", "litro", "litros",
                                  "kilo", "kilos", "gramo", "gramos", "metro", "metros",
                                  "unidad", "unidades", "caja", "cajas", "bolsa", "bolsas",
                                  "rollo", "rollos", "par", "pares"}
            while palabras_raw and palabras_raw[0] in _unidades_volumen:
                palabras_raw = palabras_raw[1:]

            # Incluir: palabras del nombre del producto + números que son tallas (van DESPUÉS del nombre base)
            # Los números como "3", "80", "100" solo se incluyen si no son la primera palabra
            # (para evitar que "3 cuartos de vinilo T1" incluya "3" que matchearía T3)
            palabras_seg = []
            nombre_producto_encontrado = False
            for p in palabras_raw:
                if p in stopwords:
                    continue
                # Tokens alfanuméricos cortos como t1, t2, t3, x1 (2 chars con al menos un dígito)
                if len(p) == 2 and any(c.isdigit() for c in p):
                    palabras_seg.append(p)
                    nombre_producto_encontrado = True
                elif len(p) > 2 and not p.replace('.','').replace(',','').isdigit():
                    palabras_seg.append(_stem(p))  # con stemming
                    nombre_producto_encontrado = True
                elif _re.match(r'^\d+x\d+', p):  # formatos como 3x3, 8x1
                    palabras_seg.append(p)
                    nombre_producto_encontrado = True
                elif nombre_producto_encontrado and p.isdigit() and 1 <= int(p) <= 999:
                    # Número de talla SOLO después de haber encontrado el nombre del producto
                    palabras_seg.append(p)

            if not palabras_seg:
                continue

            # Detectar si el segmento es de familia con tallas → usar límite más alto
            es_familia = any(f in seg.lower() or _stem(f) in seg.lower() for f in _familias_con_tallas)
            _limite_seg = 8 if es_familia else 3

            for largo in [4, 3, 2, 1]:
                encontrado_seg = False
                for i in range(len(palabras_seg) - largo + 1):
                    fragmento = " ".join(palabras_seg[i:i + largo])
                    if len(fragmento) < 3:
                        continue
                    resultados = buscar_multiples_con_alias(fragmento, limite=_limite_seg)
                    primer = True
                    for prod in resultados:
                        nl = prod["nombre_lower"]
                        combinados[nl] = prod
                        if primer:
                            # El primer resultado es el mejor match — garantizarlo en la lista final
                            _candidatos_garantizados[nl] = prod
                            primer = False
                        encontrado_seg = True
                    if encontrado_seg:
                        break
                if encontrado_seg:
                    break

        # 2. Búsqueda global adicional (fragmentos del mensaje completo)
        for largo in [4, 3, 2]:
            for i in range(len(palabras_clave) - largo + 1):
                frag_exact = " ".join(palabras_clave[i:i + largo])
                if len(frag_exact) < 4:
                    continue
                for prod in buscar_multiples_en_catalogo(frag_exact, limite=1):
                    if frag_exact in prod["nombre_lower"]:
                        combinados[prod["nombre_lower"]] = prod

        # 3. Ordenar: más palabras del mensaje completo en el nombre = mayor prioridad
        #    Los candidatos garantizados (mejor hit por segmento) siempre se incluyen primero.
        #    Luego se agregan hasta 25 adicionales del pool general, ordenados por relevancia.
        _garantizados_lista = list(_candidatos_garantizados.values())
        _garantizados_nls   = set(_candidatos_garantizados.keys())
        _resto = sorted(
            [p for p in combinados.values() if p["nombre_lower"] not in _garantizados_nls],
            key=lambda p: sum(1 for w in palabras_clave if w in p["nombre_lower"]),
            reverse=True
        )
        candidatos = _garantizados_lista + _resto
        candidatos = candidatos[:max(len(_garantizados_lista), 25)]

        if candidatos:
            lineas = [_linea_candidato(p) for p in candidatos]
            info_candidatos_extra = "MATCH:\n" + "\n".join(lineas)
            print(f"[CANDIDATOS DEBUG]\n{info_candidatos_extra}")
        elif os.getenv("MODO_MATCH_ONLY", "false").lower() == "true":
            # FALLBACK: MATCH no encontró nada — inyectar catálogo completo en parte dinámica
            # Garantiza que Claude siempre tenga precios correctos aunque el MATCH falle
            from memoria import cargar_memoria as _cm
            _mem_fb = _cm()
            _cat_fb = _mem_fb.get("catalogo", {})
            if _cat_fb:
                _lineas_fb = []
                for _p in _cat_fb.values():
                    _fracs = _p.get("precios_fraccion", {})
                    _pxc   = _p.get("precio_por_cantidad")
                    if _fracs:
                        _lineas_fb.append(_p["nombre"] + ":" + "|".join(
                            f'{k}={v["precio"] if isinstance(v,dict) else v}'
                            for k, v in _fracs.items()
                        ))
                    elif _pxc:
                        _lineas_fb.append(f'{_p["nombre"]}:{_pxc["precio_bajo_umbral"]}/{_pxc["precio_sobre_umbral"]}x{_pxc["umbral"]}')
                    else:
                        _lineas_fb.append(f'{_p["nombre"]}:{_p["precio_unidad"]}')
                info_candidatos_extra = "CATALOGO COMPLETO (MATCH sin resultados):\n" + "\n".join(_lineas_fb)
                print("[CANDIDATOS DEBUG] ⚠️ MATCH vacío — usando catálogo completo como fallback")

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
            import re as _re_cli
            # Extraer nombre despues de "para", "a nombre de", "de parte de", etc.
            _match_nombre = _re_cli.search(
                r'(?:para|a nombre de|de parte de|cuenta de)\s+([A-Za-záéíóúÁÉÍÓÚñÑ]+(?:\s+[A-Za-záéíóúÁÉÍÓÚñÑ]+){0,3})',
                mensaje_usuario, _re_cli.IGNORECASE
            )
            if _match_nombre:
                termino_cliente = _match_nombre.group(1).strip()
            else:
                palabras_cliente = [p for p in mensaje_usuario.lower().split()
                                    if len(p) > 3 and p not in stopwords]
                termino_cliente = " ".join(palabras_cliente[:4]) if palabras_cliente else ""
            if termino_cliente:
                cliente_unico, candidatos_cli = buscar_cliente_con_resultado(termino_cliente)

                if len(candidatos_cli) == 1:
                    c      = candidatos_cli[0]
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificacion", "")
                    tipo   = c.get("Tipo de identificacion", "")
                    # Solo asignar si hay 2+ palabras en comun con el nombre buscado
                    palabras_buscadas    = set(_normalizar(termino_cliente).split())
                    palabras_encontradas = set(_normalizar(nombre).split())
                    coincidencias = palabras_buscadas & palabras_encontradas
                    if len(coincidencias) >= 2 or (len(palabras_buscadas) == 1 and coincidencias):
                        clientes_texto = (
                            f"CLIENTE ENCONTRADO EN EL SISTEMA (usar este directamente):\n"
                            f"  - {nombre} ({tipo}: {id_c})"
                        )
                    else:
                        # Coincidencia parcial — marcar para preguntar ANTES de confirmar
                        clientes_texto = (
                            f"CLIENTE NO IDENTIFICADO: usa exactamente \"cliente\": \"{termino_cliente}\" en el JSON. "
                            f"NO uses \"{nombre}\". El sistema preguntara si es cliente nuevo o existente."
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
        if not config._get_drive_disponible() else ""
    )

    msg_l = mensaje_usuario.lower()

    # ── Acronal: precalcular total en Python ──
    acronal_calculado = ""
    if "acronal" in msg_l:
        import re as _re_ac
        # Normalizar "kilos y medio" -> "X.5", "medio kilo" -> "0.5"
        msg_ac = msg_l
        msg_ac = _re_ac.sub(r'(\d+)\s+(?:kilo[s]?\s+)?y\s+medio', lambda m: str(int(m.group(1))) + '.5', msg_ac)
        msg_ac = msg_ac.replace('medio kilo', '0.5').replace('kilo y medio', '1.5')
        # Buscar cantidad: "2-1/2", "2.5", "4", etc.
        # Detectar "1/2 kg" o "medio" antes del regex numerico
        if _re_ac.search(r'(?:^|\s)(?:1/2|medio)\s*(?:kilo[s]?|kg)?\s*(?:de\s+)?acronal|acronal\s*(?:1/2|medio)', msg_ac):
            acronal_calculado = "ACRONAL PRECALCULADO: 0.5kg = $7,000 (precio especial). USA cantidad=0.5, total=7000 EXACTAMENTE."
            continue_ac = False
        else:
            continue_ac = True
        m_ac = _re_ac.search(r'([\d]+(?:[.,]\d+)?(?:-1/2|-1/4)?)\s*(?:kilo[s]?|kg)?\s*(?:de\s+)?acronal|acronal\s*(?:kilo[s]?|kg)?\s*([\d]+(?:[.,]\d+)?(?:-1/2|-1/4)?)', msg_ac) if continue_ac else None
        if m_ac:
            raw = (m_ac.group(1) or m_ac.group(2) or '').strip()
            raw = raw.replace(',', '.').replace('-1/2', '.5').replace('-1/4', '.25')
            try:
                kg = float(raw)
                enteros = int(kg)
                medio   = kg - enteros
                if abs(medio - 0.5) < 0.01:
                    total_ac = enteros * 13000 + 7000
                elif abs(medio - 0.25) < 0.01:
                    total_ac = enteros * 13000 + 3500  # 1/4 kg proporcional
                else:
                    total_ac = round(kg * 13000)
                acronal_calculado = (
                    f"ACRONAL PRECALCULADO: {kg}kg = ${total_ac:,} "
                    f"({'%d*13000+7000' % enteros if abs(medio-0.5)<0.01 else '%g*13000' % kg}). "
                    f"CRITICO: USA cantidad={kg}, total={total_ac} SIN MODIFICAR. PROHIBIDO recalcular."
                )
            except Exception:
                pass

    # ── Thinner: precalcular fraccion en Python ──
    thinner_calculado = ""
    if "thinner" in msg_l:
        tabla_thinner = {3000:"1/12",4000:"1/10",5000:"1/8",6000:"1/6",8000:"1/4",
                         10000:"1/3",13000:"1/2",16000:"5/9",20000:"3/4",26000:"1 galon"}
        dec_thinner   = {3000:1/12,4000:0.1,5000:0.125,6000:1/6,8000:0.25,
                         10000:1/3,13000:0.5,16000:5/9,20000:0.75,26000:1.0}
        import re as _re
        m = _re.search(r'(\d[\d\.]*)\s*(?:de\s+)?thinner|thinner\s+(\d[\d\.]*)', msg_l)
        if m:
            precio_t = int(float(m.group(1) or m.group(2)))
            if precio_t in tabla_thinner:
                frac_t = tabla_thinner[precio_t]
                dec_t  = dec_thinner[precio_t]
                thinner_calculado = (
                    f"THINNER PRECALCULADO: ${precio_t:,} de thinner = {frac_t} galon "
                    f"(cantidad={dec_t:.4f}, total={precio_t}). USA EXACTAMENTE estos valores."
                )

    # ── Tornillos drywall: precalcular precio correcto ──
    tornillo_calculado = ""
    if "drywall" in msg_l or "tornillo" in msg_l:
        tabla_drywall = {
            "6x1/2":(25,25),"6x3/4":(58,30),"6x1":(38,35),"6x1-1/4":(42,40),
            "6x1-1/2":(58,55),"6x2":(67,60),"6x2-1/2":(75,70),"6x3":(83,80),
            "8x3/4":(33,30),"8x1":(38,35),"8x1-1/2":(58,55),"8x2":(67,60),"8x3":(83,80),
            "10x1":(83,70),"10x1-1/2":(125,100),"10x2":(150,120),"10x2-1/2":(167,160),
            "10x3":(167,160),"10x3-1/2":(208,200),"10x4":(208,200),
        }
        voz_medida = [
            ("3 y medio","3-1/2"),("3 y media","3-1/2"),("3½","3-1/2"),
            ("2 y medio","2-1/2"),("2 y media","2-1/2"),
            ("1 y medio","1-1/2"),("1 y media","1-1/2"),("1 y cuarto","1-1/4"),
        ]
        import re as _re
        # Normalizar voz a fraccion
        msg_norm = msg_l
        for voz, frac in voz_medida:
            msg_norm = msg_norm.replace(voz, frac)
        m = _re.search(r'(\d+)\s+tornillo[s]?\s+drywall\s+(\d+)\s+[xXpor]+\s+([\d\-/½]+)', msg_norm)
        if m:
            cant   = int(m.group(1))
            cal    = m.group(2)
            medida = m.group(3).strip()
            key    = f"{cal}x{medida}"
            if key in tabla_drywall:
                p1, p2 = tabla_drywall[key]
                precio_u = p1 if cant < 50 else p2
                total_t  = cant * precio_u
                tornillo_calculado = (
                    f"TORNILLO PRECALCULADO: {cant} TORNILLO DRYWALL {cal.upper()}X{medida.upper()} "
                    f"({'<' if cant < 50 else '>='} 50 uds → ${precio_u}/u) = total {total_t}. "
                    f"USA EXACTAMENTE estos valores."
                )

    # "DATOS HISTORICOS" solo se incluye cuando hay datos reales — no enviar "(no cargado)" innecesariamente
    datos_historicos_item = f"DATOS HISTORICOS:\n{datos_texto}" if datos_texto != "(no cargado)" else ""

    # Precios modificados manualmente — override del cache estático
    precios_modificados_texto = ""
    _pm = memoria.get("precios_modificados", {})
    if _pm and palabras_clave:
        overrides = []
        for clave_pm, val in _pm.items():
            if any(p in clave_pm for p in palabras_clave):
                if isinstance(val, dict):
                    for k, v in val.items():
                        frac = k.replace("fraccion_", "")
                        overrides.append(f"{clave_pm} {frac}={v}")
                else:
                    overrides.append(f"{clave_pm}={val}")
        if overrides:
            precios_modificados_texto = "PRECIOS ACTUALIZADOS (usar estos, ignorar el catalogo):\n" + "\n".join(overrides)

    partes = [
        p for p in [
            precios_modificados_texto,
            info_fracciones_extra,
            acronal_calculado,
            thinner_calculado,
            tornillo_calculado,
            info_candidatos_extra,
            clientes_recientes_texto,
            clientes_texto,
            f"VENTAS MES:{resumen_texto}",
            datos_historicos_item,
            inventario_texto,
            caja_texto,
            gastos_texto,
            aviso_drive,
            f"Vendedor:{nombre_usuario}",
        ] if p
    ]
    return "\n\n".join(partes)


# ─────────────────────────────────────────────
# FUNCIÓN AUXILIAR: calcular historial adaptativo
# ─────────────────────────────────────────────

def _calcular_historial(mensaje: str) -> int:
    """
    Determina cuántos mensajes de historial enviar según el contexto.
    OPTIMIZACIÓN: ventas simples solo necesitan 1 mensaje, ahorrando ~100 tokens.
    """
    msg_l = mensaje.lower()
    
    # Necesita contexto completo (cliente, correcciones, fiados)
    if any(k in msg_l for k in ("cliente", "fiado", "para ", "a nombre", 
                                 "corrig", "modific", "error", "equivoque",
                                 "cambia", "quita", "agrega")):
        return 4
    
    # Análisis, reportes o consultas complejas
    _kw_contexto = {"cuanto", "vendimos", "reporte", "analiz", "resumen", "estadistica",
                    "inventario", "grafica", "top", "mas vendido", "caja", "gasto"}
    if any(k in msg_l for k in _kw_contexto):
        return 4
    
    # Multi-producto (comas o saltos de línea)
    if "," in mensaje or mensaje.count("\n") > 0:
        return 2
    
    # Venta simple: solo el mensaje actual basta
    return 1


# ─────────────────────────────────────────────
# LLAMADA A CLAUDE CON PROMPT CACHING
# ─────────────────────────────────────────────

async def procesar_con_claude(mensaje_usuario: str, nombre_usuario: str, historial_chat: list) -> str:
    mensaje_usuario = aplicar_alias_ferreteria(mensaje_usuario)
    memoria        = cargar_memoria()
    parte_estatica = _construir_parte_estatica(memoria)
    parte_dinamica = _construir_parte_dinamica(mensaje_usuario, nombre_usuario, memoria)
  
    _modo = "MATCH+SIMPLE-CAT 💡"  # fracciones en MATCH, precio_unidad en estático

    # Historial adaptativo: usa _calcular_historial para determinar cuántos mensajes
    _n_hist = _calcular_historial(mensaje_usuario)

    messages = []
    for msg in historial_chat[-_n_hist:]:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            messages.append({"role": str(msg["role"]), "content": str(msg["content"])})
    messages.append({"role": "user", "content": str(mensaje_usuario)})

    # max_tokens adaptativo por tipo de mensaje:
    # - Venta simple (1 producto, sin comas ni saltos): solo JSON → 400 tok
    # - Venta multi-producto: JSON × N productos + posible texto → 250 × lineas
    # - Consulta/reporte/modificacion: respuesta larga → 2000 mínimo
    _kw_reporte = {"cuanto","vendimos","reporte","analiz","resumen","estadistica",
                   "grafica","top","mas vendido","gasto","caja","inventario"}
    _kw_edicion = {"modificar","corregir","cambia","quita","agrega","error",
                   "equivoque","fiado","debe","abono","borrar","eliminar"}
    num_lineas = mensaje_usuario.count("\n") + mensaje_usuario.count(",") + 1
    _msg_low   = mensaje_usuario.lower()
    if any(p in _msg_low for p in _kw_reporte):
        max_tokens = 2000          # reportes necesitan espacio
    elif any(p in _msg_low for p in _kw_edicion):
        max_tokens = 1200          # ediciones: algo de texto + JSON
    elif num_lineas == 1 and "," not in mensaje_usuario:
        max_tokens = 450           # venta simple: solo JSON, ~150 tok reales
    else:
        max_tokens = min(3000, max(800, num_lineas * 220))  # multi-producto

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

    # ── Log de uso de tokens y cache ──
    uso = respuesta.usage
    cache_read    = getattr(uso, "cache_read_input_tokens",    0) or 0
    cache_created = getattr(uso, "cache_creation_input_tokens", 0) or 0
    input_normal  = getattr(uso, "input_tokens",               0) or 0
    output_tokens = getattr(uso, "output_tokens",              0) or 0

    if cache_read > 0 or cache_created > 0:
        costo_input   = (input_normal  / 1_000_000) * 1.00
        costo_cached  = (cache_read    / 1_000_000) * 0.10
        costo_created = (cache_created / 1_000_000) * 1.25
        costo_output  = (output_tokens / 1_000_000) * 5.00
        costo_total   = costo_input + costo_cached + costo_created + costo_output
        logging.getLogger("ferrebot.cache").info(
            f"[CACHE] ✅ hit={cache_read} tok | created={cache_created} tok | "
            f"input={input_normal} tok | output={output_tokens} tok | "
            f"costo≈${costo_total:.5f}"
        )
    else:
        logging.getLogger("ferrebot.cache").warning(
            f"[CACHE] ⚠️ SIN CACHE — input={input_normal} tok | output={output_tokens} tok"
        )

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
                # Verificar que algún candidato coincida con al menos 2 palabras
                palabras_buscadas = set(_normalizar(nombre_cliente).split())
                match_exacto = False
                for c in candidatos:
                    palabras_encontradas = set(_normalizar(c.get("Nombre tercero", "")).split())
                    coincidencias = palabras_buscadas & palabras_encontradas
                    if len(coincidencias) >= 2 or (len(palabras_buscadas) == 1 and coincidencias):
                        match_exacto = True
                        break
                if not match_exacto:
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
