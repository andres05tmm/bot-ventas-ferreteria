"""
routers/libro_iva.py — Libro de IVA · Régimen Simple de Tributación (RST)

CONTEXTO TRIBUTARIO:
  - Ferretería Punto Rojo opera bajo el Régimen SIMPLE
  - Los precios en la DB ya incluyen IVA (precio final al cliente)
  - Solo se declara IVA de ventas que tengan Factura Electrónica emitida
  - El IVA descontable viene de compras_fiscal (libro contable, no de compras de almacén)
  - IVA neto a pagar = IVA generado (ventas FE) − IVA descontable (compras)

FÓRMULA (precios con IVA incluido):
  base_gravable = total × 100 / (100 + tarifa)
  iva           = total × tarifa / (100 + tarifa)
  Ejemplo: $119.000 con 19% → base=$100.000, IVA=$19.000

Endpoints:
  GET /libro-iva/periodos   — bimestres del año con saldos IVA
  GET /libro-iva/resumen    — cuadro IVA generado vs descontable vs neto
  GET /libro-iva/ventas     — detalle FE emitidas del período
  GET /libro-iva/compras    — detalle compras con IVA del período
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Depends

import db as _db
from routers.deps import get_current_user

logger = logging.getLogger("ferrebot.api")
router  = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_dates(desde: str, hasta: str) -> tuple[str, str]:
    try:
        d = date.fromisoformat(desde)
        h = date.fromisoformat(hasta)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fechas inválidas — usar YYYY-MM-DD")
    if d > h:
        raise HTTPException(status_code=400, detail="'desde' no puede ser mayor que 'hasta'")
    if (h - d).days > 366:
        raise HTTPException(status_code=400, detail="Rango máximo: 366 días")
    return str(d), str(h)


def _periodo_bimestral(año: int, bimestre: int) -> tuple[str, str]:
    meses = [(1,2),(3,4),(5,6),(7,8),(9,10),(11,12)]
    mes_i, mes_f = meses[bimestre - 1]
    inicio = date(año, mes_i, 1)
    fin    = date(año, 12, 31) if mes_f == 12 else date(año, mes_f + 1, 1) - timedelta(days=1)
    return str(inicio), str(fin)


# ── Fragmentos SQL para IVA incluido en precio ────────────────────────────────
# Usamos ROUND(..., 0)::BIGINT para trabajar en pesos enteros (sin decimales)

def _sql_iva(total: str, tarifa: str) -> str:
    return f"ROUND({total}::NUMERIC * {tarifa} / (100.0 + {tarifa}), 0)::BIGINT"

def _sql_base(total: str, tarifa: str) -> str:
    return f"ROUND({total}::NUMERIC * 100 / (100.0 + {tarifa}), 0)::BIGINT"


# ── Endpoint: Períodos bimestrales ────────────────────────────────────────────

@router.get("/libro-iva/periodos")
def periodos_bimestrales(
    año: int = Query(default=None),
    current_user=Depends(get_current_user),
):
    """6 bimestres del año con IVA generado (FE) e IVA descontable (compras)."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    año_q   = año or date.today().year
    nombres = ["Ene – Feb","Mar – Abr","May – Jun","Jul – Ago","Sep – Oct","Nov – Dic"]
    result  = []

    for i in range(1, 7):
        ini, fin = _periodo_bimestral(año_q, i)

        v = _db.query_one(
            f"""
            SELECT
                COALESCE(SUM({_sql_iva('vd.total','p.porcentaje_iva')}),0) AS iva_v,
                COUNT(DISTINCT fe.id) AS nfe
            FROM facturas_electronicas fe
            JOIN ventas         v  ON fe.venta_id    = v.id
            JOIN ventas_detalle vd ON vd.venta_id    = v.id
            JOIN productos      p  ON vd.producto_id = p.id
            WHERE fe.estado='emitida' AND p.tiene_iva=TRUE AND p.porcentaje_iva>0
              AND fe.fecha_emision::date BETWEEN %s AND %s
            """, (ini, fin))

        c = _db.query_one(
            f"""
            SELECT COALESCE(SUM({_sql_iva('c.costo_total','c.tarifa_iva')}),0) AS iva_c,
                   COUNT(c.id) AS nc
            FROM compras_fiscal c
            WHERE c.incluye_iva=TRUE AND c.tarifa_iva>0
              AND c.fecha BETWEEN %s AND %s
            """, (ini, fin))

        iva_v = int(v["iva_v"] or 0)
        iva_c = int(c["iva_c"] or 0)
        result.append({
            "bimestre": i, "nombre": nombres[i-1], "año": año_q,
            "fecha_inicio": ini, "fecha_fin": fin,
            "iva_ventas": iva_v, "iva_compras": iva_c,
            "iva_neto": iva_v - iva_c,
            "num_facturas": int(v["nfe"] or 0),
            "num_compras":  int(c["nc"]  or 0),
        })

    return result


