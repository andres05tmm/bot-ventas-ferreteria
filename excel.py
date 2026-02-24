"""
Operaciones sobre el archivo Excel de ventas (openpyxl).
El Excel es la fuente de verdad historica; el Sheets es la pizarra del dia.
"""

import asyncio
import os
import unicodedata
from datetime import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

import config
from utils import convertir_fraccion_a_decimal, decimal_a_fraccion_legible, obtener_nombre_hoja


# ─────────────────────────────────────────────
# UTILIDAD: normalizar texto para búsqueda
# ─────────────────────────────────────────────

def _normalizar(texto: str) -> str:
    """
    Convierte a minúsculas y elimina tildes/diacríticos.
    Permite comparar 'Andrés' con 'andres', 'MÁLAGA' con 'malaga', etc.
    """
    return unicodedata.normalize("NFD", str(texto).lower()).encode("ascii", "ignore").decode()


# ─────────────────────────────────────────────
# ESTRUCTURA INTERNA
# ─────────────────────────────────────────────

def inicializar_hoja(ws):
    """Crea la estructura real del Excel: titulo en fila 1, encabezados en fila 2."""
    if ws.max_row > 1:
        return

    num_cols = 13
    ws.merge_cells(f"A1:{get_column_letter(num_cols)}1")
    celda = ws.cell(row=1, column=1, value="DETALLE DE VENTAS")
    celda.font      = Font(bold=True, color="FFFFFF", size=13)
    celda.fill      = PatternFill("solid", fgColor="1A56DB")
    celda.alignment = Alignment(horizontal="center")

    encabezados = [
        "FECHA", "HORA", "ID CLIENTE", "CLIENTE",
        "Código del Producto", "PRODUCTO", "CANTIDAD",
        "VALOR UNITARIO", "TOTAL", "CONSECUTIVO DE VENTA",
        "ALIAS", "VENDEDOR", "METODO DE PAGO",
    ]
    for col, titulo in enumerate(encabezados, 1):
        celda       = ws.cell(row=2, column=col, value=titulo)
        celda.font  = Font(bold=True, color="FFFFFF", size=11)
        celda.fill  = PatternFill("solid", fgColor="1A56DB")
        celda.alignment = Alignment(horizontal="center")

    anchos = [12, 8, 14, 28, 18, 28, 10, 15, 14, 18, 10, 15, 16]
    for col, ancho in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(col)].width = ancho


def obtener_o_crear_hoja(wb, nombre_hoja: str):
    if nombre_hoja in wb.sheetnames:
        return wb[nombre_hoja]
    ws = wb.create_sheet(title=nombre_hoja)
    inicializar_hoja(ws)
    return ws


def inicializar_excel():
    """Crea ventas.xlsx si no existe."""
    if not os.path.exists(config.EXCEL_FILE):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = obtener_nombre_hoja()
        inicializar_hoja(ws)
        wb.save(config.EXCEL_FILE)
        from drive import subir_a_drive
        subir_a_drive(config.EXCEL_FILE)
        print("✅ Archivo Excel creado y subido a Drive.")


def detectar_columnas(ws) -> dict:
    """
    Lee los encabezados desde EXCEL_FILA_HEADERS.
    Retorna {nombre_lower: numero_columna}.
    """
    encabezados = {}
    for col in range(1, ws.max_column + 1):
        valor = ws.cell(row=config.EXCEL_FILA_HEADERS, column=col).value
        if valor:
            encabezados[str(valor).lower().strip()] = col
    return encabezados


def _col_para(cols: dict, *claves_posibles) -> int | None:
    """
    Busca la columna cuyo encabezado coincida con alguna clave.
    Primero exacto, luego containment (solo para claves de mas de 1 caracter).
    """
    for clave in claves_posibles:
        if clave in cols:
            return cols[clave]
    for clave in claves_posibles:
        for enc, num in cols.items():
            if len(enc) > 1 and len(clave) > 1 and (clave in enc or enc in clave):
                return num
    return None


# ─────────────────────────────────────────────
# CONSECUTIVO
# ─────────────────────────────────────────────

