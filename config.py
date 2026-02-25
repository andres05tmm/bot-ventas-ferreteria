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

# Nombres de columnas en el Excel (deben coincidir con los encabezados reales de inicializar_hoja)
COL_FECHA    = "fecha"
COL_HORA     = "hora"
COL_PRODUCTO = "producto"
COL_CANTIDAD = "cantidad"
COL_PRECIO   = "valor unitario"
COL_TOTAL    = "total"
COL_ALIAS    = "alias"
COL_VENDEDOR = "vendedor"
COL_METODO   = "metodo de pago"

# Encabezados del Google Sheets del dia
SHEETS_HEADERS = [
    "CONSECUTIVO DE VENTA", "FECHA", "HORA", "ID CLIENTE", "CLIENTE",
    "Código del Producto", "PRODUCTO", "CANTIDAD", "VALOR UNITARIO",
    "TOTAL", "ALIAS", "VENDEDOR", "METODO DE PAGO"
]

# Nombres de meses en español (constante global, no repetir en cada funcion)
MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

# ─────────────────────────────────────────────
# CLIENTES DE API (creados una sola vez)
# ─────────────────────────────────────────────
claude_client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client  = openai.OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────
# CLIENTES DE GOOGLE (cached — se crean una vez)
# ─────────────────────────────────────────────
_creds_dict: dict = json.loads(GOOGLE_CREDENTIALS_JSON)

def _make_drive_service():
    creds = Credentials.from_service_account_info(
        _creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def _make_sheets_client():
    return gspread.service_account_from_dict(
        _creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
    )

# Instancias cacheadas — se inicializan la primera vez que se usen
_drive_service  = None
_sheets_client  = None

def get_drive_service():
    """Retorna el servicio de Drive, creandolo si aun no existe."""
    global _drive_service
    if _drive_service is None:
        _drive_service = _make_drive_service()
    return _drive_service

def get_sheets_client():
    """Retorna el cliente de gspread, creandolo si aun no existe."""
    global _sheets_client
    if _sheets_client is None:
        _sheets_client = _make_sheets_client()
    return _sheets_client

def reset_google_clients():
    """Fuerza recreacion de clientes Google en la proxima llamada (util tras errores de auth)."""
    global _drive_service, _sheets_client
    _drive_service = None
    _sheets_client = None

# ─────────────────────────────────────────────
# FLAGS DE DISPONIBILIDAD (estado de servicios)
# ─────────────────────────────────────────────
DRIVE_DISPONIBLE   = True
SHEETS_DISPONIBLE  = bool(SHEETS_ID)
