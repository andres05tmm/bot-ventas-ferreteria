"""
Generacion de graficas de ventas con matplotlib — fuente: PostgreSQL.
Reemplaza la lectura de EXCEL_FILE por queries a `ventas` + `ventas_detalle`.
"""

import asyncio
import calendar
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

import config
import db


# ── Helpers de periodo ────────────────────────────────────────────────────────

def _periodo_label() -> str:
    """Etiqueta legible del mes en curso para títulos de gráficas."""
    ahora = datetime.now(config.COLOMBIA_TZ)
    meses = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    return f"{meses[ahora.month - 1]} {ahora.year}"


def _rango_mes_actual() -> tuple[str, str]:
    """Retorna (inicio, fin) del mes en curso como 'YYYY-MM-DD'."""
    ahora     = datetime.now(config.COLOMBIA_TZ)
    inicio    = ahora.replace(day=1).strftime("%Y-%m-%d")
    ultimo    = calendar.monthrange(ahora.year, ahora.month)[1]
    fin       = ahora.replace(day=ultimo).strftime("%Y-%m-%d")
    return inicio, fin


# ── Gráfica 1: ventas por día ─────────────────────────────────────────────────

def generar_grafica_ventas_por_dia() -> str | None:
    """
    Barras: total vendido por día en el mes actual.
    Fuente: tabla `ventas` (columnas fecha, total).
    """
    inicio, fin = _rango_mes_actual()
    nombre_periodo = _periodo_label()

    filas = db.query_all(
        """
        SELECT fecha::text AS fecha,
               SUM(total)  AS total
        FROM   ventas
        WHERE  fecha BETWEEN %s AND %s
        GROUP  BY fecha
        ORDER  BY fecha
        """,
        (inicio, fin),
    )
    if not filas:
        return None

    ventas_por_dia: dict[str, float] = {
        str(r["fecha"]): float(r["total"]) for r in filas
    }
    fechas    = sorted(ventas_por_dia.keys())
    totales   = [ventas_por_dia[f] for f in fechas]
    etiquetas = [f[-5:] for f in fechas]          # MM-DD

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(etiquetas, totales, color="#1A56DB", edgecolor="white", linewidth=0.5)
    ax.set_title(f"Ventas por día — {nombre_periodo}", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Fecha", fontsize=11)
    ax.set_ylabel("Total ($)", fontsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.set_facecolor("#F9FAFB")
    fig.patch.set_facecolor("#FFFFFF")

    max_val = max(totales) if totales else 1
    for bar, valor in zip(bars, totales):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_val * 0.01,
            f"${valor:,.0f}",
            ha="center", va="bottom", fontsize=8, color="#374151",
        )

    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    ruta = f"grafica_dias_{datetime.now(config.COLOMBIA_TZ).strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()
    return ruta


# ── Gráfica 2: productos más vendidos ────────────────────────────────────────

def generar_grafica_productos() -> str | None:
    """
    Pie: top productos por monto vendido en el mes actual.
    Fuente: `ventas_detalle` JOIN `ventas` (columnas producto_nombre, total, fecha).
    """
    inicio, fin = _rango_mes_actual()
    nombre_periodo = _periodo_label()

    filas = db.query_all(
        """
        SELECT vd.producto_nombre,
               SUM(vd.total) AS total
        FROM   ventas_detalle vd
        JOIN   ventas v ON vd.venta_id = v.id
        WHERE  v.fecha BETWEEN %s AND %s
        GROUP  BY vd.producto_nombre
        ORDER  BY total DESC
        """,
        (inicio, fin),
    )
    if not filas:
        return None

    items = [(str(r["producto_nombre"]).strip(), float(r["total"])) for r in filas]
    top          = items[:7]
    otros_total  = sum(v for _, v in items[7:])
    if otros_total > 0:
        top.append(("Otros", otros_total))

    etiquetas = [item[0] for item in top]
    valores   = [item[1] for item in top]
    colores   = [
        "#1A56DB", "#3B82F6", "#60A5FA", "#93C5FD",
        "#BFDBFE", "#DBEAFE", "#EFF6FF", "#CBD5E1",
    ]

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, _, autotexts = ax.pie(
        valores,
        labels=None,
        autopct="%1.1f%%",
        colors=colores[: len(valores)],
        startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color("white")
        at.set_fontweight("bold")

    ax.legend(
        wedges,
        [f"{e} (${v:,.0f})" for e, v in zip(etiquetas, valores)],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        fontsize=8,
        frameon=False,
    )
    ax.set_title(
        f"Productos más vendidos — {nombre_periodo}",
        fontsize=13, fontweight="bold", pad=15,
    )
    plt.tight_layout()

    ruta = f"grafica_productos_{datetime.now(config.COLOMBIA_TZ).strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close()
    return ruta


# ── Wrappers async ────────────────────────────────────────────────────────────

async def generar_grafica_ventas_por_dia_async():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, generar_grafica_ventas_por_dia)


async def generar_grafica_productos_async():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, generar_grafica_productos)
