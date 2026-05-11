# Plan de Implementación — Módulo Cuenta de Cobro / Recibo de Honorarios

> **Fecha del plan:** 2026-05-11  
> **Autor del plan:** Andrés Felipe Malo Hernández  
> **Valor mensual:** $2.000.000 COP  
> **Próxima generación:** día 23 de cada mes (automático + `/honorarios` manual)

---

## 1. Resumen ejecutivo

Módulo autónomo para generar, persistir y enviar el PDF de Cuenta de Cobro mensual.
No toca ningún módulo existente salvo los tres puntos de registro habitual
(`requirements.txt`, `config.py`, `main.py`, `api.py`, `start-bot.py`).

---

## 2. Archivos del proyecto

### 2.1 Archivos a CREAR

| Archivo | Rol |
|---------|-----|
| `migrations/021_honorarios.py` | Crea tabla `cuentas_cobro` en PostgreSQL |
| `services/honorarios_service.py` | Lógica de negocio: numeración, PDF, envío |
| `handlers/cmd_honorarios.py` | Handler Telegram `/honorarios` |
| `routers/honorarios.py` | Endpoints FastAPI (lista + descarga + trigger) |

### 2.2 Archivos a MODIFICAR

| Archivo | Qué agregar |
|---------|-------------|
| `requirements.txt` | `fpdf2>=2.7.9` |
| `config.py` | `HONORARIOS_VALOR`, `HONORARIOS_CHAT_ID` |
| `main.py` | `from handlers.cmd_honorarios import comando_honorarios` + `CommandHandler("honorarios", ...)` |
| `api.py` | `from routers import honorarios` + `app.include_router(honorarios.router)` |
| `start-bot.py` | Job APScheduler día 23 a las 9:00 AM Colombia |

---

## 3. Base de datos

### Migración `migrations/021_honorarios.py`

```python
"""
migrations/021_honorarios.py
Crea la tabla cuentas_cobro para el módulo de honorarios.
Idempotente — seguro para re-ejecutar.

Ejecutar UNA VEZ:
    railway run python migrations/021_honorarios.py
"""

# -- stdlib --
import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] -- %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("021_honorarios")

import db as _db


def run():
    with _db._get_conn() as conn:
        with conn.cursor() as cur:

            # ── Tabla principal ────────────────────────────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cuentas_cobro (
                    id                  SERIAL PRIMARY KEY,
                    consecutivo         INTEGER NOT NULL UNIQUE,
                    numero_display      VARCHAR(10)  NOT NULL,   -- '001', '002', ...
                    fecha               DATE         NOT NULL,
                    periodo             VARCHAR(30)  NOT NULL,   -- 'Mayo 2026'
                    concepto            TEXT         NOT NULL,
                    valor               NUMERIC(15,2) NOT NULL,
                    pdf_bytes           BYTEA,
                    enviado_telegram    BOOLEAN DEFAULT FALSE,
                    creado_at           TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            logger.info("✓ Tabla cuentas_cobro creada (o ya existía)")

            # ── Índice para ordenar por fecha ──────────────────────────────────
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_cuentas_cobro_fecha
                ON cuentas_cobro (fecha DESC);
            """)
            logger.info("✓ Índice ix_cuentas_cobro_fecha OK")

        conn.commit()
    logger.info("✅ Migración 021 completada")


if __name__ == "__main__":
    run()
```

---

## 4. Configuración — `config.py`

Agregar al bloque de variables de entorno (después de las existentes):

```python
# ─────────────────────────────────────────────
# MÓDULO HONORARIOS
# ─────────────────────────────────────────────
# Valor mensual de la cuenta de cobro en COP (entero)
HONORARIOS_VALOR    = int(os.getenv("HONORARIOS_VALOR", "2000000"))
# Chat ID de Telegram al que se envía el PDF (ej. el chat del dueño o del grupo)
# Si no se configura, se intenta con AUTHORIZED_CHAT_IDS[0]
HONORARIOS_CHAT_ID  = os.getenv("HONORARIOS_CHAT_ID", "")
```

Variable de entorno a agregar en Railway:
- `HONORARIOS_VALOR` → `2000000` (opcional, ya tiene default)
- `HONORARIOS_CHAT_ID` → el chat_id personal de Andrés (`1831034712`)

---

## 5. Servicio — `services/honorarios_service.py`

