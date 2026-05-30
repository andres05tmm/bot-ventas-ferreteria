# 06 · Arquitectura propuesta para el template-base

> Auditoría exhaustiva — Fase 6 de 8.
> Objetivo: definir cómo debería verse un **repo-base genérico** del que se clone una nueva ferretería con despliegue independiente y BD aparte, basado en lo aprendido en Fases 1-5.

---

## 1. Restricciones y decisiones de diseño

### 1.1. Restricciones del usuario (recordatorio)
- **Despliegue independiente** por ferretería (Railway separado).
- **Base de datos aparte** por ferretería.
- **No multi-tenant**: cada cliente tiene su instancia.
- Mantener el repo de Punto Rojo funcionando — extraer template **sin romperlo**.

### 1.2. Decisiones de diseño propuestas

| Decisión | Valor |
|---|---|
| Estrategia | **Repo-template genérico** que se clona y configura. |
| Configuración | **12-factor** (12factor.net): toda configuración en env vars. Sin URLs ni datos hardcoded. |
| Activación de módulos | **Feature flags por env** (`FE_HABILITADA=true`, `HONORARIOS_HABILITADO=true`, etc.). |
| Migraciones | **Alembic** o equivalente, con tabla `alembic_version`. Eliminar `db._init_schema()` inline. |
| Seeds | **Script separado** `seed.py` (no en migrations). |
| Branding del dashboard | **Variables de build Vite** (`VITE_EMPRESA_NOMBRE`, `VITE_COLOR_PRIMARIO`) leídas al hacer `npm run build`. |
| Datos del negocio | Tabla `empresa` (single row) o `ferrebot_config` con seed inicial vía env. |
| RBAC | Arreglado: `deps.py` filtra por rol de verdad. |
| Esquema | Una sola fuente — Alembic. |
| Linter / format | `ruff` configurado en `pyproject.toml`. CI opcional. |
| Tests | `pytest` con CI mínimo en GitHub Actions. |

### 1.3. Lo que NO cambia
- Stack tecnológico (FastAPI + python-telegram-bot + PostgreSQL + React + Vite).
- Modelo de dominio (productos, ventas, caja, fiados, etc.).
- Bypass Python para ventas simples.
- Integración Claude/Whisper.
- Despliegue Railway (con `run.sh` y `SERVICE_TYPE`).
- SSE + pg_notify para tiempo real.

---

## 2. Estructura propuesta del repo-template

```
ferrebot-template/
├── README.md                       ← documentación del template
├── CLAUDE.md                       ← guía para Claude Code
├── .env.example                    ← todas las env vars documentadas
├── pyproject.toml                  ← deps Python, config ruff/pytest
├── package.json                    ← deps Node + scripts build
├── run.sh                          ← entry Railway (sin cambios)
├── alembic.ini                     ← config migraciones
│
├── core/                           ← núcleo de la aplicación (siempre activo)
│   ├── __init__.py
│   ├── config.py                   ← env vars + Pydantic Settings
│   ├── db.py                       ← pool PG, helpers; SIN _init_schema
│   ├── events.py                   ← SSE + pg_notify
│   ├── auth.py                     ← JWT + Telegram Login (genérico)
│   ├── deps.py                     ← RBAC arreglado
│   ├── middleware.py               ← logging, rate limit, CORS
│   └── metrics.py
│
├── domains/                        ← lógica de negocio por dominio
│   ├── catalogo/
│   │   ├── service.py
│   │   ├── router.py
│   │   └── tests/
│   ├── inventario/
│   ├── ventas/
│   │   ├── bypass.py               ← bypass Python (con plurales en config)
│   │   ├── service.py
│   │   ├── router.py
│   │   └── tests/
│   ├── caja/
│   ├── clientes/
│   ├── proveedores/
│   ├── compras/
│   ├── fiados/
│   ├── gastos/
│   ├── historico/
│   ├── reportes/
│   └── usuarios/
│
├── bot/                            ← capa Telegram bot
│   ├── main.py                     ← build_app() handlers PTB
│   ├── handlers/
│   │   ├── mensajes.py             ← con @protegido aplicado
│   │   ├── audio.py
│   │   ├── callbacks.py
│   │   ├── comandos.py
│   │   └── cmd_*.py
│   ├── middleware/auth.py          ← @protegido
│   └── ventas_state.py
│
├── ai/                             ← IA (Claude + OpenAI)
│   ├── prompts/
│   │   ├── base.py                 ← prompt genérico
│   │   └── aliases.py              ← _ALIAS_FERRETERIA cargado de config
│   ├── prompt_context.py
│   ├── prompt_products.py
│   ├── response_builder.py
│   ├── price_cache.py
│   ├── budget.py
│   ├── memoria_turno.py
│   └── tests/
│
├── modules/                        ← módulos opcionales (feature-flagged)
│   ├── facturacion_dian/           ← MATIAS API
│   │   ├── __init__.py             ← decide activación por env
│   │   ├── service.py              ← facturacion_service.py actual
│   │   ├── documento_soporte.py
│   │   ├── router.py
│   │   ├── webhook.py
│   │   └── tests/
│   ├── honorarios/                 ← Cuentas de Cobro
│   │   ├── __init__.py
│   │   ├── service.py              ← honorarios_service.py con datos parametrizables
│   │   ├── router.py
│   │   └── tests/
│   ├── bancolombia/                ← Gmail Pub/Sub Bancolombia
│   ├── bold/                       ← webhook Bold
│   ├── wompi/                      ← webhook Wompi
│   ├── gmail_compras/              ← Gmail Pub/Sub compras fiscales
│   ├── cloudinary_fotos/           ← fotos de facturas proveedor
│   ├── libro_iva/                  ← bimestre IVA Colombia
│   ├── sentry/                     ← observabilidad
│   └── ia_memoria_avanzada/        ← Capas 3 y 4 (FTS + memoria_entidades)
│
├── api/
│   └── main.py                     ← entry FastAPI; arma routers según flags
│
├── start-bot.py                    ← entry bot Telegram
├── start.py                        ← dev local (bot + api)
│
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 0001_core_schema.py
│       ├── 0002_ventas_y_inventario.py
│       ├── 0003_caja_gastos_historico.py
│       ├── 0004_clientes_usuarios.py
│       ├── 0005_compras_proveedores.py
│       ├── 0006_fiados.py
│       ├── 0007_audio_logs.py
│       ├── 0010_optional_fe_dian.py     ← gated por env (alembic context)
│       ├── 0020_optional_honorarios.py
│       ├── 0030_optional_bancolombia.py
│       ├── 0040_optional_gmail_compras.py
│       ├── 0050_optional_ia_avanzada.py
│       └── …
│
├── scripts/
│   ├── seed_admin.py               ← crea el admin desde env vars
│   ├── seed_productos.py           ← importa Excel/CSV de catálogo inicial
│   ├── seed_clientes.py            ← importa CSV de clientes
│   ├── nuevo_proyecto.sh           ← bootstrap interactivo
│   └── generate_oauth_token.py     ← Gmail/Bancolombia helper
│
├── dashboard/                      ← React + Vite
│   ├── src/
│   │   ├── App.jsx
│   │   ├── config/                 ← lee VITE_* env
│   │   │   ├── branding.ts         ← nombre, color, logo
│   │   │   └── features.ts         ← qué tabs mostrar según módulos activos
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   └── tabs/                   ← tabs condicionales (TabFacturacion solo si FE activa)
│   └── public/
│       └── logo.svg                ← reemplazable por cliente
│
└── tests/
    ├── e2e/                        ← test end-to-end con Playwright
    ├── integration/
    └── unit/
```

### 2.1. Por qué esta estructura

- **`core/`**: lo que siempre arranca, sin importar la ferretería. Configuración, BD, auth, eventos, métricas.
- **`domains/`**: cada dominio de negocio en su carpeta. Service + router + tests juntos (cohesión). Facilita extraer un dominio si fuera necesario.
- **`modules/`**: lo opcional. Cada módulo es importable y activable por flag. Sin él, la app funciona perfectamente.
- **`ai/`**: separado de `core` y `domains` porque tiene su propia complejidad (prompts, budget, memoria).
- **`bot/`** y **`api/`**: solo capa de adaptación. Casi todo el trabajo está en `domains` y `modules`.
- **`alembic/`**: una sola fuente para schema. Algunas migraciones gated por flag (las opcionales solo corren si el módulo está activado).
- **`scripts/`**: utilidades operativas (seed, OAuth helper, bootstrap).
- **`dashboard/src/config/`**: branding y feature flags expuestos al frontend.

### 2.2. Decisiones de naming

| Cambio respecto al actual | Razón |
|---|---|
| `routers/` → `domains/<dominio>/router.py` | Junta router + service + tests en la misma carpeta. Cohesión por dominio. |
| `services/` se distribuye por dominio | Mismo motivo. Un dominio = una carpeta autocontenida. |
| `handlers/cmd_*.py` → `bot/handlers/cmd_*.py` | Separa capa bot de lógica. |
| Plural en URLs (`/ventas`, `/clientes`) | Ya está OK en el actual; mantener. |
| `_init_schema()` desaparece | Reemplazado por Alembic. |

---

## 3. Cómo se activan los módulos

### 3.1. Convención

Cada módulo en `modules/<nombre>/__init__.py` exporta:

```python
# modules/facturacion_dian/__init__.py
from core.config import settings

ENABLED = settings.FE_HABILITADA  # lee env FE_HABILITADA

def get_router():
    if not ENABLED:
        return None
    from .router import router
    return router

def get_migrations():
    """Para Alembic: si el módulo no está activo, no corre sus migraciones."""
    return [
        "0010_facturas_electronicas",
        "0011_iva_compras_columnas",
        "0012_compras_fiscal",
        "0013_eventos_dian",
    ] if ENABLED else []
```

### 3.2. Registro en API

```python
# api/main.py
from core.config import settings
from domains import catalogo, ventas, caja, clientes, proveedores, ...
from modules import facturacion_dian, honorarios, bancolombia, bold, wompi, ...

CORE_ROUTERS = [
    catalogo.router, ventas.router, caja.router, clientes.router,
    proveedores.router, compras.router, fiados.router, gastos.router,
    historico.router, reportes.router, usuarios.router, auth.router,
    events.router,
]

OPTIONAL_MODULES = [
    facturacion_dian, honorarios, bancolombia, bold, wompi,
    gmail_compras, libro_iva,
]

for router in CORE_ROUTERS:
    app.include_router(router)

for mod in OPTIONAL_MODULES:
    router = mod.get_router()
    if router:
        app.include_router(router)
        logger.info(f"Módulo activado: {mod.__name__}")
```

### 3.3. En el dashboard

```ts
// dashboard/src/config/features.ts
export const FEATURES = {
  facturacion: import.meta.env.VITE_FE_HABILITADA === 'true',
  honorarios: import.meta.env.VITE_HONORARIOS_HABILITADO === 'true',
  bancolombia: import.meta.env.VITE_BANCOLOMBIA_HABILITADO === 'true',
  libroIva: import.meta.env.VITE_FE_HABILITADA === 'true', // implica IVA
};
```

```jsx
// App.jsx — tabs condicionales
{FEATURES.facturacion && <Route path="/facturacion" element={<R Component={TabFacturacion} />} />}
{FEATURES.libroIva && <Route path="/libro-iva" element={<R Component={TabLibroIVA} />} />}
{FEATURES.bancolombia && <Route path="/transferencias" element={...} />}
```

---

## 4. `core/config.py` — Pydantic Settings con validación

