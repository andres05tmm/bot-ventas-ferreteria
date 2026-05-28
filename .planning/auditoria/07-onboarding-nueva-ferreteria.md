# 07 · Checklist de onboarding — Nueva ferretería

> Auditoría exhaustiva — Fase 7 de 8.
> Documento operativo: pasos concretos para arrancar una nueva ferretería con el template-base de la Fase 6. Asume que el template ya existe; si todavía no se ha extraído, las secciones marcadas con ⚠️ son aspiracionales.

---

## ⚙️ ACTUALIZACIÓN 2026-05-28 — Estado REAL vs aspiracional

Verificado contra el código actual (branch `feat/dashboard-polish`). El Sprint 4 implementó la base para clonar, pero **NO existe un repo-template separado** (todo vive en el mismo repo). Lo que YA existe vs lo que FALTA construir:

**✅ YA EXISTE (real):**
- **Alembic** (`alembic/`, `alembic.ini`, `versions/0001_baseline.py`). El schema se aplica **automáticamente** al arrancar el servicio API: `run.sh` corre `alembic upgrade head` y aborta si falla (fail-fast). NO hay que correrlo a mano ni con `railway.toml`.
- **`.env.example`** real y completo (111 líneas) — es la fuente de verdad de variables. Úsalo como base, NO el §3 de abajo (que quedó desfasado en detalles).
- **Feature flags** en `config.py`: `FE_HABILITADA`, `HONORARIOS_HABILITADO`, `BANCOLOMBIA_HABILITADO`, `BOLD_HABILITADO`, `WOMPI_HABILITADO`, `GMAIL_COMPRAS_HABILITADO`, `CLOUDINARY_HABILITADO`, `IA_MEMORIA_AVANZADA`, `INVENTARIO_HABILITADO`, `CAJA_HABILITADA`, `FIADOS_HABILITADO`, `IA_TOOL_CALLING`. Autodetectan por credencial; **OJO: INVENTARIO/CAJA/FIADOS/IA_MEMORIA autodetectan `true`** (NO "todos default false" como decía este doc).
- **Datos de empresa a env**: `EMPRESA_NOMBRE/NIT/CIUDAD`, `MATIAS_CITY_ID/POSTAL_CODE/COUNTRY_ID`, `HONORARIOS_PROVEEDOR_*`.
- **`IA_TOOL_CALLING=true`** → motor IA moderno (tool-calling + resolutores deterministas). Para una ferretería nueva, **setearlo true**.

**✅ YA EXISTE (construido 2026-05-28):**
- **`scripts/seed_admin.py`** — lee `ADMIN_TELEGRAM_ID`/`ADMIN_NOMBRE` del env e inserta el admin (UPSERT idempotente por `telegram_id`). Vars agregadas a `.env.example`.
- **`scripts/seed_productos.py`** — carga catálogo desde CSV o XLSX (UPSERT idempotente por `clave`; deriva la clave del nombre si falta; soporta `--dry-run`).

**⚠️ FALTA CONSTRUIR (gaps restantes — ver §15):**
- `scripts/seed_clientes.py`, `scripts/nuevo_proyecto.sh`, `scripts/generate_oauth_token.py` **NO existen** (aspiracionales; no bloquean un clon manual).
- El `.env.example` trae **defaults de Punto Rojo** (EMPRESA_*, HONORARIOS_PROVEEDOR=Andrés) — hay que sobreescribirlos al clonar.
- **Prueba E2E del clon nunca ejecutada** (gap real — ver §15.4).

---

## 0. Tiempo total esperado

| Escenario | Hoy (manual, repo actual) | Con template-base |
|---|---|---|
| Ferretería mínima (sin FE) | 2-3 días | **2-3 horas** |
| Ferretería con FE DIAN | 3-5 días | **medio día** |
| Ferretería con todo (Bancolombia, Gmail, Bold, etc.) | 5-7 días | **1 día** |

---

## 1. Pre-requisitos (lo que el cliente debe tener antes)

