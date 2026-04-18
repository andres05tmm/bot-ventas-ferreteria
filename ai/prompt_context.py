"""
ai/prompt_context.py — Contexto de negocio para el system prompt.

Carga y formatea datos dinámicos que cambian entre mensajes:
  - Resumen de ventas del mes e histórico
  - Clientes recientes y búsqueda de cliente en el mensaje
  - Inventario, caja, gastos del día
  - Cuentas por pagar (facturas de proveedores)

Retorna strings ya formateados listos para insertar en el prompt.

TODOS los imports de ai, memoria y db son LAZY (dentro de función).
Esto es obligatorio — evita ciclos ai/__init__.py ↔ ai/prompt_context.py.
"""

# -- stdlib --
import re
import json
import logging

# -- propios --
from utils import _normalizar

logger = logging.getLogger("ferrebot.ai.prompt_context")


def construir_seccion_ventas(mensaje_usuario: str, dashboard_mode: bool = False) -> tuple[str, str]:
    """
    Retorna (resumen_texto, datos_historicos_item).

    resumen_texto:        ej. "VENTAS MES:$1.200.000 en 45 ventas este mes"
    datos_historicos_item: bloque DATOS HISTORICOS listo para el prompt (o "" si no aplica)
    """
    # Lazy imports — evita ciclo con ai/__init__.py
    from ai import _pg_resumen_ventas, _pg_todos_los_datos

    # ── Resumen de ventas ──
    resumen               = _pg_resumen_ventas()
    resumen_excel_total   = resumen["total"]      if resumen else 0
    resumen_excel_cantidad = resumen["num_ventas"] if resumen else 0

    total_mes    = resumen_excel_total
    cantidad_mes = resumen_excel_cantidad

    resumen_raw = (
        f"${total_mes:,.0f} en {cantidad_mes} ventas este mes"
    ) if cantidad_mes > 0 else "Sin ventas este mes"
    resumen_texto = f"VENTAS MES:{resumen_raw}"

    # ── Datos históricos ──────────────────────────────────────────────────────
    # Dashboard: ampliar keywords y cargar más registros para análisis completo.
    # Telegram: solo cuando hay palabras clave explícitas (optimización de tokens).
    _palabras_analisis = {"cuanto", "vendimos", "reporte", "analiz", "total",
                          "resumen", "estadistica", "top", "mas vendido",
                          "dia", "semana", "mes", "ayer", "hoy", "vendio",
                          "gano", "ingreso", "mejor", "peor", "promedio",
                          "historico", "registro", "cuantas", "cuantos"}
    _es_analisis = any(p in mensaje_usuario.lower() for p in _palabras_analisis)
    _es_dash = dashboard_mode  # activado desde procesar_con_claude/_stream cuando viene del dashboard
    if _es_analisis or _es_dash:
        try:
            _limite     = 300 if _es_dash else 200
            todos       = _pg_todos_los_datos(_limite)
            datos_texto = json.dumps(todos, ensure_ascii=False, default=str) if todos else "Sin datos aun"
        except Exception:
            datos_texto = "Sin datos aun"
    else:
        datos_texto = "(no cargado)"

    # "DATOS HISTORICOS" solo se incluye cuando hay datos reales
    datos_historicos_item = f"DATOS HISTORICOS:\n{datos_texto}" if datos_texto != "(no cargado)" else ""

    return resumen_texto, datos_historicos_item


