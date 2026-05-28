#!/usr/bin/env bash
# scripts/nuevo_proyecto.sh — Bootstrap de .env para clonar una ferretería.
#
# Pregunta lo mínimo (núcleo + identidad + admin), genera un .env a partir de
# .env.example y deja apuntados los siguientes pasos. NO toca la base de datos.
#
# Uso:   bash scripts/nuevo_proyecto.sh
set -euo pipefail

cd "$(dirname "$0")/.."   # raíz del repo

EJEMPLO=".env.example"
DESTINO=".env"

if [[ ! -f "$EJEMPLO" ]]; then
  echo "❌ No encuentro $EJEMPLO en la raíz del repo."
  exit 1
fi
if [[ -f "$DESTINO" ]]; then
  read -r -p "⚠️  Ya existe $DESTINO. ¿Sobrescribir? [y/N] " resp
  [[ "${resp,,}" == "y" ]] || { echo "Cancelado."; exit 0; }
fi

echo "── Bootstrap de ferretería nueva ─────────────────────────────"
read -r -p "Nombre del negocio:           " EMPRESA_NOMBRE
read -r -p "NIT (con dígito, ej 900111-1): " EMPRESA_NIT
read -r -p "Ciudad (ej Cartagena, Bolívar):" EMPRESA_CIUDAD
read -r -p "Telegram ID del admin:        " ADMIN_TELEGRAM_ID
read -r -p "Nombre del admin:             " ADMIN_NOMBRE
read -r -p "TELEGRAM_TOKEN del bot:       " TELEGRAM_TOKEN
read -r -p "ANTHROPIC_API_KEY:            " ANTHROPIC_API_KEY
read -r -p "OPENAI_API_KEY:               " OPENAI_API_KEY
read -r -p "¿Activar facturación DIAN (FE)? [y/N] " FE_RESP

# SECRET_KEY automática
if command -v openssl >/dev/null 2>&1; then
  SECRET_KEY="$(openssl rand -hex 32)"
else
  SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
fi

cp "$EJEMPLO" "$DESTINO"

# Reemplazos seguros (usa | como separador para evitar choques con / en valores).
_set() {  # _set CLAVE VALOR
  local clave="$1" valor="$2"
  # Reemplaza la línea "CLAVE=...": si existe, la sustituye; respeta comentarios "# CLAVE=".
  if grep -qE "^${clave}=" "$DESTINO"; then
    # Escapar & y | del valor para sed
    local v_esc; v_esc="$(printf '%s' "$valor" | sed -e 's/[&|]/\\&/g')"
    sed -i.bak -E "s|^${clave}=.*|${clave}=${v_esc}|" "$DESTINO"
  else
    echo "${clave}=${valor}" >> "$DESTINO"
  fi
}

_set EMPRESA_NOMBRE     "$EMPRESA_NOMBRE"
_set EMPRESA_NIT        "$EMPRESA_NIT"
_set EMPRESA_CIUDAD     "$EMPRESA_CIUDAD"
_set ADMIN_TELEGRAM_ID  "$ADMIN_TELEGRAM_ID"
_set ADMIN_NOMBRE       "$ADMIN_NOMBRE"
_set TELEGRAM_TOKEN     "$TELEGRAM_TOKEN"
_set ANTHROPIC_API_KEY  "$ANTHROPIC_API_KEY"
_set OPENAI_API_KEY     "$OPENAI_API_KEY"
_set SECRET_KEY         "$SECRET_KEY"
_set IA_TOOL_CALLING    "true"
if [[ "${FE_RESP,,}" == "y" ]]; then
  _set FE_HABILITADA "true"
fi
rm -f "${DESTINO}.bak"

echo ""
echo "✅ $DESTINO generado."
echo ""
echo "Siguientes pasos:"
echo "  1. Completar en $DESTINO: DATABASE_URL, WEBHOOK_URL, CORS_ORIGIN"
echo "     (y MATIAS_* si activaste FE)."
echo "  2. Desplegar en Railway (servicios bot y api) — run.sh corre alembic upgrade head."
echo "  3. railway run python scripts/seed_admin.py"
echo "  4. railway run python scripts/seed_productos.py --file=catalogo.csv"
echo "  5. (opcional) railway run python scripts/seed_clientes.py --file=clientes.csv"
