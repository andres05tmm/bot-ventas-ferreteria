"""
handlers/cmd_proveedores.py — Comandos de facturas y proveedores.

Funciones: upload_foto_cloudinary (helper compartido, sin @protegido),
           comando_factura, comando_abonar, comando_deudas,
           comando_facturas, comando_borrar_factura
"""

# -- stdlib --
import asyncio
import logging
import os

# -- terceros --
from telegram import Update
from telegram.ext import ContextTypes

# -- propios --
import db as _db
from middleware import protegido

logger = logging.getLogger("ferrebot.handlers.cmd_proveedores")


# ─────────────────────────────────────────────────────────────────────────────
# CLOUDINARY HELPER — NO lleva @protegido (helper compartido)
# ─────────────────────────────────────────────────────────────────────────────

async def upload_foto_cloudinary(
    foto_bytes: bytes,
    public_id: str,
    carpeta: str = "ferreteria",
) -> dict:
    """
    Sube foto a Cloudinary y devuelve {ok, url, public_id, error}.

    Uso desde mensajes.py cuando se recibe una foto de factura o abono:

        from handlers.comandos import upload_foto_cloudinary
        result = await upload_foto_cloudinary(
            foto_bytes = await foto.download_as_bytearray(),
            public_id  = f"facturas/{fac_id}",
        )
        if result["ok"]:
            url_foto = result["url"]
            # guardar url_foto en PG: UPDATE facturas SET foto_url = %s WHERE id = %s

    Requiere: CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
    """
    import io
    try:
        import cloudinary
        import cloudinary.uploader

        # Configurar desde env vars (se puede hacer una sola vez en config.py también)
        cloudinary.config(
            cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            api_key    = os.environ.get("CLOUDINARY_API_KEY",    ""),
            api_secret = os.environ.get("CLOUDINARY_API_SECRET", ""),
        )

        full_public_id = f"{carpeta}/{public_id}"

        def _do_upload():
            return cloudinary.uploader.upload(
                io.BytesIO(foto_bytes),
                public_id    = full_public_id,
                overwrite    = True,
                resource_type= "image",
            )

        result = await asyncio.to_thread(_do_upload)
        return {
            "ok":        True,
            "url":       result.get("secure_url", ""),
            "public_id": result.get("public_id",  ""),
            "error":     None,
        }
    except ImportError:
        return {
            "ok":    False,
            "url":   "",
            "public_id": public_id,
            "error": "cloudinary no instalado — pip install cloudinary",
        }
    except Exception as e:
        return {
            "ok":    False,
            "url":   "",
            "public_id": public_id,
            "error": str(e),
        }


