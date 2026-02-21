"""
Bot de Ventas para Telegram con Claude AI
==========================================
Este bot permite registrar ventas por texto o voz en un grupo de Telegram.
Las ventas se guardan en un archivo Excel y puedes pedir reportes.
"""

import os
import json
import tempfile
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import openai

# ============================================================
# CARGAR VARIABLES DEL ARCHIVO .env
# ============================================================
load_dotenv()

# ============================================================
# CONFIGURACIÓN — Aquí van tus claves (las conseguirás más adelante)
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")          # Token de tu bot de Telegram
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")    # Clave de Claude (Anthropic)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")          # Clave de OpenAI (para transcribir audios)

# ============================================================
# VALIDACIÓN — Si falta alguna clave el bot se detiene con un mensaje claro
# ============================================================
claves_requeridas = {
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "OPENAI_API_KEY": OPENAI_API_KEY,
}

claves_faltantes = [nombre for nombre, valor in claves_requeridas.items() if not valor]

if claves_faltantes:
    print("\n❌ ERROR: Faltan las siguientes claves en tu archivo .env:")
    for clave in claves_faltantes:
        print(f"   • {clave}")
    print("\n📝 Abre el archivo .env y asegúrate de que todas las claves estén completas.")
    print("   Ejemplo: TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNO\n")
    exit(1)

# Nombre del archivo Excel donde se guardarán las ventas
EXCEL_FILE = "ventas.xlsx"

# ============================================================
# CLIENTES DE IA
# ============================================================
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)


# ============================================================
# FUNCIONES DE EXCEL
# ============================================================

def inicializar_excel():
    """Crea el archivo Excel si no existe, con encabezados y formato."""
    if not os.path.exists(EXCEL_FILE):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Ventas"

        # Encabezados
        encabezados = ["Fecha", "Hora", "Producto", "Cantidad", "Precio Unitario", "Total", "Vendedor", "Observaciones"]
        for col, titulo in enumerate(encabezados, 1):
            celda = ws.cell(row=1, column=col, value=titulo)
            celda.font = Font(bold=True, color="FFFFFF", size=12)
            celda.fill = PatternFill("solid", fgColor="1A56DB")
            celda.alignment = Alignment(horizontal="center")

        # Ancho de columnas
        anchos = [12, 10, 25, 12, 18, 14, 20, 30]
        for col, ancho in enumerate(anchos, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = ancho

        wb.save(EXCEL_FILE)
        print("✅ Archivo Excel creado correctamente.")


def guardar_venta_excel(fecha, hora, producto, cantidad, precio_unitario, total, vendedor, observaciones=""):
    """Guarda una venta nueva en el archivo Excel."""
    inicializar_excel()
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active

    fila = ws.max_row + 1
    ws.cell(row=fila, column=1, value=fecha)
    ws.cell(row=fila, column=2, value=hora)
    ws.cell(row=fila, column=3, value=producto)
    ws.cell(row=fila, column=4, value=cantidad)
    ws.cell(row=fila, column=5, value=precio_unitario)
    ws.cell(row=fila, column=6, value=total)
    ws.cell(row=fila, column=7, value=vendedor)
    ws.cell(row=fila, column=8, value=observaciones)

    # Alternar color de filas para mejor lectura
    if fila % 2 == 0:
        for col in range(1, 9):
            ws.cell(row=fila, column=col).fill = PatternFill("solid", fgColor="EFF6FF")

    wb.save(EXCEL_FILE)


def obtener_ventas_por_periodo(dias):
    """Obtiene todas las ventas de los últimos X días."""
    inicializar_excel()
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active

    ventas = []
    fecha_limite = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")

    for fila in ws.iter_rows(min_row=2, values_only=True):
        if fila[0] and str(fila[0]) >= fecha_limite:
            ventas.append({
                "fecha": fila[0],
                "hora": fila[1],
                "producto": fila[2],
                "cantidad": fila[3],
                "precio_unitario": fila[4],
                "total": fila[5],
                "vendedor": fila[6]
            })
    return ventas


def calcular_reporte(ventas, titulo):
    """Genera un resumen de ventas formateado."""
    if not ventas:
        return f"📊 *{titulo}*\n\nNo hay ventas registradas en este período."

    total_general = sum(v["total"] for v in ventas if v["total"])
    total_unidades = sum(v["cantidad"] for v in ventas if v["cantidad"])
    num_ventas = len(ventas)

    # Productos más vendidos
    productos = {}
    for v in ventas:
        prod = v["producto"] or "Sin nombre"
        productos[prod] = productos.get(prod, 0) + (v["cantidad"] or 0)

    top_productos = sorted(productos.items(), key=lambda x: x[1], reverse=True)[:3]
    top_texto = "\n".join([f"   • {p}: {c} unidades" for p, c in top_productos])

    reporte = f"""📊 *{titulo}*

💰 *Total vendido:* ${total_general:,.0f}
🛍️ *Número de ventas:* {num_ventas}
📦 *Unidades vendidas:* {total_unidades}

🏆 *Productos más vendidos:*
{top_texto}
"""
    return reporte


# ============================================================
# FUNCIÓN PRINCIPAL — INTERPRETAR VENTAS CON CLAUDE
# ============================================================

def interpretar_venta_con_claude(texto_mensaje, nombre_vendedor):
    """
    Envía el mensaje a Claude para que identifique si es una venta
    y extrae los datos: producto, cantidad y precio.
    """
    prompt = f"""Eres un asistente de registro de ventas. Analiza el siguiente mensaje y determina si contiene una o varias ventas.

Si el mensaje contiene ventas, extrae los datos y responde ÚNICAMENTE con un JSON válido con esta estructura:
{{
  "es_venta": true,
  "ventas": [
    {{
      "producto": "nombre del producto",
      "cantidad": número,
      "precio_unitario": número
    }}
  ]
}}

Si el mensaje NO contiene una venta (es una pregunta, saludo u otra cosa), responde ÚNICAMENTE con:
{{
  "es_venta": false
}}

REGLAS IMPORTANTES:
- Si no se menciona cantidad, asume 1
- Si no se menciona precio, usa 0 y marca precio_unitario como 0
- Los números deben ser solo dígitos, sin símbolos ni texto
- No agregues explicaciones, solo el JSON

Mensaje del vendedor "{nombre_vendedor}":
{texto_mensaje}"""

    respuesta = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    texto_respuesta = respuesta.content[0].text.strip()

    # Limpiar posibles caracteres extra
    if "```" in texto_respuesta:
        texto_respuesta = texto_respuesta.split("```")[1]
        if texto_respuesta.startswith("json"):
            texto_respuesta = texto_respuesta[4:]

    return json.loads(texto_respuesta)


# ============================================================
# FUNCIÓN DE TRANSCRIPCIÓN DE AUDIO
# ============================================================

async def transcribir_audio(archivo_audio_path):
    """Transcribe un audio usando Whisper de OpenAI."""
    with open(archivo_audio_path, "rb") as audio_file:
        transcripcion = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="es"
        )
    return transcripcion.text


