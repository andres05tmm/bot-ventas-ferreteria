"""
Configuracion central: variables de entorno, constantes y clientes de API.
100% PostgreSQL — sin Google Drive, Sheets ni archivos Excel/JSON locales.
"""

import os
import logging
from zoneinfo import ZoneInfo

import anthropic
import openai

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logger = logging.getLogger("ferrebot")

# ─────────────────────────────────────────────
# ZONA HORARIA
# ─────────────────────────────────────────────
# ZoneInfo("America/Bogota") es preferible a timezone(timedelta(hours=-5)) porque:
#   - str(COLOMBIA_TZ) produce "America/Bogota" (nombre IANA válido para APScheduler)
#   - Maneja DST correctamente si Colombia alguna vez lo adoptara
#   - Disponible en stdlib desde Python 3.9
COLOMBIA_TZ = ZoneInfo("America/Bogota")

# ─────────────────────────────────────────────
# VARIABLES DE ENTORNO
# ─────────────────────────────────────────────
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL       = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT      = int(os.getenv("PORT", "8443"))
DATABASE_URL      = os.getenv("DATABASE_URL")
SENTRY_DSN        = os.getenv("SENTRY_DSN", "")   # Opcional — captura errores en producción

# CORS_ORIGIN: dominio HTTPS del dashboard (frontend). Una sola fuente de verdad
# usada por api.py (CORSMiddleware + OPTIONS handler) y routers/auth.py (header
# de la respuesta JWT). Sin default hardcoded — el operador debe configurarlo
# explícitamente para cada despliegue. Si queda vacío, api.py loguea warning.
CORS_ORIGIN       = os.getenv("CORS_ORIGIN", "")

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
# FEATURE FLAGS — activación de módulos por ferretería
# ─────────────────────────────────────────────
# Cada módulo opcional se enciende/apaga por env var. Si la var NO está seteada,
# se AUTODETECTA por la presencia de la credencial clave del módulo: así Punto
# Rojo (que ya tiene MATIAS_*, BOLD_*, etc. configuradas) mantiene todo activo
# sin tocar nada, y una ferretería nueva sin esas credenciales arranca mínima.
# El valor explícito de la env var (true/false) siempre tiene prioridad.
def _flag(nombre: str, autodetect: bool = False) -> bool:
    v = os.getenv(nombre)
    if v is not None and v.strip() != "":
        return v.strip().lower() in ("true", "1", "yes", "si", "sí")
    return autodetect


FE_HABILITADA            = _flag("FE_HABILITADA",            autodetect=bool(os.getenv("MATIAS_EMAIL")))
HONORARIOS_HABILITADO    = _flag("HONORARIOS_HABILITADO",    autodetect=bool(os.getenv("HONORARIOS_CHAT_ID")))
BANCOLOMBIA_HABILITADO   = _flag("BANCOLOMBIA_HABILITADO",   autodetect=bool(os.getenv("BANCOLOMBIA_GMAIL_CLIENT_ID")))
BOLD_HABILITADO          = _flag("BOLD_HABILITADO",          autodetect=bool(os.getenv("BOLD_WEBHOOK_SECRET")))
WOMPI_HABILITADO         = _flag("WOMPI_HABILITADO",         autodetect=bool(os.getenv("WOMPI_EVENTS_SECRET")))
GMAIL_COMPRAS_HABILITADO = _flag("GMAIL_COMPRAS_HABILITADO", autodetect=bool(os.getenv("GMAIL_CLIENT_ID")))
CLOUDINARY_HABILITADO    = _flag("CLOUDINARY_HABILITADO",    autodetect=bool(os.getenv("CLOUDINARY_CLOUD_NAME")))
IA_MEMORIA_AVANZADA      = _flag("IA_MEMORIA_AVANZADA",      autodetect=True)
INVENTARIO_HABILITADO    = _flag("INVENTARIO_HABILITADO",    autodetect=True)
CAJA_HABILITADA          = _flag("CAJA_HABILITADA",          autodetect=True)
FIADOS_HABILITADO        = _flag("FIADOS_HABILITADO",        autodetect=True)
# Motor IA con tool-calling nativo (M-01). Default OFF: el camino de tags de
# texto sigue siendo el activo hasta encender el flag en Railway. Permite
# rollback instantáneo sin redeploy.
IA_TOOL_CALLING          = _flag("IA_TOOL_CALLING",          autodetect=False)
# Búsqueda semántica del catálogo (embeddings) como fallback del fuzzy en voz.
# Default ON: la OPENAI_API_KEY siempre está presente y el módulo es fail-safe
# (ante cualquier error → se comporta como si no existiera). Apagable por env.
IA_SEMANTIC_CATALOGO     = _flag("IA_SEMANTIC_CATALOGO",     autodetect=True)


