"""
Router: Histórico — /historico/*
"""
from __future__ import annotations

import logging
import threading as _threading
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Union

from memoria import cargar_memoria
from routers.shared import (
    _hoy, _hace_n_dias, _leer_excel_rango,
    _to_float, _cantidad_a_float,
)
from routers.deps import get_current_user

logger = logging.getLogger("ferrebot.api")

router = APIRouter()

# ── Caché en memoria ────────────────────────────────────────────────────────

# Caché para el total de hoy (evita recalcular en cada GET)
_cache_hoy_lock  = _threading.Lock()
_cache_hoy_valor: float = 0.0
_cache_hoy_fecha: str   = ""      # "YYYY-MM-DD" — se invalida al cambiar de día
_cache_hoy_ts:    float = 0.0     # timestamp UNIX de la última consulta real
_CACHE_TTL = 90                   # segundos — equilibrio entre frescura y peticiones

_NOMBRES_MES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

# ── Helpers: total en vivo desde Postgres ────────────────────────────────────

def _total_ventas_hoy_sheets() -> float:
    """
    Calcula el total de ventas del día actual desde Google Sheets (en vivo).
    Resultado cacheado durante _CACHE_TTL segundos para evitar saturar la API
    de Sheets cuando el dashboard refresca frecuentemente.
    Si Sheets falla, intenta Excel como fallback.
    """
    import time as _time
    global _cache_hoy_valor, _cache_hoy_fecha, _cache_hoy_ts

    hoy = _hoy()
    with _cache_hoy_lock:
        ahora = _time.monotonic()
        # Caché válido si es el mismo día y no expiró
        if (
            _cache_hoy_fecha == hoy
            and _cache_hoy_valor > 0
            and (ahora - _cache_hoy_ts) < _CACHE_TTL
        ):
            return _cache_hoy_valor

    # ── Consulta real a Postgres ─────────────────────────────────────────
    total = 0.0
    try:
        from db import query_all
        rows = query_all(
            "SELECT COALESCE(SUM(total), 0) AS total FROM ventas WHERE fecha = %s",
            (hoy,),
        )
        if rows:
            total = float(rows[0].get("total", 0) or 0)
    except Exception:
        pass

    if total > 0:
        import time as _time2
        with _cache_hoy_lock:
            _cache_hoy_valor = total
            _cache_hoy_fecha = hoy
            _cache_hoy_ts    = _time2.monotonic()
    return total


def _sync_historico_hoy() -> dict:
    """
    Sincroniza el total de hoy al histórico persistente.
    Desglose de métodos de pago desde Postgres; gastos desde cargar_memoria().
    """
    hoy   = _hoy()
    total = _total_ventas_hoy_sheets()
    if total <= 0:
        return {"fecha": hoy, "monto": 0, "ok": False, "razon": "sin ventas hoy"}

    monto = int(total)

    # ── Desglose método de pago (desde Postgres) ─────────────────────────
    efectivo = transferencia = datafono = 0.0
    n_trans  = 0
    try:
        from db import query_all as _qa
        rows_pg = _qa(
            """
            SELECT
                COALESCE(v.metodo_pago, '') AS metodo,
                COALESCE(SUM(d.total), 0)::float AS subtotal,
                COUNT(DISTINCT v.id) AS n
            FROM ventas v
            JOIN ventas_detalle d ON d.venta_id = v.id
            WHERE v.fecha = %s
            GROUP BY v.metodo_pago
            """,
            (hoy,),
        )
        for r in rows_pg:
            mt = str(r.get("metodo", "")).lower()
            v  = float(r.get("subtotal", 0) or 0)
            n  = int(r.get("n", 0))
            if "transfer" in mt:
                transferencia += v
            elif "data" in mt or "tarjeta" in mt:
                datafono += v
            else:
                efectivo += v
            n_trans += n
    except Exception:
        pass

    # ── Gastos y abonos del día — desde cargar_memoria() ─────────────────
    gastos_dia = 0.0
    abonos_dia = 0.0
    try:
        for g in cargar_memoria().get("gastos", {}).get(hoy, []):
            val = float(g.get("monto", 0))
            gastos_dia += val
            if g.get("categoria") == "abono_proveedor":
                abonos_dia += val
        gastos_dia = max(0.0, gastos_dia - abonos_dia)
    except Exception:
        pass

    # ── Persistir en Postgres ─────────────────────────────────────────────
    _guardar_diario_postgres(hoy, {
        "ventas":             monto,
        "efectivo":           round(efectivo, 2),
        "transferencia":      round(transferencia, 2),
        "datafono":           round(datafono, 2),
        "n_transacciones":    n_trans,
        "gastos":             round(gastos_dia, 2),
        "abonos_proveedores": round(abonos_dia, 2),
    })

    # ── Guardar total en historico principal ──────────────────────────────
    data = _leer_historico()
    data[hoy] = monto
    _guardar_historico(data)

    return {
        "fecha":             hoy,
        "monto":             monto,
        "efectivo":          round(efectivo, 2),
        "transferencia":     round(transferencia, 2),
        "datafono":          round(datafono, 2),
        "n_transacciones":   n_trans,
        "gastos":            round(gastos_dia, 2),
        "abonos":            round(abonos_dia, 2),
        "caja_neta":         monto - round(gastos_dia, 2) - round(abonos_dia, 2),
        "ok":                True,
    }