# ============================================================
# MANEJADORES DE COMANDOS
# ============================================================

async def comando_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start con instrucciones de uso."""
    mensaje = """🤖 *¡Hola! Soy tu asistente de ventas!*

Puedo registrar tus ventas automáticamente. Así de fácil:

📝 *Para registrar una venta escribe algo como:*
• "Vendí 3 camisas a $50 cada una"
• "2 pantalones a 80 mil"
• "Vendí una chaqueta en 120000"

🎤 *También puedes enviarme un audio de voz*

📊 *Comandos disponibles:*
/hoy — Reporte de ventas del día
/semana — Reporte de la semana
/mes — Reporte del mes
/excel — Descargar el archivo Excel completo
/ayuda — Ver estas instrucciones

¡Listo para registrar ventas! 💪"""

    await update.message.reply_text(mensaje, parse_mode="Markdown")


async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra instrucciones de uso."""
    await comando_inicio(update, context)


async def comando_reporte_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera reporte del día actual."""
    ventas = obtener_ventas_por_periodo(1)
    reporte = calcular_reporte(ventas, "Reporte de Hoy")
    await update.message.reply_text(reporte, parse_mode="Markdown")


async def comando_reporte_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera reporte de los últimos 7 días."""
    ventas = obtener_ventas_por_periodo(7)
    reporte = calcular_reporte(ventas, "Reporte Semanal (últimos 7 días)")
    await update.message.reply_text(reporte, parse_mode="Markdown")


async def comando_reporte_mes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera reporte de los últimos 30 días."""
    ventas = obtener_ventas_por_periodo(30)
    reporte = calcular_reporte(ventas, "Reporte Mensual (últimos 30 días)")
    await update.message.reply_text(reporte, parse_mode="Markdown")


async def comando_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía el archivo Excel al grupo."""
    inicializar_excel()
    await update.message.reply_text("📎 Aquí está el archivo Excel con todas las ventas:")
    with open(EXCEL_FILE, "rb") as archivo:
        await update.message.reply_document(document=archivo, filename="ventas.xlsx")