def _validar_flags() -> None:
    """Aborta el arranque si un flag activo carece de sus credenciales."""
    problemas = []
    if FE_HABILITADA and not os.getenv("MATIAS_EMAIL"):
        problemas.append("FE_HABILITADA=true requiere MATIAS_EMAIL / MATIAS_PASSWORD / MATIAS_RESOLUTION")
    if BANCOLOMBIA_HABILITADO and not os.getenv("BANCOLOMBIA_GMAIL_CLIENT_ID"):
        problemas.append("BANCOLOMBIA_HABILITADO=true requiere BANCOLOMBIA_GMAIL_CLIENT_ID / _SECRET / _REFRESH_TOKEN")
    if GMAIL_COMPRAS_HABILITADO and not os.getenv("GMAIL_CLIENT_ID"):
        problemas.append("GMAIL_COMPRAS_HABILITADO=true requiere GMAIL_CLIENT_ID / _SECRET / _REFRESH_TOKEN")
    if problemas:
        print("\n❌ Configuración de feature flags inválida:")
        for p in problemas:
            print(f"   • {p}")
        raise SystemExit(1)


_validar_flags()

# ─────────────────────────────────────────────
# VERSION
# ─────────────────────────────────────────────
VERSION = "v9.0-pg-only"

# ─────────────────────────────────────────────
# ARCHIVOS LOCALES (legacy — usados por memoria.py
# mientras notas/negocio no se migren a config_sistema PG)
# ─────────────────────────────────────────────
MEMORIA_FILE    = os.getenv("MEMORIA_FILE", "memoria.json")
EXCEL_FILA_DATOS = 2  # fila donde comienzan los datos en Excels subidos por el usuario

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
# Headers beta de Anthropic:
#   - prompt-caching-2024-07-31      → habilita cache_control en los mensajes
#   - extended-cache-ttl-2025-04-11  → permite TTL de 1h (en lugar de 5min default)
#     El TTL 1h cuesta 2× el precio base de escritura, pero nuestro catálogo no
#     cambia en todo el día — así que pagamos la escritura una vez y leemos barato
#     durante 1h con cada mensaje del vendedor (vs. reescribir cada 5min).
# ─────────────────────────────────────────────
# IDENTIDAD DEL NEGOCIO (adquirente / receptor)
# ─────────────────────────────────────────────
# Datos de la ferretería. Defaults = Punto Rojo para compatibilidad; en una
# ferretería nueva se sobreescriben por env. Se usan en facturación DIAN y CC.
EMPRESA_NOMBRE = os.getenv("EMPRESA_NOMBRE", "Ferretería Punto Rojo F.D")
EMPRESA_NIT    = os.getenv("EMPRESA_NIT", "1235046119-1")
EMPRESA_CIUDAD = os.getenv("EMPRESA_CIUDAD", "Cartagena, Bolívar")

# IDs internos de MATIAS para la ubicación (NO son códigos DANE; ver CLAUDE.md §10)
MATIAS_CITY_ID     = os.getenv("MATIAS_CITY_ID", "149")
MATIAS_POSTAL_CODE = os.getenv("MATIAS_POSTAL_CODE", "130001")
MATIAS_COUNTRY_ID  = os.getenv("MATIAS_COUNTRY_ID", "45")

# ─────────────────────────────────────────────
# MÓDULO HONORARIOS
# ─────────────────────────────────────────────
HONORARIOS_VALOR   = int(os.getenv("HONORARIOS_VALOR", "2000000"))
HONORARIOS_CHAT_ID = os.getenv("HONORARIOS_CHAT_ID", "")

# Proveedor que emite la Cuenta de Cobro + Documento Soporte (persona natural).
# Defaults = Andrés (Punto Rojo). En otra ferretería, el contratista pone los suyos.
HON_PROV_NOMBRE      = os.getenv("HONORARIOS_PROVEEDOR_NOMBRE", "Andrés Felipe Malo Hernández")
HON_PROV_NOMBRE_DIAN = os.getenv("HONORARIOS_PROVEEDOR_NOMBRE_DIAN", "MALO HERNANDEZ ANDRES FELIPE")
HON_PROV_CC          = os.getenv("HONORARIOS_PROVEEDOR_CC", "1.043.295.412")
HON_PROV_DNI         = os.getenv("HONORARIOS_PROVEEDOR_DNI", "1043295412")
HON_PROV_NIT         = os.getenv("HONORARIOS_PROVEEDOR_NIT", "1043295412-4")
HON_PROV_DIRECCION   = os.getenv("HONORARIOS_PROVEEDOR_DIRECCION", "CON EL REFUGIO BL 12 AP 2A")
HON_PROV_CIUDAD      = os.getenv("HONORARIOS_PROVEEDOR_CIUDAD", "Cartagena, Bolívar")
HON_PROV_MOBILE      = os.getenv("HONORARIOS_PROVEEDOR_MOBILE", "3001234567")
HON_PROV_EMAIL       = os.getenv("HONORARIOS_PROVEEDOR_EMAIL", "andresfmalo05@gmail.com")
HON_PROV_REGIMEN     = os.getenv("HONORARIOS_PROVEEDOR_REGIMEN", "No responsable de IVA — Artículo 437 E.T.")

claude_client = anthropic.Anthropic(
    api_key=ANTHROPIC_API_KEY,
    default_headers={
        "anthropic-beta": "prompt-caching-2024-07-31,extended-cache-ttl-2025-04-11"
    },
)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
