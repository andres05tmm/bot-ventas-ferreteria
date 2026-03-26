# FerreBot — Contexto para Claude Code

## ¿Qué es este sistema?

FerreBot es un sistema POS completo para **Ferretería Punto Rojo** (Cartagena, Colombia). Tiene tres componentes:

1. **Bot de Telegram** — los vendedores registran ventas por voz o texto en lenguaje natural. Claude (AI) interpreta los mensajes y extrae los datos de venta.
2. **API FastAPI** — backend que expone endpoints para el dashboard y gestiona toda la lógica de negocio.
3. **Dashboard React/Vite** — interfaz web con múltiples tabs: Resumen, Ventas Rápidas, Historial, Inventario, Histórico, Caja, Gastos, Compras, Proveedores, Kardex, Resultados, Top Productos.

Desplegado en **Railway** como un proceso unificado (`start.py`): el bot corre en el hilo principal y la API en un hilo daemon.

---

## Stack tecnológico

- **Backend:** Python 3.11, FastAPI, python-telegram-bot, Anthropic Claude API, OpenAI Whisper (transcripción de audio)
- **Frontend:** React 18 + Vite, desplegado como archivos estáticos servidos por FastAPI
- **Persistencia actual:** Google Drive (archivos JSON y Excel), Google Sheets (buffer de ventas del día)
- **Persistencia objetivo (migración):** PostgreSQL en Railway
- **Deploy:** Railway (auto-deploy desde GitHub master branch)

---

## Estructura del proyecto

```
/
├── start.py              # Punto de entrada — arranca API + bot en hilos separados
├── main.py               # Configura el bot de Telegram y registra handlers
├── api.py                # App FastAPI — registra todos los routers
├── config.py             # Variables de entorno, clientes API, constantes
├── memoria.py            # CAPA DE DATOS ACTUAL — toda la lógica de negocio sobre memoria.json
├── drive.py              # Subir/bajar archivos a Google Drive con debounce y cola de reintentos
├── excel.py              # Leer/escribir ventas.xlsx (archivo principal de ventas)
├── sheets.py             # Google Sheets (buffer en vivo del día)
├── ai.py                 # Integración con Claude — interpreta mensajes de ventas
├── fuzzy_match.py        # Búsqueda fuzzy de productos en el catálogo
├── precio_sync.py        # Sincronizar precios entre memoria.json y BASE_DE_DATOS_PRODUCTOS.xlsx
├── alias_manager.py      # Gestión de alias/sinónimos de productos
├── keepalive.py          # Sistema de keep-alive para prompt caching de Claude
├── bypass.py             # Sistema de procesamiento alternativo
├── utils.py              # Helpers varios
├── ventas_state.py       # Estado en memoria de ventas pendientes por chat
├── handlers/
│   ├── comandos.py       # Handlers de comandos Telegram (/cerrar, /gastos, /compra, etc.)
│   ├── mensajes.py       # Handler principal de mensajes de texto y audio
│   ├── callbacks.py      # Callbacks de botones inline (confirmar pago, etc.)
│   ├── productos.py      # Handlers relacionados con productos
│   └── alias_handler.py  # Handler del comando /alias
├── routers/
│   ├── historico.py      # /historico/* — histórico de ventas diarias
│   ├── ventas.py         # /ventas/* — ventas del día
│   ├── proveedores.py    # /proveedores/* — facturas y abonos a proveedores
│   ├── caja.py           # /caja/* — estado de caja
│   ├── gastos.py         # /gastos/* — gastos del día
│   ├── catalogo.py       # /catalogo/* — productos y precios
│   ├── clientes.py       # /clientes/* — gestión de clientes
│   ├── reportes.py       # /reportes/* — reportes y exports
│   ├── chat.py           # /chat/* — chat con AI desde dashboard
│   ├── kardex.py         # /kardex — kardex de inventario
│   └── shared.py         # Helpers compartidos entre routers (_hoy, _leer_excel_rango, etc.)
└── dashboard/
    └── src/
        └── tabs/         # TabResumen, TabVentasRapidas, TabHistorial, etc.
```

---

## Persistencia actual — LO QUE VAMOS A MIGRAR

### memoria.json (archivo crítico)
Es el corazón del sistema. Se descarga de Drive al arrancar y se sube cada vez que cambia. Contiene:

