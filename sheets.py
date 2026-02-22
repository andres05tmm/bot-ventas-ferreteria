"""
Google Sheets: pizarra del dia en tiempo real.
Columnas: #, Fecha, Hora, Producto, Cantidad, Precio Unitario, Total, Vendedor, Metodo Pago
"""

from datetime import datetime

import config
from utils import decimal_a_fraccion_legible


def _obtener_hoja_sheets():
    """
    Retorna la worksheet 'Ventas del Dia'.
    Si no existe la pestana la crea con encabezados y formato.
    Retorna None si no hay conexion.
    """
    if not config.SHEETS_ID:
        return None
    try:
        import gspread
        gc           = config.get_sheets_client()
        spreadsheet  = gc.open_by_key(config.SHEETS_ID)
        try:
            ws = spreadsheet.worksheet("Ventas del Dia")
        except gspread.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(
                "Ventas del Dia", rows=500, cols=len(config.SHEETS_HEADERS)
            )
            ws.append_row(config.SHEETS_HEADERS)
            ws.format("A1:I1", {
                "backgroundColor": {"red": 0.102, "green": 0.337, "blue": 0.855},
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                },
                "horizontalAlignment": "CENTER",
            })
        config.SHEETS_DISPONIBLE = True
        return ws
    except Exception as e:
        print(f"⚠️ Error accediendo a Sheets: {e}")
        config.SHEETS_DISPONIBLE = False
        config.reset_google_clients()
        return None


def sheets_agregar_venta(num, producto, cantidad, precio_unitario, total, vendedor, metodo) -> bool:
    """Agrega una fila de venta al Google Sheets en tiempo real."""
    if not config.SHEETS_ID:
        return False
    try:
        ws = _obtener_hoja_sheets()
        if not ws:
            return False

        fecha = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
        hora  = datetime.now(config.COLOMBIA_TZ).strftime("%H:%M")
        cantidad_legible = (
            decimal_a_fraccion_legible(float(cantidad))
            if not isinstance(cantidad, str) else str(cantidad)
        )
        fila = [
            num, fecha, hora, str(producto), cantidad_legible,
            float(precio_unitario), float(total), str(vendedor), str(metodo),
        ]
        ws.append_row(fila, value_input_option="USER_ENTERED")

        # Alternar color de fila
        num_filas = len(ws.get_all_values())
        if num_filas % 2 == 0:
            ws.format(f"A{num_filas}:I{num_filas}", {
                "backgroundColor": {"red": 0.937, "green": 0.961, "blue": 1.0}
            })

        config.SHEETS_DISPONIBLE = True
        return True
    except Exception as e:
        print(f"⚠️ Error agregando al Sheets: {e}")
        config.SHEETS_DISPONIBLE = False
        config.reset_google_clients()
        return False


def sheets_borrar_fila(numero_venta) -> bool:
    """Borra del Sheets la fila cuyo primer campo sea numero_venta."""
    if not config.SHEETS_ID:
        return False
    try:
        ws = _obtener_hoja_sheets()
        if not ws:
            return False
        celdas = ws.get_all_values()
        for idx, fila in enumerate(celdas):
            if idx == 0:
                continue
            try:
                if int(fila[0]) == int(numero_venta):
                    ws.delete_rows(idx + 1)
                    return True
            except (ValueError, IndexError):
                pass
        return False
    except Exception as e:
        print(f"⚠️ Error borrando fila del Sheets: {e}")
        return False