# ─────────────────────────────────────────────────────────────────────────────
# /factura - Registrar factura de proveedor
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_factura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Registra una factura de proveedor.
    Uso: /factura Proveedor Total descripción opcional

    La foto de la factura se guarda en Cloudinary (ver mensajes.py).
    """
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "📄 *Registrar factura de proveedor*\n\n"
            "Uso: `/factura Proveedor Total Descripción`\n\n"
            "Ejemplos:\n"
            "• `/factura Ferrisariato 700000 surtido tornillería`\n"
            "• `/factura Pinturas Davinci 350000 brochas`\n\n"
            "Después podrás adjuntar la foto de la factura (se guarda en Cloudinary).",
            parse_mode="Markdown"
        )
        return

    import re as _re
    texto    = " ".join(args)
    m_total  = _re.search(r'(\d[\d.,]*)', texto)
    if not m_total:
        await update.message.reply_text("❌ No encontré el monto. Ejemplo: `/factura Ferrisariato 700000`", parse_mode="Markdown")
        return

    total_str = m_total.group(1).replace(".", "").replace(",", "")
    try:
        total = float(total_str)
    except ValueError:
        await update.message.reply_text("❌ Monto inválido.", parse_mode="Markdown")
        return

    idx_num     = texto.find(m_total.group(0))
    proveedor   = texto[:idx_num].strip().strip('"').strip("'")
    if not proveedor:
        await update.message.reply_text("❌ Falta el nombre del proveedor.", parse_mode="Markdown")
        return

    descripcion = texto[idx_num + len(m_total.group(0)):].strip() or "Sin descripción"

    from memoria import registrar_factura_proveedor
    factura = registrar_factura_proveedor(
        proveedor   = proveedor,
        descripcion = descripcion,
        total       = total,
    )
    fac_id = factura["id"]

    # Estado para recibir la foto → mensajes.py llamará upload_foto_cloudinary()
    context.user_data["esperando_foto_factura"] = fac_id

    await update.message.reply_text(
        f"✅ *Factura {fac_id} registrada*\n\n"
        f"🏪 Proveedor: {proveedor}\n"
        f"💰 Total: ${total:,.0f}\n"
        f"📝 Descripción: {descripcion}\n"
        f"📊 Estado: PENDIENTE\n\n"
        f"📸 Envía la foto de la factura ahora (se guardará en Cloudinary)\n"
        f"_(o escribe `sin foto` para omitir)_",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /abonar - Registrar abono a factura
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_abonar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Registra un abono a una factura existente.
    Uso: /abonar FAC-001 500000

    El comprobante de pago se guarda en Cloudinary (ver mensajes.py).
    """
    args = context.args
    if len(args) < 2:
        from memoria import listar_facturas
        try:
            pendientes = listar_facturas(solo_pendientes=True)
        except RuntimeError as e:
            await update.message.reply_text(f"❌ {e}")
            return
        if not pendientes:
            await update.message.reply_text(
                "📋 No hay facturas pendientes.\n\n"
                "Usa `/factura Proveedor Total` para registrar una.",
                parse_mode="Markdown"
            )
            return
        lineas = ["📋 *Facturas pendientes:*\n"]
        for f in pendientes[:8]:
            lineas.append(
                f"• `{f['id']}` — {f['proveedor']} — "
                f"Pendiente: ${f['pendiente']:,.0f} ({f['estado']})"
            )
        lineas.append("\nUso: `/abonar FAC-001 500000`")
        await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")
        return

    fac_id    = args[0].upper()
    monto_str = args[1].replace(".", "").replace(",", "")
    try:
        monto = float(monto_str)
    except ValueError:
        await update.message.reply_text("❌ Monto inválido.", parse_mode="Markdown")
        return

    from memoria import registrar_abono_factura
    result = registrar_abono_factura(fac_id=fac_id, monto=monto)

    if not result["ok"]:
        await update.message.reply_text(f"❌ {result['error']}", parse_mode="Markdown")
        return

    fac          = result["factura"]
    estado_emoji = {"pagada":"✅","parcial":"🔶","pendiente":"🔴"}.get(fac["estado"], "📄")

    # Estado para recibir el comprobante → mensajes.py llamará upload_foto_cloudinary()
    context.user_data["esperando_foto_abono"] = fac_id

    await update.message.reply_text(
        f"✅ *Abono registrado — {fac_id}*\n\n"
        f"🏪 Proveedor: {fac['proveedor']}\n"
        f"💸 Abono: ${monto:,.0f}\n"
        f"✔️ Total pagado: ${fac['pagado']:,.0f}\n"
        f"⏳ Pendiente: ${fac['pendiente']:,.0f}\n"
        f"{estado_emoji} Estado: {fac['estado'].upper()}\n\n"
        f"📸 Envía el comprobante de pago (se guardará en Cloudinary)\n"
        f"_(o escribe `sin foto` para omitir)_",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /deudas
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_deudas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from memoria import listar_facturas
    from collections import defaultdict

    try:
        todas = listar_facturas()
    except RuntimeError as e:
        await update.message.reply_text(f"❌ {e}")
        return
    if not todas:
        await update.message.reply_text(
            "📋 No hay facturas registradas.\n"
            "Usa `/factura Proveedor Total` para registrar una.",
            parse_mode="Markdown"
        )
        return

    pendientes  = [f for f in todas if f["estado"] != "pagada"]
    total_deuda = sum(f["pendiente"] for f in pendientes)

    por_proveedor = defaultdict(float)
    for f in pendientes:
        por_proveedor[f["proveedor"]] += f["pendiente"]

    lineas = [f"💳 *DEUDAS CON PROVEEDORES*\n"]
    for prov, deuda in sorted(por_proveedor.items(), key=lambda x: -x[1]):
        lineas.append(f"• {prov}: ${deuda:,.0f}")
    lineas.append(f"\n💰 *Total deuda: ${total_deuda:,.0f}*")
    lineas.append(f"\n{len(pendientes)} factura(s) pendiente(s)")
    lineas.append("\nUsa `/abonar` para ver las facturas o registrar un pago.")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────────────────────
# /facturas — historial completo con fotos
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_facturas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Muestra historial de facturas con sus abonos y links de fotos.

    Uso:
      /facturas              → todas las facturas
      /facturas pagadas      → solo las pagadas
      /facturas pendientes   → solo pendientes/parciales
      /facturas Davinci      → filtra por nombre de proveedor
    """
    if not _db.DB_DISPONIBLE:
        await update.message.reply_text("⚠️ Base de datos no disponible.")
        return

    filtro = " ".join(context.args).strip() if context.args else ""
    filtro_lower = filtro.lower()

    # Armar query según filtro
    if filtro_lower == "pagadas":
        where = "WHERE fp.estado = 'pagada'"
        params = []
        titulo = "✅ Facturas PAGADAS"
    elif filtro_lower in ("pendientes", "pendiente"):
        where = "WHERE fp.estado IN ('pendiente', 'parcial')"
        params = []
        titulo = "🔴 Facturas PENDIENTES / PARCIALES"
    elif filtro:
        where = "WHERE fp.proveedor ILIKE %s"
        params = [f"%{filtro}%"]
        titulo = f"📋 Facturas — {filtro}"
    else:
        where = ""
        params = []
        titulo = "📋 Historial completo de facturas"

    facturas = await asyncio.to_thread(
        _db.query_all,
        f"""
        SELECT fp.id, fp.proveedor, fp.descripcion, fp.total,
               fp.pagado, fp.pendiente, fp.estado, fp.fecha::text,
               fp.foto_url, fp.foto_nombre
        FROM   facturas_proveedores fp
        {where}
        ORDER  BY fp.fecha DESC, fp.id DESC
        """,
        params or None,
    )

    if not facturas:
        await update.message.reply_text(
            f"📋 No hay facturas{' para «' + filtro + '»' if filtro else ''}.\n\n"
            "Usa `/factura Proveedor Total Descripción` para registrar una.",
            parse_mode="Markdown"
        )
        return

    # Cargar abonos de todas las facturas de una sola query
    ids = [r["id"] for r in facturas]
    placeholders = ",".join(["%s"] * len(ids))
    abonos_rows = await asyncio.to_thread(
        _db.query_all,
        f"""
        SELECT factura_id, monto, fecha::text, foto_url, foto_nombre
        FROM   facturas_abonos
        WHERE  factura_id IN ({placeholders})
        ORDER  BY factura_id, id
        """,
        ids,
    )
    # Indexar abonos por factura_id
    abonos_por_fac: dict = {}
    for ab in (abonos_rows or []):
        abonos_por_fac.setdefault(ab["factura_id"], []).append(ab)

    estado_emoji = {"pagada": "✅", "parcial": "🔶", "pendiente": "🔴"}

    bloques = [f"*{titulo}* ({len(facturas)} factura(s))\n"]

    for fac in facturas:
        fid    = fac["id"]
        prov   = fac["proveedor"]
        desc   = fac["descripcion"] or "—"
        total  = int(fac["total"])
        pagado = int(fac["pagado"])
        pend   = int(fac["pendiente"])
        estado = fac["estado"]
        fecha  = str(fac["fecha"])[:10]
        emoji  = estado_emoji.get(estado, "📄")
        foto_fac = fac.get("foto_url", "")

        linea = (
            f"\n{emoji} *{fid}* — {prov}\n"
            f"   📅 {fecha}  |  💰 ${total:,.0f}  |  {estado.upper()}\n"
            f"   📝 {desc}\n"
        )
        if pagado > 0:
            linea += f"   ✔️ Pagado: ${pagado:,.0f}  |  ⏳ Pendiente: ${pend:,.0f}\n"
        if foto_fac:
            linea += f"   📎 [Ver factura]({foto_fac})\n"

        # Abonos de esta factura
        abonos = abonos_por_fac.get(fid, [])
        for i, ab in enumerate(abonos, 1):
            monto_ab = int(ab["monto"])
            fecha_ab = str(ab["fecha"])[:10]
            foto_ab  = ab.get("foto_url", "")
            linea += f"   💸 Abono {i}: ${monto_ab:,.0f} el {fecha_ab}"
            if foto_ab:
                linea += f"  [Ver comprobante]({foto_ab})"
            linea += "\n"

        bloques.append(linea)

    # Enviar en mensajes de máx 4000 chars
    msg = ""
    for bloque in bloques:
        if len(msg) + len(bloque) > 3800:
            await update.message.reply_text(msg, parse_mode="Markdown",
                                            disable_web_page_preview=True)
            msg = ""
        msg += bloque
    if msg.strip():
        await update.message.reply_text(msg, parse_mode="Markdown",
                                        disable_web_page_preview=True)


# ─────────────────────────────────────────────────────────────────────────────
# /borrar_factura
# ─────────────────────────────────────────────────────────────────────────────

@protegido
async def comando_borrar_factura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    import db as _db

    if not _db.DB_DISPONIBLE:
        await update.message.reply_text(
            "❌ Base de datos no disponible. No se puede ejecutar esta operación."
        )
        return

    # ── SIN ARGUMENTOS: listar facturas ──────────────────────────────────────
    if not args:
        rows = _db.query_all(
            """SELECT fp.id, fp.proveedor, fp.total, fp.estado,
                      COUNT(fa.id) AS n_abonos
               FROM facturas_proveedores fp
               LEFT JOIN facturas_abonos fa ON fa.factura_id = fp.id
               GROUP BY fp.id, fp.proveedor, fp.total, fp.estado
               ORDER BY fp.fecha DESC""",
            (),
        )
        if not rows:
            await update.message.reply_text("📋 No hay facturas registradas.")
            return
        lineas = ["📋 *Facturas registradas:*\n"]
        for f in rows:
            icon = {"pagada": "✅", "parcial": "🔶", "pendiente": "🔴"}.get(f["estado"], "📄")
            lineas.append(
                f"{icon} `{f['id']}` — {f['proveedor']} — ${f['total']:,.0f} ({f['estado']})"
            )
        lineas.append("\nUso: `/borrar_factura FAC-001`")
        await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")
        return

    # ── CON ARGUMENTO: buscar y borrar ───────────────────────────────────────
    fac_id = args[0].upper()
    if not fac_id.startswith("FAC-"):
        fac_id = "FAC-" + fac_id

    factura = _db.query_one(
        "SELECT id, proveedor, total, estado FROM facturas_proveedores WHERE id = %s",
        (fac_id,),
    )
    if not factura:
        await update.message.reply_text(
            f"❌ No encontré la factura `{fac_id}` en la base de datos.\n"
            f"Usa `/borrar_factura` sin argumentos para ver la lista.",
            parse_mode="Markdown",
        )
        return

    abonos_row = _db.query_one(
        "SELECT COUNT(*) AS n FROM facturas_abonos WHERE factura_id = %s",
        (fac_id,),
    )
    n_abonos    = abonos_row["n"] if abonos_row else 0
    aviso_abonos = (
        f"\n⚠️ Esta factura tenía {n_abonos} abono(s) que también fueron eliminados."
        if n_abonos else ""
    )

    # ON DELETE CASCADE en facturas_abonos elimina los abonos automáticamente
    deleted = _db.execute(
        "DELETE FROM facturas_proveedores WHERE id = %s",
        (fac_id,),
    )
    if deleted == 0:
        await update.message.reply_text(
            f"❌ No se pudo eliminar la factura `{fac_id}`. Intenta de nuevo.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text(
        f"🗑️ Factura `{fac_id}` eliminada.\n"
        f"Proveedor: {factura['proveedor']} — ${factura['total']:,.0f}"
        f"{aviso_abonos}\n\n"
        f"_Nota: las fotos en Cloudinary no se borran automáticamente._",
        parse_mode="Markdown",
    )