# ── Helpers internos ──────────────────────────────────────────────────────────

# ── Postgres helpers (HIS-01 a HIS-04) ───────────────────────────────────────

def _leer_historico_postgres() -> dict:
    """Lee historico_ventas desde Postgres. Retorna {fecha_str: monto} o {} si no disponible."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return {}
        rows = _db.query_all("SELECT fecha, ventas FROM historico_ventas ORDER BY fecha")
        return {str(row["fecha"]): int(row["ventas"]) for row in rows}
    except Exception as e:
        logger.warning("Error leyendo historico de Postgres: %s", e)
        return {}


def _leer_diario_postgres(año: int = 0, mes: int = 0) -> dict:
    """Lee desglose diario desde historico_ventas en Postgres. Retorna {fecha_str: {ventas, efectivo, ...}}."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return {}
        if año and mes:
            rows = _db.query_all(
                "SELECT * FROM historico_ventas WHERE fecha >= %s AND fecha < (%s::date + interval '1 month') ORDER BY fecha",
                (f"{año}-{mes:02d}-01", f"{año}-{mes:02d}-01")
            )
        elif año:
            rows = _db.query_all(
                "SELECT * FROM historico_ventas WHERE fecha >= %s AND fecha < %s ORDER BY fecha",
                (f"{año}-01-01", f"{año + 1}-01-01")
            )
        else:
            rows = _db.query_all("SELECT * FROM historico_ventas ORDER BY fecha")
        result = {}
        for r in rows:
            result[str(r["fecha"])] = {
                "ventas":             int(r.get("ventas", 0)),
                "efectivo":           int(r.get("efectivo", 0)),
                "transferencia":      int(r.get("transferencia", 0)),
                "datafono":           int(r.get("datafono", 0)),
                "n_transacciones":    int(r.get("n_transacciones", 0)),
                "gastos":             int(r.get("gastos", 0)),
                "abonos_proveedores": int(r.get("abonos_proveedores", 0)),
            }
        return result
    except Exception as e:
        logger.warning("Error leyendo diario de Postgres: %s", e)
        return {}


def _guardar_historico_postgres(data: dict) -> None:
    """UPSERT all historico entries to Postgres. Non-fatal."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return
        for fecha, monto in data.items():
            _db.execute(
                """INSERT INTO historico_ventas (fecha, ventas)
                   VALUES (%s, %s)
                   ON CONFLICT (fecha) DO UPDATE SET
                     ventas = EXCLUDED.ventas,
                     updated_at = NOW()""",
                (fecha, int(monto))
            )
    except Exception as e:
        logger.warning("Error guardando historico en Postgres: %s", e)


def _guardar_diario_postgres(fecha: str, datos: dict) -> None:
    """UPSERT one day's enriched data to historico_ventas in Postgres. Non-fatal."""
    try:
        import db as _db
        if not _db.DB_DISPONIBLE:
            return
        _db.execute(
            """INSERT INTO historico_ventas (fecha, ventas, efectivo, transferencia, datafono, n_transacciones, gastos, abonos_proveedores)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (fecha) DO UPDATE SET
                 ventas = EXCLUDED.ventas,
                 efectivo = EXCLUDED.efectivo,
                 transferencia = EXCLUDED.transferencia,
                 datafono = EXCLUDED.datafono,
                 n_transacciones = EXCLUDED.n_transacciones,
                 gastos = EXCLUDED.gastos,
                 abonos_proveedores = EXCLUDED.abonos_proveedores,
                 updated_at = NOW()""",
            (fecha, int(datos.get("ventas", 0)), int(datos.get("efectivo", 0)),
             int(datos.get("transferencia", 0)), int(datos.get("datafono", 0)),
             int(datos.get("n_transacciones", 0)), int(datos.get("gastos", 0)),
             int(datos.get("abonos_proveedores", 0)))
        )
    except Exception as e:
        logger.warning("Error guardando diario en Postgres: %s", e)