def obtener_siguiente_consecutivo() -> int:
    hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")

    if config.SHEETS_ID and config.SHEETS_DISPONIBLE:
        try:
            from sheets import sheets_leer_ventas_del_dia
            ventas_hoy = sheets_leer_ventas_del_dia()
            if ventas_hoy:
                numeros = []
                for v in ventas_hoy:
                    try:
                        numeros.append(int(float(str(v.get("num", 0)))))
                    except (TypeError, ValueError):
                        pass
                if numeros:
                    return max(numeros) + 1
            return 1
        except Exception:
            pass

    if not os.path.exists(config.EXCEL_FILE):
        return 1
    try:
        wb          = openpyxl.load_workbook(config.EXCEL_FILE, read_only=True)
        nombre_hoja = obtener_nombre_hoja()
        max_hoy     = 0

        if nombre_hoja in wb.sheetnames:
            ws   = wb[nombre_hoja]
            cols = {}
            for col in range(1, ws.max_column + 1):
                valor = ws.cell(row=config.EXCEL_FILA_HEADERS, column=col).value
                if valor:
                    cols[str(valor).lower().strip()] = col

            col_fecha  = next((v for k, v in cols.items() if "fecha"       in k), None)
            col_consec = next((v for k, v in cols.items() if "consecutivo" in k), None)

            if col_fecha and col_consec:
                for fila in ws.iter_rows(min_row=config.EXCEL_FILA_DATOS, values_only=True):
                    if str(fila[col_fecha - 1] or "")[:10] != hoy:
                        continue
                    try:
                        num = int(float(str(fila[col_consec - 1])))
                        if num > max_hoy:
                            max_hoy = num
                    except (TypeError, ValueError):
                        pass

        wb.close()
        return max_hoy + 1
    except Exception as e:
        print(f"Error leyendo consecutivo del Excel: {e}")
        return 1


def obtener_consecutivo_actual() -> int:
    return obtener_siguiente_consecutivo() - 1


# ─────────────────────────────────────────────
# CLIENTES (dentro del Excel)
# ─────────────────────────────────────────────