def sheets_leer_ventas_del_dia() -> list:
    """
    Lee todas las filas de ventas del Sheets (excluyendo encabezado).
    Retorna lista de dicts. Respeta ediciones manuales.
    """
    if not config.SHEETS_ID:
        return []
    try:
        ws = _obtener_hoja_sheets()
        if not ws:
            return []
        todas = ws.get_all_records()
        resultado = []
        for fila in todas:
            if not any(fila.values()):
                continue
            resultado.append({
                "num":             fila.get("#", fila.get("num", "")),
                "fecha":           fila.get("Fecha", fila.get("fecha", "")),
                "hora":            fila.get("Hora", fila.get("hora", "")),
                "producto":        fila.get("Producto", fila.get("producto", "")),
                "cantidad":        fila.get("Cantidad", fila.get("cantidad", "")),
                "precio_unitario": fila.get("Precio Unitario", fila.get("precio_unitario", 0)),
                "total":           fila.get("Total", fila.get("total", 0)),
                "vendedor":        fila.get("Vendedor", fila.get("vendedor", "")),
                "metodo":          fila.get("Método Pago", fila.get("metodo", "")),
            })
        return resultado
    except Exception as e:
        print(f"⚠️ Error leyendo Sheets: {e}")
        return []


def sheets_detectar_ediciones_vs_excel() -> list[str]:
    """
    Compara el Sheets con el Excel local.
    Retorna lista de strings describiendo diferencias (ediciones manuales).
    """
    from excel import inicializar_excel, obtener_nombre_hoja, detectar_columnas
    import openpyxl
    from config import EXCEL_FILE, EXCEL_FILA_DATOS

    ventas_sheets = sheets_leer_ventas_del_dia()
    if not ventas_sheets:
        return []

    hoy = datetime.now(config.COLOMBIA_TZ).strftime("%Y-%m-%d")
    inicializar_excel()

    import openpyxl
    wb           = openpyxl.load_workbook(EXCEL_FILE)
    nombre_hoja  = obtener_nombre_hoja()
    ventas_excel = {}

    if nombre_hoja in wb.sheetnames:
        ws   = wb[nombre_hoja]
        cols = detectar_columnas(ws)
        col_num   = next((v for k, v in cols.items() if k == "#"), None)
        col_fecha = next((v for k, v in cols.items() if "fecha" in k), None)
        col_prod  = next((v for k, v in cols.items() if "producto" in k), None)
        col_total = next((v for k, v in cols.items() if "total" in k), None)
        for fila in ws.iter_rows(min_row=EXCEL_FILA_DATOS, values_only=True):
            if not any(fila):
                continue
            if col_fecha and str(fila[col_fecha - 1])[:10] == hoy:
                n = fila[col_num - 1] if col_num else None
                if n:
                    ventas_excel[int(n)] = {
                        "producto": fila[col_prod  - 1] if col_prod  else "",
                        "total":    fila[col_total - 1] if col_total else 0,
                    }

    diferencias = []
    for v in ventas_sheets:
        try:
            num = int(v["num"])
        except (ValueError, TypeError):
            continue
        if num not in ventas_excel:
            diferencias.append(
                f"  • Venta #{num} ({v['producto']}) esta en el Sheet pero no en el Excel local"
            )
        else:
            prod_xl = str(ventas_excel[num]["producto"]).lower()
            prod_sh = str(v["producto"]).lower()
            if prod_xl != prod_sh:
                diferencias.append(
                    f"  • #{num}: producto cambiado de '{ventas_excel[num]['producto']}' a '{v['producto']}'"
                )
            try:
                if abs(float(ventas_excel[num]["total"]) - float(v["total"])) > 1:
                    diferencias.append(
                        f"  • #{num} ({v['producto']}): total cambiado de "
                        f"${float(ventas_excel[num]['total']):,.0f} a ${float(v['total']):,.0f}"
                    )
            except (ValueError, TypeError):
                pass
    return diferencias


def sheets_limpiar() -> bool:
    """Limpia todas las ventas del Sheets (deja solo el encabezado)."""
    if not config.SHEETS_ID:
        return False
    try:
        ws = _obtener_hoja_sheets()
        if not ws:
            return False
        num_filas = len(ws.get_all_values())
        if num_filas > 1:
            ws.delete_rows(2, num_filas)
        print("🧹 Google Sheets limpiado para el nuevo dia.")
        return True
    except Exception as e:
        print(f"⚠️ Error limpiando Sheets: {e}")
        return False
