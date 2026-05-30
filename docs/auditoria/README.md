# Auditoría exhaustiva — FerreBot Ferretería Punto Rojo

> Documento maestro de la auditoría completa del proyecto `bot-ventas-ferreteria`.
> Generado en mayo 2026 sobre el commit `e8987b0` de la rama `feat/dashboard-polish`.
> Objetivo: extraer la lógica reutilizable, detectar problemas y trazar el camino para replicar el sistema a otras ferreterías.

---

## Resumen ejecutivo

**FerreBot** es un sistema dual bot Telegram + dashboard web para ferreterías. Construido por un desarrollador en solitario para **Ferretería Punto Rojo** (Cartagena, Colombia), implementa ventas, inventario, caja, fiados, proveedores, facturación electrónica DIAN, integración con Bancolombia/Bold/Wompi, y un agente IA (Claude + OpenAI) que entiende mensajes en lenguaje natural.

**Tamaño**: ~74 k LOC (38 k Python + 36 k JSX), 19 routers, ~95 endpoints, 26 tablas, 30 migraciones, 24 archivos de tests, 53 variables de entorno, dos servicios Railway (`bot` y `api`).

**Estado general**:
- ✅ **Funcionalmente completo y en producción** desde hace meses.
- ✅ **Lógica de negocio rica**: ~60% de las ventas se resuelven sin Claude vía un bypass Python (<5 ms vs 800 ms).
- ⚠️ **Deuda técnica acumulada** característica de proyecto en solitario sin code reviews: drift documental, doble fuente de verdad del schema, RBAC documentado pero no implementado, datos personales del desarrollador hardcoded.
- ⚠️ **~10% del código es específico de Punto Rojo o Colombia** — mayormente DIAN/MATIAS, datos personales y URLs hardcoded. El otro **~70% es reutilizable directamente** y **~20% parametrizable** con env vars.

**Viabilidad de replicar a otras ferreterías**: **alta**, una vez que se extraiga un template-base. Sin template, clonar a una nueva ferretería toma 3-5 días de trabajo manual; con template, **2-3 horas**.

---

## TOP-10 hallazgos críticos

| # | ID | Hallazgo | Severidad | Esfuerzo |
|---|---|---|---|---|
| 1 | C-01+C-03 | RBAC desactivado — `get_filtro_usuario` siempre retorna `None`; vendedores ven datos de otros vendedores; ataque `?vendor_id=N` trivial. Contradice CLAUDE.md. | CRITICAL | 1 día |
| 2 | C-02 | `manejar_mensaje` (handler principal) y todos los callbacks del bot **sin `@protegido`**. `AUTHORIZED_CHAT_IDS` fail-open. | CRITICAL | 1 día |
| 3 | C-06 | Doble fuente de verdad del schema: `db._init_schema()` inline + 30 migraciones manuales sin tabla `schema_migrations`. Clonar produce schema incompleto. | CRITICAL | 3-5 días (Alembic) |
| 4 | C-05 | CORS hardcoded a la URL de Punto Rojo en 3 archivos distintos. | CRITICAL | 30 min |
| 5 | C-08 | Descuento de inventario **fuera** de la transacción de la venta — sobreventas silenciosas si falla. | CRITICAL | 2 horas |
| 6 | C-04 | Apertura de caja: `await notify_all(...)` después del `return` — **código muerto**, el dashboard no refresca. | CRITICAL | 5 min |
| 7 | C-07 | Consecutivo de venta inconsistente entre bot (reset diario) y API (MAX global). | CRITICAL | 1 hora |
| 8 | H-13 | `clientes.regimen_fiscal` con tipo divergente entre migraciones (VARCHAR vs INTEGER). Schema diverge según orden de aplicación. | HIGH | 2 horas |
| 9 | H-14 | Fiados sin tabla de movimientos — el historial vive en memoria y se pierde al reiniciar. | HIGH | 4 horas |
| 10 | H-08 | Webhook Telegram sin `secret_token` — token en URL path expuesto en cualquier log HTTP. | HIGH | 1 hora |

