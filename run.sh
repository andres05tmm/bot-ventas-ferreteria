#!/bin/bash
if [ "$SERVICE_TYPE" = "bot" ]; then
  echo "Arrancando Bot (webhook)..."
  python3 start-bot.py
else
  echo "Arrancando API + Dashboard..."
  python3 -m uvicorn api:app --host 0.0.0.0 --port $PORT
fi