# ============================================================
# MANEJADOR DE MENSAJES DE TEXTO
# ============================================================

async def manejar_mensaje_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa mensajes de texto para detectar y registrar ventas."""
    mensaje = update.message.text
    vendedor = update.message.from_user.first_name or "Desconocido"

    # Ignorar comandos
    if mensaje.startswith("/"):
        return

    try:
        resultado = interpretar_venta_con_claude(mensaje, vendedor)

        if resultado.get("es_venta"):
            ventas_registradas = []
            fecha_hoy = datetime.now().strftime("%Y-%m-%d")
            hora_ahora = datetime.now().strftime("%H:%M")

            for venta in resultado.get("ventas", []):
                producto = venta.get("producto", "Sin nombre")
                cantidad = float(venta.get("cantidad", 1))
                precio = float(venta.get("precio_unitario", 0))
                total = cantidad * precio

                guardar_venta_excel(
                    fecha=fecha_hoy,
                    hora=hora_ahora,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=precio,
                    total=total,
                    vendedor=vendedor
                )
                ventas_registradas.append(f"• {producto}: {int(cantidad)} x ${precio:,.0f} = *${total:,.0f}*")

            confirmacion = "✅ *Venta registrada por {}*\n\n{}".format(
                vendedor, "\n".join(ventas_registradas)
            )
            await update.message.reply_text(confirmacion, parse_mode="Markdown")

    except Exception as e:
        print(f"Error procesando mensaje: {e}")


# ============================================================
# MANEJADOR DE MENSAJES DE VOZ
# ============================================================

async def manejar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Descarga el audio, lo transcribe y lo procesa como venta."""
    vendedor = update.message.from_user.first_name or "Desconocido"

    await update.message.reply_text("🎤 Escuchando tu audio...")

    try:
        # Descargar el audio
        archivo_voz = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await archivo_voz.download_to_drive(tmp.name)
            ruta_audio = tmp.name

        # Transcribir
        texto_transcrito = await transcribir_audio(ruta_audio)
        os.unlink(ruta_audio)  # Borrar archivo temporal

        await update.message.reply_text(f"📝 Escuché: _{texto_transcrito}_", parse_mode="Markdown")

        # Procesar como venta
        resultado = interpretar_venta_con_claude(texto_transcrito, vendedor)

        if resultado.get("es_venta"):
            ventas_registradas = []
            fecha_hoy = datetime.now().strftime("%Y-%m-%d")
            hora_ahora = datetime.now().strftime("%H:%M")

            for venta in resultado.get("ventas", []):
                producto = venta.get("producto", "Sin nombre")
                cantidad = float(venta.get("cantidad", 1))
                precio = float(venta.get("precio_unitario", 0))
                total = cantidad * precio

                guardar_venta_excel(
                    fecha=fecha_hoy,
                    hora=hora_ahora,
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=precio,
                    total=total,
                    vendedor=vendedor
                )
                ventas_registradas.append(f"• {producto}: {int(cantidad)} x ${precio:,.0f} = *${total:,.0f}*")

            confirmacion = "✅ *Venta registrada por {}*\n\n{}".format(
                vendedor, "\n".join(ventas_registradas)
            )
            await update.message.reply_text(confirmacion, parse_mode="Markdown")
        else:
            await update.message.reply_text("ℹ️ No detecté una venta en tu audio. ¿Puedes intentarlo de nuevo?")

    except Exception as e:
        print(f"Error procesando audio: {e}")
        await update.message.reply_text("⚠️ Hubo un error procesando el audio. Intenta de nuevo.")


# ============================================================
# INICIO DEL BOT
# ============================================================

def main():
    """Función principal que inicia el bot."""
    print("🚀 Iniciando bot de ventas...")
    inicializar_excel()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registrar comandos
    app.add_handler(CommandHandler("start", comando_inicio))
    app.add_handler(CommandHandler("ayuda", comando_ayuda))
    app.add_handler(CommandHandler("hoy", comando_reporte_hoy))
    app.add_handler(CommandHandler("semana", comando_reporte_semana))
    app.add_handler(CommandHandler("mes", comando_reporte_mes))
    app.add_handler(CommandHandler("excel", comando_excel))

    # Registrar manejadores de mensajes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje_texto))
    app.add_handler(MessageHandler(filters.VOICE, manejar_audio))

    print("✅ Bot funcionando. Esperando mensajes...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