**Tiempo total para los 10 hallazgos**: ~10 días persona.

---

## Índice de documentos

| # | Documento | Resumen |
|---|---|---|
| 0 | [README.md](README.md) | Este documento — resumen ejecutivo + índice. |
| 1 | [01-mapa-estructural.md](01-mapa-estructural.md) | Inventario completo: 2 servicios, 19 routers, ~95 endpoints, 30 migraciones, 53 env vars, grafo de dependencias entre módulos. |
| 2 | [02-modelo-de-datos.md](02-modelo-de-datos.md) | 26 tablas con diagramas ER por dominio. FKs, índices, constraints, discrepancias detectadas (FK faltantes, tipos inconsistentes). |
| 3 | [03-logica-negocio.md](03-logica-negocio.md) | 12 dominios con flujos mermaid: ventas, caja, inventario, fiados, proveedores, DIAN, honorarios, RBAC, tiempo real, IA, etc. Reglas, edge cases, qué es reutilizable. |
| 4 | [04-hallazgos.md](04-hallazgos.md) | 47 hallazgos clasificados CRIT/HIGH/MED/LOW con `archivo:línea`, descripción y propuesta de fix. |
| 5 | [05-reutilizable-vs-especifico.md](05-reutilizable-vs-especifico.md) | Matriz dominio × reutilización. Lista exhaustiva de constantes hardcoded y env vars. Mapa módulo → tabla → endpoints → env. |
| 6 | [06-nueva-arquitectura.md](06-nueva-arquitectura.md) | Propuesta de template-base: estructura de carpetas `core/ domains/ modules/`, feature flags, Alembic, Pydantic Settings, path de migración. |
| 7 | [07-onboarding-nueva-ferreteria.md](07-onboarding-nueva-ferreteria.md) | Checklist paso-a-paso para arrancar una ferretería nueva con el template: pre-requisitos, env, Railway, migraciones, seeds, pruebas E2E. |

---

## Estadísticas clave

| Métrica | Valor |
|---|---|
| Líneas de código totales | ~74 000 |
| Python | ~38 000 LOC |
| Dashboard React (JSX) | ~36 000 LOC |
| Archivos Python | ~100 |
| Routers FastAPI | 19 |
| Endpoints HTTP | ~95 |
| Comandos Telegram | ~60 |
| Tabs del dashboard | 16 |
| Tablas PostgreSQL | 26 |
| Migraciones | 30 (con 6 colisiones de número) |
| Variables de entorno | 53 documentadas |
| Tests | 24 archivos |
| `except Exception` | 438 ocurrencias en 68 archivos |
| Foreign keys explícitas | ~20 |
| Índices | ~30 |

---

## Hallazgos por severidad

| Severidad | Cantidad | % |
|---|---|---|
| **CRITICAL** | 8 | 17% |
| **HIGH** | 14 | 30% |
| **MEDIUM** | 18 | 38% |
| **LOW** | 7 | 15% |
| **TOTAL** | 47 | 100% |

### Por dominio

| Dominio | Hallazgos | Severidad máx |
|---|---|---|
| Seguridad / RBAC | 5 | CRITICAL |
| Esquema / migraciones | 5 | CRITICAL |
| Infra / Configuración | 7 | CRITICAL |
| Ventas / Caja | 3 | CRITICAL |
| Bot (handlers) | 3 | HIGH |
| Catch-all / API hygiene | 4 | HIGH |
| Drift documental | 3 | HIGH |
| Eventos / SSE | 1 | HIGH |
| Realtime / multi-réplica | 1 | HIGH |
| Reusabilidad | 4 | MEDIUM |
| Tests | 2 | HIGH |
| Estilo | 3 | LOW |

---

## Lo que está bien (no todo son hallazgos)

Para balance, lo que el proyecto hace particularmente bien:

- ✅ **Bypass Python para ventas simples** (~60% de mensajes, <5 ms). Pieza de ingeniería notable.
- ✅ **Pool PG con reconexión robusta** (`db.py` con retry, broken connection detection).
- ✅ **SSE + pg_notify para tiempo real multi-réplica** — diseño correcto.
- ✅ **Code-splitting por tab** en React con `lazy()`.
- ✅ **Memoria del bot en 4 capas** (conversaciones, ventas FTS, memoria entidades, prompt cache). Sofisticado.
- ✅ **Budget tracking de Claude por vendedor/modelo/día** — observabilidad financiera.
- ✅ **Prompt caching con TTL 1h** (Anthropic) — ahorro real de costo.
- ✅ **Cache thread-safe** con `threading.Lock` para ciudades MATIAS.
- ✅ **LOCK TABLE ... SHARE ROW EXCLUSIVE** para consecutivo DIAN — concurrencia correcta.
- ✅ **Telegram Login Widget** con verificación criptográfica correcta.
- ✅ **Logger estructurado** con request_id correlacionable.
- ✅ **Sentry integrado** con webhook a Telegram.
- ✅ **APScheduler** con jobs de compresor nocturno y honorarios mensual.
- ✅ **Diccionario MATIAS** (POST IDs vs GET DIAN codes) documentado con comentarios.
- ✅ **Tests presentes** para los servicios principales (24 archivos).
- ✅ **CLAUDE.md detallado** con reglas críticas (aunque drifteado en algunos puntos).
- ✅ **Idempotencia** en migraciones (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).

---

## Plan de acción sugerido

### Sprint 1 (1 semana) — fixes críticos en el repo actual
- C-04 (5 min): mover `await notify_all` antes del `return` en `caja/abrir`.
- C-05 (30 min): centralizar CORS_ORIGIN.
- C-07 (1 h): unificar `obtener_siguiente_consecutivo()` con LOCK TABLE.
- H-08 (1 h): agregar secret_token al webhook Telegram.
- C-08 (2 h): mover descuento de inventario dentro de la transacción.
- H-06 (30 min): reemplazar `datetime.utcnow()`.
- C-01 + C-03 (1 día): arreglar RBAC en `deps.py` + tests.
- C-02 (1 día): aplicar `@protegido` a todos los handlers o mover a middleware.
- H-13 (2 h): normalizar `clientes.regimen_fiscal`.

### Sprint 2 (1 semana) — fixes high + tests
- H-04, H-09, H-10, H-11, H-12, H-14.
- M-08: tests de bypass.

### Sprint 3-5 (3 semanas) — extracción del template
- Implementar Alembic + baseline (C-06).
- Reorganizar `core/ domains/ modules/`.
- Implementar feature flags + Pydantic Settings.
- Sacar datos hardcoded a env (M-12, M-13, M-14).
- Branding configurable en dashboard.
- Scripts de seed + bootstrap.

### Sprint 6 (1 semana) — clonar a primera ferretería piloto
- Probar el template con un cliente real (cliente "0" interno o piloto).
- Iterar fricciones encontradas en el onboarding.

**Total**: **6 semanas** de un desarrollador full-time desde cero hasta tener el template usable + Punto Rojo migrado + primer cliente piloto.

---

## Decisiones que el usuario debe tomar

1. **¿Cuándo arrancar el refactor?**
   - Opción A: arreglar críticos en repo actual primero (1 semana), template después.
   - Opción B: ir directo al template (3-5 semanas), Punto Rojo migra al final.
   - **Recomendación**: A, porque reduce riesgo del repo en producción y los aprendizajes del fix informan el diseño del template.

2. **¿Cómo se versiona el template?**
   - Un repo Git público o privado.
   - Cada cliente: fork del repo o clone-disconnect (sin upstream sync).
   - **Recomendación**: repo privado + clone-disconnect. Los upstream syncs entre clientes generan más complejidad que valor.

3. **¿Quién opera el template?**
   - Solo Andrés (servicio gestionado).
   - Andrés + un colaborador.
   - El cliente self-host.
   - **Recomendación**: gestionado por Andrés (al menos al principio). Los clientes ferreteros no tienen capacidad para operar Postgres/Railway.