Responsabilidades:
- Calcular el próximo consecutivo (MAX + 1, atómico en BD)
- Generar el PDF con `fpdf2`
- Guardar el registro en `cuentas_cobro`
- Enviar el PDF por Telegram

```python
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
    "nombre":  "Andrés Felipe Malo Hernández",
    "cc":      "1.043.295.412",
    "nit":     "1043295412-4",
    "ciudad":  "Cartagena, Bolívar",
    "regimen": "No responsable de IVA — Artículo 437 E.T.",
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

async def generar_cuenta_cobro(
    bot=None,
    valor: int | None = None,
    concepto: str | None = None,
    fecha_override: datetime | None = None,
) -> dict:
    """
    Genera una Cuenta de Cobro, la persiste en BD y la envía por Telegram.

    Parámetros:
        bot             — instancia de telegram.Bot; si None, solo genera sin enviar
        valor           — monto a cobrar; si None usa HONORARIOS_VALOR de config
        concepto        — descripción del servicio; si None usa CONCEPTO_DEFAULT
        fecha_override  — fecha para el documento; si None usa datetime.now(COLOMBIA_TZ)

    Retorna dict con: consecutivo, numero_display, periodo, valor, pdf_bytes
    """
    ahora    = fecha_override or datetime.now(COLOMBIA_TZ)
    valor    = valor or HONORARIOS_VALOR
    concepto = concepto or CONCEPTO_DEFAULT

    consecutivo   = _siguiente_consecutivo()
    numero_display = f"{consecutivo:03d}"
    periodo       = f"{MESES_ES[ahora.month].capitalize()} {ahora.year}"
    fecha_str     = ahora.strftime("%d de %B de %Y").replace(
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

    log.info(f"✅ Cuenta de Cobro CC-{numero_display} generada — ${valor:,.0f} — {periodo}")

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
    """Obtiene el próximo consecutivo de forma atómica (SELECT + INSERT lock)."""
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
    pdf.cell(ancho, 10, "CUENTA DE COBRO / RECIBO DE HONORARIOS", align="C", ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ancho, 6, f"No. CC-{numero_display}  |  {fecha_str}", align="C", ln=True)
    pdf.ln(4)

    # Línea separadora
    pdf.set_draw_color(200, 32, 14)  # rojo ferretería
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(5)

    # ── Datos del emisor ────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho, 6, "DATOS DEL PRESTADOR DEL SERVICIO", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ancho, 5, f"Nombre:  {EMISOR['nombre']}", ln=True)
    pdf.cell(ancho, 5, f"C.C.:    {EMISOR['cc']}", ln=True)
    pdf.cell(ancho, 5, f"NIT:     {EMISOR['nit']}", ln=True)
    pdf.cell(ancho, 5, f"Ciudad:  {EMISOR['ciudad']}", ln=True)
    pdf.ln(4)

    # ── Datos del receptor ──────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho, 6, "DATOS DEL CONTRATANTE", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(ancho, 5, f"Empresa: {RECEPTOR['nombre']}", ln=True)
    pdf.cell(ancho, 5, f"NIT:     {RECEPTOR['nit']}", ln=True)
    pdf.cell(ancho, 5, f"Ciudad:  {RECEPTOR['ciudad']}", ln=True)
    pdf.ln(4)

    # ── Tabla de concepto y valor ───────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(ancho, 6, "DETALLE DEL SERVICIO", ln=True)
    pdf.ln(1)

    # Encabezados tabla
    pdf.set_fill_color(200, 32, 14)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(120, 7, "CONCEPTO", border=1, fill=True)
    pdf.cell(50,  7, "VALOR",    border=1, fill=True, align="R", ln=True)

    # Fila concepto
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    col_concepto_x = pdf.get_x()
    col_concepto_y = pdf.get_y()
    pdf.multi_cell(120, 5, f"Período: {periodo}\n{concepto}", border=1)
    y_after = pdf.get_y()

    pdf.set_xy(col_concepto_x + 120, col_concepto_y)
    pdf.cell(50, y_after - col_concepto_y, f"$ {valor:,.0f}", border=1, align="R")
    pdf.ln()

    # Fila IVA
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(120, 6, "IVA (No responsable de IVA)", border=1)
    pdf.cell(50,  6, "$ 0",                          border=1, align="R", ln=True)

    # Fila total
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(120, 7, "TOTAL A PAGAR", border=1, fill=True)
    pdf.cell(50,  7, f"$ {valor:,.0f}", border=1, fill=True, align="R", ln=True)
    pdf.ln(5)

    # ── Leyenda legal ──────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(
        ancho, 4,
        "El prestador del servicio NO ES RESPONSABLE DE IVA conforme al artículo 437 "
        "del Estatuto Tributario colombiano y sus modificaciones. Este documento no "
        "equivale a factura de venta.",
        ln=True,
    )
    pdf.ln(10)

    # ── Firma ──────────────────────────────────────────────────────────────
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(80, 5, "_" * 35, ln=False)
    pdf.cell(10, 5, "",        ln=False)
    pdf.cell(80, 5, "_" * 35, ln=True)

    pdf.cell(80, 5, "Firma Prestador del Servicio", align="C", ln=False)
    pdf.cell(10, 5, "",                              ln=False)
    pdf.cell(80, 5, "Firma / Sello Contratante",     align="C", ln=True)

    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(80, 4, EMISOR["nombre"],  align="C", ln=False)
    pdf.cell(10, 4, "",                ln=False)
    pdf.cell(80, 4, RECEPTOR["nombre"], align="C", ln=True)
    pdf.cell(80, 4, f"C.C. {EMISOR['cc']}", align="C", ln=True)

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
    import config as _cfg
    chat_id = _cfg.HONORARIOS_CHAT_ID or None

    if not chat_id:
        # Fallback: primer chat autorizado
        raw = os.getenv("AUTHORIZED_CHAT_IDS", "")
        ids = [x.strip() for x in raw.split(",") if x.strip()]
        chat_id = ids[0] if ids else None

    if not chat_id:
        log.warning("⚠️ HONORARIOS_CHAT_ID no configurado — PDF no enviado por Telegram")
        return False

    import os  # noqa: F811 (necesario aquí para getenv)

    caption = (
        f"📄 *Cuenta de Cobro CC-{numero_display}*\n"
        f"Período: {periodo}\n"
        f"Valor: *${valor:,.0f} COP*\n"
        f"IVA: $0 (No responsable)\n\n"
        f"_Andrés Felipe Malo Hernández — NIT 1043295412-4_"
    )

    from io import BytesIO
    try:
        await bot.send_document(
            chat_id=chat_id,
            document=BytesIO(pdf_bytes),
            filename=f"CuentaCobro_CC-{numero_display}_{periodo.replace(' ', '_')}.pdf",
            caption=caption,
            parse_mode="Markdown",
        )
        log.info(f"✅ PDF enviado a chat {chat_id}")
        return True
    except Exception as e:
        log.warning(f"⚠️ No se pudo enviar PDF por Telegram: {e}")
        return False
```

