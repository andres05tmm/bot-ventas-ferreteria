# FerreBot + Dashboard — Ferretería Punto Rojo

Bot de ventas en Telegram con dashboard web de análisis en tiempo real.

---

## Estructura del proyecto

```
bot-ventas/
├── main.py          # Bot de Telegram (punto de entrada)
├── api.py           # API REST (FastAPI) — datos para el dashboard
├── config.py        # Variables de entorno y clientes de API
├── sheets.py        # Integración Google Sheets
├── memoria.py       # Catálogo y estado persistente
├── memoria.json     # Datos persistentes (catálogo, inventario, etc.)
├── ventas.xlsx      # Historial de ventas en Excel
├── Procfile         # Procesos para Railway
├── requirements.txt # Dependencias Python
└── dashboard/       # Frontend React + Vite
    ├── src/
    │   ├── App.jsx
    │   ├── tabs/
    │   │   ├── TabResumen.jsx
    │   │   ├── TabTopProductos.jsx
    │   │   ├── TabInventario.jsx
    │   │   └── TabHistorial.jsx
    │   └── components/shared.jsx
    ├── package.json
    └── vite.config.js
```

---

## Variables de entorno requeridas

| Variable                 | Descripción                                      |
|--------------------------|--------------------------------------------------|
| `TELEGRAM_TOKEN`         | Token del bot de Telegram                        |
| `ANTHROPIC_API_KEY`      | API key de Anthropic (Claude)                    |
| `OPENAI_API_KEY`         | API key de OpenAI                                |
| `GOOGLE_CREDENTIALS_JSON`| Credenciales de Google Service Account (JSON)    |
| `GOOGLE_FOLDER_ID`       | ID de carpeta en Google Drive para backups       |
| `SHEETS_ID`              | ID del Google Spreadsheet de ventas              |
| `WEBHOOK_URL`            | URL pública del servicio (Railway), vacío = polling |
| `PORT`                   | Puerto del servidor (Railway lo asigna automáticamente) |

---

## Correr en desarrollo local

### 1. Bot de Telegram

```bash
# Instalar dependencias Python
pip install -r requirements.txt

# Copiar y completar variables de entorno
cp .env.example .env  # edita con tus claves

# Correr el bot (modo polling local)
python main.py
```

### 2. API (FastAPI)

```bash
# En otra terminal, desde la raíz del proyecto
uvicorn api:app --reload --port 8001
```

La API queda disponible en `http://localhost:8001`.
Documentación interactiva: `http://localhost:8001/docs`

### 3. Dashboard (React)

```bash
cd dashboard

# Instalar dependencias Node (solo la primera vez)
npm install

# Correr en desarrollo (con proxy a la API en :8001)
npm run dev
```

El dashboard queda en `http://localhost:5173`.

---

## Endpoints de la API

| Método | Ruta                        | Descripción                                    |
|--------|-----------------------------|------------------------------------------------|
| GET    | `/`                         | Health check                                   |
| GET    | `/ventas/hoy`               | Ventas de hoy desde Google Sheets              |
| GET    | `/ventas/semana`            | Ventas de los últimos 7 días desde Excel       |
| GET    | `/ventas/top?periodo=semana`| Top 10 productos por cantidad (`semana`\|`mes`)  |
| GET    | `/ventas/resumen`           | KPIs: hoy, semana, pedidos, ticket promedio    |
| GET    | `/productos`                | Catálogo completo desde memoria.json           |
| GET    | `/inventario/bajo`          | Productos sin precio o con stock en cero       |

---

## Despliegue en Railway

### Opción A — Mismo servicio (recomendado para plan Hobby+)

Railway ejecuta ambos procesos del `Procfile` dentro del mismo servicio:

- **`web`** → FastAPI en el puerto público (`$PORT`)
- **`worker`** → Bot de Telegram en modo polling

> **Importante:** Si usas esta opción, el bot corre en **modo polling** (sin webhook).
> Para eso, deja la variable `WEBHOOK_URL` **vacía** en Railway.

```
# Procfile (ya creado)
web: uvicorn api:app --host 0.0.0.0 --port ${PORT:-8001}
worker: python main.py
```

### Opción B — Servicios separados (recomendado si ya tienes el bot funcionando)

1. **Servicio existente (bot):** sin cambios, sigue usando `WEBHOOK_URL`.
2. **Nuevo servicio (API):** crea un nuevo servicio Railway en el mismo proyecto con el comando:
   ```
   uvicorn api:app --host 0.0.0.0 --port $PORT
   ```
   Copia todas las variables de entorno del servicio del bot al nuevo servicio.

3. **Conectar el dashboard al servicio de API:**
   En `dashboard/`, crea un archivo `.env.local`:
   ```
   VITE_API_URL=https://tu-api.up.railway.app
   ```

### Build del dashboard para producción

```bash
cd dashboard
npm run build
# Los archivos quedan en dashboard/dist/
# Sirve la carpeta dist/ con cualquier hosting estático (Vercel, Netlify, Railway Static)
```

---

## Pestañas del dashboard

| Pestaña          | Contenido                                                          |
|------------------|--------------------------------------------------------------------|
| **Resumen**      | 4 KPIs + gráfica de área (7 días) + top 5 barras                  |
| **Top Productos**| Top 10 por unidades con selector semana/mes + tabla con ranking    |
| **Inventario**   | Catálogo completo con alertas de stock bajo o sin precio           |
| **Historial**    | Tabla de ventas del día con búsqueda y totales                     |