def cargar_clientes() -> list:
    if not os.path.exists(config.EXCEL_FILE):
        return []
    try:
        wb = openpyxl.load_workbook(config.EXCEL_FILE)
        if "Clientes" not in wb.sheetnames:
            return []
        ws      = wb["Clientes"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        clientes = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            cliente = {}
            for i, h in enumerate(headers):
                if h:
                    cliente[str(h).strip()] = row[i] if i < len(row) else None
            clientes.append(cliente)
        return clientes
    except Exception as e:
        print(f"Error cargando clientes: {e}")
        return []


def buscar_clientes_multiples(termino: str, limite: int = 5) -> list:
    """
    Busca clientes cuyo nombre contenga cualquiera de las palabras del termino.
    - Insensible a tildes: 'andres' encuentra 'ANDRÉS'
    - Busqueda por palabras sueltas: 'malo' encuentra 'ANDRÉS FELIPE MALO'
    - Retorna hasta `limite` resultados ordenados por longitud de nombre (mas especifico primero)
    """
    clientes     = cargar_clientes()
    termino_norm = _normalizar(termino)
    # Palabras de mas de 2 letras (evita articulos como "de", "el")
    palabras     = [p for p in termino_norm.split() if len(p) > 2]

    if not palabras:
        return []

    resultado = []
    for c in clientes:
        nombre_norm = _normalizar(c.get("Nombre tercero", "") or "")
        # Matchea si AL MENOS UNA palabra del termino aparece en el nombre
        if any(p in nombre_norm for p in palabras):
            resultado.append(c)

    # Ordenar: nombres mas cortos primero (mas especificos)
    resultado.sort(key=lambda x: len(str(x.get("Nombre tercero", ""))))
    return resultado[:limite]


def buscar_cliente(termino: str) -> dict | None:
    """
    Busca UN cliente unico.
    - Coincidencia exacta por numero de identificacion
    - Luego busqueda flexible por nombre (sin tildes, palabras sueltas)
    - Si hay exactamente 1 resultado: lo retorna
    - Si hay varios: retorna None (el llamador debe manejar la ambiguedad)
    """
    clientes     = cargar_clientes()
    termino_norm = _normalizar(termino)

    # 1. Coincidencia exacta por identificacion
    for c in clientes:
        if _normalizar(c.get("Identificación", "") or "") == termino_norm:
            return c

    # 2. Busqueda flexible por nombre
    palabras = [p for p in termino_norm.split() if len(p) > 2]
    if not palabras:
        return None

    coincidencias = []
    for c in clientes:
        nombre_norm = _normalizar(c.get("Nombre tercero", "") or "")
        if any(p in nombre_norm for p in palabras):
            coincidencias.append(c)

    if len(coincidencias) == 1:
        return coincidencias[0]

    # Multiples resultados — retornar None para que el bot pregunte
    # (la desambiguacion se maneja en buscar_clientes_multiples + ai.py)
    return None


def buscar_cliente_con_resultado(termino: str) -> tuple[dict | None, list]:
    """
    Version extendida de buscar_cliente que ademas retorna todos los candidatos.
    Retorna: (cliente_unico_o_None, lista_de_candidatos)

    Uso en ai.py para incluir en el system prompt:
    - Si hay 1 candidato: cliente encontrado directamente
    - Si hay varios: el bot pregunta al usuario cual es
    - Si hay 0: no existe, ofrecer crear
    """
    clientes     = cargar_clientes()
    termino_norm = _normalizar(termino)

    # 1. Coincidencia exacta por identificacion
    for c in clientes:
        if _normalizar(c.get("Identificación", "") or "") == termino_norm:
            return c, [c]

    # 2. Busqueda flexible por nombre
    palabras = [p for p in termino_norm.split() if len(p) > 2]
    if not palabras:
        return None, []

    candidatos = []
    for c in clientes:
        nombre_norm = _normalizar(c.get("Nombre tercero", "") or "")
        if any(p in nombre_norm for p in palabras):
            candidatos.append(c)

    candidatos.sort(key=lambda x: len(str(x.get("Nombre tercero", ""))))

    if len(candidatos) == 1:
        return candidatos[0], candidatos
    return None, candidatos


def obtener_clientes_recientes(limite: int = 5) -> list:
    """
    Retorna los últimos N clientes registrados, ordenados por Fecha registro (más reciente primero).
    Clientes sin fecha quedan al final.
    """
    clientes = cargar_clientes()
    def _fecha(c):
        f = c.get("Fecha registro") or ""
        return str(f)
    con_fecha    = [c for c in clientes if c.get("Fecha registro")]
    sin_fecha    = [c for c in clientes if not c.get("Fecha registro")]
    con_fecha.sort(key=_fecha, reverse=True)
    return (con_fecha + sin_fecha)[:limite]


def obtener_nombre_id_cliente(termino: str) -> tuple[str, str]:
    """
    Busca un cliente por nombre o identificación y retorna (identificacion, nombre).
    Si no lo encuentra, retorna ("CF", "Consumidor Final").
    """
    cliente = buscar_cliente(termino)
    if cliente:
        id_c = cliente.get("Identificación") or "CF"
        nombre_c = cliente.get("Nombre tercero") or "Consumidor Final"
        return str(id_c), str(nombre_c)
    return "CF", "Consumidor Final"


def guardar_cliente_nuevo(nombre, tipo_id, identificacion, tipo_persona="Natural", correo="", telefono="", direccion="") -> bool:
    try:
        inicializar_excel()
        wb = openpyxl.load_workbook(config.EXCEL_FILE)
        if "Clientes" not in wb.sheetnames:
            ws_c = wb.create_sheet("Clientes")
            headers = [
                "Nombre tercero", "Es Juridica o Persona", "Tipo de identificación",
                "Identificación", "Digito verificación", "Correo electrónico",
                "Dirección", "Teléfono.", "Nombres contacto", "Fecha registro",
            ]
            for col, h in enumerate(headers, 1):
                celda      = ws_c.cell(row=1, column=col, value=h)
                celda.font = Font(bold=True, color="FFFFFF")
                celda.fill = PatternFill("solid", fgColor="1A56DB")
        else:
            ws_c = wb["Clientes"]

        fila = ws_c.max_row + 1
        ws_c.cell(row=fila, column=1, value=nombre.upper())
        ws_c.cell(row=fila, column=2, value=tipo_persona)
        ws_c.cell(row=fila, column=3, value=tipo_id)
        ws_c.cell(row=fila, column=4, value=identificacion)
        ws_c.cell(row=fila, column=5, value="0")
        ws_c.cell(row=fila, column=6, value=correo)
        ws_c.cell(row=fila, column=7, value=direccion or "No aplica")
        ws_c.cell(row=fila, column=8, value=telefono or "000-0000000-")
        ws_c.cell(row=fila, column=9, value=nombre.upper())
        from datetime import datetime
        ws_c.cell(row=fila, column=10, value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        wb.save(config.EXCEL_FILE)
        from drive import subir_a_drive
        subir_a_drive(config.EXCEL_FILE)
        return True
    except Exception as e:
        print(f"Error guardando cliente: {e}")
        return False


def borrar_cliente(termino: str) -> tuple[bool, str]:
    """
    Borra un cliente de la hoja Clientes por nombre o identificacion.
    Retorna (exito, mensaje).
    """
    try:
        inicializar_excel()
        wb = openpyxl.load_workbook(config.EXCEL_FILE)
        if "Clientes" not in wb.sheetnames:
            return False, "No hay clientes registrados."
        ws = wb["Clientes"]
        termino_norm = _normalizar(termino)
        fila_borrar = None
        nombre_borrado = None
        for fila in range(2, ws.max_row + 1):
            nombre = str(ws.cell(row=fila, column=1).value or "")
            id_val  = str(ws.cell(row=fila, column=4).value or "")
            if _normalizar(nombre) == termino_norm or _normalizar(id_val) == termino_norm:
                fila_borrar   = fila
                nombre_borrado = nombre
                break
            # Busqueda flexible por palabras
            palabras = [p for p in termino_norm.split() if len(p) > 2]
            if palabras and all(p in _normalizar(nombre) for p in palabras):
                fila_borrar   = fila
                nombre_borrado = nombre
                break
        if not fila_borrar:
            return False, f"No encontre un cliente que coincida con '{termino}'."
        ws.delete_rows(fila_borrar)
        wb.save(config.EXCEL_FILE)
        from drive import subir_a_drive
        subir_a_drive(config.EXCEL_FILE)
        return True, f"✅ Cliente '{nombre_borrado}' borrado del sistema."
    except Exception as e:
        print(f"Error borrando cliente: {e}")
        return False, "Hubo un error borrando el cliente."
    if not nombre_mencionado:
        return "CF", "Consumidor Final"
    cliente = buscar_cliente(nombre_mencionado)
    if cliente:
        id_c     = str(cliente.get("Identificación", "CF") or "CF").strip()
        nombre_c = str(cliente.get("Nombre tercero", "Consumidor Final") or "Consumidor Final").strip()
        return id_c, nombre_c
    return "CF", "Consumidor Final"


# ─────────────────────────────────────────────
# CRUD DE VENTAS
# ─────────────────────────────────────────────

_DATOS_A_COLS = {
    "fecha":                "fecha",
    "hora":                 "hora",
    "id cliente":           "id cliente",
    "cliente":              "cliente",
    "código del producto":  "código del producto",
    "producto":             "producto",
    "cantidad":             "cantidad",
    "valor unitario":       "valor unitario",
    "total":                "total",
    "subtotal":             "subtotal",
    "consecutivo de venta": "consecutivo de venta",
    "alias":                "alias",
    "vendedor":             "vendedor",
    "metodo de pago":       "metodo de pago",
}


def guardar_venta_excel(producto, cantidad, precio_unitario, total, vendedor,
                        observaciones="", cliente_nombre=None, cliente_id=None,
                        codigo_producto=None, consecutivo=None) -> int:
    from drive import subir_a_drive
    from sheets import sheets_agregar_venta
    from memoria import cargar_memoria

    inicializar_excel()
    wb           = openpyxl.load_workbook(config.EXCEL_FILE)
    nombre_hoja  = obtener_nombre_hoja()
    ws           = obtener_o_crear_hoja(wb, nombre_hoja)
    cols         = detectar_columnas(ws)

    fila       = max(ws.max_row + 1, config.EXCEL_FILA_DATOS)
    fecha_hoy  = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
    hora_ahora = datetime.now(config.COLOMBIA_TZ).strftime("%H:%M")
    num_fila   = fila - config.EXCEL_FILA_DATOS + 1

    consecutivo_final    = consecutivo if consecutivo is not None else obtener_consecutivo_actual()
    id_cliente_final     = cliente_id    or "CF"
    nombre_cliente_final = cliente_nombre or "Consumidor Final"

    cod_producto_final = codigo_producto or ""
    if not cod_producto_final:
        from memoria import buscar_producto_en_catalogo
        prod_encontrado = buscar_producto_en_catalogo(str(producto))
        if prod_encontrado:
            # Usar campo 'codigo' si existe, si no dejar vacio
            cod_producto_final = prod_encontrado.get("codigo", "")

    datos = {
        "fecha":                  fecha_hoy,
        "hora":                   hora_ahora,
        "id cliente":             id_cliente_final,
        "cliente":                nombre_cliente_final,
        "código del producto":    cod_producto_final,
        "producto":               str(producto),
        "cantidad":               cantidad,
        "valor unitario":         float(precio_unitario),
        "total":                  float(total),
        "subtotal":               float(total),
        "consecutivo de venta":   consecutivo_final,
        "alias":                  str(num_fila),
        "vendedor":               str(vendedor),
        "metodo de pago":         str(observaciones),
    }

    for nombre_col, num_col in cols.items():
        clave = nombre_col.lower().strip()
        if clave in datos:
            ws.cell(row=fila, column=num_col, value=datos[clave])
            continue
        for dato_key, dato_val in datos.items():
            if len(dato_key) > 5 and len(clave) > 5 and (dato_key in clave or clave in dato_key):
                ws.cell(row=fila, column=num_col, value=dato_val)
                break

    if consecutivo_final % 2 == 0:
        for col in range(1, ws.max_column + 1):
            ws.cell(row=fila, column=col).fill = PatternFill("solid", fgColor="EFF6FF")

    wb.save(config.EXCEL_FILE)
    subir_a_drive(config.EXCEL_FILE)

    sheets_agregar_venta(
        consecutivo_final, producto, cantidad, precio_unitario, total, vendedor, observaciones,
        id_cliente=id_cliente_final, nombre_cliente=nombre_cliente_final,
        codigo_producto=cod_producto_final, alias=str(num_fila)
    )

    return consecutivo_final


def borrar_venta_excel(numero_venta) -> tuple[bool, str]:
    from drive import subir_a_drive
    from sheets import sheets_borrar_fila

    inicializar_excel()
    wb          = openpyxl.load_workbook(config.EXCEL_FILE)
    nombre_hoja = obtener_nombre_hoja()
    if nombre_hoja not in wb.sheetnames:
        return False, "No hay ventas este mes."

    ws        = wb[nombre_hoja]
    cols      = detectar_columnas(ws)
    col_alias = cols.get(config.COL_ALIAS)

    for fila in range(config.EXCEL_FILA_DATOS, ws.max_row + 1):
        val = ws.cell(row=fila, column=col_alias).value if col_alias else None
        try:
            if val is not None and int(float(str(val))) == int(numero_venta):
                ws.delete_rows(fila)
                wb.save(config.EXCEL_FILE)
                subir_a_drive(config.EXCEL_FILE)
                sheets_borrar_fila(numero_venta)
                return True, f"✅ Venta #{numero_venta} borrada del Excel y del Sheets."
        except (ValueError, TypeError):
            pass

    return False, f"No encontre la venta #{numero_venta}."


def obtener_venta_por_numero(numero_venta) -> dict | None:
    inicializar_excel()
    wb          = openpyxl.load_workbook(config.EXCEL_FILE)
    nombre_hoja = obtener_nombre_hoja()
    if nombre_hoja not in wb.sheetnames:
        return None
    ws        = wb[nombre_hoja]
    cols      = detectar_columnas(ws)
    col_alias = cols.get(config.COL_ALIAS)
    for fila in range(config.EXCEL_FILA_DATOS, ws.max_row + 1):
        val = ws.cell(row=fila, column=col_alias).value if col_alias else None
        try:
            if val is not None and int(float(str(val))) == int(numero_venta):
                return {nombre: ws.cell(row=fila, column=num).value for nombre, num in cols.items()}
        except (ValueError, TypeError):
            pass
    return None


def obtener_ventas_recientes(limite: int = 10) -> list:
    inicializar_excel()
    wb          = openpyxl.load_workbook(config.EXCEL_FILE)
    nombre_hoja = obtener_nombre_hoja()
    if nombre_hoja not in wb.sheetnames:
        return []
    ws   = wb[nombre_hoja]
    cols = detectar_columnas(ws)
    ventas = []
    for fila in ws.iter_rows(min_row=config.EXCEL_FILA_DATOS, values_only=True):
        if not any(fila):
            continue
        ventas.append({nombre: fila[num - 1] for nombre, num in cols.items()})
    return ventas[-limite:]


def buscar_ventas(termino: str) -> list:
    inicializar_excel()
    wb            = openpyxl.load_workbook(config.EXCEL_FILE)
    termino_lower = termino.lower().strip()
    resultados    = []
    for nombre_hoja in wb.sheetnames:
        ws   = wb[nombre_hoja]
        cols = detectar_columnas(ws)
        for fila in ws.iter_rows(min_row=config.EXCEL_FILA_DATOS, values_only=True):
            if not any(fila):
                continue
            fila_texto = " ".join(str(v).lower() for v in fila if v is not None)
            if termino_lower in fila_texto:
                d = {"hoja": nombre_hoja}
                d.update({nombre: fila[num - 1] for nombre, num in cols.items()})
                resultados.append(d)
    return resultados


def obtener_todos_los_datos() -> list:
    inicializar_excel()
    wb    = openpyxl.load_workbook(config.EXCEL_FILE)
    todos = []
    for nombre_hoja in wb.sheetnames:
        ws   = wb[nombre_hoja]
        cols = detectar_columnas(ws)
        for fila in ws.iter_rows(min_row=config.EXCEL_FILA_DATOS, values_only=True):
            if any(fila):
                d = {"hoja": nombre_hoja}
                d.update({nombre: fila[num - 1] for nombre, num in cols.items()})
                todos.append(d)
    return todos


def obtener_resumen_ventas() -> dict | None:
    inicializar_excel()
    wb          = openpyxl.load_workbook(config.EXCEL_FILE)
    nombre_hoja = obtener_nombre_hoja()
    if nombre_hoja not in wb.sheetnames:
        return None
    ws        = wb[nombre_hoja]
    cols      = detectar_columnas(ws)
    col_total = next((v for k, v in cols.items() if k == "total"), None)
    total_general = 0
    num_ventas    = 0
    for fila in ws.iter_rows(min_row=config.EXCEL_FILA_DATOS, values_only=True):
        if not any(fila):
            continue
        num_ventas += 1
        if col_total and fila[col_total - 1]:
            try:
                total_general += float(fila[col_total - 1])
            except Exception:
                pass
    return {"hoja": nombre_hoja, "total": total_general, "num_ventas": num_ventas}


# ─────────────────────────────────────────────
# EXCEL PERSONALIZADO
# ─────────────────────────────────────────────

def generar_excel_personalizado(titulo: str, encabezados: list, filas: list, nombre_archivo: str) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titulo[:31]

    ws.merge_cells(f"A1:{get_column_letter(len(encabezados))}1")
    celda       = ws.cell(row=1, column=1, value=titulo)
    celda.font  = Font(bold=True, color="FFFFFF", size=14)
    celda.fill  = PatternFill("solid", fgColor="1A56DB")
    celda.alignment = Alignment(horizontal="center")

    for col, enc in enumerate(encabezados, 1):
        celda       = ws.cell(row=2, column=col, value=enc)
        celda.font  = Font(bold=True, color="FFFFFF", size=11)
        celda.fill  = PatternFill("solid", fgColor="374151")
        celda.alignment = Alignment(horizontal="center")

    for i, fila in enumerate(filas, 3):
        for col, valor in enumerate(fila, 1):
            celda = ws.cell(row=i, column=col, value=valor)
            if i % 2 == 0:
                celda.fill = PatternFill("solid", fgColor="EFF6FF")

    for col in range(1, len(encabezados) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 20

    wb.save(nombre_archivo)
    return nombre_archivo


# ─────────────────────────────────────────────
# WRAPPER ASYNC para operaciones bloqueantes
# ─────────────────────────────────────────────

async def guardar_venta_excel_async(*args, **kwargs) -> int:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: guardar_venta_excel(*args, **kwargs))


async def borrar_venta_excel_async(*args, **kwargs) -> tuple[bool, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: borrar_venta_excel(*args, **kwargs))


async def inicializar_excel_async():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, inicializar_excel)