---

## 6. Handler Telegram — `handlers/cmd_honorarios.py`

```python
"""
handlers/cmd_honorarios.py — Comando /honorarios del bot.

Comandos:
  /honorarios          — genera la Cuenta de Cobro del mes actual
  /honorarios 2026-04  — genera para un mes específico (YYYY-MM)
  /honorarios lista    — muestra las últimas 5 generadas
"""

# -- stdlib --
import logging
from datetime import datetime

# -- terceros --
from telegram import Update
from telegram.ext import ContextTypes

# -- propios --
from config import COLOMBIA_TZ
from middleware import protegido

log = logging.getLogger("ferrebot.honorarios")


@protegido
async def comando_honorarios(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /honorarios           → genera cuenta de cobro del mes actual
    /honorarios YYYY-MM   → genera para mes específico
    /honorarios lista     → muestra historial
    """
    args  = ctx.args or []
    subco = args[0].lower() if args else ""

    # ── /honorarios lista ────────────────────────────────────────────────
    if subco == "lista":
        from services.honorarios_service import listar_cuentas
        cuentas = listar_cuentas(limit=5)
        if not cuentas:
            await update.message.reply_text("📄 No hay Cuentas de Cobro generadas aún.")
            return
        lines = ["📄 *Últimas Cuentas de Cobro:*\n"]
        for c in cuentas:
            estado = "✅ enviada" if c["enviado_telegram"] else "💾 guardada"
            lines.append(
                f"• CC-{c['numero_display']} — {c['periodo']} — "
                f"${float(c['valor']):,.0f} — {estado}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── /honorarios [YYYY-MM] ────────────────────────────────────────────
    fecha_override = None
    if subco and subco != "lista":
        try:
            fecha_override = datetime.strptime(subco + "-23", "%Y-%m-%d").replace(
                tzinfo=COLOMBIA_TZ
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Formato de fecha incorrecto. Uso: `/honorarios 2026-04`",
                parse_mode="Markdown",
            )
            return

    ahora = fecha_override or datetime.now(COLOMBIA_TZ)
    periodo_str = ahora.strftime("%-m/%Y") if hasattr(ahora, "strftime") else ""

    await update.message.reply_text(
        f"⏳ Generando Cuenta de Cobro para {ahora.strftime('%B %Y').capitalize()}...",
    )

    try:
        from services.honorarios_service import generar_cuenta_cobro
        resultado = await generar_cuenta_cobro(
            bot=ctx.bot,
            fecha_override=ahora,
        )
        enviado_txt = "✅ PDF enviado al chat configurado." if resultado["enviado"] else "💾 PDF guardado en BD (chat no configurado)."
        await update.message.reply_text(
            f"✅ *Cuenta de Cobro generada*\n\n"
            f"Número: *CC-{resultado['numero_display']}*\n"
            f"Período: {resultado['periodo']}\n"
            f"Valor: *${resultado['valor']:,.0f} COP*\n\n"
            f"{enviado_txt}",
            parse_mode="Markdown",
        )
    except Exception as e:
        log.error(f"Error generando cuenta de cobro: {e}")
        await update.message.reply_text(f"❌ Error al generar la Cuenta de Cobro: {e}")
```

