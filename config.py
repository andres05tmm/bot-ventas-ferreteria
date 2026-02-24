"""
Configuracion central: variables de entorno, constantes y clientes de API.
Los clientes de Google se crean una sola vez aqui (cached) para evitar
parsear las credenciales JSON y autenticar en cada llamada.
"""

import os
import json
from datetime import timezone, timedelta

import anthropic
import openai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ─────────────────────────────────────────────
# ZONA HORARIA
# ─────────────────────────────────────────────
COLOMBIA_TZ = timezone(timedelta(hours=-5))

# ─────────────────────────────────────────────
# VARIABLES DE ENTORNO
# ─────────────────────────────────────────────
TELEGRAM_TOKEN         = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY      = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY         = os.getenv("OPENAI_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_FOLDER_ID       = os.getenv("GOOGLE_FOLDER_ID")
SHEETS_ID              = os.getenv("SHEETS_ID", "")
WEBHOOK_URL            = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT           = int(os.getenv("PORT", "8443"))

# Validar claves obligatorias al importar
_CLAVES_REQUERIDAS = {
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "GOOGLE_CREDENTIALS_JSON": GOOGLE_CREDENTIALS_JSON,
    "GOOGLE_FOLDER_ID": GOOGLE_FOLDER_ID,
}
_faltantes = [k for k, v in _CLAVES_REQUERIDAS.items() if not v]
if _faltantes:
    print("\n❌ Faltan claves en las variables de entorno:")
    for c in _faltantes:
        print(f"   • {c}")
    raise SystemExit(1)

# ─────────────────────────────────────────────
# ARCHIVOS Y VERSION
# ─────────────────────────────────────────────
EXCEL_FILE    = "ventas.xlsx"
MEMORIA_FILE  = "memoria.json"
VERSION       = "v8.0-refactor"

# ─────────────────────────────────────────────
# ESTRUCTURA DEL EXCEL
# ─────────────────────────────────────────────
EXCEL_FILA_TITULO  = 1
EXCEL_FILA_HEADERS = 3
EXCEL_FILA_DATOS   = 4

# Nombres de columnas en el Excel (ACTUALIZADO AL NUEVO FORMATO)
COL_FECHA    = "FECHA"
COL_HORA     = "HORA"
COL_PRODUCTO = "PRODUCTO"
COL_CANTIDAD = "CANTIDAD"
COL_PRECIO   = "VALOR UNITARIO"
COL_TOTAL    = "TOTAL"
COL_ALIAS    = "ALIAS"
COL_VENDEDOR = "VENDEDOR"
COL_METODO   = "METODO DE PAGO"

# Encabezados del Google Sheets del dia
SHEETS_HEADERS = [
    "CONSECUTIVO DE VENTA", "FECHA", "HORA", "ID CLIENTE", "CLIENTE",
    "Código del Producto", "PRODUCTO", "CANTIDAD", "VALOR UNITARIO",
    "TOTAL", "ALIAS", "VENDEDOR", "METODO DE PAGO"
]

# Nombres de meses en español (constante global, no repetir en cada funcion)
MESES = {
    1: "Enero", 2:
