#!/usr/bin/env python3
"""
generar_facturas.py — Generador masivo de ventas + facturas electrónicas DIAN

Genera ventas aleatorias en PostgreSQL y emite cada una como factura electrónica
a la DIAN a través de MATIAS API, hasta alcanzar el monto objetivo.

Todos los clientes son Consumidor Final (no se requieren datos de cliente).

Uso:
    cd /ruta/al/proyecto
    python generar_facturas.py [--dry-run]

    --dry-run   Solo muestra las ventas que generaría sin insertar ni emitir.

Variables de entorno requeridas (las mismas del proyecto):
    DATABASE_URL        — Conexión PostgreSQL (Railway)
    MATIAS_EMAIL        — Credencial MATIAS API
    MATIAS_PASSWORD     — Credencial MATIAS API
    MATIAS_RESOLUTION   — Número resolución DIAN
    MATIAS_PREFIX       — Prefijo factura (ej: LZT, FPR)
    MATIAS_NUM_DESDE    — Primer número del rango DIAN (default: 1)
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
from datetime import date, timedelta

# ── Cargar .env si existe (opcional) ─────────────────────────────────────────
# Si python-dotenv está instalado Y hay un archivo .env en la carpeta,
# carga las variables automáticamente.  Si no, usa las vars del sistema.
try:
    from dotenv import load_dotenv
    _env_loaded = load_dotenv(override=False)   # override=False: vars del sistema ganan
    if _env_loaded:
        print("✅ Variables cargadas desde .env")
except ImportError:
    pass   # python-dotenv no instalado — usar vars del sistema directamente

# ── Parche para config.py ─────────────────────────────────────────────────────
# config.py valida TELEGRAM_TOKEN, ANTHROPIC_API_KEY y OPENAI_API_KEY al
# importarse y hace SystemExit si faltan.  Este script no los necesita,
# así que ponemos valores ficticios SOLO si no están ya en el entorno.
os.environ.setdefault("TELEGRAM_TOKEN",    "dummy_not_needed_by_this_script")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy_not_needed_by_this_script")
os.environ.setdefault("OPENAI_API_KEY",    "dummy_not_needed_by_this_script")

# ── Parámetros ajustables ─────────────────────────────────────────────────────

TARGET_TOTAL  = 12_686_537   # Monto objetivo en COP (restante tras primera corrida)

TICKET_MIN    = 10_000       # Ticket mínimo por factura
TICKET_MAX    = 380_000      # Ticket máximo por factura

FECHA_INICIO  = date(2026, 4, 29)
FECHA_FIN     = date(2026, 4, 29)

METODO_PAGO   = "efectivo"   # efectivo | transferencia | datafono
VENDEDOR      = "Dashboard"

MAX_ITEMS_POR_VENTA = 4      # Máximo de productos distintos por venta
PAUSA_SEG           = 0.3    # Segundos entre facturas (respeta rate limit MATIAS API)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("generar_facturas.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("generar_facturas")


# ── Carga de catálogo ─────────────────────────────────────────────────────────

def _cargar_catalogo() -> list[dict]:
    """
    Retorna productos activos con precio > 0 y sus datos de IVA.
    El JOIN en emitir_factura usa producto_id para resolver tiene_iva/porcentaje_iva,
    así que traemos esos datos aquí para guardarlos en ventas_detalle.
    """
    import db as _db

    rows = _db.query_all(
        """
        SELECT id,
               nombre,
               precio_unidad                     AS precio,
               COALESCE(unidad_medida, 'Unidad') AS unidad_medida,
               COALESCE(tiene_iva,     false)    AS tiene_iva,
               COALESCE(porcentaje_iva, 0)       AS porcentaje_iva
        FROM productos
        WHERE precio_unidad > 0
          AND activo = true
          AND nombre IS NOT NULL
          AND nombre != ''
        ORDER BY nombre
        """,
        None,
    )
    return [dict(r) for r in (rows or [])]


# ── Generación de ítems de venta ──────────────────────────────────────────────

def _generar_items(catalogo: list[dict], target_ticket: int) -> list[dict]:
    """
    Selecciona 1–MAX_ITEMS_POR_VENTA productos del catálogo y genera
    cantidades para que el total esté cerca de target_ticket.
    """
    n = random.randint(1, min(MAX_ITEMS_POR_VENTA, len(catalogo)))
    seleccionados = random.sample(catalogo, n)
    items: list[dict] = []
    total_acum = 0

    for i, prod in enumerate(seleccionados):
        precio = float(prod.get("precio") or 0)
        if precio <= 0:
            continue

        es_ultimo = (i == len(seleccionados) - 1)

        if es_ultimo and items:
            # El último ítem rellena el restante hacia el target
            restante = target_ticket - total_acum
            if restante <= 0:
                break
            cant = max(1, round(restante / precio))
            cant = min(cant, 20)           # Máximo razonable por ítem
        else:
            # Ítems intermedios: cantidad aleatoria 1–6
            cant = random.randint(1, 6)

        total_item = round(precio * cant)

        items.append({
            "nombre":        prod["nombre"],
            "cantidad":      float(cant),
            "precio_unit":   precio,
            "total":         total_item,
            "unidad_medida": prod["unidad_medida"],
            "producto_id":   prod["id"],
        })
        total_acum += total_item

    return items


# ── Inserción en PostgreSQL ───────────────────────────────────────────────────

def _insertar_venta(items: list[dict], fecha_v: date, hora_str: str) -> tuple[int, int]:
    """
    Inserta la venta y su detalle en PostgreSQL.
    Retorna (venta_id, consecutivo).
    """
    import db as _db

    total = sum(i["total"] for i in items)

    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            # Consecutivo atómico
            cur.execute(
                "SELECT COALESCE(MAX(consecutivo), 0) + 1 AS sig FROM ventas"
            )
            consecutivo = cur.fetchone()["sig"]

            cur.execute(
                """
                INSERT INTO ventas
                    (consecutivo, fecha, hora, vendedor, metodo_pago,
                     total, cliente_nombre, cliente_id, usuario_id)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, NULL)
                RETURNING id
                """,
                (consecutivo, str(fecha_v), hora_str, VENDEDOR, METODO_PAGO, total),
            )
            venta_id = cur.fetchone()["id"]

            for item in items:
                cur.execute(
                    """
                    INSERT INTO ventas_detalle
                        (venta_id, producto_nombre, cantidad,
                         precio_unitario, total, unidad_medida, producto_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        venta_id,
                        item["nombre"],
                        item["cantidad"],
                        item["precio_unit"],
                        item["total"],
                        item["unidad_medida"],
                        item["producto_id"],
                    ),
                )
        conn.commit()

    return venta_id, consecutivo