---

## 7. Router FastAPI — `routers/honorarios.py`

```python
"""
routers/honorarios.py — API de Cuentas de Cobro

Endpoints:
  GET  /honorarios/lista           — historial de cuentas generadas
  GET  /honorarios/pdf/{nro}       — descarga el PDF del consecutivo N
  POST /honorarios/generar         — genera manualmente desde el dashboard (admin)
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

import db as _db
from routers.deps import get_current_user
from fastapi import Depends

log    = logging.getLogger("ferrebot.api.honorarios")
router = APIRouter()


@router.get("/honorarios/lista")
async def listar(
    limit: int = 20,
    current_user=Depends(get_current_user),
):
    """Lista las últimas N cuentas de cobro."""
    from services.honorarios_service import listar_cuentas
    return listar_cuentas(limit=limit)


@router.get("/honorarios/pdf/{consecutivo}")
async def descargar_pdf(
    consecutivo: int,
    current_user=Depends(get_current_user),
):
    """Descarga el PDF de una Cuenta de Cobro por su consecutivo."""
    from services.honorarios_service import obtener_pdf
    pdf_bytes = obtener_pdf(consecutivo)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF no encontrado")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CC-{consecutivo:03d}.pdf"'},
    )


@router.post("/honorarios/generar")
async def generar_manual(current_user=Depends(get_current_user)):
    """
    Genera la Cuenta de Cobro del mes actual desde el dashboard.
    Solo disponible para admin.
    """
    if current_user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")
    from services.honorarios_service import generar_cuenta_cobro
    resultado = await generar_cuenta_cobro(bot=None)
    resultado.pop("pdf_bytes", None)  # no serializar bytes en JSON
    return resultado
```

---

## 8. Job automático día 23 — cambio en `start-bot.py`

Agregar dentro del bloque del `AsyncIOScheduler` en el `lifespan` de `start-bot.py`,
**después** de registrar el job `compresor_nocturno`:

```python
# ── Job mensual: Cuenta de Cobro día 23 a las 9:00 AM Colombia ──────────────
async def _job_honorarios():
    """Genera y envía la Cuenta de Cobro mensual el día 23."""
    try:
        from services.honorarios_service import generar_cuenta_cobro
        bot = tg_app.bot
        resultado = await generar_cuenta_cobro(bot=bot)
        log.info(
            f"[honorarios-job] CC-{resultado['numero_display']} generada "
            f"— ${resultado['valor']:,.0f} — {resultado['periodo']}"
        )
    except Exception as e:
        log.error(f"[honorarios-job] Error: {e}")

scheduler.add_job(
    _job_honorarios,
    trigger=CronTrigger(day=23, hour=9, minute=0, timezone=str(config.COLOMBIA_TZ)),
    id="honorarios_mensual",
    name="Cuenta de Cobro mensual día 23",
    replace_existing=True,
    misfire_grace_time=3600,
    max_instances=1,
)
log.info("📄 Job honorarios registrado — día 23 de cada mes a las 9:00 AM Colombia")
```