```json
{
  "catalogo": {
    "brocha_2_pulgadas": {
      "nombre": "Brocha 2\"",
      "nombre_lower": "brocha 2\"",
      "categoria": "1 Artículos de Ferreteria",
      "precio_unidad": 7000,
      "precios_fraccion": {},
      "precio_por_cantidad": {}
    }
  },
  "inventario": {
    "brocha_2_pulgadas": {"cantidad": 25, "minimo": 5, "unidad": "Unidad"}
  },
  "gastos": {
    "2026-03-25": [
      {"concepto": "domicilio", "monto": 5000, "categoria": "operativo", "origen": "bot", "hora": "14:30"}
    ]
  },
  "caja_actual": {
    "abierta": true,
    "fecha": "2026-03-25",
    "monto_apertura": 50000,
    "efectivo": 0,
    "transferencias": 0,
    "datafono": 0
  },
  "fiados": {
    "juan_perez": {"nombre": "Juan Pérez", "deuda": 150000, "historial": []}
  },
  "cuentas_por_pagar": [
    {
      "id": "FAC-001",
      "proveedor": "Ferrisariato",
      "descripcion": "Surtido tornillería",
      "total": 700000,
      "pagado": 200000,
      "pendiente": 500000,
      "estado": "parcial",
      "fecha": "2026-03-20",
      "foto_url": "",
      "abonos": []
    }
  ],
  "productos_pendientes": [
    {"nombre": "silicon transparente", "fecha": "2026-03-25", "hora": "10:30"}
  ],
  "keepalive_activo": false
}
```

**~576 productos en catálogo, ~151 referencias a cargar_memoria/guardar_memoria en el código.**

### ventas.xlsx
Archivo Excel con hojas por mes (ej: "Marzo 2026") + hoja acumulada. Cada fila es una línea de venta:
- Columnas: #, Fecha, Hora, ID Cliente, Cliente, Código Producto, Producto, Unidad de Medida, Cantidad, Valor Unitario, Total, Vendedor, Método de Pago

**~388 referencias a operaciones Excel en el código.**

### Google Sheets
Buffer temporal del día actual. Se llena durante el día y se vacía con `/cerrar`. Mismas columnas que el Excel.

### Archivos de histórico
- `historico_ventas.json` — `{"2026-03-19": 888600, "2026-03-20": 481300, ...}`
- `historico_diario.json` — desglose por día con efectivo/transferencia/datáfono/gastos

---

## Flujo principal de una venta

1. Vendedor escribe o habla por Telegram: *"2 brochas 2 pulgadas y 1 rodillo 4"*
2. `handlers/mensajes.py` recibe el mensaje
3. `ai.py` → Claude API interpreta y emite tags `[VENTA]...[/VENTA]` por cada producto
4. `ventas_state.py` guarda las ventas pendientes en memoria RAM
5. El bot muestra botones: Efectivo / Transferencia / Datáfono
6. Vendedor confirma método de pago
7. `sheets.py` registra la venta en Google Sheets (en vivo)
8. Al final del día: `/cerrar` → copia Sheets → Excel → Drive → limpia Sheets

## Flujo de cierre del día (/cerrar)
1. Lee todas las ventas de Sheets
2. Las escribe en ventas.xlsx (hoja del mes + acumulado)
3. Sube ventas.xlsx a Drive
4. Llama a `_sync_historico_hoy()` → guarda total + desglose en historico_diario.json → Drive
5. Limpia Google Sheets
6. Cierra la caja
7. Análisis del día con Claude AI

---

## Variables de entorno requeridas

```
TELEGRAM_TOKEN
ANTHROPIC_API_KEY
OPENAI_API_KEY
GOOGLE_CREDENTIALS_JSON    # JSON completo de la Service Account
GOOGLE_FOLDER_ID           # ID de la carpeta en Drive
SHEETS_ID                  # ID del Google Sheets del día
DATABASE_URL               # ← NUEVA: PostgreSQL connection string de Railway
```

---

## Reglas importantes — NO TOCAR durante la migración

1. **`ai.py` y el sistema de prompts** — no modificar el prompt de Claude ni la lógica de parsing de `[VENTA]` tags
2. **`fuzzy_match.py`** — el índice fuzzy debe seguir funcionando igual, solo cambiar de dónde lee el catálogo
3. **`ventas_state.py`** — estado en RAM, no persiste, no migrar
4. **`alias_manager.py`** — los alias deben migrar a Postgres pero la interfaz pública no cambia
5. **El dashboard React** — los endpoints de la API deben mantener los mismos nombres y formatos de respuesta (solo cambia la fuente de datos internamente)
6. **Google Sheets del día** — mantener durante la migración, eliminar solo cuando las ventas ya estén en Postgres
7. **Las fotos de facturas en Drive** — siguen en Drive, no se migran a Postgres

---

## Convenciones del código

- Zona horaria: siempre `config.COLOMBIA_TZ` (UTC-5)
- Fechas: siempre strings `"YYYY-MM-DD"` 
- Montos: siempre enteros en pesos colombianos (sin decimales en la mayoría de casos)
- Locks de threading: usar para todo lo que toca archivos (`_historico_lock`, `_diario_lock`)
- Drive uploads: usar `subir_a_drive_urgente()` para datos críticos, `subir_a_drive()` para el resto (tiene debounce de 2s)
- Errores silenciosos: el código actual usa muchos `except Exception: pass` — en la migración mantener ese patrón para no romper el bot por errores de DB

---

## Tests

`test_suite.py` tiene ~1096 tests sobre el catálogo y fuzzy matching. Deben seguir pasando después de cada fase de migración.
