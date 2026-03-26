# Phase 4: Proveedores + Fiados + Compras - Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-03-26
**Phase:** 04-proveedores-fiados-compras
**Mode:** assumptions
**Areas analyzed:** Write Path, Read Path (GET /compras), Photo URL en Postgres, Fiados Scope

## Assumptions Presented

### Write Path
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Dual-write inline en memoria.py write functions (registrar_factura_proveedor, registrar_abono_factura, guardar_fiado_movimiento, _registrar_historial_compra) usando patrón lazy import db + non-fatal try/except | Confident | memoria.py lines 962, 1264, 1518, 1556; 03-CONTEXT.md D-01/D-03 |

### Read Path: GET /compras
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| routers/caja.py GET /compras reescrito con Postgres-first + JSON fallback, igual que GET /gastos en el mismo archivo | Confident | routers/caja.py lines 396-427 (no Postgres path); lines 309-391 (GET /gastos ya implementado) |

### Photo URL en Postgres
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| POST /proveedores/.../foto agrega UPDATE no-fatal en Postgres después del write a memoria.json | Likely | routers/proveedores.py lines 91-139 y 179-230 — solo llaman guardar_memoria; facturas_proveedores.foto_url + facturas_abonos.foto_url columns in db.py |

### Fiados Scope
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Fiados solo Telegram-only; dual-write en guardar_fiado_movimiento(); PROV-06 cubre facturas, no fiados | Likely | No REST endpoint para fiados en ningún router; no dashboard tab para fiados |

## Corrections Made

No corrections — all assumptions confirmed.

## External Research

None required — codebase provided sufficient evidence for all areas.
