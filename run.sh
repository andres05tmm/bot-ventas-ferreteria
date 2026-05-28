#!/bin/bash
if [ "$SERVICE_TYPE" = "bot" ]; then
  echo "Arrancando Bot (webhook)..."
  python3 start-bot.py
else
  echo "Aplicando migraciones (alembic upgrade head)..."
  # Solo el servicio API aplica migraciones — un único corredor evita carreras
  # con el servicio bot. Si el upgrade falla, NO se arranca uvicorn (fail-fast:
  # no servir con un esquema desactualizado).
  python3 -m alembic upgrade head || { echo "❌ alembic upgrade falló — abortando arranque"; exit 1; }
  echo "Arrancando API + Dashboard..."
  python3 -m uvicorn api:app --host 0.0.0.0 --port $PORT
fi
