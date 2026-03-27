# Roadmap: FerreBot — Migración a PostgreSQL

## Overview

Migración completa de la persistencia del sistema POS FerreBot desde Google Drive (memoria.json + ventas.xlsx + JSONs de histórico) hacia PostgreSQL en Railway. La migración se ejecuta en 5 fases incrementales, cada una deja el bot funcionando en producción antes de avanzar a la siguiente. Al finalizar, Drive queda únicamente para fotos de facturas.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: DB Infra + Catálogo + Inventario** - Crear db.py, desplegar schema, migrar productos e inventario desde memoria.json a Postgres (completed 2026-03-26)
- [x] **Phase 2: Histórico + Gastos + Caja** - Migrar archivos JSON de histórico y campos de memoria.json a tablas Postgres (completed 2026-03-26)
- [ ] **Phase 3: Ventas** - Migrar la escritura y lectura de ventas desde Sheets/Excel a Postgres
- [ ] **Phase 4: Proveedores + Fiados + Compras** - Migrar cuentas por pagar, fiados y compras a Postgres
- [ ] **Phase 5: Limpieza** - Export Excel on-demand, eliminar dependencias de Drive y Sheets para datos estructurados

## Phase Details

### Phase 1: DB Infra + Catálogo + Inventario
**Goal**: El sistema puede conectarse a PostgreSQL y leer el catálogo e inventario desde Postgres en lugar de memoria.json
**Depends on**: Nothing (first phase)
**Requirements**: DB-01, DB-02, DB-03, DB-04, CAT-01, CAT-02, CAT-03, CAT-04, CAT-05, CAT-06, CAT-07
**Success Criteria** (what must be TRUE):
  1. El bot arranca sin errores con DATABASE_URL presente en Railway
  2. Los comandos /precios, /buscar e /inventario devuelven resultados correctos leyendo desde Postgres
  3. La búsqueda fuzzy encuentra productos con la misma precisión que antes (test_suite.py pasa 1096+ tests)
  4. memoria.py mantiene las firmas públicas de cargar_memoria() y guardar_memoria() sin cambios externos visibles
  5. El bot sigue funcionando si DATABASE_URL no está presente (fallback a comportamiento anterior)
**Plans:** 3/3 plans complete

Plans:
- [x] 01-01-PLAN.md — Create db.py module with ThreadedConnectionPool, schema init, and wire into boot sequence
- [x] 01-02-PLAN.md — Refactor memoria.py to read/write catalogo+inventario from Postgres with JSON fallback
- [x] 01-03-PLAN.md — Create migrate_memoria.py script to migrate ~576 products from memoria.json to Postgres

### Phase 2: Histórico + Gastos + Caja
**Goal**: Los datos operativos del día (gastos, caja) y el histórico de ventas diarias viven en Postgres y el tab Histórico del dashboard los muestra desde allí
**Depends on**: Phase 1
**Requirements**: HIS-01, HIS-02, HIS-03, HIS-04, GAS-01, GAS-02, CAJ-01, CAJ-02
**Success Criteria** (what must be TRUE):
  1. El tab Histórico del dashboard muestra el histórico de ventas diarias leyendo desde Postgres
  2. Registrar un gasto escribe en la tabla gastos de Postgres
  3. Abrir y cerrar caja escribe el estado en la tabla caja de Postgres
  4. Las subidas a Drive de archivos JSON de histórico ya no ocurren tras el cierre diario
**Plans**: TBD

### Phase 3: Ventas
**Goal**: Las ventas se registran en Postgres y todos los routers del dashboard leen ventas desde Postgres en lugar de Excel
**Depends on**: Phase 2
**Requirements**: VEN-01, VEN-02, VEN-03, VEN-04, VEN-05, VEN-06
**Success Criteria** (what must be TRUE):
  1. Confirmar el método de pago en Telegram escribe la venta en las tablas ventas y ventas_detalle de Postgres
  2. El endpoint /ventas/hoy devuelve las ventas del día leyendo desde Postgres
  3. El endpoint /ventas/historial devuelve el historial leyendo desde Postgres
  4. El dashboard muestra ventas con los mismos formatos JSON que antes (sin cambios en el frontend)
  5. Las ventas históricas del Excel están importadas en Postgres y visibles en el dashboard
**Plans:** 2/3 plans executed

Plans:
- [x] 03-01-PLAN.md — Write ventas to Postgres on payment confirm + /cerrar triple-write
- [x] 03-02-PLAN.md — Replace _leer_excel_rango with Postgres-first reads in ventas endpoints
- [x] 03-03-PLAN.md — Create migrate_ventas.py to import historical ventas from Excel

### Phase 4: Proveedores + Fiados + Compras
**Goal**: Las cuentas por pagar a proveedores, los fiados de clientes y las compras de mercancía viven en Postgres y el tab Proveedores funciona desde allí
**Depends on**: Phase 3
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04, PROV-05, PROV-06
**Success Criteria** (what must be TRUE):
  1. El tab Proveedores del dashboard muestra facturas y abonos leyendo desde Postgres
  2. Registrar un abono a proveedor escribe en facturas_abonos de Postgres
  3. Los fiados de clientes se leen y escriben desde las tablas fiados y fiados_historial
  4. Las fotos de facturas siguen almacenadas en Drive sin cambios
**Plans:** 1/3 plans executed

Plans:
- [x] 04-01-PLAN.md — Dual-write Postgres in 4 memoria.py write functions (facturas, abonos, fiados, compras)
- [ ] 04-02-PLAN.md — Postgres-first reads in listar_facturas, cargar_fiados, GET /compras + photo URL sync
- [ ] 04-03-PLAN.md — Create migrate_proveedores.py, migrate_fiados.py, migrate_compras.py

### Phase 5: Limpieza
**Goal**: El sistema no depende de Drive ni de Sheets para datos estructurados — Drive queda solo para fotos de facturas y el Excel se genera bajo demanda
**Depends on**: Phase 4
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04, CLEAN-05, CLEAN-06
**Success Criteria** (what must be TRUE):
  1. El endpoint GET /export/ventas.xlsx genera y descarga un archivo Excel actualizado desde Postgres
  2. El arranque del sistema (start.py) no descarga ni restaura ningún JSON desde Drive
  3. El cierre diario (/cerrar) no sube ningún archivo JSON a Drive
  4. Google Sheets ya no recibe escrituras de ventas nuevas (o solo se mantiene como lectura opcional)
  5. test_suite.py pasa 1096+ tests en el estado final limpio
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. DB Infra + Catálogo + Inventario | 3/3 | Complete   | 2026-03-26 |
| 2. Histórico + Gastos + Caja | 2/2 | Complete   | 2026-03-26 |
| 3. Ventas | 2/3 | In Progress|  |
| 4. Proveedores + Fiados + Compras | 1/3 | In Progress|  |
| 5. Limpieza | 0/TBD | Not started | - |