```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
from zoneinfo import ZoneInfo

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # ── Núcleo (obligatorias) ─────────────────────────────────────────────────
    TELEGRAM_TOKEN: str
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str
    DATABASE_URL: str
    SECRET_KEY: str  # mínimo 32 chars
    WEBHOOK_URL: str
    SERVICE_TYPE: str = Field(pattern="^(bot|api)$")
    PORT: int = 8000
    CORS_ORIGIN: str  # ya sin default hardcoded — el operador DEBE proveerlo

    # ── Identidad del negocio ─────────────────────────────────────────────────
    EMPRESA_NOMBRE: str
    EMPRESA_NIT: str
    EMPRESA_CIUDAD: str = "Cartagena"
    EMPRESA_DIRECCION: str = ""
    EMPRESA_TELEFONO: str = ""
    EMPRESA_TZ: str = "America/Bogota"

    # ── Admin inicial (seed) ──────────────────────────────────────────────────
    ADMIN_TELEGRAM_ID: int
    ADMIN_NOMBRE: str = "Administrador"

    # ── Feature flags ─────────────────────────────────────────────────────────
    FE_HABILITADA: bool = False
    HONORARIOS_HABILITADO: bool = False
    BANCOLOMBIA_HABILITADO: bool = False
    BOLD_HABILITADO: bool = False
    WOMPI_HABILITADO: bool = False
    GMAIL_COMPRAS_HABILITADO: bool = False
    CLOUDINARY_HABILITADO: bool = False
    IA_MEMORIA_AVANZADA: bool = True

    # ── Tuning ─────────────────────────────────────────────────────────────────
    RATE_LIMIT_SEGUNDOS: int = 2
    RATE_LIMIT_MAX: int = 5
    BUDGET_SONNET_DIARIO: int = 300
    BUDGET_HAIKU_DIARIO: int = 1000
    HORA_CIERRE_SAFETY_NET: int = 21
    HORA_COMPRESOR_NOCTURNO: int = 3

    # ── MATIAS (solo si FE_HABILITADA) ────────────────────────────────────────
    MATIAS_EMAIL: str | None = None
    MATIAS_PASSWORD: str | None = None
    MATIAS_RESOLUTION: str | None = None
    MATIAS_PREFIX: str | None = None
    MATIAS_NUM_DESDE: int = 1
    MATIAS_API_URL: str = "https://api-v2.matias-api.com/api/ubl2.1"
    MATIAS_AMBIENTE: str = "produccion"
    MATIAS_WEBHOOK_SECRET: str | None = None
    MATIAS_RESOLUTION_DSNO: str | None = None
    MATIAS_DS_NUM_DESDE: int = 1

    # ── Honorarios (solo si HONORARIOS_HABILITADO) ────────────────────────────
    HONORARIOS_VALOR: int = 0
    HONORARIOS_CHAT_ID: str | None = None
    HONORARIOS_PROVEEDOR_NOMBRE: str | None = None
    HONORARIOS_PROVEEDOR_CC: str | None = None
    HONORARIOS_PROVEEDOR_NIT: str | None = None
    HONORARIOS_PROVEEDOR_DIRECCION: str | None = None
    HONORARIOS_PROVEEDOR_MOBILE: str | None = None
    HONORARIOS_PROVEEDOR_EMAIL: str | None = None

    # ── Validaciones cruzadas ─────────────────────────────────────────────────
    @validator("MATIAS_EMAIL", always=True)
    def fe_requires_matias(cls, v, values):
        if values.get("FE_HABILITADA") and not v:
            raise ValueError("FE_HABILITADA=true requiere MATIAS_EMAIL")
        return v

    @property
    def COLOMBIA_TZ(self):  # mantiene compatibilidad con código actual
        return ZoneInfo(self.EMPRESA_TZ)


settings = Settings()
```

**Beneficio**: si falta una variable obligatoria, la app **no arranca** y dice qué falta. Si activas `FE_HABILITADA=true` sin las MATIAS_*, también falla al arranque con mensaje claro.

---

## 5. Alembic — migraciones modulares

### 5.1. Migraciones core (siempre se aplican)

```
0001_core_productos_inventario.py
0002_core_clientes_usuarios.py
0003_core_ventas_detalle.py
0004_core_caja_gastos_historico.py
0005_core_compras_proveedores.py
0006_core_fiados.py
0007_core_config_kv.py
0008_core_audio_logs.py
```

### 5.2. Migraciones opcionales (gated)

```python
# alembic/versions/0010_optional_fe_dian.py
def upgrade():
    from core.config import settings
    if not settings.FE_HABILITADA:
        op.create_table('_skipped', ...)  # no-op marker
        return
    op.create_table('facturas_electronicas', ...)
    op.add_column('ventas', sa.Column('factura_numero', ...))
    op.add_column('clientes', sa.Column('regimen_fiscal', sa.Integer, server_default='2'))
    op.add_column('productos', sa.Column('tiene_iva', sa.Boolean, server_default='false'))
```

### 5.3. Comando único de migración

```bash
alembic upgrade head  # aplica todo lo activo según .env
```

Vs el modelo actual que requiere correr 30 archivos manualmente.

### 5.4. Path de migración desde el repo actual

1. Cristalizar el schema actual de Punto Rojo como **baseline** (Alembic stamp).
2. Crear `alembic_version` con un único registro `'baseline_v1'`.
3. Toda nueva migración de aquí en adelante es Alembic.
4. Eliminar `db._init_schema()` y todas las migraciones manuales viejas (archivadas como referencia).

---

## 6. Cambios concretos al sacar el template del repo actual

