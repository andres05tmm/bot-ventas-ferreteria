#!/usr/bin/env python3
"""
generar_facturas.py — Generador masivo de ventas + facturas electrónicas DIAN

Genera ventas desde el catálogo real de la ferretería y emite cada una como
factura electrónica a la DIAN vía MATIAS API, hasta alcanzar el monto objetivo.
Todas a CONSUMIDOR FINAL (la venta va sin cliente_id → el emisor resuelve
identity_document_id=6 / dni 222222222222).

Uso:
    python generar_facturas.py --dry-run           # simula, no toca nada
    python generar_facturas.py --limite 3          # piloto: 3 facturas reales
    python generar_facturas.py                     # corrida completa

Flags:
    --dry-run          simula tickets y distribución, NO inserta ni emite
    --limite N         corta después de N facturas emitidas (piloto)
    --target N         monto objetivo en COP (default 11.000.000)
    --fecha YYYY-MM-DD fecha DIAN de los documentos (default: hoy Colombia)

Variables de entorno: DATABASE_URL y MATIAS_* (las mismas del proyecto).

REGLAS DE ESTA CORRIDA (30-sep-2026)
  1. Sin tornillería: se excluye la categoría '3 Tornilleria' y cualquier
     nombre con tornillo/tuerca/arandela/perno/... (5 sueltos en otra categoría).
  2. Tickets entre $40.000 y $300.000, sesgados hacia abajo (~80% < $100.000,
     ~5% > $150.000).
  3. Todas a Consumidor Final.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sys
from datetime import date, datetime

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# config.py exige claves del bot que este script no usa
os.environ.setdefault("TELEGRAM_TOKEN",    "dummy_not_needed_by_this_script")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy_not_needed_by_this_script")
os.environ.setdefault("OPENAI_API_KEY",    "dummy_not_needed_by_this_script")

# ── Parámetros ────────────────────────────────────────────────────────────────

TARGET_TOTAL = 11_000_000

TICKET_MIN = 40_000
TICKET_MAX = 300_000

# Distribución del ticket: (min, max, peso). Sesgada a tickets chicos —
# ~80% de las facturas quedan bajo $100.000 y ~5% sobre $150.000.  Media ≈ $85.000.
BANDAS = [
    (40_000,  70_000,  45),
    (70_000,  100_000, 35),
    (100_000, 150_000, 15),
    (150_000, 300_000,  5),
]

METODO_PAGO = "efectivo"
VENDEDOR    = "Dashboard"   # marca las ventas generadas vs. las reales

MAX_ITEMS_POR_VENTA = 4
MAX_CANT_POR_ITEM   = 50
PAUSA_SEG           = 0.3   # respeta el rate limit de MATIAS
MAX_FALLOS_SEGUIDOS = 5     # aborta si la DIAN/MATIAS empieza a rechazar en serie

# Tornillería: categoría completa + los que se colaron en otras categorías
CATEGORIA_EXCLUIDA = "3 Tornilleria"
RE_TORNILLERIA = (
    r"tornill|tuerca|arandela|perno|remache|chazo|tirafondo|"
    r"esp[áa]rrago|golosa|autoperforante"
)

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


# ── Catálogo ──────────────────────────────────────────────────────────────────

def _cargar_catalogo() -> list[dict]:
    """Productos activos con precio, SIN tornillería."""
    import db as _db

    rows = _db.query_all(
        """
        SELECT id,
               nombre,
               precio_unidad                     AS precio,
               COALESCE(unidad_medida, 'Unidad') AS unidad_medida
        FROM productos
        WHERE precio_unidad > 0
          AND activo = true
          AND nombre IS NOT NULL
          AND nombre != ''
          AND COALESCE(categoria, '') <> %s
          AND COALESCE(nombre_lower, lower(nombre)) !~ %s
        ORDER BY nombre
        """,
        (CATEGORIA_EXCLUIDA, RE_TORNILLERIA),
    )
    return [dict(r) for r in (rows or [])]


# ── Armado de un ticket ───────────────────────────────────────────────────────

def _objetivo_ticket() -> int:
    lo, hi, _ = random.choices(BANDAS, weights=[b[2] for b in BANDAS])[0]
    return random.randint(lo, hi)


def _objetivo_y_piso(restante: int) -> tuple[int, int]:
    """
    Objetivo del próximo ticket y piso aceptable.

    Mientras sobre plata se sortea de las bandas. Al final, el ticket se ajusta
    a lo que falta pero nunca baja de TICKET_MIN: la corrida se pasa del objetivo
    por menos de un ticket mínimo en vez de emitir una factura de cola de $2.700.
    """
    if restante > TICKET_MAX:
        return _objetivo_ticket(), TICKET_MIN
    return max(restante, TICKET_MIN), TICKET_MIN


def _item(prod: dict, cant: int) -> dict:
    precio = int(prod["precio"])
    return {
        "nombre":        prod["nombre"],
        "cantidad":      float(cant),
        "precio_unit":   precio,
        "total":         precio * cant,
        "unidad_medida": prod["unidad_medida"],
        "producto_id":   prod["id"],
    }


def _intento_ticket(catalogo: list[dict], objetivo: int,
                    usos: dict[int, int] | None = None) -> list[dict]:
    """
    Arma 2–MAX_ITEMS productos distintos apuntando a `objetivo`.

    Los ítems intermedios son chicos (no pasan del 60% del objetivo) y el último
    es el que rellena: se elige entre los productos cuyo precio permite acercarse
    al restante con una cantidad razonable (1..MAX_CANT_POR_ITEM).

    `usos` cuenta cuántas veces se usó cada producto como relleno en la corrida:
    el relleno se reparte entre los menos usados y se prefiere precio no redondo,
    para que no salgan facturas de una sola línea con el mismo monto redondo.
    """
    usos = usos if usos is not None else {}
    n_extra = random.choice([1, 1, 1, 2, 2, MAX_ITEMS_POR_VENTA - 1])
    elegidos = random.sample(catalogo, min(n_extra + 1, len(catalogo)))

    items: list[dict] = []
    acum = 0

    for prod in elegidos[:-1]:
        precio = int(prod["precio"])
        cant = random.randint(1, 6)
        if precio * cant > objetivo * 0.6:
            continue
        items.append(_item(prod, cant))
        acum += precio * cant

    restante = objetivo - acum
    if restante <= 0:
        return items

    # El relleno: precio que alcance el restante con cantidad razonable
    ya_usados = {i["producto_id"] for i in items}
    cands = [
        p for p in catalogo
        if int(p["precio"]) <= restante
        and int(p["precio"]) * MAX_CANT_POR_ITEM >= restante
        and p["id"] not in ya_usados
    ]
    if not cands:
        return []

    # Repartir entre los menos usados, y preferir precio no redondo para que el
    # total de la factura no caiga siempre en múltiplos de $10.000.
    menos = min(usos.get(p["id"], 0) for p in cands)
    frescos = [p for p in cands if usos.get(p["id"], 0) <= menos]
    no_redondos = [p for p in frescos if int(p["precio"]) % 1000]
    pool = no_redondos if (no_redondos and random.random() < 0.7) else frescos

    prod = random.choice(pool)
    precio = int(prod["precio"])
    cant = max(1, min(round(restante / precio), MAX_CANT_POR_ITEM))
    items.append(_item(prod, cant))
    return items


def generar_ticket(catalogo: list[dict], objetivo: int,
                   piso: int = TICKET_MIN, techo: int = TICKET_MAX,
                   usos: dict[int, int] | None = None) -> list[dict]:
    """
    Reintenta hasta que el total caiga dentro de [piso, techo], prefiriendo
    tickets de 2+ líneas. Si en 200 intentos solo logra uno de una línea dentro
    de rango, devuelve ese. [] si no logra ninguno.
    """
    usos = usos if usos is not None else {}
    respaldo: list[dict] = []
    for _ in range(200):
        items = _intento_ticket(catalogo, objetivo, usos)
        if not items:
            continue
        total = sum(i["total"] for i in items)
        if not piso <= total <= techo or total in _TOTALES_VISTOS:
            continue
        if len(items) >= 2:
            respaldo = items
            break
        respaldo = respaldo or items
    for i in respaldo:
        usos[i["producto_id"]] = usos.get(i["producto_id"], 0) + 1
    if respaldo:
        # Un producto sale en hasta MAX_USOS_DIA facturas del día, y ningún monto se repite.
        _TOTALES_VISTOS.add(sum(i["total"] for i in respaldo))
        for i in respaldo:
            _USOS_DIA[i["producto_id"]] = _USOS_DIA.get(i["producto_id"], 0) + 1
        catalogo[:] = [p for p in catalogo if _USOS_DIA.get(p["id"], 0) < MAX_USOS_DIA]
    return respaldo


_TOTALES_VISTOS: set[int] = set()
_USOS_DIA: dict[int, int] = {}  # producto_id → facturas del día en que ya salió
MAX_USOS_DIA = 1                # --max-usos-dia; 1 = cada producto en UNA sola factura


def _descontar_lo_ya_emitido(catalogo: list[dict], fecha_v: date) -> None:
    """Saca del catálogo lo ya facturado hoy por este script (corridas previas)."""
    import db as _db

    rows = _db.query_all(
        """
        SELECT v.id, v.total, d.producto_id
        FROM ventas v JOIN ventas_detalle d ON d.venta_id = v.id
        WHERE v.fecha = %s AND v.vendedor = %s
        """,
        (str(fecha_v), VENDEDOR),
    ) or []
    _TOTALES_VISTOS.update(int(r["total"]) for r in rows)
    for _venta_id, pid in {(r["id"], r["producto_id"]) for r in rows}:
        _USOS_DIA[pid] = _USOS_DIA.get(pid, 0) + 1
    catalogo[:] = [p for p in catalogo if _USOS_DIA.get(p["id"], 0) < MAX_USOS_DIA]


# ── Inserción en PostgreSQL ───────────────────────────────────────────────────

def _insertar_venta(items: list[dict], fecha_v: date, hora_str: str) -> tuple[int, int]:
    """
    Inserta venta + detalle. Retorna (venta_id, consecutivo).

    El consecutivo de ventas REINICIA cada día en este sistema (lo asigna el
    dashboard por fecha), así que se toma el máximo del día, no el global.
    """
    import db as _db

    total = sum(i["total"] for i in items)

    with _db._get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(consecutivo), 0) + 1 AS sig FROM ventas WHERE fecha = %s",
                (str(fecha_v),),
            )
            consecutivo = cur.fetchone()["sig"]

            cur.execute(
                """
                INSERT INTO ventas
                    (consecutivo, fecha, hora, vendedor, metodo_pago,
                     total, cliente_nombre, cliente_id, usuario_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'Consumidor Final', NULL, NULL)
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
                    (venta_id, item["nombre"], item["cantidad"], item["precio_unit"],
                     item["total"], item["unidad_medida"], item["producto_id"]),
                )
        conn.commit()

    return venta_id, consecutivo


