# -- stdlib --
import os
import time
import hmac
import hashlib
import logging
from datetime import datetime, timedelta

# -- terceros --
import jwt
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# -- propios --
import db

logger = logging.getLogger("ferrebot.auth")

router = APIRouter()


class TelegramAuthRequest(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


def _verify_telegram_hash(data: dict, received_hash: str) -> bool:
    """
    Verifica la autenticidad del hash de Telegram.

    Algoritmo:
    1. Construye data_check_string con todos los campos excepto 'hash',
       ordenados alfabéticamente, formato "key=value\n" (separado por newlines)
    2. secret_key = SHA256(BOT_TOKEN)
    3. expected_hash = HMAC-SHA256(secret_key, data_check_string).hexdigest()
    4. Compara con el hash recibido
    """
    bot_token = os.environ.get("BOT_TOKEN", "")
    if not bot_token:
        logger.warning("BOT_TOKEN no configurada")
        return False

    # Excluye 'hash' del diccionario
    check_fields = {k: v for k, v in data.items() if k != "hash"}

    # Ordena alfabéticamente y construye "key=value\n" separado por newlines
    sorted_items = sorted(check_fields.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_items)

    # secret_key = SHA256(BOT_TOKEN)
    secret_key = hashlib.sha256(bot_token.encode()).digest()

    # expected_hash = HMAC-SHA256(secret_key, data_check_string).hexdigest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_hash, received_hash)


@router.post("/auth/telegram")
async def auth_telegram(request: TelegramAuthRequest):
    """
    POST /auth/telegram

    Verifica el login de Telegram, busca al usuario en BD y emite JWT.
    """
    print(f"[auth] POST /auth/telegram — id={request.id} first_name={request.first_name} auth_date={request.auth_date}")
    # 1. Verifica hash de Telegram
    request_dict = request.dict()
    if not _verify_telegram_hash(request_dict, request.hash):
        logger.warning(f"Hash verification failed for user {request.id}")
        raise HTTPException(status_code=401, detail="Hash verification failed")

    # 2. Verifica que auth_date no sea antiguo (> 24 horas)
    now = int(time.time())
    if now - request.auth_date > 86400:
        logger.warning(f"Login expired for user {request.id} (auth_date={request.auth_date})")
        raise HTTPException(status_code=401, detail="Login expired")

    # 3. Busca usuario en base de datos
    try:
        user = db.query_one(
            "SELECT usuario_id, nombre, rol FROM usuarios WHERE telegram_id = %s AND activo = TRUE",
            (request.id,)
        )
    except Exception as e:
        logger.error(f"Database error querying user {request.id}: {e}")
        user = None

    if not user:
        logger.warning(f"User {request.id} not found or inactive")
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso al dashboard"
        )

    usuario_id, nombre, rol = user[0], user[1], user[2]

    # 4. Emite JWT
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        logger.error("SECRET_KEY not configured")
        raise HTTPException(status_code=500, detail="Server configuration error")

    now = datetime.utcnow()
    expiry = now + timedelta(days=7)

    payload = {
        "usuario_id": usuario_id,
        "telegram_id": request.id,
        "nombre": nombre,
        "rol": rol,
        "exp": expiry,
    }

    try:
        token = jwt.encode(payload, secret_key, algorithm="HS256")
    except Exception as e:
        logger.error(f"Failed to encode JWT: {e}")
        raise HTTPException(status_code=500, detail="Token generation failed")

    logger.info(f"User {nombre} ({request.id}) authenticated successfully")

    return JSONResponse(
        content={"token": token, "nombre": nombre, "rol": rol},
        headers={
            "Access-Control-Allow-Origin": "https://bot-ventas-ferreteria-production.up.railway.app",
            "Access-Control-Allow-Credentials": "true",
        },
    )


@router.get("/auth/me")
async def auth_me(authorization: str | None = Header(None)):
    """
    GET /auth/me

    Verifica JWT y retorna información del usuario autenticado.
    Header: Authorization: Bearer <token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("Missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization[7:]  # "Bearer " = 7 chars

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        logger.error("SECRET_KEY not configured")
        raise HTTPException(status_code=500, detail="Server configuration error")

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "usuario_id": payload.get("usuario_id"),
        "nombre": payload.get("nombre"),
        "rol": payload.get("rol"),
    }