# ── Loop principal ────────────────────────────────────────────────────────────

async def _main(dry_run: bool = False) -> None:

    # ── Validaciones previas ──────────────────────────────────────────────────
    try:
        import db as _db
    except ImportError:
        log.error(
            "No se pueden importar módulos del proyecto.\n"
            "Asegúrate de correr desde la raíz del proyecto:\n"
            "    cd /ruta/del/proyecto && python generar_facturas.py"
        )
        sys.exit(1)

    # init_db() debe llamarse explícitamente — no se auto-ejecuta al importar
    _db.init_db()

    if not _db.DB_DISPONIBLE:
        log.error("Base de datos no disponible. Verifica DATABASE_URL.")
        sys.exit(1)

    import os
    if not dry_run and not os.getenv("MATIAS_EMAIL"):
        log.error(
            "Falta MATIAS_EMAIL en variables de entorno.\n"
            "Configura las variables MATIAS_* antes de correr el script."
        )
        sys.exit(1)

    # ── Cargar catálogo ───────────────────────────────────────────────────────
    catalogo = _cargar_catalogo()
    if not catalogo:
        log.error("Catálogo vacío. No hay productos con precio > 0 en la BD.")
        sys.exit(1)

    # ── Estimación ────────────────────────────────────────────────────────────
    ticket_promedio_estimado = (TICKET_MIN + TICKET_MAX) // 2
    facturas_estimadas = TARGET_TOTAL // ticket_promedio_estimado

    log.info("=" * 60)
    log.info("  GENERADOR DE FACTURAS ELECTRÓNICAS — FERRETERÍA PUNTO ROJO")
    log.info("=" * 60)
    log.info("  Catálogo          : %d productos activos", len(catalogo))
    log.info("  Objetivo          : $%s", f"{TARGET_TOTAL:,}")
    log.info("  Tickets           : $%s – $%s", f"{TICKET_MIN:,}", f"{TICKET_MAX:,}")
    log.info("  Facturas aprox.   : ~%d", facturas_estimadas)
    log.info("  Fechas            : %s – %s", FECHA_INICIO, FECHA_FIN)
    log.info("  Método de pago    : %s", METODO_PAGO)
    log.info("  Modo              : %s", "DRY-RUN (sin insertar)" if dry_run else "PRODUCCIÓN")
    log.info("=" * 60)

    if dry_run:
        log.info("--- SIMULACIÓN (primeras 10 ventas) ---")
        for _ in range(10):
            target_ticket = random.randint(TICKET_MIN, TICKET_MAX)
            items = _generar_items(catalogo, target_ticket)
            total = sum(i["total"] for i in items)
            productos_str = ", ".join(
                f"{i['nombre']} x{int(i['cantidad'])}" for i in items
            )
            log.info("  $%s  —  %s", f"{total:,}", productos_str[:80])
        log.info("--- Fin simulación ---")
        return

    # ── Importar servicio de facturación ──────────────────────────────────────
    from services.facturacion_service import emitir_factura

    # ── Variables de control ──────────────────────────────────────────────────
    total_acumulado = 0
    facturas_ok     = 0
    facturas_error  = 0
    ventas_insertadas = 0
    num_dias = (FECHA_FIN - FECHA_INICIO).days + 1

    # ── Loop hasta alcanzar el target ─────────────────────────────────────────
    while total_acumulado < TARGET_TOTAL:
        restante = TARGET_TOTAL - total_acumulado

        # Ajustar rango de ticket al dinero que falta
        t_max = min(TICKET_MAX, restante)
        t_min = min(TICKET_MIN, restante)
        if t_max < t_min:
            t_max = t_min

        target_ticket = random.randint(t_min, t_max)

        # Fecha y hora aleatorias en el rango configurado
        offset = random.randint(0, num_dias - 1)
        fecha_v = FECHA_INICIO + timedelta(days=offset)
        hora_v  = f"{random.randint(8, 17):02d}:{random.randint(0, 59):02d}"

        # Generar ítems
        items = _generar_items(catalogo, target_ticket)
        if not items:
            continue

        total_venta = sum(i["total"] for i in items)

        # ── Insertar venta en BD ──────────────────────────────────────────────
        try:
            venta_id, consecutivo = _insertar_venta(items, fecha_v, hora_v)
            ventas_insertadas += 1
        except Exception as exc:
            log.error("Error insertando venta: %s", exc)
            continue

        total_acumulado += total_venta
        pct = total_acumulado / TARGET_TOTAL * 100

        log.info(
            "  [%5.1f%%] Venta #%d → $%s | acum: $%s",
            pct, consecutivo, f"{total_venta:,}", f"{total_acumulado:,}",
        )

        # ── Emitir factura electrónica ────────────────────────────────────────
        try:
            resultado = await emitir_factura(venta_id)
            if resultado.get("ok"):
                facturas_ok += 1
                log.info(
                    "         📄 %s emitida OK  (CUFE: %s…)",
                    resultado["numero"],
                    resultado.get("cufe", "")[:16],
                )
            else:
                facturas_error += 1
                log.warning(
                    "         ⚠️  Factura NO emitida venta_id=%d: %s",
                    venta_id, resultado.get("error", "error desconocido"),
                )
        except Exception as exc:
            facturas_error += 1
            log.error("         Error en emitir_factura(%d): %s", venta_id, exc)

        # Pausa para no saturar MATIAS API
        if PAUSA_SEG > 0:
            await asyncio.sleep(PAUSA_SEG)

    # ── Resumen final ─────────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 60)
    log.info("  🎉  PROCESO COMPLETADO")
    log.info("  Total acumulado    : $%s", f"{total_acumulado:,}")
    log.info("  Ventas insertadas  : %d", ventas_insertadas)
    log.info("  Facturas emitidas  : %d", facturas_ok)
    log.info("  Facturas con error : %d", facturas_error)
    if facturas_error:
        log.info("  ⚠️  Revisa el log 'generar_facturas.log' para los errores.")
        log.info("     Puedes reemitir facturas pendientes desde el dashboard:")
        log.info("     Facturación → Pendientes → Emitir una a una o en lote.")
    log.info("=" * 60)


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(_main(dry_run=dry_run))
