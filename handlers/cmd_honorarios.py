"""
handlers/cmd_honorarios.py — Comando /honorarios del bot.

Comandos:
  /honorarios              — genera la Cuenta de Cobro del mes actual
  /honorarios 2026-04      — genera para un mes específico (YYYY-MM)
  /honorarios lista        — muestra las últimas 5 generadas
  /honorarios forzar       — genera aunque ya exista una CC para el mes actual
  /honorarios dsno         — flujo completo: CC + Documento Soporte DIAN
  /honorarios dsno 2500000 — flujo completo con valor personalizado
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
    /honorarios              → genera cuenta de cobro del mes actual
    /honorarios YYYY-MM      → genera para mes específico
    /honorarios lista        → muestra historial
    /honorarios dsno [valor] → flujo completo CC + Documento Soporte DIAN
    """
    from services.honorarios_service import generar_cuenta_cobro, PeriodoYaExisteError, listar_cuentas

    args  = ctx.args or []
    subco = args[0].lower() if args else ""

    # ── /honorarios dsno [valor_opcional] ───────────────────────────────
    if subco == "dsno":
        import io
        from services.documento_soporte_service import generar_documento_soporte

        valor_override: int | None = None
        if len(args) >= 2:
            try:
                valor_override = int(args[1].replace(".", "").replace(",", ""))
            except ValueError:
                await update.message.reply_text(
                    "Valor inválido. Uso: `/honorarios dsno 2500000`",
                    parse_mode="Markdown",
                )
                return

        await update.message.reply_text("Generando Cuenta de Cobro y Documento Soporte DIAN...")

        try:
            resultado_cc = await generar_cuenta_cobro(bot=None, valor=valor_override)
        except PeriodoYaExisteError as e:
            await update.message.reply_text(
                f"Ya existe *CC-{e.numero_display}* para *{e.periodo}*.\n\n"
                f"Si necesitas generar una adicional usa `/honorarios forzar`.",
                parse_mode="Markdown",
            )
            return
        except Exception as e:
            log.error("Error generando CC en flujo dsno: %s", e)
            await update.message.reply_text(f"Error al generar la Cuenta de Cobro: {e}")
            return

        resultado_ds = await generar_documento_soporte(
            valor=resultado_cc["valor"],
            cuenta_cobro_id=resultado_cc["consecutivo"],
        )

        valor_fmt = f"${resultado_cc['valor']:,.0f}".replace(",", ".")
        if resultado_ds["ok"]:
            cude = resultado_ds.get("cude", "")
            cude_short = (cude[:40] + "...") if len(cude) > 40 else cude
            caption = (
                f"✅ Cuenta de cobro *CC-{resultado_cc['numero_display']}* generada\n"
                f"✅ Documento Soporte transmitido a DIAN\n"
                f"📋 CUDE: `{cude_short}`\n"
                f"💰 Valor: *{valor_fmt}*"
            )
        else:
            caption = (
                f"✅ Cuenta de cobro *CC-{resultado_cc['numero_display']}* generada\n"
                f"⚠️ Documento Soporte falló: {resultado_ds.get('error', 'error desconocido')}\n"
                f"💰 Valor: *{valor_fmt}*"
            )

        await ctx.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(resultado_cc["pdf_bytes"]),
            filename=(
                f"CuentaCobro_CC-{resultado_cc['numero_display']}"
                f"_{resultado_cc['periodo'].replace(' ', '_')}.pdf"
            ),
            caption=caption,
            parse_mode="Markdown",
        )
        return

    # ── /honorarios lista ────────────────────────────────────────────────
    if subco == "lista":
        cuentas = listar_cuentas(limit=5)
        if not cuentas:
            await update.message.reply_text("No hay Cuentas de Cobro generadas aún.")
            return
        lines = ["*Últimas Cuentas de Cobro:*\n"]
        for c in cuentas:
            estado = "enviada" if c["enviado_telegram"] else "guardada"
            lines.append(
                f"• CC-{c['numero_display']} — {c['periodo']} — "
                f"${float(c['valor']):,.0f} — {estado}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── /honorarios forzar ───────────────────────────────────────────────
    forzar = subco == "forzar"

    # ── /honorarios [YYYY-MM] ────────────────────────────────────────────
    fecha_override = None
    if subco and subco not in ("lista", "forzar"):
        try:
            fecha_override = datetime.strptime(subco + "-23", "%Y-%m-%d").replace(
                tzinfo=COLOMBIA_TZ
            )
        except ValueError:
            await update.message.reply_text(
                "Formato de fecha incorrecto. Uso: `/honorarios 2026-04`",
                parse_mode="Markdown",
            )
            return

    ahora = fecha_override or datetime.now(COLOMBIA_TZ)

    await update.message.reply_text(
        f"Generando Cuenta de Cobro para {ahora.strftime('%B %Y').capitalize()}...",
    )

    try:
        resultado = await generar_cuenta_cobro(
            bot=ctx.bot,
            fecha_override=ahora,
            forzar=forzar,
        )
        enviado_txt = (
            "PDF enviado al chat configurado."
            if resultado["enviado"]
            else "PDF guardado en BD (chat no configurado)."
        )
        await update.message.reply_text(
            f"*Cuenta de Cobro generada*\n\n"
            f"Número: *CC-{resultado['numero_display']}*\n"
            f"Período: {resultado['periodo']}\n"
            f"Valor: *${resultado['valor']:,.0f} COP*\n\n"
            f"{enviado_txt}",
            parse_mode="Markdown",
        )
    except PeriodoYaExisteError as e:
        await update.message.reply_text(
            f"Ya existe *CC-{e.numero_display}* para *{e.periodo}*.\n\n"
            f"Si necesitas generar una adicional usa `/honorarios forzar`.",
            parse_mode="Markdown",
        )
    except Exception as e:
        log.error(f"Error generando cuenta de cobro: {e}")
        await update.message.reply_text(f"Error al generar la Cuenta de Cobro: {e}")