# ── Simulación ────────────────────────────────────────────────────────────────

def _simular(catalogo: list[dict], target: int) -> None:
    """Simula la corrida completa y reporta la distribución real de tickets."""
    totales: list[int] = []
    lineas: list[int] = []
    usos: dict[int, int] = {}
    acum = 0
    sin_ticket = 0
    while acum < target and sin_ticket < 10:
        objetivo, piso = _objetivo_y_piso(target - acum)
        items = generar_ticket(catalogo, objetivo, piso, TICKET_MAX, usos)
        if not items:
            sin_ticket += 1
            continue
        sin_ticket = 0
        t = sum(i["total"] for i in items)
        totales.append(t)
        lineas.append(len(items))
        acum += t

    fuera = [t for t in totales if not TICKET_MIN <= t <= TICKET_MAX]
    bajo_100k = sum(1 for t in totales if t <= 100_000)
    una_linea = sum(1 for n in lineas if n == 1)
    repes = len(totales) - len(set(totales))
    top_uso = max(usos.values()) if usos else 0

    log.info("  Facturas          : %d", len(totales))
    log.info("  Total             : $%s", f"{acum:,}")
    log.info("  Ticket promedio   : $%s", f"{acum // len(totales):,}")
    log.info("  <= $100.000       : %d (%.0f%%)", bajo_100k, bajo_100k / len(totales) * 100)
    log.info("  Mín / máx         : $%s / $%s", f"{min(totales):,}", f"{max(totales):,}")
    log.info("  Líneas promedio   : %.1f  (de una sola línea: %d)",
             sum(lineas) / len(lineas), una_linea)
    log.info("  Montos repetidos  : %d de %d facturas", repes, len(totales))
    log.info("  Producto más usado: %d veces (de %d en catálogo)", top_uso, len(catalogo))
    log.info("  Fuera de rango    : %d", len(fuera))
    assert not fuera, f"tickets fuera de [{TICKET_MIN}, {TICKET_MAX}]: {fuera[:5]}"
    assert acum >= target, "la simulación no alcanzó el objetivo"

    log.info("--- muestra de 8 tickets ---")
    for _ in range(8):
        items = generar_ticket(catalogo, _objetivo_ticket(), usos=usos)
        det = ", ".join(f"{i['nombre']} x{int(i['cantidad'])}" for i in items)
        log.info("  $%9s  —  %s", f"{sum(i['total'] for i in items):,}", det[:90])


