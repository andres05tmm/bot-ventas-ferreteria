#!/bin/bash
set -e

# Instalar Node.js si no está disponible
if ! command -v npm &> /dev/null; then
    echo "📦 Instalando Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
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
