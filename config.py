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