# ── Endpoint: Cuadro resumen ──────────────────────────────────────────────────

@router.get("/libro-iva/resumen")
def resumen_iva(
    desde: str = Query(...),
    hasta: str = Query(...),
    current_user=Depends(get_current_user),
):
    """
    IVA generado (ventas FE) vs IVA descontable (compras) vs IVA neto.
    Si iva_neto < 0 el saldo es a favor de la empresa.
    """
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    desde, hasta = _validate_dates(desde, hasta)

    filas_v = _db.query_all(
        f"""
        SELECT p.porcentaje_iva AS tarifa,
               COUNT(DISTINCT fe.id)                                       AS num_facturas,
               COUNT(vd.id)                                                AS num_lineas,
               SUM(vd.total)::BIGINT                                       AS total_con_iva,
               SUM({_sql_base('vd.total','p.porcentaje_iva')})             AS base_gravable,
               SUM({_sql_iva('vd.total','p.porcentaje_iva')})              AS iva_valor
        FROM facturas_electronicas fe
        JOIN ventas         v  ON fe.venta_id    = v.id
        JOIN ventas_detalle vd ON vd.venta_id    = v.id
        JOIN productos      p  ON vd.producto_id = p.id
        WHERE fe.estado='emitida' AND p.tiene_iva=TRUE AND p.porcentaje_iva>0
          AND fe.fecha_emision::date BETWEEN %s AND %s
        GROUP BY p.porcentaje_iva ORDER BY p.porcentaje_iva
        """, (desde, hasta))

    filas_c = _db.query_all(
        f"""
        SELECT c.tarifa_iva AS tarifa,
               COUNT(c.id)                                                 AS num_compras,
               SUM(c.costo_total)::BIGINT                                  AS total_con_iva,
               SUM({_sql_base('c.costo_total','c.tarifa_iva')})            AS base_gravable,
               SUM({_sql_iva('c.costo_total','c.tarifa_iva')})             AS iva_valor
        FROM compras_fiscal c
        WHERE c.incluye_iva=TRUE AND c.tarifa_iva>0
          AND c.fecha BETWEEN %s AND %s
        GROUP BY c.tarifa_iva ORDER BY c.tarifa_iva
        """, (desde, hasta))

    ventas  = [dict(r) for r in filas_v]
    compras = [dict(r) for r in filas_c]

    iva_v = sum(int(r["iva_valor"] or 0) for r in ventas)
    iva_c = sum(int(r["iva_valor"] or 0) for r in compras)
    neto  = iva_v - iva_c

    return {
        "desde": desde, "hasta": hasta,
        "ventas": {
            "por_tarifa":  ventas,
            "total_iva":   iva_v,
            "total_base":  sum(int(r["base_gravable"] or 0) for r in ventas),
            "total_bruto": sum(int(r["total_con_iva"] or 0) for r in ventas),
        },
        "compras": {
            "por_tarifa":  compras,
            "total_iva":   iva_c,
            "total_base":  sum(int(r["base_gravable"] or 0) for r in compras),
            "total_bruto": sum(int(r["total_con_iva"] or 0) for r in compras),
        },
        "iva_neto": {
            "valor":       neto,
            "a_favor":     "empresa" if neto < 0 else "dian",
            "descripcion": (
                f"Saldo a tu favor: ${abs(neto):,}"
                if neto < 0 else f"IVA a pagar a la DIAN: ${neto:,}"
            ),
        },
    }


# ── Endpoint: Libro ventas FE ─────────────────────────────────────────────────

