# Requirements: FerreBot — Migración a PostgreSQL

**Defined:** 2026-03-25
**Core Value:** El bot debe registrar ventas sin interrupciones — si la DB falla, el bot no puede caer.

## v1 Requirements

Requirements para la migración completa de Drive/JSON/Excel → PostgreSQL.

### Infraestructura DB

- [x] **DB-01**: Sistema puede conectarse a PostgreSQL usando `DATABASE_URL` desde variables de entorno de Railway
- [x] **DB-02**: Módulo `db.py` centraliza todo el acceso a Postgres con context manager, `query_one`, `query_all`, `execute`, `execute_returning`
- [x] **DB-03**: Schema completo creado en Railway: tablas `productos`, `productos_fracciones`, `productos_precio_cantidad`, `productos_alias`, `inventario`, `clientes`, `ventas`, `ventas_detalle`, `gastos`, `caja`, `fiados`, `fiados_historial`, `facturas_proveedores`, `facturas_abonos`, `historico_ventas`, `compras`, `productos_pendientes`, `config_sistema`
- [x] **DB-04**: Sistema arranca sin errores cuando `DATABASE_URL` está presente, y sigue funcionando (con fallback) si no está

### Catálogo e Inventario (Fase 1)

- [x] **CAT-01**: Script `migrate_memoria.py` migra los ~576 productos de `memoria.json` a tabla `productos` con fracciones y precios por cantidad
- [x] **CAT-02**: Script migra alias de productos a tabla `productos_alias`
- [x] **CAT-03**: Script migra inventario a tabla `inventario`
- [x] **CAT-04**: `memoria.py` lee catálogo desde Postgres manteniendo la firma pública de `cargar_memoria()` y `guardar_memoria()`
- [x] **CAT-05**: `fuzzy_match.py` construye el índice de búsqueda leyendo productos desde Postgres
- [x] **CAT-06**: Comandos `/precios`, `/buscar`, `/inventario` funcionan igual que antes
- [x] **CAT-07**: `test_suite.py` pasa 1096+ tests después de Fase 1

### Histórico, Gastos y Caja (Fase 2)

- [x] **HIS-01**: Script migra `historico_ventas.json` + `historico_diario.json` a tabla `historico_ventas`
- [x] **HIS-02**: `_sync_historico_hoy()` escribe el cierre diario en Postgres en lugar de JSON + Drive
- [x] **GAS-01**: Gastos de `memoria.json["gastos"]` migrados a tabla `gastos`
- [x] **GAS-02**: Nuevo registro de gastos escribe en Postgres
- [x] **CAJ-01**: Estado de caja de `memoria.json["caja_actual"]` migrado a tabla `caja`
- [x] **CAJ-02**: Apertura/cierre de caja escribe en Postgres
- [x] **HIS-03**: Tab Histórico del dashboard muestra datos desde Postgres
- [x] **HIS-04**: Subidas a Drive de archivos JSON de histórico eliminadas

### Ventas (Fase 3)

- [x] **VEN-01**: Confirmación de pago escribe venta en tabla `ventas` + `ventas_detalle` (en paralelo con Sheets durante transición)
- [x] **VEN-02**: `/cerrar` copia ventas de Sheets → Postgres (en lugar de Sheets → Excel)
- [x] **VEN-03**: `_leer_excel_rango()` en `routers/shared.py` reemplazada por query a `ventas` + `ventas_detalle`
- [x] **VEN-04**: Endpoints `/ventas/hoy`, `/ventas/historial` leen desde Postgres
- [x] **VEN-05**: Script de migración importa ventas históricas del Excel a Postgres
- [x] **VEN-06**: Dashboard muestra ventas desde Postgres (mismos formatos de respuesta JSON)

### Proveedores, Fiados y Compras (Fase 4)

- [ ] **PROV-01**: `memoria.json["cuentas_por_pagar"]` migrado a tabla `facturas_proveedores` + `facturas_abonos`
- [ ] **PROV-02**: `memoria.json["fiados"]` migrado a tablas `fiados` + `fiados_historial`
- [ ] **PROV-03**: Compras del Excel migradas a tabla `compras`
- [x] **PROV-04**: Routers de proveedores, fiados y compras leen/escriben en Postgres
- [ ] **PROV-05**: Fotos de facturas siguen en Google Drive sin cambios
- [ ] **PROV-06**: Tab Proveedores funciona desde Postgres

