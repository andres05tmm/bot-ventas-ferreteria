"""
routers/bancolombia_notifier.py — Transferencias Bancolombia → Telegram vía Gmail propio

FLUJO COMPLETO:
  Email de Bancolombia llega al correo dedicado (distinto al de compras fiscal)
    └─► Gmail notifica a Google Pub/Sub (watch independiente)
          └─► Pub/Sub hace POST a /bancolombia/gmail/webhook
                └─► descarga headers del mensaje (metadatos, ~10ms)
                      └─► ¿es email de transferencia entrante de Bancolombia?
                            ├─► SÍ → descarga body → parsea monto/remitente/descripción
                            │         └─► envía a Telegram → registra en BD
                            └─► NO → skip silencioso

VARIABLES DE ENTORNO (separadas de compras_fiscal):
  BANCOLOMBIA_GMAIL_CLIENT_ID      → OAuth2 client ID (puede ser el mismo proyecto GCP)
  BANCOLOMBIA_GMAIL_CLIENT_SECRET  → OAuth2 client secret
  BANCOLOMBIA_GMAIL_REFRESH_TOKEN  → token de refresco del correo Bancolombia
  BANCOLOMBIA_GMAIL_USER           → correo donde llegan las notificaciones (ej: ferreteria.bancolombia@gmail.com)
  BANCOLOMBIA_PUBSUB_TOPIC         → projects/TU_PROJECT/topics/bancolombia-notif
  BANCOLOMBIA_PUBSUB_TOKEN         → token secreto para validar el push de Pub/Sub

YA EXISTENTES (reutilizadas):
  TELEGRAM_TOKEN            → token del bot
  TELEGRAM_NOTIFY_CHAT_ID   → ID del grupo de Telegram (número negativo)

REMITENTES BANCOLOMBIA reconocidos:
  notificaciones@notificaciones.bancolombia.com.co
  alertas@notificaciones.bancolombia.com.co
  no-reply@notificaciones.bancolombia.com.co
  transacciones@notificaciones.bancolombia.com.co
"""

from __future__ import annotations

import base64
import html as _html_module
import json
import logging
import os
import re
from datetime import datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

import db as _db
from config import COLOMBIA_TZ

log    = logging.getLogger("ferrebot.bancolombia_notifier")
router = APIRouter()

GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE  = "https://gmail.googleapis.com/gmail/v1"

# ── Dominios/fragmentos de remitentes oficiales de Bancolombia ───────────────
# Se verifica que el campo From contenga CUALQUIERA de estos fragmentos.
# Bancolombia usa varios dominios:
#   - notificaciones.bancolombia.com.co
#   - an.notificacionesbancolombia.com
#   - alertas.bancolombia.com.co
# Por eso se busca el substring "bancolombia" en el remitente.
_BANCOLOMBIA_SENDER_FRAGMENTS = [
    "bancolombia",
]

# ── Palabras clave en Subject que indican movimiento de dinero ───────────────
# Lista amplia — también cubre subjects genéricos como "Alertas y Notificaciones"
_SUBJECT_KEYWORDS_MOVIMIENTO = [
    "transferencia",
    "te transfirieron",
    "recibiste",
    "transferido",
    "consignación",
    "consignacion",
    "abono",
    "pse",
    "nequi",
    "daviplata",
    "te han transferido",
    "recibido",
    "movimiento",
    "alertas y notificaciones",
    "alerta",
    "notificacion",
    "notificación",
    "todo salio bien",
    "todo salió bien",
    "pago",
    "débito",
    "debito",
    "crédito",
    "credito",
    "transaccion",
    "transacción",
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. OAuth2 — access_token para la cuenta Bancolombia
# ─────────────────────────────────────────────────────────────────────────────

async def _get_access_token() -> str:
    """Obtiene access_token OAuth2 usando las credenciales del correo Bancolombia."""
    client_id     = (os.getenv("BANCOLOMBIA_GMAIL_CLIENT_ID")     or "").strip()
    client_secret = (os.getenv("BANCOLOMBIA_GMAIL_CLIENT_SECRET") or "").strip()
    refresh_token = (os.getenv("BANCOLOMBIA_GMAIL_REFRESH_TOKEN") or "").strip()

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Faltan variables de entorno: BANCOLOMBIA_GMAIL_CLIENT_ID, "
            "BANCOLOMBIA_GMAIL_CLIENT_SECRET o BANCOLOMBIA_GMAIL_REFRESH_TOKEN"
        )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(GMAIL_TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "client_id":     client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        })
        resp.raise_for_status()
        return resp.json()["access_token"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Gmail API — obtener mensajes nuevos por historyId
# ─────────────────────────────────────────────────────────────────────────────

async def _get_message_ids_from_history(history_id: str, token: str, user: str) -> list[str]:
    """Consulta history.list y retorna IDs de mensajes agregados al INBOX."""
    url = f"{GMAIL_API_BASE}/users/{user}/history"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"startHistoryId": history_id, "historyTypes": "messageAdded"},
        )
        if resp.status_code == 404:
            log.warning("historyId %s expirado — sin mensajes que procesar", history_id)
            return []
        resp.raise_for_status()
        data = resp.json()
        log.debug("Bancolombia history.list: %s", data)

    message_ids: list[str] = []
    for entry in data.get("history", []):
        for msg in entry.get("messagesAdded", []):
            mid = msg.get("message", {}).get("id")
            if mid and mid not in message_ids:
                message_ids.append(mid)
    return message_ids