def _leer_historico() -> dict:
    """Lee historial desde Postgres (única fuente de verdad)."""
    return _leer_historico_postgres()

def _guardar_historico(data: dict) -> None:
    """Persiste en Postgres (única fuente de verdad)."""
    _guardar_historico_postgres(data)

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/historico/ventas")
def historico_ventas_get(año: int = 0, mes: int = 0, current_user=Depends(get_current_user)):
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
    """Guarda los montos de un mes en Postgres."""
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

@router.get("/historico/resumen")
def historico_resumen(current_user=Depends(get_current_user)):
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


@router.get("/historico/diario")
def historico_diario_get(año: int = 0, mes: int = 0, current_user=Depends(get_current_user)):
    """
    Retorna el desglose diario (efectivo, transferencia, datáfono, gastos, abonos).
    Fuente: Postgres (única fuente de verdad).
    """
    diario = _leer_diario_postgres(año, mes)
    if not año and not mes:
        return diario
    prefijo = f"{año}-{mes:02d}" if mes else str(año)
    return {k: v for k, v in diario.items() if k.startswith(prefijo)}


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


class CorreccionDia(BaseModel):
    fecha:        str    # "YYYY-MM-DD"
    monto:        int    # total de ventas del día
    efectivo:     Optional[int] = None
    transferencia: Optional[int] = None
    datafono:     Optional[int] = None
    gastos:       Optional[int] = None
    abonos:       Optional[int] = None