### Limpieza y Finalización (Fase 5)

- [ ] **CLEAN-01**: Endpoint `GET /export/ventas.xlsx` genera Excel on-demand desde Postgres
- [ ] **CLEAN-02**: Eliminadas todas las subidas a Drive de archivos JSON (histórico, memoria, etc.)
- [ ] **CLEAN-03**: Google Sheets eliminado o mantenido solo como lectura opcional
- [ ] **CLEAN-04**: `start.py` simplificado: `_restaurar_memoria()` eliminado o reemplazado por inicialización desde Postgres
- [ ] **CLEAN-05**: Cero dependencias de Drive para datos estructurados — Drive solo para fotos de facturas
- [ ] **CLEAN-06**: `test_suite.py` pasa 1096+ tests en estado final

## v2 Requirements

### Observabilidad

- **OBS-01**: Logging de queries lentas (>500ms) a Postgres
- **OBS-02**: Health check endpoint que verifica conectividad a Postgres
- **OBS-03**: Métricas de uso de conexiones del pool

### Exportación avanzada

- **EXP-01**: Endpoint `GET /export/historico.xlsx` para el histórico
- **EXP-02**: Export de gastos por período a Excel

## Out of Scope

| Feature | Reason |
|---------|--------|
| Modificar `ai.py` o prompts de Claude | Crítico para el negocio, no tocar durante migración |
| Migrar fotos de facturas de Drive | Costo/complejidad no justificado; Drive es adecuado para archivos binarios |
| Cambiar nombres/formatos de endpoints de la API | Dashboard React depende de ellos; solo cambia la fuente interna |
| Refactorizar `ventas_state.py` | Estado en RAM intencional, no persiste entre reinicios |
| Agregar autenticación a la API | Fuera del scope de esta migración |
| Base de datos de alta disponibilidad (replica, sharding) | Railway PostgreSQL es suficiente para el volumen actual |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-01 | Phase 1 | Complete |
| DB-02 | Phase 1 | Complete |
| DB-03 | Phase 1 | Complete |
| DB-04 | Phase 1 | Complete |
| CAT-01 | Phase 1 | Complete |
| CAT-02 | Phase 1 | Complete |
| CAT-03 | Phase 1 | Complete |
| CAT-04 | Phase 1 | Complete |
| CAT-05 | Phase 1 | Complete |
| CAT-06 | Phase 1 | Complete |
| CAT-07 | Phase 1 | Complete |
| HIS-01 | Phase 2 | Complete |
| HIS-02 | Phase 2 | Complete |
| HIS-03 | Phase 2 | Complete |
| HIS-04 | Phase 2 | Complete |
| GAS-01 | Phase 2 | Complete |
| GAS-02 | Phase 2 | Complete |
| CAJ-01 | Phase 2 | Complete |
| CAJ-02 | Phase 2 | Complete |
| VEN-01 | Phase 3 | Complete |
| VEN-02 | Phase 3 | Complete |
| VEN-03 | Phase 3 | Complete |
| VEN-04 | Phase 3 | Complete |
| VEN-05 | Phase 3 | Complete |
| VEN-06 | Phase 3 | Complete |
| PROV-01 | Phase 4 | Pending |
| PROV-02 | Phase 4 | Pending |
| PROV-03 | Phase 4 | Pending |
| PROV-04 | Phase 4 | Complete |
| PROV-05 | Phase 4 | Pending |
| PROV-06 | Phase 4 | Pending |
| CLEAN-01 | Phase 5 | Pending |
| CLEAN-02 | Phase 5 | Pending |
| CLEAN-03 | Phase 5 | Pending |
| CLEAN-04 | Phase 5 | Pending |
| CLEAN-05 | Phase 5 | Pending |
| CLEAN-06 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-25*
*Last updated: 2026-03-25 after initial definition*
