"""
Configuracion central: variables de entorno, constantes y clientes de API.
100% PostgreSQL — sin Google Drive, Sheets ni archivos Excel/JSON locales.
"""

import os
import logging
from datetime import timezone, timedelta

import anthropic
import openai

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logger = logging.getLogger("ferrebot")

# ─────────────────────────────────────────────
# ZONA HORARIA
# ─────────────────────────────────────────────
COLOMBIA_TZ = timezone(timedelta(hours=-5))

# ─────────────────────────────────────────────
# VARIABLES DE ENTORNO
# ─────────────────────────────────────────────
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL       = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT      = int(os.getenv("PORT", "8443"))
DATABASE_URL      = os.getenv("DATABASE_URL")

# Validar claves obligatorias al importar
_CLAVES_REQUERIDAS = {
    "TELEGRAM_TOKEN":    TELEGRAM_TOKEN,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "OPENAI_API_KEY":    OPENAI_API_KEY,
}
_faltantes = [k for k, v in _CLAVES_REQUERIDAS.items() if not v]
if _faltantes:
    print("\n❌ Faltan claves en las variables de entorno:")
    for c in _faltantes:
        print(f"   • {c}")
    raise SystemExit(1)

# ─────────────────────────────────────────────
# VERSION
# ─────────────────────────────────────────────
VERSION = "v9.0-pg-only"

# ─────────────────────────────────────────────
# Nombres de meses en español
# ─────────────────────────────────────────────
MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo",  6: "Junio",   7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

# ─────────────────────────────────────────────
# CLIENTES DE API (creados una sola vez)
# ─────────────────────────────────────────────
claude_client = anthropic.Anthropic(
    api_key=ANTHROPIC_API_KEY,
    default_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