### 6.1. Refactors necesarios (en orden de menor a mayor impacto)

1. **CORS centralizado** (C-05): eliminar URLs hardcoded; usar solo `settings.CORS_ORIGIN`. **30 min**.
2. **Arreglar RBAC** (C-01, C-03): reescribir `deps.py`. **2 horas + tests**.
3. **Aplicar `@protegido` a todos los handlers** (C-02): decorar handlers de `mensajes.py`, `callbacks.py`, `dispatch.py`, etc., o mover a middleware único. **3 horas + tests**.
4. **Mover `await notify_all` en `caja/abrir`** (C-04). **5 min**.
5. **Unificar consecutivo de venta** (C-07): un solo helper en `db.py` con `LOCK TABLE`. **1 hora**.
6. **Descuento de inventario dentro de la transacción de venta** (C-08). **2 horas**.
7. **Mover constantes a env**: branding, admin inicial, datos honorarios. **1 día**.
8. **Reorganizar carpetas a `core/ domains/ modules/`** + ajustar imports. **2-3 días** (gran refactor mecánico, riesgo BAJO con tests).
9. **Implementar Alembic** + migrar el schema actual a baseline. **2-3 días**.
10. **Pydantic Settings**. **1 día**.
11. **Feature flags en dashboard**. **1 día**.
12. **Limpieza de migraciones duplicadas** (sin tocar Punto Rojo). **1 día**.

**Total estimado**: **2-3 semanas persona** para sacar el template completo y funcional. Se puede hacer iterativo (los primeros 7 puntos arreglan los hallazgos críticos del repo actual sin reorganizar carpetas).

### 6.2. Estrategia: extracción incremental, no big-bang

**Fase A — arreglar Punto Rojo (1 semana)**: aplicar fixes 1-7 sobre el repo actual. Esto reduce el riesgo y mejora la BD sin tocar la arquitectura.

**Fase B — extraer template (2 semanas)**:
- Crear nuevo repo `ferrebot-template` (público o privado).
- Copiar el código del repo actual, aplicar reorganización 8-12.
- Verificar que arranca con `.env.example` mínimo (sólo core, sin módulos).
- Probar activar cada módulo opcional uno a uno.
- **No tocar el repo de Punto Rojo durante esta fase** — sigue corriendo con los fixes de Fase A.

**Fase C — migrar Punto Rojo al template (1 semana)**:
- Configurar `.env` de Punto Rojo activando todos los módulos que usa.
- Apuntar el deploy de Punto Rojo al nuevo repo (o reemplazar el código del repo actual con el del template, eligiendo lo que ganó cada uno).
- Validación side-by-side antes del cutover.

---

## 7. Dashboard — branding configurable

### 7.1. Variables de build

```bash
# .env del dashboard
VITE_EMPRESA_NOMBRE="Ferretería Punto Rojo"
VITE_EMPRESA_LOGO="/logo.svg"
VITE_COLOR_PRIMARIO="#C8200E"
VITE_COLOR_SECUNDARIO="#2c3e50"
VITE_FE_HABILITADA=true
VITE_HONORARIOS_HABILITADO=true
VITE_BANCOLOMBIA_HABILITADO=true
VITE_API_URL="https://api.puntorojo.example.com"
```

### 7.2. Cómo se consume

```ts
// dashboard/src/config/branding.ts
export const BRANDING = {
  nombre: import.meta.env.VITE_EMPRESA_NOMBRE,
  logo:   import.meta.env.VITE_EMPRESA_LOGO,
  colorPrimario:   import.meta.env.VITE_COLOR_PRIMARIO,
  colorSecundario: import.meta.env.VITE_COLOR_SECUNDARIO,
};
```

```css
/* dashboard/src/index.css */
:root {
  --color-primary: var(--vite-color-primario); /* o configurado por Tailwind */
}
```

### 7.3. Logo

- Por defecto, `public/logo.svg` — el operador lo reemplaza al clonar.
- En el AppShell: `<img src={BRANDING.logo} alt={BRANDING.nombre} />`.
- Favicon: idem.

---

## 8. Activación de módulos — escenarios típicos

### 8.1. Ferretería mínima (sin FE)

```env
EMPRESA_NOMBRE=Ferretería Don Pedro
EMPRESA_NIT=900111222-1
ADMIN_TELEGRAM_ID=987654321
FE_HABILITADA=false
HONORARIOS_HABILITADO=false
BANCOLOMBIA_HABILITADO=false
```