@router.post("/historico/corregir-dia")
def historico_corregir_dia(body: CorreccionDia):
    """
    Corrige o agrega manualmente el total de un día específico.
    Acepta opcionalmente el desglose (efectivo, transferencia, datáfono).
    """
    # Validar formato fecha
    try:
        datetime.strptime(body.fecha, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usar YYYY-MM-DD")

    if body.monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a 0")

    # Actualizar historico principal en Postgres
    data = _leer_historico()
    anterior = data.get(body.fecha, 0)
    data[body.fecha] = body.monto
    _guardar_historico(data)

    # Actualizar desglose si se proporcionó
    if any(v is not None for v in [body.efectivo, body.transferencia, body.datafono, body.gastos, body.abonos]):
        try:
            existente = _leer_diario_postgres().get(body.fecha, {})
            nuevo_desglose = {
                "ventas":             body.monto,
                "efectivo":           body.efectivo          if body.efectivo          is not None else existente.get("efectivo", 0),
                "transferencia":      body.transferencia      if body.transferencia      is not None else existente.get("transferencia", 0),
                "datafono":           body.datafono           if body.datafono           is not None else existente.get("datafono", 0),
                "n_transacciones":    existente.get("n_transacciones", 0),
                "gastos":             body.gastos             if body.gastos             is not None else existente.get("gastos", 0),
                "abonos_proveedores": body.abonos             if body.abonos             is not None else existente.get("abonos_proveedores", 0),
            }
            _guardar_diario_postgres(body.fecha, nuevo_desglose)
        except Exception as e:
            logger.warning(f"[corregir-dia] No se pudo actualizar desglose: {e}")

    return {
        "ok":       True,
        "fecha":    body.fecha,
        "anterior": anterior,
        "nuevo":    body.monto,
    }


@router.post("/historico/reconstruir-desglose")
def historico_reconstruir_desglose(dias: int = Query(default=60, ge=1, le=365)):
    """
    Reconstruye el desglose diario leyendo ventas desde Postgres y gastos desde
    cargar_memoria(). Escribe exclusivamente a historico_ventas en Postgres.
    Usar cuando efectivo/transferencia/datáfono aparezcan en 0.
    """
    # Leer desglose existente desde Postgres (para preservar lo que ya hay)
    diario: dict = _leer_diario_postgres()

    desde = _hace_n_dias(dias).strftime("%Y-%m-%d")
    hasta = _hoy()

    # Leer ventas desde Postgres (vía _leer_excel_rango → _leer_ventas_postgres)
    try:
        rows = _leer_excel_rango(dias=dias)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo ventas: {e}")

    # Agrupar por fecha y método de pago
    por_dia: dict = defaultdict(lambda: {
        "ventas": 0.0, "efectivo": 0.0,
        "transferencia": 0.0, "datafono": 0.0,
        "n_transacciones": 0, "gastos": 0.0, "abonos_proveedores": 0.0
    })

    for r in rows:
        fecha = str(r.get("fecha", ""))[:10]
        if not fecha or fecha < desde or fecha > hasta:
            continue
        total = float(r.get("total", 0) or 0)
        mt    = str(r.get("metodo", "")).lower()
        por_dia[fecha]["ventas"]          += total
        por_dia[fecha]["n_transacciones"] += 1
        if "transfer" in mt:
            por_dia[fecha]["transferencia"] += total
        elif "data" in mt or "tarjeta" in mt:
            por_dia[fecha]["datafono"] += total
        else:
            por_dia[fecha]["efectivo"] += total

    # Gastos y abonos desde cargar_memoria()
    try:
        gastos_mem = cargar_memoria().get("gastos", {})
        for fecha, lista in gastos_mem.items():
            if fecha < desde or fecha > hasta:
                continue
            for g in lista:
                val = float(g.get("monto", 0))
                if g.get("categoria") == "abono_proveedor":
                    por_dia[fecha]["abonos_proveedores"] += val
                else:
                    por_dia[fecha]["gastos"] += val
    except Exception:
        pass

    # Fusionar: respetar desglose existente; siempre actualizar gastos/abonos
    reconstruidos = 0
    for fecha, vals in por_dia.items():
        existente = diario.get(fecha, {})
        ya_tiene_desglose = (
            existente.get("efectivo", 0) > 0
            or existente.get("transferencia", 0) > 0
            or existente.get("datafono", 0) > 0
        )
        if not ya_tiene_desglose:
            nuevo = {
                "ventas":             round(vals["ventas"], 2),
                "efectivo":           round(vals["efectivo"], 2),
                "transferencia":      round(vals["transferencia"], 2),
                "datafono":           round(vals["datafono"], 2),
                "n_transacciones":    vals["n_transacciones"],
                "gastos":             round(vals["gastos"], 2),
                "abonos_proveedores": round(vals["abonos_proveedores"], 2),
            }
            diario[fecha] = nuevo
            _guardar_diario_postgres(fecha, nuevo)
            reconstruidos += 1
        else:
            if vals["gastos"] > 0 or vals["abonos_proveedores"] > 0:
                existente["gastos"]             = round(vals["gastos"], 2)
                existente["abonos_proveedores"] = round(vals["abonos_proveedores"], 2)
                diario[fecha] = existente
                _guardar_diario_postgres(fecha, existente)

    return {
        "ok":                   True,
        "dias_escaneados":      dias,
        "fechas_reconstruidas": reconstruidos,
        "total_dias_en_diario": len(diario),
    }


@router.post("/historico/sync-rango")
def historico_sync_rango(dias: int = Query(default=30, ge=1, le=365)):
    """
    Sincroniza los totales de los últimos N días desde Postgres → historico_ventas.
    No sobreescribe datos existentes (solo agrega los que faltan o tienen monto mayor).
    """
    try:
        data = _leer_historico()

        # Calcular totales por día directamente desde Postgres
        totales_pg: dict[str, int] = {}
        try:
            rows = _leer_excel_rango(dias=dias)   # delega a _leer_ventas_postgres
            por_dia: dict[str, float] = defaultdict(float)
            for v in rows:
                fecha = str(v.get("fecha", ""))[:10]
                if fecha:
                    por_dia[fecha] += float(v.get("total", 0) or 0)
            totales_pg = {k: int(v) for k, v in por_dia.items() if v > 0}
        except Exception:
            pass

        nuevos = 0
        actualizados = 0
        for fecha, monto in totales_pg.items():
            if fecha not in data:
                data[fecha] = monto
                nuevos += 1
            elif monto > data[fecha]:
                data[fecha] = monto
                actualizados += 1

        # Inyectar hoy en vivo
        hoy = _hoy()
        total_hoy = _total_ventas_hoy_sheets()
        if total_hoy > 0:
            if hoy not in data or int(total_hoy) > data.get(hoy, 0):
                data[hoy] = int(total_hoy)
                if hoy not in totales_pg:
                    nuevos += 1

        _guardar_historico(data)
        return {
            "ok":             True,
            "dias_escaneados": dias,
            "nuevos":          nuevos,
            "actualizados":    actualizados,
            "total_registros": len(data),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