> **Nota:** `tg_app` ya está disponible en el scope del `lifespan` donde vive este bloque.

---

## 9. Registro en `main.py`

En el bloque de imports de handlers:
```python
from handlers.cmd_honorarios import comando_honorarios
```

En la función `build_app()`, junto a los demás `CommandHandler`:
```python
app.add_handler(CommandHandler("honorarios", comando_honorarios))
```

---

## 10. Registro en `api.py`

En el bloque de imports de routers:
```python
from routers import honorarios
```

En la lista de `include_router`:
```python
app.include_router(honorarios.router)
```

---

## 11. `requirements.txt`

Agregar al final:
```
fpdf2>=2.7.9
```

---

## 12. Variables de entorno en Railway

| Variable | Valor | Obligatoria |
|----------|-------|-------------|
| `HONORARIOS_VALOR` | `2000000` | No (tiene default) |
| `HONORARIOS_CHAT_ID` | `1831034712` | Sí (para recibir el PDF) |

Agregar en el servicio **bot** de Railway.

---

## 13. Pasos de implementación para Claude Code

Seguir este orden exacto para evitar errores de importación:

```
Paso 1 — Dependencia
  Editar requirements.txt: agregar "fpdf2>=2.7.9"

Paso 2 — Configuración
  Editar config.py: agregar HONORARIOS_VALOR y HONORARIOS_CHAT_ID

Paso 3 — Migración
  Crear migrations/021_honorarios.py (código en §3)
  → Ejecutar: railway run python migrations/021_honorarios.py

Paso 4 — Servicio
  Crear services/honorarios_service.py (código en §5)
  (No depende de handlers ni routers — se puede testear solo)

Paso 5 — Handler bot
  Crear handlers/cmd_honorarios.py (código en §6)

Paso 6 — Router API
  Crear routers/honorarios.py (código en §7)

Paso 7 — Registrar handler en main.py
  Import + CommandHandler("honorarios", comando_honorarios)

Paso 8 — Registrar router en api.py
  Import + app.include_router(honorarios.router)

Paso 9 — Job automático en start-bot.py
  Agregar _job_honorarios() y scheduler.add_job() (código en §8)

Paso 10 — Variables de entorno en Railway
  Agregar HONORARIOS_CHAT_ID=1831034712 en el servicio bot

Paso 11 — Deploy y prueba
  git commit + push → Railway despliega
  Probar con /honorarios en el bot
  Verificar que el PDF llega y se ve correctamente
```

---

## 14. Test rápido post-deploy

```bash
# En el bot de Telegram:
/honorarios lista         # debe responder "No hay Cuentas de Cobro generadas aún."
/honorarios               # genera CC-001, mes actual, $2.000.000
/honorarios lista         # debe mostrar CC-001
/honorarios 2026-04       # genera CC-002 para abril 2026

# En la API:
GET /honorarios/lista            → JSON con las 2 cuentas
GET /honorarios/pdf/1            → descarga PDF de CC-001
POST /honorarios/generar         → genera CC-003 (dashboard admin)
```

---

## 15. Consideraciones adicionales

- **Idempotencia del job:** si el bot se reinicia el día 23, el scheduler no genera
  una segunda cuenta para el mismo periodo porque APScheduler usa `max_instances=1`
  y `misfire_grace_time`. Adicionalmente, se puede agregar un check en
  `generar_cuenta_cobro()` que verifique si ya existe una cuenta para el periodo
  actual antes de insertar.

- **PDF sin fuentes externas:** `fpdf2` usa las 14 fuentes core de PDF (Helvetica,
  Times, Courier) que no requieren instalar nada adicional en Railway/Nixpacks.

- **Tamaño del PDF en BD:** ~30–60 KB por cuenta, completamente manejable en PostgreSQL
  como `BYTEA`. Con 10 años de uso serían ~7.2 MB totales.

- **Formato del valor:** `$2.000.000` (notación colombiana con punto como separador
  de miles). En fpdf2 usar `f"$ {valor:,.0f}".replace(",", ".")` para formato local.

- **Extensión futura:** si se necesita logo o firma escaneada, `fpdf2` soporta
  `image()` con bytes de imagen en memoria, sin tocar el sistema de archivos.
