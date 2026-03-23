#!/bin/bash
set -e

# Instalar y activar Node.js via mise
if ! command -v npm &> /dev/null; then
    echo "📦 Instalando Node.js via mise..."
    mise use -g node@20.20.1
    export PATH="$HOME/.local/share/mise/shims:$PATH"
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
