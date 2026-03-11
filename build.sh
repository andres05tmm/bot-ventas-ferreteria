#!/bin/bash
set -e

echo "📦 Instalando dependencias del dashboard..."
cd dashboard
npm install
echo "🔨 Buildeando dashboard React..."
npm run build
cd ..

echo "🚀 Iniciando FerreBot..."
python start.py