Resultado: bot Telegram + dashboard con catálogo, ventas, caja, fiados, proveedores. **Sin nada DIAN**.

### 8.2. Ferretería con FE DIAN

```env
… mismas core …
FE_HABILITADA=true
MATIAS_EMAIL=correo@matias.com
MATIAS_PASSWORD=...
MATIAS_RESOLUTION=18764108150755
MATIAS_PREFIX=FDP
MATIAS_NUM_DESDE=1
```

Resultado: + tabs de Facturación + Libro IVA + Notas crédito/débito.

### 8.3. Ferretería con todo activado (clon de Punto Rojo)

```env
… core + FE + …
HONORARIOS_HABILITADO=true
HONORARIOS_VALOR=2000000
HONORARIOS_PROVEEDOR_*=…  (todos)
BANCOLOMBIA_HABILITADO=true
BANCOLOMBIA_GMAIL_*=…
BOLD_HABILITADO=true
WOMPI_HABILITADO=true
GMAIL_COMPRAS_HABILITADO=true
CLOUDINARY_HABILITADO=true
```

Resultado: equivalente al Punto Rojo actual, pero con cero datos hardcoded.

---

## 9. Migración del esquema actual al baseline Alembic

Estrategia "stamp + diff":

1. Conectar Alembic a la BD de producción de Punto Rojo.
2. `alembic stamp head` — marca la versión actual como baseline (sin ejecutar nada).
3. Sacar `alembic --autogenerate` revision para detectar cualquier drift contra el modelo SQLAlchemy.
4. Revisar y limpiar la revisión generada (especialmente las inconsistencias detectadas en Fase 4: `clientes.regimen_fiscal`, tipos de montos, `TIMESTAMP` vs `TIMESTAMPTZ`).
5. Aplicar las correcciones como **migración explícita** `0099_normalize_schema.py`.
6. A partir de ahí, **todo** cambio de schema pasa por Alembic.

---

## 10. Tabla resumen de cambios vs el repo actual

| Aspecto | Actual | Template |
|---|---|---|
| Carpetas | `routers/ services/ handlers/ ai/ migrations/` | `core/ domains/ modules/ bot/ ai/ api/ alembic/` |
| Schema | `db._init_schema()` + 30 migrations sueltas | Alembic con baseline |
| Config | `os.getenv()` disperso, defaults hardcoded | `Settings` Pydantic central |
| RBAC | roto en `deps.py` | arreglado, con tests |
| Handlers protegidos | sólo `cmd_*.py` | TODOS los handlers de Telegram |
| Branding | hardcoded en código fuente | env vars + logo file |
| Módulos opcionales | acoplados | feature-flagged, importables/desactivables |
| Datos del negocio | hardcoded en `services/honorarios_service.py`, `services/documento_soporte_service.py` | env vars |
| Admin inicial | hardcoded en migración 004 | env vars + `seed_admin.py` |
| Tests | 24 archivos, faltan dominios sensibles | + tests para bypass, deps, FE, DSNO |
| CI | sin CI | GitHub Actions con `pytest` + `ruff` |
| Documentación | CLAUDE.md + 1 README | CLAUDE.md + README + ARCHITECTURE.md + ONBOARDING.md |

---

## 11. Riesgos de la extracción

| Riesgo | Mitigación |
|---|---|
| Romper Punto Rojo al refactorizar | Hacer Fase A (fixes) en el repo actual sin tocar arquitectura. Fase B en repo aparte. |
| Olvidar un dato hardcoded | Auditoría grep masiva por: `Punto Rojo`, `1043295412`, `1235046119`, `Cartagena`, `Andrés`, `andresfmalo`. Lista completa en Fase 5 §2. |
| Migraciones drifteadas en producción | Stamp + autogenerate + normalize step (`0099_normalize_schema.py`). |
| Módulo opcional rompe core | Tests de "core sin módulos" para asegurar que la app arranca con todos los flags=false. |
| Alguien clona el template sin leer ONBOARDING | README en raíz dice "lee `ONBOARDING.md` antes de tocar nada"; script `scripts/nuevo_proyecto.sh` validador interactivo. |

---

**Siguiente paso**: Fase 7 — checklist paso a paso de onboarding de una ferretería nueva con este template.