def construir_seccion_clientes(mensaje_usuario: str) -> str:
    """
    Retorna texto con clientes recientes y cliente encontrado en el mensaje.
    Devuelve string vacío si no hay nada relevante.
    """
    # Lazy imports — evita ciclo con ai/__init__.py
    from ai import _pg_clientes_recientes, _pg_buscar_cliente

    stopwords = {"que", "del", "los", "las", "una", "uno", "con", "por", "para", "como",
                 "fue", "son", "precio", "vale", "cuesta", "cuanto", "la", "el", "de", "en",
                 "galon", "galones", "litro", "litros", "kilo", "kilos", "metro", "metros",
                 "pulgada", "pulgadas", "unidad", "unidades",
                 "botella", "botellas",
                 "vendi", "vendo", "vendimos", "dame", "quiero", "necesito", "par",
                 "y", "un", "cuarto", "medio", "media", "octavo", "tres"}

    partes = []

    # ── Clientes recientes ──
    palabras_recientes = ["ultimo", "ultimos", "reciente", "recientes", "nuevo", "nuevos",
                          "anadido", "anadidos", "agregado", "agregados", "registrado", "registrados"]
    _msg_norm = _normalizar(mensaje_usuario)
    if any(p in _msg_norm for p in palabras_recientes) and "cliente" in _msg_norm:
        try:
            recientes = _pg_clientes_recientes(5)
            if recientes:
                lineas = []
                for c in recientes:
                    nombre = c.get("Nombre tercero", "")
                    id_c   = c.get("Identificacion", "")
                    tipo   = c.get("Tipo de identificacion", "")
                    fecha  = c.get("Fecha registro", "Sin fecha")
                    lineas.append(f"  - {nombre} ({tipo}: {id_c}) — registrado: {fecha}")
                partes.append(
                    "ULTIMOS 5 CLIENTES REGISTRADOS EN EL SISTEMA:\n" + "\n".join(lineas)
                )
        except Exception as e:
            print(f"Error clientes recientes: {e}")

    # ── Búsqueda de cliente si el mensaje lo indica ──
    _indicadores_cliente = [
        "cliente", "para ", "de parte", "a nombre", "factura", "facturar",
        "a credito", "fiado", "cuenta de",
    ]
    _menciona_cliente = any(ind in mensaje_usuario.lower() for ind in _indicadores_cliente)
    if _menciona_cliente:
        try:
            # Extraer nombre despues de "para", "a nombre de", "de parte de", etc.
            _match_nombre = re.search(
                r'(?:para|a nombre de|de parte de|cuenta de)\s+([A-Za-záéíóúÁÉÍÓÚñÑ]+(?:\s+[A-Za-záéíóúÁÉÍÓÚñÑ]+){0,3})',
                mensaje_usuario, re.IGNORECASE
            )
            if _match_nombre:
                termino_cliente = _match_nombre.group(1).strip()
            else:
                palabras_cliente = [p for p in mensaje_usuario.lower().split()
                                    if len(p) > 3 and p not in stopwords]
                termino_cliente = " ".join(palabras_cliente[:4]) if palabras_cliente else ""
            if termino_cliente:
                cliente_unico, candidatos_cli = _pg_buscar_cliente(termino_cliente)

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
                        partes.append(
                            f"CLIENTE ENCONTRADO EN EL SISTEMA (usar este directamente):\n"
                            f"  - {nombre} ({tipo}: {id_c})"
                        )
                    else:
                        # Coincidencia parcial — marcar para preguntar ANTES de confirmar
                        partes.append(
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
                    partes.append(
                        "MULTIPLES CLIENTES ENCONTRADOS — pregunta al usuario cual es:\n"
                        + "\n".join(lineas_cli)
                        + "\nEjemplo: 'Te refieres a NOMBRE1 (CC: 123) o NOMBRE2 (CC: 456)?'"
                    )
        except Exception:
            pass

    return "\n\n".join(partes)


def construir_contexto_turno() -> str:
    """
    Retorna contexto situacional que ayuda a Claude a ser proactivo sin que
    nadie pregunte: hora del día, día de semana y últimas ventas registradas hoy.

    Se llama una vez por mensaje, siempre — no depende de keywords.
    """
    # Lazy imports — evita ciclo con ai/__init__.py
    from config import COLOMBIA_TZ
    from datetime import datetime as _dt
    import db as _db

    partes = []

    # ── Momento del día ───────────────────────────────────────────────────────
    ahora    = _dt.now(COLOMBIA_TZ)
    hora     = ahora.hour
    periodo  = "mañana" if hora < 12 else ("tarde" if hora < 18 else "noche")
    _DIAS    = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    dia_sem  = _DIAS[ahora.weekday()]
    partes.append(
        f"MOMENTO: {dia_sem} en la {periodo} ({ahora.strftime('%H:%M')} hora Colombia)"
    )

    # ── Últimas 3 ventas del día (contexto de qué se está vendiendo) ──────────
    try:
        ultimas = _db.query_all(
            """
            SELECT v.consecutivo,
                   v.total,
                   v.metodo_pago,
                   STRING_AGG(d.nombre_producto, ', ' ORDER BY d.id) AS productos
            FROM ventas v
            LEFT JOIN ventas_detalle d ON d.venta_id = v.id
            WHERE DATE(v.fecha AT TIME ZONE 'America/Bogota') = CURRENT_DATE
              AND v.estado = 'registrada'
            GROUP BY v.id, v.consecutivo, v.total, v.metodo_pago
            ORDER BY v.id DESC
            LIMIT 3
            """,
            [],
        )
        if ultimas:
            lineas = [
                f"  #{r['consecutivo']}: {r.get('productos') or 'sin detalle'} — "
                f"${r['total']:,.0f} ({r.get('metodo_pago') or 'sin método'})"
                for r in ultimas
            ]
            partes.append("ÚLTIMAS VENTAS HOY:\n" + "\n".join(lineas))
    except Exception:
        pass

    return "\n\n".join(partes)


def construir_seccion_memoria_entidades(mensaje_usuario: str, vendedor: str | None = None) -> str:
    """
    Inyecta notas vigentes de memoria de entidad (productos + vendedor) cuando
    el mensaje del usuario menciona una entidad conocida.

    Estrategia (cero tokens si no hay match):
      1. Productos → fuzzy match contra el catálogo en RAM (cero costo, ya cargado).
         Para cada producto detectado, traer máx 2 notas vigentes.
      2. Vendedor activo → siempre traer máx 2 notas (el vendedor es conocido).
      3. Cap total: máx 4 productos + vendedor → ~6 notas → ~600 chars en prompt.

    Las notas las genera el compresor nocturno (Capa 4). Si la tabla está vacía
    o la DB falla, retorna "" sin tocar el prompt.

    Returns:
        Bloque "NOTAS DE MEMORIA — ..." listo para insertar en el prompt,
        o "" si no hay matches.
    """
    # Lazy imports — evita ciclo con services y cargar el módulo si no se usa
    try:
        from services.memoria_entidad_service import (
            obtener_notas_producto,
            obtener_notas_vendedor,
            formatear_para_prompt,
        )
        from memoria import cargar_memoria
    except Exception as e:
        logger.debug("memoria_entidad no disponible: %s", e)
        return ""

    if not mensaje_usuario:
        return ""

    bloques: list[str] = []
    msg_norm = _normalizar(mensaje_usuario)

    # ── 1. Productos mencionados en el mensaje ──────────────────────────────
    try:
        mem = cargar_memoria() or {}
        catalogo = mem.get("catalogo", {}) or {}
        # Match barato: si alguna palabra del nombre del producto aparece en el msg
        # (cap de 4 productos para no inflar el prompt)
        productos_detectados: list[str] = []
        for prod in catalogo.values():
            nombre = (prod.get("nombre") or "").strip()
            if not nombre:
                continue
            nombre_norm = _normalizar(nombre)
            # palabras significativas del nombre (>3 chars) que aparecen en msg
            palabras = [p for p in nombre_norm.split() if len(p) > 3]
            if palabras and any(p in msg_norm for p in palabras):
                productos_detectados.append(nombre)
                if len(productos_detectados) >= 4:
                    break
        for nombre in productos_detectados:
            notas = obtener_notas_producto(nombre, limit=2)
            txt = formatear_para_prompt(notas, nombre)
            if txt:
                bloques.append(txt)
    except Exception as e:
        logger.debug("memoria_entidad productos falló: %s", e)

    # ── 2. Notas del vendedor activo ────────────────────────────────────────
    if vendedor:
        try:
            notas_v = obtener_notas_vendedor(vendedor, limit=2)
            txt = formatear_para_prompt(notas_v, f"vendedor {vendedor}")
            if txt:
                bloques.append(txt)
        except Exception as e:
            logger.debug("memoria_entidad vendedor falló: %s", e)

    return "\n\n".join(bloques)


def construir_seccion_operaciones(mensaje_usuario: str) -> str:
    """
    Retorna texto con inventario bajo stock, caja del día, gastos y facturas pendientes.
    Devuelve string vacío si ninguna keyword está en el mensaje.
    """
    # Lazy imports — evita ciclo con memoria
    from memoria import cargar_inventario, cargar_gastos_hoy, obtener_resumen_caja

    partes = []
    msg_lower = mensaje_usuario.lower()

    # ── Inventario ──
    palabras_inv = ["inventario", "stock", "queda", "quedan", "hay", "cuanto hay", "existencia"]
    if any(p in msg_lower for p in palabras_inv):
        partes.append(
            f"INVENTARIO ACTUAL:\n{json.dumps(cargar_inventario(), ensure_ascii=False)}"
        )

    # ── Caja y gastos ──
    palabras_caja_kw = ["caja", "gasto", "gastos", "apertura", "cierre", "efectivo", "cuanto hay en caja"]
    if any(p in msg_lower for p in palabras_caja_kw):
        partes.append(f"ESTADO CAJA:\n{obtener_resumen_caja()}")
        partes.append(
            f"GASTOS DE HOY:\n{json.dumps(cargar_gastos_hoy(), ensure_ascii=False, default=str)}"
        )

    # ── Cuentas por pagar (facturas de proveedores) ───────────────────────────
    _kw_proveedores = ["deuda", "debo", "factura", "proveedor", "abono a", "le pague",
                       "pague a", "cuanto le debo", "fac-", "pendiente", "llego mercancia",
                       "llegó", "trajo"]
    if any(k in msg_lower for k in _kw_proveedores):
        try:
            from memoria import listar_facturas as _lf
            _facturas_pend = _lf(solo_pendientes=True)
            if _facturas_pend:
                _lineas_prov = []
                _total_deuda = 0.0
                for _f in _facturas_pend[:10]:  # máx 10 para no inflar el prompt
                    _lineas_prov.append(
                        f"{_f['id']} | {_f['proveedor']} | Total:{_f['total']:,.0f} | "
                        f"Pagado:{_f['pagado']:,.0f} | Pendiente:{_f['pendiente']:,.0f} | "
                        f"Fecha:{_f['fecha']} | Estado:{_f['estado']}"
                    )
                    _total_deuda += _f["pendiente"]
                partes.append(
                    "CUENTAS_POR_PAGAR (deuda total: ${:,.0f}):\n".format(_total_deuda)
                    + "\n".join(_lineas_prov)
                )
        except Exception:
            pass

    return "\n\n".join(partes)