async def _get_message_headers(message_id: str, token: str, user: str) -> list[dict]:
    """
    Descarga solo los headers From y Subject (formato metadata, ~10ms).
    NOTA: metadataHeaders debe pasarse como parámetros separados, no como
    un solo string "From,Subject" — Gmail API no acepta la forma combinada.
    Retorna lista vacía si falla.
    """
    url = f"{GMAIL_API_BASE}/users/{user}/messages/{message_id}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                # Lista de tuples para enviar metadataHeaders dos veces:
                # ?format=metadata&metadataHeaders=From&metadataHeaders=Subject
                params=[
                    ("format",          "metadata"),
                    ("metadataHeaders", "From"),
                    ("metadataHeaders", "Subject"),
                ],
            )
            resp.raise_for_status()
            data    = resp.json()
            headers = data.get("payload", {}).get("headers", [])
            log.debug(
                "Headers mensaje %s → payload keys=%s headers_count=%d",
                message_id, list(data.get("payload", {}).keys()), len(headers),
            )
            return headers
    except Exception as e:
        log.warning("Error obteniendo headers del mensaje %s: %s", message_id, e)
        return []


async def _get_message_full(message_id: str, token: str, user: str) -> dict | None:
    """Descarga el mensaje completo (payload con body). Retorna None si falla."""
    url = f"{GMAIL_API_BASE}/users/{user}/messages/{message_id}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "full"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        log.warning("Error descargando mensaje completo %s: %s", message_id, e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Detección — ¿es un email de transferencia entrante de Bancolombia?
# ─────────────────────────────────────────────────────────────────────────────

