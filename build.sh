#!/bin/bash
set -e

# Instalar Node.js via mise (ya está instalado en Railway)
if ! command -v npm &> /dev/null; then
    echo "📦 Instalando Node.js via mise..."
    mise install node@20
    eval "$(mise activate bash)"
fi

echo "✅ Node $(node --version) / npm $(npm --version)"

echo "📦 Instalando dependencias del dashboard..."
cd dashboard
npm install
echo "🔨 Buildeando dashboard React..."
npm run build
cd ..

echo "🚀 Iniciando FerreBot..."
python start.py