### 1.1. Cuentas y servicios

- [ ] Bot de Telegram creado con [BotFather](https://t.me/botfather) → guardar el `TELEGRAM_TOKEN`.
- [ ] Cuenta Railway con plan que soporte 2 servicios + Postgres (Hobby es suficiente para empezar).
- [ ] Cuenta Anthropic con API key (`ANTHROPIC_API_KEY`).
- [ ] Cuenta OpenAI con API key (`OPENAI_API_KEY`) — para Whisper (audio).
- [ ] (Opcional, si FE) Cuenta MATIAS API con resolución DIAN asignada al NIT del negocio.
- [ ] (Opcional, si Cloudinary) Cuenta Cloudinary.
- [ ] (Opcional, si Bancolombia/Gmail) Cuenta Google Cloud con Pub/Sub habilitado + cuenta Gmail dedicada para recibir notificaciones.

### 1.2. Información del negocio

- [ ] NIT del negocio (con dígito de verificación).
- [ ] Nombre legal del negocio.
- [ ] Dirección, ciudad, teléfono.
- [ ] (Si FE) Régimen fiscal: Responsable IVA / No responsable.
- [ ] (Si FE) Código DANE del municipio.
- [ ] Logo (PNG/SVG transparente) y color primario del branding.

### 1.3. Datos del admin

- [ ] Telegram ID del dueño (puede obtenerlo con [@userinfobot](https://t.me/userinfobot)).
- [ ] Nombre del admin.

### 1.4. Catálogo inicial (puede venir después)

- [ ] CSV o Excel con: nombre del producto, categoría, código (opcional), precio_unidad, unidad_medida, stock inicial.

---

## 2. Fase A — Bootstrap del repo (10 minutos)

⚠️ Asume template ya extraído.

```bash
# 1. Clonar template
git clone https://github.com/<tu-org>/ferrebot-template.git ferrebot-<cliente>
cd ferrebot-<cliente>

# 2. Renombrar y conectar a un nuevo repo Git
rm -rf .git
git init
git remote add origin https://github.com/<tu-org>/ferrebot-<cliente>.git

# 3. Crear .env desde el template
cp .env.example .env
# editar .env con los datos del cliente (ver §3)

# 4. (Opcional) Script interactivo que pregunta lo esencial
./scripts/nuevo_proyecto.sh
```

`nuevo_proyecto.sh` (a implementar en el template) debería preguntar lo mínimo: nombre, NIT, ciudad, telegram_id admin, qué módulos activar, y generar `.env`, reemplazar logo, validar que las env vars críticas están completas.

---

## 3. Fase B — Configurar `.env`

### 3.1. Variables siempre obligatorias

```env
# ── Infraestructura ──────────────────────────────────────────────────────────
SERVICE_TYPE=api                     # Railway override por servicio
PORT=8000                            # Railway lo inyecta automáticamente
DATABASE_URL=postgresql://...        # Railway lo provee al crear PG
WEBHOOK_URL=https://bot-<cliente>.up.railway.app
CORS_ORIGIN=https://dashboard-<cliente>.up.railway.app
SECRET_KEY=                          # generar: openssl rand -hex 32

# ── Bot / IA ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# ── Identidad del negocio ────────────────────────────────────────────────────
EMPRESA_NOMBRE=Ferretería Don Pedro
EMPRESA_NIT=900111222-1
EMPRESA_CIUDAD=Cartagena
EMPRESA_DIRECCION=Calle X #12-34
EMPRESA_TELEFONO=+57 300 1234567
EMPRESA_TZ=America/Bogota

# ── Admin inicial ────────────────────────────────────────────────────────────
ADMIN_TELEGRAM_ID=123456789
ADMIN_NOMBRE=Pedro Pérez

# ── Auth bot Telegram ────────────────────────────────────────────────────────
AUTHORIZED_CHAT_IDS=123456789,987654321  # IDs autorizados, separados por coma

# ── Feature flags (todos default false; activar solo lo necesario) ───────────
FE_HABILITADA=false
HONORARIOS_HABILITADO=false
BANCOLOMBIA_HABILITADO=false
BOLD_HABILITADO=false
WOMPI_HABILITADO=false
GMAIL_COMPRAS_HABILITADO=false
CLOUDINARY_HABILITADO=false
IA_MEMORIA_AVANZADA=true             # recomendado dejar en true
```

### 3.2. Si se activa FE_HABILITADA=true

```env
FE_HABILITADA=true
MATIAS_EMAIL=correo@matias.com
MATIAS_PASSWORD=...
MATIAS_RESOLUTION=18764108150755     # asignada por DIAN para el NIT del cliente
MATIAS_PREFIX=FDP                    # prefijo asignado para el negocio
MATIAS_NUM_DESDE=1                   # primer consecutivo del rango DIAN
MATIAS_AMBIENTE=produccion            # o "pruebas"
MATIAS_WEBHOOK_SECRET=               # secreto para POST /facturacion/webhook
```

### 3.3. Si se activa HONORARIOS_HABILITADO=true

```env
HONORARIOS_HABILITADO=true
HONORARIOS_VALOR=2000000             # COP por mes
HONORARIOS_CHAT_ID=-100123456789     # ID del grupo Telegram que recibe el PDF
HONORARIOS_PROVEEDOR_NOMBRE=Andrés Felipe Malo Hernández
HONORARIOS_PROVEEDOR_CC=1043295412
HONORARIOS_PROVEEDOR_NIT=1043295412-4
HONORARIOS_PROVEEDOR_DIRECCION=Conjunto El Refugio BL 12 AP 2A
HONORARIOS_PROVEEDOR_MOBILE=3001234567
HONORARIOS_PROVEEDOR_EMAIL=andresfmalo05@gmail.com
# Si además se quiere DSNO automático:
MATIAS_RESOLUTION_DSNO=18764108150999
MATIAS_DS_NUM_DESDE=1
```

### 3.4. Si se activa BANCOLOMBIA_HABILITADO=true

```env
BANCOLOMBIA_HABILITADO=true
BANCOLOMBIA_GMAIL_CLIENT_ID=...
BANCOLOMBIA_GMAIL_CLIENT_SECRET=...
BANCOLOMBIA_GMAIL_REFRESH_TOKEN=...   # generar con scripts/generate_oauth_token.py
BANCOLOMBIA_PUBSUB_TOPIC=projects/<proyecto>/topics/<topic>
BANCOLOMBIA_GMAIL_USER=correo@ferreteria.com
BANCOLOMBIA_PUBSUB_TOKEN=<token-secreto-en-url-suscripcion>
TELEGRAM_NOTIFY_CHAT_ID=-100<grupo>
```

### 3.5. Si se activa CLOUDINARY_HABILITADO=true

```env
CLOUDINARY_HABILITADO=true
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

---

## 4. Fase C — Crear infraestructura Railway

### 4.1. Crear el proyecto

```
1. Login en Railway, clic en "New Project".
2. Elegir "Empty Project". Llamarlo "ferrebot-<cliente>".
```

### 4.2. Provisión Postgres

```
1. Dentro del proyecto: "New" → "Database" → "PostgreSQL".
2. Esperar a que termine de provisionarse.
3. Copiar la `DATABASE_URL` interna.
```

### 4.3. Crear servicio "bot"

```
1. "New" → "GitHub Repo" → seleccionar el repo del cliente.
2. Nombre del servicio: "bot".
3. Settings → Variables:
   - SERVICE_TYPE = bot
   - DATABASE_URL = ${{Postgres.DATABASE_URL}}  (referenciado)
   - WEBHOOK_URL = (placeholder por ahora; se actualiza después)
   - resto de variables del .env
4. Settings → Networking → Generate Domain.
   Copiar el dominio generado (ej. `bot-cliente.up.railway.app`).
5. Actualizar WEBHOOK_URL en variables con ese dominio.
```

### 4.4. Crear servicio "api"

```
1. "New" → "GitHub Repo" → mismo repo.
2. Nombre del servicio: "api".
3. Settings → Variables:
   - SERVICE_TYPE = api
   - DATABASE_URL = ${{Postgres.DATABASE_URL}}
   - CORS_ORIGIN = (placeholder por ahora)
   - resto de variables
4. Settings → Networking → Generate Domain.
   Copiar el dominio (ej. `dashboard-cliente.up.railway.app`).
5. Actualizar CORS_ORIGIN en variables con ese dominio.
```

### 4.5. Verificar arranque

```
1. Ambos servicios deberían tener status "Active".
2. Visitar https://dashboard-<cliente>.up.railway.app → debería ver la pantalla de login.
3. /health en ambos → {"status": "ok"} o {"estado": "activo"}.
```

---

## 5. Fase D — Migrar el schema

✅ **REAL (2026-05-28): es automático.** `run.sh` corre `alembic upgrade head` al arrancar el servicio API, y aborta el arranque si falla (no sirve con schema desactualizado). NO hay que correrlo a mano ni configurar `railway.toml`. Solo el servicio `api` migra (el `bot` no, para evitar carreras).

```bash
# Verificación manual (opcional), tras el primer deploy del servicio api:
railway run psql $DATABASE_URL -c "\dt"
# Debe listar las tablas del baseline (alembic/versions/0001_baseline.py).
```

Nota: hoy hay un único `0001_baseline.py` (snapshot del schema de prod). Una BD vacía nueva queda con TODAS las tablas, pero **sin datos** (sin admin, sin catálogo) → ver Fase E.

---

## 6. Fase E — Seeds iniciales

✅ **REAL (2026-05-28): `scripts/seed_admin.py` y `scripts/seed_productos.py` existen y están probados.**

### 6.1. Admin ✅

```bash
# Requiere ADMIN_TELEGRAM_ID y ADMIN_NOMBRE en el entorno (ver .env.example).
railway run python scripts/seed_admin.py
```
Inserta/actualiza el admin en `usuarios` (UPSERT idempotente por `telegram_id`, rol='admin', activo=true). Correrlo dos veces no duplica.

### 6.2. Productos (catálogo) ✅

```bash
railway run python scripts/seed_productos.py --file=catalogo.csv     # o .xlsx
railway run python scripts/seed_productos.py --file=catalogo.csv --dry-run   # previsualizar
```
Columnas: `nombre*`, `precio_unidad*` (obligatorias), `clave` (se deriva del nombre si falta), `categoria`, `codigo`, `unidad_medida`. UPSERT idempotente por `clave`. Alternativa: `/actualizar_catalogo` del bot (adjuntar .xlsx).

### 6.3. Clientes (opcional) — ⚠️ script no existe aún

Diseño: `scripts/seed_clientes.py --file=clientes.csv`. Alternativa: crear clientes desde el dashboard (tab Clientes) o el wizard del bot.

---

## 7. Fase F — Configurar Telegram

### 7.1. Registrar webhook

El servicio bot lo hace automáticamente al arrancar (`lifespan` ejecuta `set_webhook`). Verificar manualmente:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_TOKEN>/getWebhookInfo"
# debe devolver "url": "https://bot-<cliente>.up.railway.app/<TOKEN>"
```

### 7.2. Telegram Login Widget para el dashboard

```
1. Bot → BotFather → /setdomain → poner el dominio del dashboard.
2. Verificar en dashboard/src/pages/Login.jsx que el widget apunta al bot username correcto.
```

### 7.3. Autorizar el grupo del admin

```
1. Agregar el bot al grupo del cliente (si tienen uno).
2. /start desde el chat privado o del grupo.
3. Verificar que `AUTHORIZED_CHAT_IDS` incluye el ID del grupo o del admin.
```

---

## 8. Fase G — Configurar módulos opcionales

### 8.1. Facturación electrónica DIAN (MATIAS)

```
1. El cliente debe tener cuenta MATIAS con resolución asignada.
2. Variables MATIAS_* ya configuradas en .env (paso 3.2).
3. Probar autenticación desde Railway:
   railway run python test_matias_auth.py
   → debe devolver un JWT.
4. Probar emitir una factura de prueba desde el dashboard.
5. Configurar webhook MATIAS apuntando a:
   https://api-<cliente>.up.railway.app/facturacion/webhook
   con el MATIAS_WEBHOOK_SECRET correspondiente.
```

### 8.2. Cloudinary

```
1. Crear cuenta y app en cloudinary.com.
2. Copiar Cloud Name, API Key, API Secret a Railway env.
3. Probar subir una foto de factura desde Telegram (/factura + foto).
```

### 8.3. Bancolombia (Gmail Pub/Sub)

```
1. Crear proyecto GCP, habilitar Gmail API + Pub/Sub.
2. Crear OAuth credentials (Web app type) — descargar JSON.
3. Crear Pub/Sub topic y subscription tipo push, apuntando a:
   https://api-<cliente>.up.railway.app/bancolombia/gmail/webhook?token=<PUBSUB_TOKEN>
4. Configurar Gmail watch con el script:
   railway run python scripts/generate_oauth_token.py bancolombia
5. Guardar el REFRESH_TOKEN devuelto en Railway env.
6. POST /bancolombia/gmail/watch para inicializar.
```

### 8.4. Gmail compras fiscales (similar a Bancolombia)

Mismo procedimiento, con prefijo `GMAIL_*` y endpoint `/gmail/webhook`.

### 8.5. Bold / Wompi

```
1. Configurar webhook en el dashboard del PSP apuntando a:
   - https://api-<cliente>.up.railway.app/bold/webhook
   - https://api-<cliente>.up.railway.app/wompi/webhook
2. Guardar el secret del webhook en BOLD_WEBHOOK_SECRET / WOMPI_EVENTS_SECRET.
3. Probar con un pago de prueba en sandbox.
```

### 8.6. Honorarios mensuales

```
1. Variables HONORARIOS_* configuradas (paso 3.3).
2. El job APScheduler corre automáticamente día 23 a las 9 AM (hora Colombia).
3. Para probar antes:
   railway run python -c "import asyncio; from services.honorarios_service import generar_cuenta_cobro; asyncio.run(generar_cuenta_cobro(forzar=True))"
```

### 8.7. Sentry

```
1. Crear proyecto Sentry tipo Python (FastAPI).
2. Copiar el DSN a SENTRY_DSN en Railway env.
3. (Opcional) Configurar webhook Sentry → /webhooks/sentry para alerta Telegram:
   - Alerts → Create Alert → Send Webhook → URL = https://api-<cliente>.../webhooks/sentry
   - Configurar SENTRY_ALERT_CHAT_ID con el chat Telegram destino.
```

---

## 9. Fase H — Personalizar branding del dashboard

```
1. Reemplazar archivos en dashboard/public/:
   - logo.svg (o logo.png con transparencia)
   - favicon.ico
   - apple-touch-icon.png
2. Editar .env del dashboard (variables VITE_*):
   VITE_EMPRESA_NOMBRE="..."
   VITE_COLOR_PRIMARIO="#..."
3. Rebuild + redeploy.
4. Verificar en el browser: colores, nombre, logo, favicon.
```

---

## 10. Fase I — Pruebas end-to-end antes de entregar

### Checklist de validación

#### Bot Telegram (golden path)
- [ ] `/start` desde el admin responde correctamente.
- [ ] Texto simple: `2 martillo` (cantidad entera) → bypass Python, venta registrada en <1s.
- [ ] Texto con fracción: `1/2 vinilo azul` → venta con precio fraccionado.
- [ ] Texto mixto: `1-1/2 galones` → suma entero + fracción.
- [ ] Mensaje complejo: `3 martillos y 2 destornilladores para Juan` → Claude resuelve, registra fiado.
- [ ] Audio: enviar voz → transcripción Whisper + venta.
- [ ] `/caja` → muestra estado de caja.
- [ ] `/fiados` → lista clientes con saldo.
- [ ] `/inventario` → lista productos.

#### Dashboard
- [ ] Login con Telegram Widget → recibe JWT.
- [ ] Tab "Hoy": ventas del día en tiempo real (SSE — registrar una venta desde el bot y ver que aparece sin refresh).
- [ ] Tab "Inventario": stock visible, ajuste manual funciona.
- [ ] Tab "Caja": apertura/cierre, gastos.
- [ ] Tab "Clientes": CRUD.
- [ ] Tab "Proveedores": registrar factura + abono + foto Cloudinary.
- [ ] Tab "Resultados": gráficos del mes.

#### RBAC
- [ ] Login como admin → ve datos de todos los vendedores.
- [ ] Login como vendedor → ve solo sus datos (sin trampa con `?vendor_id=X`).
- [ ] Admin con `?vendor_id=N` → ve datos del vendedor N.

#### Módulos opcionales (si activos)
- [ ] FE: emitir factura electrónica de una venta → CUFE devuelto, ventas.factura_estado='emitida'.
- [ ] FE: emitir nota crédito → razon_id correcto, ref CUFE original.
- [ ] Libro IVA: cerrar bimestre.
- [ ] Cloudinary: foto de factura proveedor sube y se ve.
- [ ] Bancolombia: enviar transferencia de prueba → llega notificación Telegram.
- [ ] Bold/Wompi: pago de prueba sandbox → notificación Telegram.
- [ ] Honorarios: CC generada manualmente → PDF correcto, enviado a HONORARIOS_CHAT_ID.

#### Métricas y observabilidad
- [ ] `/metrics` retorna texto Prometheus.
- [ ] Sentry recibe un error sintético (ej. visitar `/__force_error` si lo implementaste).
- [ ] Logs de Railway muestran requests con request_id.

---

## 11. Fase J — Entrega al cliente

### Credenciales
- [ ] URL del dashboard.
- [ ] Username del bot (`@<bot-name>`).
- [ ] (Opcional) Documento PDF/Notion con:
  - Cómo ingresar al dashboard.
  - Cómo hablarle al bot.
  - Lista de comandos `/`.
  - Cómo agregar nuevos vendedores (admin → tab Usuarios → "Nuevo").
  - Cómo emitir una factura electrónica.
  - Procedimiento de fin de día (cerrar caja).

### Lo que el cliente debe saber operativamente
- [ ] El bot solo responde a chats autorizados (AUTHORIZED_CHAT_IDS). Para agregar nuevos vendedores: admin agrega su telegram_id en Railway, redeploy.
- [ ] La hora del sistema es Bogotá. Ventas después de medianoche cuentan para el día siguiente.
- [ ] Si se cae el bot, el dashboard sigue funcionando para consultas/reportes (pero no para registrar ventas vía Telegram).
- [ ] Backups de la BD: Railway hace backups automáticos diarios; el cliente puede descargar dumps desde el dashboard de Railway.

### Soporte
- [ ] Acceso de lectura al proyecto Railway (para troubleshooting).
- [ ] Acceso de lectura al proyecto Sentry.
- [ ] Canal de soporte (email, Telegram, etc.).

---

## 12. Mantenimiento posterior

### Frecuencia recomendada
| Tarea | Cuándo | Cómo |
|---|---|---|
| Revisar Sentry | semanal | dashboard sentry.io |
| Revisar métricas | semanal | `/metrics` o Grafana si conectado |
| Backups BD | mensual | descargar dump Railway, guardar offsite |
| Actualizar dependencias | trimestral | `pip-compile`, `npm update` + tests |
| Renovar resolución DIAN | según vigencia (anual) | actualizar MATIAS_RESOLUTION y MATIAS_NUM_DESDE |
| Auditar AUTHORIZED_CHAT_IDS | si rota personal | remover ex-empleados |

### Eventos puntuales
- **Cambio de admin**: actualizar `ADMIN_TELEGRAM_ID` + crear seed nuevo o actualizar manualmente la tabla `usuarios`.
- **Cambio de NIT** del negocio: requiere nueva resolución MATIAS y actualización de `MATIAS_*`.
- **Nueva ubicación**: solo si afecta DIAN — cambiar `EMPRESA_CIUDAD`, `clientes.municipio_dian` para clientes locales nuevos.

---

## 13. Anti-patrones — qué NO hacer al clonar

- ❌ Copiar `migrations/004_usuarios_auth.py` con los seeds de Punto Rojo (Andrés y vendedores). Usar `seed_admin.py`.
- ❌ Dejar `CORS_ORIGIN` con el fallback de Punto Rojo. Siempre explicit.
- ❌ Reutilizar el mismo `SECRET_KEY` entre ferreterías. Generar uno nuevo con `openssl rand -hex 32`.
- ❌ Reutilizar el mismo bot Telegram entre ferreterías. Crear uno nuevo con BotFather.
- ❌ Compartir Postgres entre ferreterías. **Cada cliente con su BD**.
- ❌ Activar FE_HABILITADA sin tener cuenta MATIAS — falla al arranque.
- ❌ Olvidar `MATIAS_AMBIENTE=produccion` (default suele ser pruebas en algunos templates).

---

## 14. Lista corta — el "happy path"

Si el cliente es "ferretería con FE pero sin Bancolombia/Gmail/honorarios":

1. (5 min) Crear repo desde template, `cp .env.example .env`.
2. (20 min) Completar `.env` con datos del cliente (sin módulos opcionales avanzados).
3. (10 min) Crear proyecto Railway + Postgres.
4. (5 min) Crear servicios "bot" y "api", pegar variables.
5. (5 min) `alembic upgrade head`.
6. (5 min) `seed_admin.py` + `seed_productos.py`.
7. (15 min) Crear bot Telegram en BotFather, registrar webhook, agregar admin a `AUTHORIZED_CHAT_IDS`.
8. (20 min) Cargar resolución MATIAS, probar emisión FE.
9. (20 min) Personalizar branding (logo, color, nombre).
10. (30 min) Pruebas E2E del happy path.

**Total: ~2:15 horas**.

---

## 15. ⚠️ GAPS reales para poder clonar (2026-05-28)

Estado de los gaps (en orden de prioridad):

1. ✅ **`scripts/seed_admin.py`** — HECHO (2026-05-28). Lee `ADMIN_TELEGRAM_ID`/`ADMIN_NOMBRE`, UPSERT idempotente. Vars en `.env.example`.
2. ✅ **`scripts/seed_productos.py`** — HECHO (2026-05-28). CSV/XLSX, UPSERT por clave, `--dry-run`.
3. ⬜ **Limpiar defaults de Punto Rojo en `.env.example`** — `EMPRESA_*` y `HONORARIOS_PROVEEDOR_*` traen datos de Andrés; dejarlos vacíos/placeholders para no arrastrarlos a un clon.
4. ⬜ **Prueba E2E del clon (GAP PRINCIPAL restante)** — nadie ha corrido `alembic upgrade head` sobre BD vacía + `seed_admin` + login + registrar venta en una 2ª ferretería. Es el verdadero "¿funciona el clon?".
5. ⬜ **(Opcional)** `scripts/seed_clientes.py`, `scripts/nuevo_proyecto.sh`, `scripts/generate_oauth_token.py` — no bloquean un clon manual.

**Resumen**: infraestructura LISTA (Alembic auto + flags + env) y **seeds de admin/catálogo HECHOS**. El gap principal restante es **ejecutar un clon de prueba** (§15.4) para validar el flujo punta a punta.

---

**Siguiente paso**: Fase 8 — índice maestro + resumen ejecutivo de toda la auditoría.