@router.get("/libro-iva/ventas")
def detalle_ventas_fe(
    desde: str = Query(...),
    hasta: str = Query(...),
    current_user=Depends(get_current_user),
):
    """Detalle línea a línea de IVA generado — solo facturas electrónicas emitidas."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    desde, hasta = _validate_dates(desde, hasta)

    filas = _db.query_all(
        f"""
        SELECT
            fe.fecha_emision::date::text                                   AS fecha,
            v.consecutivo,
            fe.numero                                                      AS factura_numero,
            COALESCE(v.cliente_nombre,'Consumidor Final')                 AS cliente_nombre,
            COALESCE(c.tipo_id,'CC')                                      AS tipo_id_cliente,
            COALESCE(c.identificacion,'222222222222')                     AS nit_cliente,
            vd.producto_nombre                                             AS concepto,
            p.porcentaje_iva                                               AS tarifa_iva,
            vd.total                                                       AS total_con_iva,
            {_sql_base('vd.total','p.porcentaje_iva')}                    AS base_gravable,
            {_sql_iva('vd.total','p.porcentaje_iva')}                     AS iva_valor
        FROM facturas_electronicas fe
        JOIN ventas         v  ON fe.venta_id    = v.id
        JOIN ventas_detalle vd ON vd.venta_id    = v.id
        JOIN productos      p  ON vd.producto_id = p.id
        LEFT JOIN clientes  c  ON v.cliente_id   = c.id
        WHERE fe.estado='emitida' AND p.tiene_iva=TRUE AND p.porcentaje_iva>0
          AND fe.fecha_emision::date BETWEEN %s AND %s
        ORDER BY fe.fecha_emision, v.consecutivo, vd.id
        """, (desde, hasta))

    rows = [dict(r) for r in filas]
    return {
        "desde": desde, "hasta": hasta, "registros": rows,
        "totales": {
            "num_lineas":    len(rows),
            "total_con_iva": sum(int(r["total_con_iva"] or 0) for r in rows),
            "base_gravable": sum(int(r["base_gravable"] or 0) for r in rows),
            "iva_generado":  sum(int(r["iva_valor"]     or 0) for r in rows),
        },
    }


# ── Endpoint: Libro compras (IVA descontable) ─────────────────────────────────

@router.get("/libro-iva/compras")
def detalle_compras_iva(
    desde: str = Query(...),
    hasta: str = Query(...),
    current_user=Depends(get_current_user),
):
    """Detalle línea a línea de IVA descontable — compras fiscales con IVA."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    desde, hasta = _validate_dates(desde, hasta)

    filas = _db.query_all(
        f"""
        SELECT
            c.id,
            c.fecha::text,
            COALESCE(c.proveedor,'Sin proveedor')  AS proveedor,
            c.producto_nombre                       AS concepto,
            c.tarifa_iva                            AS tarifa_iva,
            c.cantidad::TEXT                        AS cantidad,
            c.costo_unitario,
            c.costo_total                           AS total_con_iva,
            COALESCE(c.numero_factura,'')           AS numero_factura,
            COALESCE(c.notas_fiscales,'')           AS notas_fiscales,
            {_sql_base('c.costo_total','c.tarifa_iva')} AS base_gravable,
            {_sql_iva('c.costo_total','c.tarifa_iva')}  AS iva_valor
        FROM compras_fiscal c
        WHERE c.incluye_iva=TRUE AND c.tarifa_iva>0
          AND c.fecha BETWEEN %s AND %s
        ORDER BY c.fecha, c.id
        """, (desde, hasta))

    rows = [dict(r) for r in filas]
    return {
        "desde": desde, "hasta": hasta, "registros": rows,
        "totales": {
            "num_lineas":      len(rows),
            "total_con_iva":   sum(int(r["total_con_iva"] or 0) for r in rows),
            "base_gravable":   sum(int(r["base_gravable"] or 0) for r in rows),
            "iva_descontable": sum(int(r["iva_valor"]     or 0) for r in rows),
        },
    }


# ── Modelos nuevos ────────────────────────────────────────────────────────────

from pydantic import BaseModel as _BM

class CierreBimestreBody(_BM):
    año:           int
    bimestre:      int
    observaciones: str = ""


# ── Endpoint: Cerrar bimestre ─────────────────────────────────────────────────

