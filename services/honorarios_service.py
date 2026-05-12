"""
services/honorarios_service.py — Generación y envío de Cuentas de Cobro.

Flujo:
    generar_cuenta_cobro()
      ├─ _siguiente_consecutivo()   ← atómico en BD
      ├─ _generar_pdf()             ← fpdf2
      ├─ _guardar_en_db()           ← INSERT en cuentas_cobro
      └─ _enviar_telegram()         ← send_document()
"""

# -- stdlib --
import io
import logging
import os
from datetime import datetime

# -- terceros --
from fpdf import FPDF

# -- propios --
import db as _db
from config import COLOMBIA_TZ, HONORARIOS_VALOR, HONORARIOS_CHAT_ID

log = logging.getLogger("ferrebot.honorarios")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

EMISOR = {
    "nombre":   "Andrés Felipe Malo Hernández",
    "cc":       "1.043.295.412",
    "nit":      "1043295412-4",
    "direccion": "CON el Refugio BL 12 AP 2A",
    "ciudad":   "Cartagena, Bolívar",
    "regimen":  "No responsable de IVA — Artículo 437 E.T.",
}

RECEPTOR = {
    "nombre":  "Ferretería Punto Rojo F.D",
    "nit":     "1235046119-1",
    "ciudad":  "Cartagena, Bolívar",
}

CONCEPTO_DEFAULT = (
    "Servicios de desarrollo de software, soporte técnico y mantenimiento "
    "del sistema de gestión integral (POS, inventario, facturación electrónica "
    "DIAN y bot de ventas Telegram) para Ferretería Punto Rojo."
)

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo",  6: "junio",   7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


# ─────────────────────────────────────────────────────────────────────────────
# API PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────

class PeriodoYaExisteError(Exception):
    """Se lanza cuando ya existe una CC para el período solicitado."""
    def __init__(self, numero_display: str, periodo: str):
        self.numero_display = numero_display
        self.periodo = periodo
        super().__init__(f"CC-{numero_display} ya existe para {periodo}")


async def generar_cuenta_cobro(
    bot=None,
    valor: int | None = None,
    concepto: str | None = None,
    fecha_override: datetime | None = None,
    forzar: bool = False,
) -> dict:
    """
    Genera una Cuenta de Cobro, la persiste en BD y la envía por Telegram.

    Parámetros:
        bot             — instancia de telegram.Bot; si None, solo genera sin enviar
        valor           — monto a cobrar; si None usa HONORARIOS_VALOR de config
        concepto        — descripción del servicio; si None usa CONCEPTO_DEFAULT
        fecha_override  — fecha para el documento; si None usa datetime.now(COLOMBIA_TZ)
        forzar          — si True, genera aunque ya exista una CC para el período

    Lanza PeriodoYaExisteError si ya hay una CC para el período y forzar=False.
    Retorna dict con: consecutivo, numero_display, periodo, valor, pdf_bytes
    """
    ahora    = fecha_override or datetime.now(COLOMBIA_TZ)
    valor    = valor or HONORARIOS_VALOR
    concepto = concepto or CONCEPTO_DEFAULT

    periodo = f"{MESES_ES[ahora.month].capitalize()} {ahora.year}"

    if not forzar:
        existente = _db.query_one(
            "SELECT numero_display FROM cuentas_cobro WHERE periodo = %s ORDER BY consecutivo DESC LIMIT 1",
            [periodo],
        )
        if existente:
            raise PeriodoYaExisteError(existente["numero_display"], periodo)

    consecutivo    = _siguiente_consecutivo()
    numero_display = f"{consecutivo:03d}"
    fecha_str      = ahora.strftime("%d de %B de %Y").replace(
        ahora.strftime("%B"), MESES_ES[ahora.month]
    )

    pdf_bytes = _generar_pdf(
        numero_display=numero_display,
        fecha_str=fecha_str,
        periodo=periodo,
        concepto=concepto,
        valor=valor,
    )

    _guardar_en_db(
        consecutivo=consecutivo,
        numero_display=numero_display,
        fecha=ahora.date(),
        periodo=periodo,
        concepto=concepto,
        valor=valor,
        pdf_bytes=pdf_bytes,
    )

    enviado = False
    if bot:
        enviado = await _enviar_telegram(
            bot=bot,
            pdf_bytes=pdf_bytes,
            numero_display=numero_display,
            periodo=periodo,
            valor=valor,
        )
        if enviado:
            _db.execute(
                "UPDATE cuentas_cobro SET enviado_telegram = TRUE WHERE consecutivo = %s",
                [consecutivo],
            )

    log.info(f"Cuenta de Cobro CC-{numero_display} generada — ${valor:,.0f} — {periodo}")

    return {
        "consecutivo":    consecutivo,
        "numero_display": numero_display,
        "periodo":        periodo,
        "valor":          valor,
        "pdf_bytes":      pdf_bytes,
        "enviado":        enviado,
    }


