"""
Router: Histórico — /historico/*
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Union

import config
from sheets import sheets_leer_ventas_del_dia
from routers.shared import (
    _hoy, _hace_n_dias, _leer_excel_rango, _leer_excel_compras,
    _to_float, _cantidad_a_float, _stock_wayper,
)

logger = logging.getLogger("ferrebot.api")

router = APIRouter()

# ── Historial manual de ventas diarias ────────────────────────────────────────

HISTORICO_FILE  = "historico_ventas.json"
HISTORICO_EXCEL = "historico_ventas.xlsx"
_NOMBRES_MES    = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                   "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

# ── Helpers: total en vivo desde Sheets / Excel ──────────────────────────────

def _total_ventas_hoy_sheets() -> float:
    """
    Calcula el total de ventas del día actual desde Google Sheets (en vivo).
    Si Sheets falla, intenta Excel como fallback.
    """
    hoy = _hoy()
    try:
        ventas = sheets_leer_ventas_del_dia()
        total = 0.0
        for v in ventas:
            if str(v.get("fecha", ""))[:10] == hoy:
                try:
                    total += float(str(v.get("total", 0)).replace(",", ".") or 0)
                except (ValueError, TypeError):
                    pass
        if total > 0:
            return total
    except Exception:
        pass
    # Fallback: Excel
    try:
        ventas_xls = _leer_excel_rango(dias=1)
        return sum(
            float(str(v.get("total", 0)).replace(",", ".") or 0)
            for v in ventas_xls
            if str(v.get("fecha", ""))[:10] == hoy
        )
    except Exception:
        return 0.0


def _totales_por_dia_excel(dias: int = 30) -> dict:
    """
    Lee ventas del Excel y retorna {fecha: total} para los últimos N días.
    Útil para sincronizar históricos de días pasados.
    """
    try:
        ventas = _leer_excel_rango(dias=dias)
    except Exception:
        return {}
    por_dia: dict[str, float] = defaultdict(float)
    for v in ventas:
        fecha = str(v.get("fecha", ""))[:10]
        if fecha:
            try:
                por_dia[fecha] += float(str(v.get("total", 0)).replace(",", ".") or 0)
            except (ValueError, TypeError):
                pass
    return {k: int(v) for k, v in por_dia.items() if v > 0}


def _sync_historico_hoy() -> dict:
    """
    Sincroniza el total de hoy (desde Sheets) al histórico persistente.
    Retorna {"fecha": ..., "monto": ..., "ok": True/False}.
    """
    hoy = _hoy()
    total = _total_ventas_hoy_sheets()
    if total <= 0:
        return {"fecha": hoy, "monto": 0, "ok": False, "razon": "sin ventas hoy"}
    monto = int(total)
    data = _leer_historico()
    data[hoy] = monto
    _guardar_historico(data)
    return {"fecha": hoy, "monto": monto, "ok": True}


# ── Helpers internos ──────────────────────────────────────────────────────────

def _excel_a_dict(ruta: str) -> dict:
    """
    Lee historico_ventas.xlsx y retorna {fecha: monto}.
    Columna A = Fecha (YYYY-MM-DD), Columna E = Monto.
    Ignora filas con fecha o monto inválidos.
    """
    data = {}
    try:
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            fecha = str(row[0] or "").strip()
            monto = row[4]  # Col E
            if not fecha or not monto:
                continue
            try:
                # Validar formato YYYY-MM-DD
                parts = fecha.split("-")
                if len(parts) == 3 and len(parts[0]) == 4:
                    m = int(monto)
                    if m > 0:
                        data[fecha] = m
            except Exception:
                pass
    except Exception as e:
        logging.getLogger("ferrebot.api").warning(f"[historico] No se pudo leer Excel: {e}")
    return data

def _dict_a_excel(data: dict, ruta: str) -> None:
    """
    Escribe {fecha: monto} en historico_ventas.xlsx.
    Columnas: Fecha | Año | Mes | Día | Monto
    """
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Historial"

    # Encabezados
    headers = ["Fecha", "Año", "Mes", "Día", "Monto"]
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C0392B")
        c.alignment = Alignment(horizontal="center")

    # Datos ordenados por fecha
    for row_idx, (fecha, monto) in enumerate(sorted(data.items()), 2):
        try:
            parts   = fecha.split("-")
            año_n   = int(parts[0])
            mes_n   = int(parts[1])
            dia_n   = int(parts[2])
            nom_mes = _NOMBRES_MES[mes_n] if 1 <= mes_n <= 12 else str(mes_n)
            ws.cell(row=row_idx, column=1, value=fecha)
            ws.cell(row=row_idx, column=2, value=año_n)
            ws.cell(row=row_idx, column=3, value=nom_mes)
            ws.cell(row=row_idx, column=4, value=dia_n)
            ws.cell(row=row_idx, column=5, value=int(monto))
        except Exception:
            pass

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["E"].width = 16
    wb.save(ruta)

def _leer_historico_de_excel() -> dict:
    """
    Descarga el Excel de Drive → lee datos → retorna dict.
    Es la fuente de verdad cuando existe.
    """
    try:
        from drive import descargar_de_drive
        ruta_tmp = HISTORICO_EXCEL + ".tmp"
        if descargar_de_drive(HISTORICO_EXCEL, ruta_tmp):
            data = _excel_a_dict(ruta_tmp)
            try:
                import os as _os; _os.remove(ruta_tmp)
            except Exception:
                pass
            return data
    except Exception:
        pass
    return {}

def _leer_historico() -> dict:
    """
    Lee historial: primero intenta Excel de Drive (fuente de verdad),
    luego JSON local como fallback.
    """
    # 1. Excel en Drive (fuente de verdad)
    data = _leer_historico_de_excel()
    if data:
        # Actualizar caché JSON local
        try:
            with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return data

    # 2. JSON local como fallback
    if os.path.exists(HISTORICO_FILE):
        try:
            with open(HISTORICO_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 3. JSON en Drive como último recurso
    try:
        from drive import descargar_de_drive
        if descargar_de_drive(HISTORICO_FILE, HISTORICO_FILE):
            with open(HISTORICO_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _guardar_historico(data: dict) -> None:
    """
    Guarda en JSON local + Excel local, y sube ambos a Drive.
    Excel es la fuente de verdad — siempre se regenera completo.
    """
    # 1. JSON local (caché rápida para el API)
    with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 2. Excel local (fuente de verdad editable)
    _dict_a_excel(data, HISTORICO_EXCEL)

    # 3. Subir ambos a Drive
    try:
        from drive import subir_a_drive_urgente
        subir_a_drive_urgente(HISTORICO_FILE)
        subir_a_drive_urgente(HISTORICO_EXCEL)
    except Exception:
        pass

# ── Endpoints ─────────────────────────────────────────────────────────────────
# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/historico/ventas")
def historico_ventas_get(año: int = 0, mes: int = 0):
    """
    Retorna montos del mes/año.
    SIEMPRE inyecta el total en vivo de hoy desde Sheets, para que el
    dashboard muestre el dato real aunque no se haya hecho sync manual.
    """
    data = _leer_historico()

    # ── Inyectar total en vivo del día actual ────────────────────────────
    hoy = _hoy()
    total_hoy = _total_ventas_hoy_sheets()
    if total_hoy > 0:
        data[hoy] = int(total_hoy)

    if not año and not mes:
        return data
    prefijo = f"{año}-{mes:02d}" if mes else str(año)
    return {k: v for k, v in data.items() if k.startswith(prefijo)}

class HistoricoBody(BaseModel):
    año:   int
    mes:   int
    datos: dict   # { "2026-03-01": 850000, ... }

@router.post("/historico/ventas")
def historico_ventas_post(body: HistoricoBody):
    """
    Guarda los montos de un mes.
    1. Lee estado actual del Excel (para no pisar otros meses)
    2. Fusiona con los nuevos datos
    3. Guarda JSON + Excel + sube Drive
    """
    try:
        # Leer estado actual (Excel como fuente de verdad)
        data   = _leer_historico()
        prefijo = f"{body.año}-{body.mes:02d}"

        # Eliminar entradas previas del mes
        data = {k: v for k, v in data.items() if not k.startswith(prefijo)}

        # Agregar los nuevos (solo > 0)
        for fecha, monto in body.datos.items():
            if fecha.startswith(prefijo) and monto and int(monto) > 0:
                data[fecha] = int(monto)

        _guardar_historico(data)
        registros_mes = len([v for k, v in data.items() if k.startswith(prefijo)])
        return {"ok": True, "registros": registros_mes, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/historico/sincronizar-excel")
def historico_sincronizar_excel():
    """
    Lee el Excel de Drive (editado manualmente) y actualiza el JSON.
    Llamar desde dashboard cuando quieras traer cambios hechos en Excel.
    """
    try:
        data = _leer_historico_de_excel()
        if not data:
            return {"ok": False, "error": "No se encontró historico_ventas.xlsx en Drive o está vacío"}
        # Actualizar JSON local con lo que tiene el Excel
        with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            from drive import subir_a_drive_urgente
            subir_a_drive_urgente(HISTORICO_FILE)
        except Exception:
            pass
        return {"ok": True, "registros": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/historico/resumen")
def historico_resumen():
    """Totales mensuales para gráficas — incluye hoy en vivo."""
    data = _leer_historico()

    # Inyectar hoy en vivo
    hoy = _hoy()
    total_hoy = _total_ventas_hoy_sheets()
    if total_hoy > 0:
        data[hoy] = int(total_hoy)

    por_mes: dict = defaultdict(int)
    for fecha, monto in data.items():
        if monto and monto > 0:
            por_mes[fecha[:7]] += monto
    return dict(sorted(por_mes.items()))


@router.post("/historico/auto-sync")
def historico_auto_sync():
    """
    Sincroniza el total de hoy desde Sheets → histórico persistente.
    Llamar desde el dashboard o automáticamente al cierre del día.
    """
    try:
        result = _sync_historico_hoy()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/historico/sync-rango")
def historico_sync_rango(dias: int = Query(default=30, ge=1, le=365)):
    """
    Sincroniza los totales de los últimos N días desde Excel → histórico.
    Útil para llenar histórico con datos de días pasados que no se guardaron.
    No sobreescribe datos existentes (solo agrega los que faltan).
    """
    try:
        data = _leer_historico()
        totales_excel = _totales_por_dia_excel(dias=dias)

        nuevos = 0
        actualizados = 0
        for fecha, monto in totales_excel.items():
            if fecha not in data:
                data[fecha] = monto
                nuevos += 1
            elif data[fecha] != monto:
                # Solo actualizar si el Excel tiene un monto mayor
                # (probablemente el dato manual estaba incompleto)
                if monto > data[fecha]:
                    data[fecha] = monto
                    actualizados += 1

        # Inyectar hoy en vivo desde Sheets (más preciso que Excel para el día actual)
        hoy = _hoy()
        total_hoy = _total_ventas_hoy_sheets()
        if total_hoy > 0:
            if hoy not in data or int(total_hoy) > data.get(hoy, 0):
                data[hoy] = int(total_hoy)
                if hoy not in totales_excel:
                    nuevos += 1

        _guardar_historico(data)
        return {
            "ok": True,
            "dias_escaneados": dias,
            "nuevos": nuevos,
            "actualizados": actualizados,
            "total_registros": len(data),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