@router.post("/libro-iva/cerrar-bimestre")
def cerrar_bimestre(body: CierreBimestreBody, current_user=Depends(get_current_user)):
    """
    Calcula y persiste el cierre del período bimestral:
      iva_neto = iva_ventas_FE - iva_compras - saldo_a_favor_anterior
    Si iva_neto < 0 el saldo se arrastra automáticamente al siguiente bimestre.
    """
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    año      = body.año
    bimestre = body.bimestre
    if not (1 <= bimestre <= 6):
        raise HTTPException(status_code=400, detail="Bimestre debe ser 1-6")

    ini, fin = _periodo_bimestral(año, bimestre)

    # IVA generado — solo FE emitidas
    v = _db.query_one(
        """
        SELECT COALESCE(SUM(ROUND(vd.total::NUMERIC * p.porcentaje_iva
                                  / (100.0 + p.porcentaje_iva), 0)), 0) AS iva_v
        FROM facturas_electronicas fe
        JOIN ventas         v  ON fe.venta_id    = v.id
        JOIN ventas_detalle vd ON vd.venta_id    = v.id
        JOIN productos      p  ON vd.producto_id = p.id
        WHERE fe.estado = 'emitida'
          AND p.tiene_iva = TRUE AND p.porcentaje_iva > 0
          AND fe.fecha_emision::date BETWEEN %s AND %s
        """, (ini, fin))

    # IVA descontable — compras_fiscal con IVA explícito (libro contable)
    c = _db.query_one(
        """
        SELECT COALESCE(SUM(ROUND(costo_total::NUMERIC * tarifa_iva
                                  / (100.0 + tarifa_iva), 0)), 0) AS iva_c
        FROM compras_fiscal
        WHERE incluye_iva = TRUE AND tarifa_iva > 0
          AND fecha BETWEEN %s AND %s
        """, (ini, fin))

    iva_ventas  = int(v["iva_v"] or 0)
    iva_compras = int(c["iva_c"] or 0)

    # Saldo a favor del bimestre anterior (si terminó a favor de la empresa)
    bim_ant = bimestre - 1
    año_ant  = año
    if bim_ant == 0:
        bim_ant = 6
        año_ant = año - 1

    anterior = _db.query_one(
        "SELECT iva_neto FROM iva_saldos_bimestrales WHERE año=%s AND bimestre=%s",
        (año_ant, bim_ant))
    saldo_anterior = 0
    if anterior:
        neto_ant = int(anterior["iva_neto"] or 0)
        if neto_ant < 0:
            saldo_anterior = abs(neto_ant)

    iva_neto = iva_ventas - iva_compras - saldo_anterior

    _db.execute(
        """
        INSERT INTO iva_saldos_bimestrales
            (año, bimestre, iva_ventas, iva_compras, saldo_anterior,
             iva_neto, estado, observaciones, cerrado_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'cerrado', %s, NOW())
        ON CONFLICT (año, bimestre) DO UPDATE SET
            iva_ventas     = EXCLUDED.iva_ventas,
            iva_compras    = EXCLUDED.iva_compras,
            saldo_anterior = EXCLUDED.saldo_anterior,
            iva_neto       = EXCLUDED.iva_neto,
            estado         = 'cerrado',
            observaciones  = EXCLUDED.observaciones,
            cerrado_at     = NOW()
        """,
        (año, bimestre, iva_ventas, iva_compras, saldo_anterior,
         iva_neto, body.observaciones or None))

    logger.info("Bimestre %s/%s cerrado — IVA neto: %s", bimestre, año, iva_neto)
    return {
        "ok":             True,
        "año":            año,
        "bimestre":       bimestre,
        "iva_ventas":     iva_ventas,
        "iva_compras":    iva_compras,
        "saldo_anterior": saldo_anterior,
        "iva_neto":       iva_neto,
        "a_favor":        "empresa" if iva_neto < 0 else "dian",
        "descripcion":    (
            f"Saldo a tu favor ${abs(iva_neto):,} — se arrastra al siguiente bimestre"
            if iva_neto < 0 else f"IVA a pagar a la DIAN: ${iva_neto:,}"
        ),
    }


# ── Endpoint: Historial de cierres ────────────────────────────────────────────

@router.get("/libro-iva/historial-cierres")
def historial_cierres(
    año: int = Query(default=None),
    current_user=Depends(get_current_user),
):
    """Lista los bimestres cerrados con saldos para el año indicado."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")

    año_q   = año or date.today().year
    nombres = ["Ene-Feb","Mar-Abr","May-Jun","Jul-Ago","Sep-Oct","Nov-Dic"]
    rows    = _db.query_all(
        """
        SELECT año, bimestre, iva_ventas, iva_compras, saldo_anterior,
               iva_neto, estado, observaciones, cerrado_at::text AS cerrado_at
        FROM iva_saldos_bimestrales
        WHERE año = %s
        ORDER BY bimestre
        """, (año_q,))

    result = []
    for r in rows:
        d = dict(r)
        d["nombre"]   = nombres[int(r["bimestre"]) - 1]
        d["a_favor"]  = "empresa" if int(r["iva_neto"] or 0) < 0 else "dian"
        result.append(d)
    return result