def listar_cuentas(limit: int = 20) -> list[dict]:
    """Retorna las últimas N cuentas de cobro generadas."""
    rows = _db.query_all(
        """
        SELECT id, consecutivo, numero_display, fecha::text, periodo,
               valor, enviado_telegram, creado_at::text
        FROM cuentas_cobro
        ORDER BY consecutivo DESC
        LIMIT %s
        """,
        [limit],
    )
    return [dict(r) for r in rows] if rows else []


def obtener_pdf(consecutivo: int) -> bytes | None:
    """Retorna los bytes del PDF para un consecutivo dado."""
    row = _db.query_one(
        "SELECT pdf_bytes FROM cuentas_cobro WHERE consecutivo = %s",
        [consecutivo],
    )
    return bytes(row["pdf_bytes"]) if row and row["pdf_bytes"] else None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _siguiente_consecutivo() -> int:
    """Obtiene el próximo consecutivo de forma atómica (SELECT MAX + 1)."""
    row = _db.query_one(
        "SELECT COALESCE(MAX(consecutivo), 0) + 1 AS siguiente FROM cuentas_cobro"
    )
    return row["siguiente"] if row else 1


def _generar_pdf(
    numero_display: str,
    fecha_str: str,
    periodo: str,
    concepto: str,
    valor: int,
) -> bytes:
    """
    Genera el PDF de la Cuenta de Cobro usando fpdf2.
    Retorna los bytes del PDF.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)

    ancho = 170  # ancho útil (A4=210 - 2*20 márgenes)

    # ── Encabezado ─────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(ancho, 10, "CUENTA DE COBRO / RECIBO DE HONORARIOS", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ancho, 6, f"No. CC-{numero_display}  |  {fecha_str}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Línea separadora
    pdf.set_draw_color(200, 32, 14)  # rojo ferretería
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(5)

    # ── Datos del emisor ────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho, 6, "DATOS DEL PRESTADOR DEL SERVICIO", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ancho, 5, f"Nombre:    {EMISOR['nombre']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(ancho, 5, f"C.C.:      {EMISOR['cc']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(ancho, 5, f"NIT:       {EMISOR['nit']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(ancho, 5, f"Dirección: {EMISOR['direccion']}, {EMISOR['ciudad']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Datos del receptor ──────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho, 6, "DATOS DEL CONTRATANTE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ancho, 5, f"Empresa: {RECEPTOR['nombre']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(ancho, 5, f"NIT:     {RECEPTOR['nit']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(ancho, 5, f"Ciudad:  {RECEPTOR['ciudad']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Tabla de concepto y valor ───────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho, 6, "DETALLE DEL SERVICIO", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # Encabezados tabla
    pdf.set_fill_color(200, 32, 14)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(120, 7, "CONCEPTO", border=1, fill=True)
    pdf.cell(50,  7, "VALOR",    border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

    # Fila concepto
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    col_concepto_x = pdf.get_x()
    col_concepto_y = pdf.get_y()
    pdf.multi_cell(120, 5, f"Período: {periodo}\nContrato: PSV-001-2026\n{concepto}", border=1)
    y_after = pdf.get_y()

    pdf.set_xy(col_concepto_x + 120, col_concepto_y)
    valor_fmt = f"$ {valor:,.0f}".replace(",", ".")
    pdf.cell(50, y_after - col_concepto_y, valor_fmt, border=1, align="R")
    pdf.ln()

    # Fila IVA
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(120, 6, "IVA (No responsable de IVA)", border=1)
    pdf.cell(50,  6, "$ 0",                          border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    # Fila total
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(120, 7, "TOTAL A PAGAR", border=1, fill=True)
    pdf.cell(50,  7, valor_fmt, border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # ── Leyenda legal ──────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(
        ancho, 4,
        "El prestador del servicio NO ES RESPONSABLE DE IVA conforme al artículo 437 "
        "del Estatuto Tributario colombiano y sus modificaciones. Este documento no "
        "equivale a factura de venta.",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(10)

    # ── Firma ──────────────────────────────────────────────────────────────
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)

    # Imágenes de firma: ~150 pt → 52 mm; 20 mm de espacio reservado
    _SIG_W_MM = 52
    _SIG_H_MM = 20
    firmas_base = os.getenv("FIRMAS_PATH", "assets/firmas")
    firma_y = pdf.get_y()

    try:
        ruta = os.path.join(firmas_base, "firma_andres.png")
        pdf.image(ruta, x=20 + (80 - _SIG_W_MM) / 2, y=firma_y, w=_SIG_W_MM)
    except Exception:
        pass

    try:
        ruta = os.path.join(firmas_base, "firma_farid.png")
        pdf.image(ruta, x=110 + (80 - _SIG_W_MM) / 2, y=firma_y, w=_SIG_W_MM)
    except Exception:
        pass

    pdf.set_y(firma_y + _SIG_H_MM)

    pdf.cell(80, 5, "_" * 35)
    pdf.cell(10, 5, "")
    pdf.cell(80, 5, "_" * 35, new_x="LMARGIN", new_y="NEXT")

    pdf.cell(80, 5, "Firma Prestador del Servicio", align="C")
    pdf.cell(10, 5, "")
    pdf.cell(80, 5, "Firma / Sello Contratante",    align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(80, 4, EMISOR["nombre"],   align="C")
    pdf.cell(10, 4, "")
    pdf.cell(80, 4, RECEPTOR["nombre"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(80, 4, f"C.C. {EMISOR['cc']}", align="C", new_x="LMARGIN", new_y="NEXT")

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def _guardar_en_db(
    consecutivo: int,
    numero_display: str,
    fecha,
    periodo: str,
    concepto: str,
    valor: int,
    pdf_bytes: bytes,
) -> None:
    """Persiste el registro en cuentas_cobro."""
    _db.execute(
        """
        INSERT INTO cuentas_cobro
            (consecutivo, numero_display, fecha, periodo, concepto, valor, pdf_bytes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (consecutivo) DO NOTHING
        """,
        [consecutivo, numero_display, fecha, periodo, concepto, valor,
         bytes(pdf_bytes)],
    )


async def _enviar_telegram(
    bot,
    pdf_bytes: bytes,
    numero_display: str,
    periodo: str,
    valor: int,
) -> bool:
    """
    Envía el PDF al chat configurado en HONORARIOS_CHAT_ID.
    Retorna True si el envío fue exitoso.
    """
    chat_id = HONORARIOS_CHAT_ID or None

    if not chat_id:
        raw = os.getenv("AUTHORIZED_CHAT_IDS", "")
        ids = [x.strip() for x in raw.split(",") if x.strip()]
        chat_id = ids[0] if ids else None

    if not chat_id:
        log.warning("HONORARIOS_CHAT_ID no configurado — PDF no enviado por Telegram")
        return False

    valor_fmt = f"${valor:,.0f}".replace(",", ".")
    caption = (
        f"*Cuenta de Cobro CC-{numero_display}*\n"
        f"Período: {periodo}\n"
        f"Valor: *{valor_fmt} COP*\n"
        f"IVA: $0 (No responsable)\n\n"
        f"_Andrés Felipe Malo Hernández — NIT 1043295412-4_"
    )

    try:
        await bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(pdf_bytes),
            filename=f"CuentaCobro_CC-{numero_display}_{periodo.replace(' ', '_')}.pdf",
            caption=caption,
            parse_mode="Markdown",
        )
        log.info(f"PDF enviado a chat {chat_id}")
        return True
    except Exception as e:
        log.warning(f"No se pudo enviar PDF por Telegram: {e}")
        return False