# ── Loop principal ────────────────────────────────────────────────────────────

async def _main(args) -> None:
    try:
        import db as _db
    except ImportError:
        log.error("Corré el script desde la raíz del proyecto (cd bot-ventas-ferreteria).")
        sys.exit(1)

    _db.init_db()
    if not _db.DB_DISPONIBLE:
        log.error("Base de datos no disponible. Verificá DATABASE_URL.")
        sys.exit(1)

    if not args.dry_run and not os.getenv("MATIAS_EMAIL"):
        log.error("Falta MATIAS_EMAIL. Cargá las variables MATIAS_* antes de correr.")
        sys.exit(1)

    catalogo = _cargar_catalogo()
    if not catalogo:
        log.error("Catálogo vacío tras excluir tornillería.")
        sys.exit(1)

    from config import COLOMBIA_TZ
    hoy = datetime.now(COLOMBIA_TZ).date()
    fecha_v = (
        datetime.strptime(args.fecha, "%Y-%m-%d").date() if args.fecha else hoy
    )
    if fecha_v > hoy:
        log.error("La DIAN rechaza documentos con fecha futura (%s > %s).", fecha_v, hoy)
        sys.exit(1)

    global MAX_USOS_DIA
    MAX_USOS_DIA = args.max_usos_dia
    _descontar_lo_ya_emitido(catalogo, fecha_v)

    log.info("=" * 64)
    log.info("  FACTURAS ELECTRÓNICAS — FERRETERÍA PUNTO ROJO")
    log.info("=" * 64)
    log.info("  Catálogo (sin tornillería) : %d productos", len(catalogo))
    log.info("  Objetivo                   : $%s", f"{args.target:,}")
    log.info("  Tickets                    : $%s – $%s (sesgo bajo)",
             f"{TICKET_MIN:,}", f"{TICKET_MAX:,}")
    log.info("  Fecha DIAN                 : %s", fecha_v)
    log.info("  Cliente                    : Consumidor Final")
    log.info("  Método de pago / vendedor  : %s / %s", METODO_PAGO, VENDEDOR)
    log.info("  Límite de facturas         : %s", args.limite or "sin límite")
    log.info("  Modo                       : %s",
             "DRY-RUN (no inserta ni emite)" if args.dry_run
             else "PRODUCCIÓN — EMITE A LA DIAN")
    log.info("=" * 64)

    if args.dry_run:
        _simular(catalogo, args.target)
        return

    from services.facturacion_service import emitir_factura

    total_acumulado = 0
    facturas_ok = facturas_error = 0
    fallos_seguidos = 0
    sin_ticket = 0
    usos: dict[int, int] = {}

    while total_acumulado < args.target:
        if args.limite and facturas_ok >= args.limite:
            log.info("Límite de %d facturas alcanzado — corte del piloto.", args.limite)
            break

        objetivo, piso = _objetivo_y_piso(args.target - total_acumulado)
        items = generar_ticket(catalogo, objetivo, piso, TICKET_MAX, usos)
        if not items:
            sin_ticket += 1
            log.warning("No se pudo armar un ticket de ~$%s (%d seguidos).",
                        f"{objetivo:,}", sin_ticket)
            if sin_ticket >= 10:
                log.info("Quedan $%s sin repartir — corte.",
                         f"{args.target - total_acumulado:,}")
                break
            continue
        sin_ticket = 0

        total_venta = sum(i["total"] for i in items)
        hora_v = f"{random.randint(8, 18):02d}:{random.randint(0, 59):02d}"

        try:
            venta_id, consecutivo = _insertar_venta(items, fecha_v, hora_v)
        except Exception as exc:
            log.error("Error insertando venta: %s", exc)
            continue

        total_acumulado += total_venta
        pct = total_acumulado / args.target * 100
        log.info("  [%5.1f%%] Venta #%d (id %d) → $%s | acum: $%s",
                 pct, consecutivo, venta_id, f"{total_venta:,}", f"{total_acumulado:,}")

        try:
            resultado = await emitir_factura(venta_id, fecha_emision=str(fecha_v))
        except Exception as exc:
            resultado = {"ok": False, "error": f"excepción: {exc}"}

        if resultado.get("ok"):
            facturas_ok += 1
            fallos_seguidos = 0
            log.info("         [OK] %s emitida (CUFE %s...)",
                     resultado["numero"], resultado.get("cufe", "")[:16])
        else:
            facturas_error += 1
            fallos_seguidos += 1
            log.warning("         [ERR] venta_id=%d NO emitida: %s",
                        venta_id, resultado.get("error", "error desconocido"))
            if fallos_seguidos >= MAX_FALLOS_SEGUIDOS:
                log.error("%d rechazos seguidos — ABORTO para no quemar consecutivos.",
                          fallos_seguidos)
                break

        if PAUSA_SEG:
            await asyncio.sleep(PAUSA_SEG)

    log.info("")
    log.info("=" * 64)
    log.info("  Total facturado    : $%s de $%s", f"{total_acumulado:,}", f"{args.target:,}")
    log.info("  Facturas emitidas  : %d", facturas_ok)
    log.info("  Facturas con error : %d", facturas_error)
    if total_acumulado < args.target:
        log.info("  Falta              : $%s  → --target %d para continuar",
                 f"{args.target - total_acumulado:,}", args.target - total_acumulado)
    log.info("=" * 64)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--target", type=int, default=TARGET_TOTAL)
    ap.add_argument("--fecha", type=str, default=None)
    ap.add_argument("--max-usos-dia", type=int, default=1,
                    help="en cuántas facturas del día puede salir un mismo producto")
    asyncio.run(_main(ap.parse_args()))
