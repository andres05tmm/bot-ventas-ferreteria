"""
ai/excel_gen.py — Generacion y edicion de Excel con Claude.
Extraido de ai.py (Tarea G).

Imports: openpyxl (inside functions), config, asyncio, json.
No imports de db ni memoria a nivel de modulo (PRM-04).
"""

# -- stdlib --
import asyncio
import json
import logging

# -- propios --
import config

logger = logging.getLogger("ferrebot.ai.excel_gen")


def generar_excel_personalizado(titulo: str, encabezados: list, filas: list, nombre_archivo: str) -> str:
    """Genera un .xlsx con cabecera azul y filas alternas. Reemplaza excel.generar_excel_personalizado."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titulo[:31]
    ws.merge_cells(f"A1:{get_column_letter(len(encabezados))}1")
    celda           = ws.cell(row=1, column=1, value=titulo)
    celda.font      = Font(bold=True, color="FFFFFF", size=14)
    celda.fill      = PatternFill("solid", fgColor="1A56DB")
    celda.alignment = Alignment(horizontal="center")
    for col, enc in enumerate(encabezados, 1):
        celda           = ws.cell(row=2, column=col, value=enc)
        celda.font      = Font(bold=True, color="FFFFFF", size=11)
        celda.fill      = PatternFill("solid", fgColor="374151")
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