def _es_transferencia_entrante(headers: list[dict]) -> bool:
    """
    Recibe la lista de headers (payload.headers) de un mensaje Gmail.
    Retorna True si el email proviene de Bancolombia (cualquier dominio oficial).

    Estrategia:
      1. El campo From debe contener el fragmento "bancolombia" (cubre todos los dominios).
      2. El Subject debe contener al menos una palabra clave de movimiento.
         La lista es amplia para capturar subjects genéricos como "Alertas y Notificaciones".
    """
    from_val = ""
    subject  = ""
    for h in headers:
        name = (h.get("name") or "").lower()
        val  = (h.get("value") or "").lower()
        if name == "from":
            from_val = val
        elif name == "subject":
            subject = val

    # Paso 1: ¿viene de un dominio Bancolombia?
    if not any(frag in from_val for frag in _BANCOLOMBIA_SENDER_FRAGMENTS):
        log.debug("From '%s' no es Bancolombia — skip", from_val[:80])
        return False

    # Paso 2: ¿el subject indica algún movimiento?
    if any(kw in subject for kw in _SUBJECT_KEYWORDS_MOVIMIENTO):
        return True

    # Si el subject no coincide con ninguna palabra clave, igual procesar
    # porque Bancolombia a veces usa subjects muy genéricos.
    # Se loguea para auditoría.
    log.info(
        "Email Bancolombia con subject no reconocido ('%s') — procesando de todas formas",
        subject[:80],
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Parseo del body HTML del email
# ─────────────────────────────────────────────────────────────────────────────

def _extraer_body(payload: dict) -> str:
    """Extrae el body HTML (o text/plain) de un mensaje Gmail, prefiriendo HTML."""
    html_content  = ""
    plain_content = ""

    def _walk(parts: list) -> None:
        nonlocal html_content, plain_content
        for part in parts:
            mime     = part.get("mimeType", "")
            data_b64 = part.get("body", {}).get("data", "")
            if mime == "text/html" and data_b64 and not html_content:
                try:
                    html_content = base64.urlsafe_b64decode(data_b64 + "==").decode("utf-8", errors="replace")
                except Exception:
                    pass
            elif mime == "text/plain" and data_b64 and not plain_content:
                try:
                    plain_content = base64.urlsafe_b64decode(data_b64 + "==").decode("utf-8", errors="replace")
                except Exception:
                    pass
            sub = part.get("parts", [])
            if sub:
                _walk(sub)

    parts = payload.get("parts", [])
    if parts:
        _walk(parts)
    else:
        # Mensaje simple
        data_b64 = payload.get("body", {}).get("data", "")
        if data_b64:
            try:
                return base64.urlsafe_b64decode(data_b64 + "==").decode("utf-8", errors="replace")
            except Exception:
                pass

    return html_content or plain_content


def _limpiar_html(texto: str) -> str:
    """Elimina tags HTML y decodifica entidades."""
    sin_tags = re.sub(r"<[^>]+>", " ", texto)
    return _html_module.unescape(sin_tags)


def _extraer_valor(texto: str, patrones: list[str]) -> str:
    """Aplica una lista de patrones regex y retorna el primer grupo capturado."""
    for patron in patrones:
        m = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return ""


def parsear_email_bancolombia(body_raw: str) -> dict:
    """
    Extrae los campos relevantes de un email de Bancolombia (HTML o texto plano).

    Retorna:
      monto         — int (pesos, sin decimales)
      monto_str     — str formateada "$1.500.000"
      remitente     — str nombre de quien transfirió
      descripcion   — str referencia/concepto
      tipo          — str tipo de canal (Transferencia, PSE, Nequi, etc.)
      hora          — str hora HH:MM
      fecha_str     — str DD/MM/YYYY
    """
    texto = _limpiar_html(body_raw)
    texto = re.sub(r"\s+", " ", texto)

    # ── Monto ─────────────────────────────────────────────────────────────────
    monto_str_raw = _extraer_valor(texto, [
        r"\$\s*([\d][0-9.,]+)",
        r"por valor de\s+\$?\s*([\d][0-9.,]+)",
        r"valor[:\s]+\$?\s*([\d][0-9.,]+)",
        r"monto[:\s]+\$?\s*([\d][0-9.,]+)",
        r"transferencia de\s+\$?\s*([\d][0-9.,]+)",
        r"recibiste\s+\$?\s*([\d][0-9.,]+)",
        r"te transfirieron\s+\$?\s*([\d][0-9.,]+)",
    ])

    monto     = 0
    monto_fmt = ""
    if monto_str_raw:
        # Quitar separadores de miles y decimales: "1.500.000,00" → 1500000
        limpio = re.sub(r"[.,](\d{2})$", "", monto_str_raw)
        limpio = limpio.replace(".", "").replace(",", "")
        try:
            monto = int(limpio)
        except ValueError:
            monto = 0
        monto_fmt = f"${monto:,}".replace(",", ".") if monto > 0 else f"${monto_str_raw}"

    # ── Remitente ─────────────────────────────────────────────────────────────
    remitente = _extraer_valor(texto, [
        r"de[:\s]+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,60}?)(?:\s{2,}|\||\n|cuenta|ref|desc|documento)",
        r"remitente[:\s]+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,60}?)(?:\s{2,}|\||$)",
        r"nombre[:\s]+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,60}?)(?:\s{2,}|\||$)",
        r"origen[:\s]+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,60}?)(?:\s{2,}|\||$)",
        r"quien env[íi]a[:\s]+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,60}?)(?:\s{2,}|\||$)",
        r"transferido por[:\s]+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{2,60}?)(?:\s{2,}|\||$)",
    ])

    # ── Descripción / referencia ──────────────────────────────────────────────
    descripcion = _extraer_valor(texto, [
        r"descripci[oó]n[:\s]+([^\n|]{3,100}?)(?:\s{2,}|\||$)",
        r"referencia[:\s]+([^\n|]{3,100}?)(?:\s{2,}|\||$)",
        r"concepto[:\s]+([^\n|]{3,100}?)(?:\s{2,}|\||$)",
        r"motivo[:\s]+([^\n|]{3,100}?)(?:\s{2,}|\||$)",
        r"mensaje[:\s]+([^\n|]{3,100}?)(?:\s{2,}|\||$)",
    ])

    # ── Tipo de canal ─────────────────────────────────────────────────────────
    tipo = _extraer_valor(texto, [
        r"tipo[:\s]+(transferencia|pse|nequi|daviplata|consignaci[oó]n|[^\n|]{3,40}?)(?:\s{2,}|\||$)",
        r"canal[:\s]+([^\n|]{3,40}?)(?:\s{2,}|\||$)",
    ])
    if not tipo:
        for kw in ["PSE", "Nequi", "Daviplata", "Consignación", "Transferencia"]:
            if kw.lower() in texto.lower():
                tipo = kw
                break

    # ── Hora ─────────────────────────────────────────────────────────────────
    hora = _extraer_valor(texto, [
        r"(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)",
        r"hora[:\s]+(\d{1,2}:\d{2}(?::\d{2})?)",
    ])

    # ── Fecha ─────────────────────────────────────────────────────────────────
    fecha_str = _extraer_valor(texto, [
        r"(\d{2}/\d{2}/\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"fecha[:\s]+(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
    ])

    return {
        "monto":       monto,
        "monto_str":   monto_fmt or monto_str_raw or "—",
        "remitente":   remitente[:100] if remitente else "",
        "descripcion": descripcion[:200] if descripcion else "",
        "tipo":        tipo[:60] if tipo else "Transferencia",
        "hora":        hora[:20] if hora else "",
        "fecha_str":   fecha_str[:20] if fecha_str else "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Telegram — mensaje formateado
# ─────────────────────────────────────────────────────────────────────────────

def _construir_mensaje(datos: dict, subject: str) -> str:
    """Construye el mensaje Markdown para Telegram."""
    ahora = datetime.now(COLOMBIA_TZ).strftime("%H:%M")

    lineas = ["🏦 *Transferencia recibida — Bancolombia*"]

    if datos["monto"] > 0:
        lineas.append(f"💰 *{datos['monto_str']}*")
    else:
        # Fallback: usar el subject del email
        lineas.append(f"📩 {subject[:80]}")

    if datos["remitente"]:
        lineas.append(f"👤 De: {datos['remitente']}")

    if datos["descripcion"]:
        lineas.append(f"📝 {datos['descripcion']}")

    tipo_lower = datos["tipo"].lower()
    if datos["tipo"] and tipo_lower not in ("transferencia", ""):
        lineas.append(f"📲 Canal: {datos['tipo']}")

    hora_display = datos["hora"] or ahora
    lineas.append(f"🕐 {hora_display.strip()}")

    return "\n".join(lineas)


async def _enviar_telegram(mensaje: str) -> None:
    """Envía mensaje al grupo de Telegram configurado."""
    token   = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
    if not token or not chat_id:
        log.warning("Falta TELEGRAM_TOKEN o TELEGRAM_NOTIFY_CHAT_ID — notificación omitida")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id":                  chat_id,
                    "text":                     mensaje,
                    "parse_mode":               "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code != 200:
                log.warning("Telegram respondió %s: %s", resp.status_code, resp.text[:200])
            else:
                log.info("✅ Notificación Bancolombia enviada a Telegram")
    except Exception as e:
        log.warning("Error enviando a Telegram: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Deduplicación y persistencia
# ─────────────────────────────────────────────────────────────────────────────

def _ya_notificado(gmail_message_id: str) -> bool:
    try:
        row = _db.query_one(
            "SELECT id FROM bancolombia_transferencias WHERE gmail_message_id = %s LIMIT 1",
            (gmail_message_id,),
        )
        return row is not None
    except Exception as e:
        log.warning("Error consultando deduplicación Bancolombia: %s", e)
        return False


def _registrar_transferencia(gmail_message_id: str, datos: dict) -> None:
    """Persiste la transferencia para deduplicación y auditoría."""
    try:
        hoy = datetime.now(COLOMBIA_TZ).strftime("%Y-%m-%d")
        _db.execute(
            """
            INSERT INTO bancolombia_transferencias (
                gmail_message_id, fecha, hora, monto,
                remitente, descripcion, tipo_transaccion, notificado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (gmail_message_id) DO NOTHING
            """,
            (
                gmail_message_id,
                hoy,
                datos.get("hora", ""),
                datos.get("monto", 0),
                datos.get("remitente", ""),
                datos.get("descripcion", ""),
                datos.get("tipo", ""),
            ),
        )
        log.info(
            "Transferencia Bancolombia registrada — gmail_id=%s monto=%s remitente=%s",
            gmail_message_id, datos.get("monto"), datos.get("remitente"),
        )
    except Exception as e:
        log.warning("Error registrando transferencia Bancolombia en BD: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Persistencia del historyId (igual que gmail_webhook.py)
# ─────────────────────────────────────────────────────────────────────────────

_HISTORY_KEY = "bancolombia_gmail_last_history_id"


def _cargar_last_history_id() -> str | None:
    try:
        row = _db.query_one(
            "SELECT valor FROM config WHERE clave = %s",
            (_HISTORY_KEY,),
        )
        return row["valor"] if row else None
    except Exception as e:
        log.warning("Error leyendo %s de config: %s", _HISTORY_KEY, e)
        return None


def _guardar_last_history_id(history_id: str) -> None:
    try:
        _db.execute(
            """
            INSERT INTO config (clave, valor, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (clave) DO UPDATE
                SET valor = EXCLUDED.valor, updated_at = NOW()
            """,
            (_HISTORY_KEY, history_id),
        )
    except Exception as e:
        log.warning("Error guardando %s en config: %s", _HISTORY_KEY, e)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tarea de fondo — procesar notificación Pub/Sub
# ─────────────────────────────────────────────────────────────────────────────

async def _background_procesar(history_id_notificacion: str) -> None:
    """Procesa todos los mensajes nuevos desde el historyId notificado."""
    if not _db.DB_DISPONIBLE:
        log.error("DB no disponible — notificación Bancolombia omitida")
        return

    gmail_user = (os.getenv("BANCOLOMBIA_GMAIL_USER") or "me").strip()

    history_id_guardado = _cargar_last_history_id()
    if history_id_guardado and int(history_id_guardado) < int(history_id_notificacion):
        start_id = history_id_guardado
        log.info(
            "Usando historyId guardado (%s) en vez del notificado (%s)",
            history_id_guardado, history_id_notificacion,
        )
    else:
        start_id = history_id_notificacion

    try:
        token = await _get_access_token()
    except Exception as e:
        log.error("Error obteniendo access_token Bancolombia: %s", e)
        return

    try:
        message_ids = await _get_message_ids_from_history(start_id, token, gmail_user)
    except Exception as e:
        log.error("Error en history.list Bancolombia (historyId=%s): %s", start_id, e)
        return

    if not message_ids:
        log.debug("historyId %s sin mensajes nuevos", start_id)
        _guardar_last_history_id(history_id_notificacion)
        return

    for mid in message_ids:
        try:
            await _procesar_mensaje(mid, token, gmail_user)
        except Exception as e:
            log.error("Error procesando mensaje Bancolombia %s: %s", mid, e, exc_info=True)

    _guardar_last_history_id(history_id_notificacion)


async def _procesar_mensaje(message_id: str, token: str, user: str) -> None:
    """Descarga, valida, parsea y notifica un mensaje de Gmail."""
    if _ya_notificado(message_id):
        log.info("Mensaje %s ya notificado — skip", message_id)
        return

    # Primero: solo headers (~10ms, sin descargar body)
    headers = await _get_message_headers(message_id, token, user)
    if not headers:
        log.warning("No se pudieron obtener headers del mensaje %s", message_id)
        return

    if not _es_transferencia_entrante(headers):
        log.debug("Mensaje %s no es transferencia entrante Bancolombia — skip", message_id)
        return

    # Extraer subject para fallback del mensaje Telegram
    subject = ""
    for h in headers:
        if (h.get("name") or "").lower() == "subject":
            subject = h.get("value", "")
            break

    log.info("📱 Transferencia Bancolombia detectada — mensaje %s | subject: %s", message_id, subject)

    # Descargar body completo
    msg = await _get_message_full(message_id, token, user)
    if not msg:
        log.warning("No se pudo descargar body del mensaje %s", message_id)
        datos = {"monto": 0, "monto_str": "—", "remitente": "", "descripcion": "", "tipo": "", "hora": "", "fecha_str": ""}
    else:
        body_text = _extraer_body(msg.get("payload", {}))
        datos     = parsear_email_bancolombia(body_text) if body_text else {
            "monto": 0, "monto_str": "—", "remitente": "", "descripcion": "", "tipo": "", "hora": "", "fecha_str": "",
        }

    mensaje_tg = _construir_mensaje(datos, subject)
    await _enviar_telegram(mensaje_tg)
    _registrar_transferencia(message_id, datos)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/bancolombia/gmail/webhook")
async def bancolombia_pubsub_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Query(..., description="Token secreto configurado en BANCOLOMBIA_PUBSUB_TOKEN"),
):
    """Recibe notificaciones push de Google Pub/Sub cuando llega un email al correo Bancolombia."""
    pubsub_token = (os.getenv("BANCOLOMBIA_PUBSUB_TOKEN") or "").strip()
    if not pubsub_token or token != pubsub_token:
        log.warning("Webhook Bancolombia con token inválido: %s", token[:8] if token else "—")
        raise HTTPException(status_code=403, detail="Token inválido")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body inválido — se esperaba JSON")

    message  = body.get("message", {})
    data_b64 = message.get("data", "")

    if not data_b64:
        return {"ok": True, "skip": "sin_data"}

    try:
        data_json  = json.loads(base64.urlsafe_b64decode(data_b64 + "==").decode())
        history_id = str(int(data_json.get("historyId", 0)) - 1)
    except Exception as e:
        log.warning("Error decodificando data Pub/Sub Bancolombia: %s", e)
        return {"ok": True, "skip": "data_invalida"}

    if not history_id or history_id == "-1":
        return {"ok": True, "skip": "sin_historyId"}

    log.info("📬 Pub/Sub Bancolombia recibido — historyId=%s", history_id)
    background_tasks.add_task(_background_procesar, history_id)
    return {"ok": True, "historyId": history_id}


@router.post("/bancolombia/gmail/watch")
async def bancolombia_watch_setup():
    """
    Configura (o renueva) el Gmail watch para el correo Bancolombia.
    El watch expira cada 7 días — llamar este endpoint semanalmente.
    """
    pubsub_topic = (os.getenv("BANCOLOMBIA_PUBSUB_TOPIC") or "").strip()
    gmail_user   = (os.getenv("BANCOLOMBIA_GMAIL_USER") or "me").strip()

    if not pubsub_topic:
        raise HTTPException(
            status_code=500,
            detail="Falta variable BANCOLOMBIA_PUBSUB_TOPIC (ej: projects/mi-proyecto/topics/bancolombia-notif)",
        )

    try:
        token = await _get_access_token()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error OAuth Bancolombia: {e}")

    url = f"{GMAIL_API_BASE}/users/{gmail_user}/watch"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"labelIds": ["INBOX"], "topicName": pubsub_topic},
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Gmail API error {e.response.status_code}: {e.response.text}",
            )
        data = resp.json()

    expire_dt = None
    if "expiration" in data:
        try:
            expire_dt = datetime.fromtimestamp(int(data["expiration"]) / 1000).isoformat()
        except Exception:
            pass

    log.info("✅ Watch Bancolombia configurado — historyId=%s, expira=%s", data.get("historyId"), expire_dt)
    return {
        "ok":        True,
        "historyId": data.get("historyId"),
        "expira":    expire_dt,
        "topic":     pubsub_topic,
        "nota":      "El watch expira en ~7 días. Renuévalo con POST /bancolombia/gmail/watch",
    }


@router.get("/bancolombia/transferencias/status")
async def bancolombia_status():
    """Estado del notificador: estadísticas de transferencias procesadas."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="DB no disponible")
    try:
        fila = _db.query_one(
            """
            SELECT
                COUNT(*)              AS total,
                COALESCE(SUM(monto), 0) AS monto_total,
                MAX(created_at)::text AS ultima_notificacion
            FROM bancolombia_transferencias
            WHERE notificado = TRUE
            """
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando BD: {e}")

    return {
        "ok":    True,
        "stats": dict(fila) if fila else {},
        "nota":  "Notificaciones enviadas al grupo configurado en TELEGRAM_NOTIFY_CHAT_ID",
    }


@router.get("/bancolombia/transferencias")
async def listar_transferencias(limite: int = 20):
    """Últimas transferencias recibidas (auditoría)."""
    if not _db.DB_DISPONIBLE:
        raise HTTPException(status_code=503, detail="DB no disponible")
    try:
        rows = _db.query_all(
            """
            SELECT id, fecha, hora, monto, remitente, descripcion,
                   tipo_transaccion, created_at::text
            FROM bancolombia_transferencias
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (min(limite, 100),),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando BD: {e}")

    return {"ok": True, "transferencias": [dict(r) for r in rows]}
