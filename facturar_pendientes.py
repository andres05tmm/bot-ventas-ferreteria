#!/usr/bin/env python3
"""
facturar_pendientes.py — Emite factura electrónica DIAN de las ventas ya
registradas que todavía no tienen FE.

A diferencia de generar_facturas.py (que INVENTA ventas para llegar a un monto),
este script no crea ni modifica ventas: solo factura las que ya existen en la BD
y quedaron con factura_estado != 'emitida'.

La fecha DIAN del documento es la de HOY (no la de la venta): una FE no se puede
retrofechar, se emite el día en que realmente se transmite.

Uso:
    railway run python facturar_pendientes.py --desde 2026-07-01 --hasta 2026-07-31 --dry-run
    railway run python facturar_pendientes.py --desde 2026-07-01 --hasta 2026-07-31 --limite 5
    railway run python facturar_pendientes.py --desde 2026-07-01 --hasta 2026-07-31

Recomendado: correr primero con --dry-run, luego con --limite 5 para verificar en
la DIAN, y solo entonces la corrida completa.

Variables de entorno: las mismas del proyecto (DATABASE_URL, MATIAS_*).
"""
from __future__ import annotations

# -- stdlib --
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

# -- terceros --
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# config.py exige claves del bot que este script no usa
os.environ.setdefault("TELEGRAM_TOKEN",    "dummy_not_needed_by_this_script")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy_not_needed_by_this_script")
os.environ.setdefault("OPENAI_API_KEY",    "dummy_not_needed_by_this_script")

# -- propios --
import db as _db
from config import COLOMBIA_TZ

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("facturar_pendientes.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("facturar_pendientes")

PAUSA_SEG        = 0.5   # entre facturas, para no saturar MATIAS API
MAX_FALLOS_SEGUIDOS = 5  # aborta si la DIAN/MATIAS empieza a rechazar en serie


def _pendientes(desde: str, hasta: str) -> list[dict]:
    """Ventas del rango sin FE emitida, con detalle válido."""
    rows = _db.query_all(
        """
        SELECT v.id, v.consecutivo, v.fecha::text AS fecha, v.total,
               COALESCE(v.cliente_nombre, 'Consumidor Final') AS cliente
        FROM ventas v
        WHERE v.fecha BETWEEN %s AND %s
          AND v.factura_estado IS DISTINCT FROM 'emitida'
          AND v.total > 0
          AND EXISTS (SELECT 1 FROM ventas_detalle vd WHERE vd.venta_id = v.id)
        ORDER BY v.fecha, v.consecutivo
        """,
        (desde, hasta),
    )
    return [dict(r) for r in (rows or [])]


async def run(desde: str, hasta: str, dry_run: bool, limite: int | None) -> int:
    from services.facturacion_service import emitir_factura

    hoy       = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d")
    ventas    = _pendientes(desde, hasta)
    if limite:
        ventas = ventas[:limite]

    monto = sum(int(v["total"] or 0) for v in ventas)
    log.info("Pendientes %s → %s: %s ventas, $%s", desde, hasta, len(ventas), f"{monto:,}")
    log.info("Fecha DIAN de emisión: %s", hoy)

    if dry_run:
        for v in ventas[:20]:
            log.info("  [dry-run] venta %s (cons %s, %s) $%s — %s",
                     v["id"], v["consecutivo"], v["fecha"], f"{int(v['total']):,}", v["cliente"])
        if len(ventas) > 20:
            log.info("  … y %s más", len(ventas) - 20)
        log.info("DRY-RUN: no se emitió nada.")
        return 0

    ok = fallos = seguidos = 0
    for i, v in enumerate(ventas, 1):
        try:
            res = await emitir_factura(v["id"], fecha_emision=hoy)
        except Exception as e:                      # noqa: BLE001 — estabilidad
            res = {"ok": False, "error": str(e)}

        if res.get("ok"):
            ok += 1
            seguidos = 0
            log.info("[%s/%s] ✅ %s — venta %s $%s",
                     i, len(ventas), res["numero"], v["id"], f"{int(v['total']):,}")
        else:
            fallos += 1
            seguidos += 1
            log.error("[%s/%s] ❌ venta %s: %s", i, len(ventas), v["id"], res.get("error"))
            if seguidos >= MAX_FALLOS_SEGUIDOS:
                log.error("ABORTADO: %s fallos seguidos (¿rango DIAN agotado o API caída?)",
                          seguidos)
                break

        await asyncio.sleep(PAUSA_SEG)

    log.info("── Resumen ── emitidas: %s | fallidas: %s | pendientes restantes: %s",
             ok, fallos, len(ventas) - ok - fallos)
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Emite FE de ventas ya registradas sin factura")
    ap.add_argument("--desde",   required=True, help="Fecha inicial YYYY-MM-DD (fecha de la venta)")
    ap.add_argument("--hasta",   required=True, help="Fecha final YYYY-MM-DD (fecha de la venta)")
    ap.add_argument("--dry-run", action="store_true", help="Solo lista, no emite nada")
    ap.add_argument("--limite",  type=int, default=None, help="Emitir solo las primeras N (prueba)")
    args = ap.parse_args()

    if not _db.init_db():
        log.error("❌ No se pudo conectar a la DB. Verifica DATABASE_URL.")
        sys.exit(1)

    sys.exit(asyncio.run(run(args.desde, args.hasta, args.dry_run, args.limite)))