4. **¿Cómo se cobra a las nuevas ferreterías?**
   - Setup fee + mensualidad: cubre licencia + alojamiento Railway + APIs (Anthropic, OpenAI, MATIAS, Cloudinary).
   - Calcular costo unitario por ferretería antes de cotizar (BUDGET_*_DIARIO sirve como benchmark).

5. **¿Qué nombre comercial usa el producto?**
   - "FerreBot" en el código actual.
   - Si quieres comercializar, conviene definir marca + dominio para el template.

---

## Anexos

### A. Glosario rápido

| Término | Significado |
|---|---|
| **FE** | Facturación Electrónica (DIAN Colombia, UBL 2.1) |
| **DSNO** | Documento Soporte en Adquisiciones a No Obligados a Facturar |
| **CUFE** | Código Único de Factura Electrónica |
| **CUDE** | Código Único de Documento Electrónico (DSNO) |
| **MATIAS** | Proveedor de software de facturación electrónica autorizado DIAN |
| **CC** | Cédula de Ciudadanía / también Cuenta de Cobro |
| **NIT** | Número de Identificación Tributaria |
| **RADIAN** | Registro de Facturas Electrónicas DIAN (eventos 030, 031, 032, 033) |
| **SSE** | Server-Sent Events |
| **PTB** | python-telegram-bot |
| **PG** | PostgreSQL |
| **FTS** | Full-Text Search (índice GIN sobre `to_tsvector`) |

### B. Comandos útiles

```bash
# Correr todos los tests
python test_suite.py

# Aplicar una migración
railway run python migrations/0XX_*.py

# Generar token OAuth para Bancolombia/Gmail
python generate_bancolombia_token.py

# Verificar autenticación MATIAS
python test_matias_auth.py

# Importar clientes masivamente
python import_clientes.py clientes.csv

# Generar facturas históricas
python generar_facturas.py --desde=2025-01-01 --hasta=2025-12-31

# Ver logs Railway
railway logs --tail

# Conectar a la BD
railway run psql $DATABASE_URL
```

### C. Archivos clave para empezar a leer el código

Para alguien nuevo en el proyecto, el orden óptimo:

1. `CLAUDE.md` (raíz) — reglas críticas.
2. `api.py` — entry FastAPI.
3. `start-bot.py` — entry bot.
4. `db.py` — acceso a datos.
5. `routers/ventas.py` — el dominio más complejo.
6. `bypass.py` — joya del proyecto, leer entero.
7. `ai/prompts.py` — construcción del system prompt.
8. `services/facturacion_service.py` — integración MATIAS.

### D. Referencias

- [CLAUDE.md](../../CLAUDE.md) — guía oficial del proyecto.
- [MATIAS API](https://api-v2.matias-api.com) — proveedor FE.
- [Telegram Login Widget](https://core.telegram.org/widgets/login) — auth dashboard.
- [Railway](https://railway.app) — plataforma de deploy.
- [Anthropic Claude API](https://docs.anthropic.com) — IA principal.

---

## Cierre

Esta auditoría está **completa** y entrega 7 documentos (~32 000 palabras totales) con:
- Mapa estructural del sistema actual.
- Modelo de datos completo con diagramas ER por dominio.
- Lógica de negocio de 12 dominios con flujos mermaid.
- 47 hallazgos técnicos accionables.
- Matriz de reutilización para clonar a nuevas ferreterías.
- Arquitectura propuesta de template-base.
- Checklist operativo de onboarding.

**Próximos pasos recomendados** para el usuario:
1. Leer este README + Fase 4 (hallazgos) para entender el estado del repo.
2. Decidir si arrancar con Sprint 1 (críticos) o directo al template.
3. Tomar las 5 decisiones de §"Decisiones que el usuario debe tomar".
4. Crear plan GSD (`/gsd:new-milestone "Fixes críticos + extracción de template"`) con las fases de los Sprints 1-6.

Cualquier sección que quieras profundizar (más detalle de un dominio, más hallazgos en un área específica, prototipo de una pieza del template), avísame y la armamos.

— Auditoría generada por Claude Opus 4.7 · mayo 2026
