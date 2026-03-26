# Plan de Migración: Drive/JSON/Excel → PostgreSQL

## Objetivo

Reemplazar `memoria.json` + `ventas.xlsx` + archivos de histórico como fuentes de persistencia por **PostgreSQL en Railway**. Google Drive queda solo para fotos de facturas.

---

## Schema de PostgreSQL

Ejecutar este SQL completo en Railway para crear todas las tablas antes de empezar:

```sql
-- ═══════════════════════════════════════════════════════════════
-- FERREBOT — Schema PostgreSQL
-- ═══════════════════════════════════════════════════════════════

-- Extensión para UUIDs (opcional, usamos SERIAL por simplicidad)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ───────────────────────────────────────────────────────────────
-- CATÁLOGO DE PRODUCTOS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS productos (
    id              SERIAL PRIMARY KEY,
    clave           VARCHAR(200) UNIQUE NOT NULL,  -- ej: "brocha_2_pulgadas"
    nombre          VARCHAR(300) NOT NULL,
    nombre_lower    VARCHAR(300) NOT NULL,
    codigo          VARCHAR(100),
    categoria       VARCHAR(200),
    precio_unidad   INTEGER NOT NULL DEFAULT 0,
    unidad_medida   VARCHAR(50) DEFAULT 'Unidad',
    activo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Precios por fracción (pinturas/disolventes: 1/4, 1/2, 3/4, etc.)
CREATE TABLE IF NOT EXISTS productos_fracciones (
    id              SERIAL PRIMARY KEY,
    producto_id     INTEGER REFERENCES productos(id) ON DELETE CASCADE,
    fraccion        VARCHAR(10) NOT NULL,  -- "1/4", "1/2", "3/4", "1/8", "1/16"
    precio_total    INTEGER NOT NULL,      -- precio de venta de esa fracción
    precio_unitario INTEGER NOT NULL       -- precio por unidad fraccionada
);

-- Precio por cantidad (tornillería: precio distinto si compra >= umbral)
CREATE TABLE IF NOT EXISTS productos_precio_cantidad (
    id                   SERIAL PRIMARY KEY,
    producto_id          INTEGER REFERENCES productos(id) ON DELETE CASCADE UNIQUE,
    umbral               INTEGER NOT NULL DEFAULT 50,
    precio_bajo_umbral   INTEGER NOT NULL,
    precio_sobre_umbral  INTEGER NOT NULL
);

-- Alias/sinónimos de productos
CREATE TABLE IF NOT EXISTS productos_alias (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER REFERENCES productos(id) ON DELETE CASCADE,
    alias       VARCHAR(200) NOT NULL,
    UNIQUE(alias)
);

-- ───────────────────────────────────────────────────────────────
-- INVENTARIO
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inventario (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER REFERENCES productos(id) ON DELETE CASCADE UNIQUE,
    cantidad    NUMERIC(10,3) DEFAULT 0,
    minimo      NUMERIC(10,3) DEFAULT 0,
    unidad      VARCHAR(50) DEFAULT 'Unidad',
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- CLIENTES
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clientes (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(300) NOT NULL,
    tipo_id         VARCHAR(10),           -- CC, NIT, CE
    identificacion  VARCHAR(50),
    tipo_persona    VARCHAR(20),           -- Natural, Juridica
    correo          VARCHAR(200),
    telefono        VARCHAR(50),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- VENTAS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ventas (
    id              SERIAL PRIMARY KEY,
    consecutivo     INTEGER NOT NULL,
    fecha           DATE NOT NULL,
    hora            TIME,
    cliente_id      INTEGER REFERENCES clientes(id),
    cliente_nombre  VARCHAR(300) DEFAULT 'Consumidor Final',
    vendedor        VARCHAR(100),
    metodo_pago     VARCHAR(50),           -- efectivo, transferencia, datafono
    total           INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Líneas de cada venta
CREATE TABLE IF NOT EXISTS ventas_detalle (
    id              SERIAL PRIMARY KEY,
    venta_id        INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id     INTEGER REFERENCES productos(id),
    producto_nombre VARCHAR(300) NOT NULL,  -- guardamos nombre en caso de que cambie
    cantidad        NUMERIC(10,3) NOT NULL,
    unidad_medida   VARCHAR(50) DEFAULT 'Unidad',
    precio_unitario INTEGER,
    total           INTEGER NOT NULL,
    alias_usado     VARCHAR(200)
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_consecutivo ON ventas(consecutivo);
CREATE INDEX IF NOT EXISTS idx_ventas_detalle_venta ON ventas_detalle(venta_id);

-- ───────────────────────────────────────────────────────────────
-- GASTOS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gastos (
    id          SERIAL PRIMARY KEY,
    fecha       DATE NOT NULL,
    hora        TIME,
    concepto    VARCHAR(300) NOT NULL,
    monto       INTEGER NOT NULL,
    categoria   VARCHAR(100),              -- operativo, abono_proveedor, etc.
    origen      VARCHAR(50) DEFAULT 'bot', -- bot, manual
    fac_id      VARCHAR(20),               -- referencia a factura si es abono
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);

-- ───────────────────────────────────────────────────────────────
-- CAJA
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS caja (
    id              SERIAL PRIMARY KEY,
    fecha           DATE UNIQUE NOT NULL,
    abierta         BOOLEAN DEFAULT FALSE,
    monto_apertura  INTEGER DEFAULT 0,
    efectivo        INTEGER DEFAULT 0,
    transferencias  INTEGER DEFAULT 0,
    datafono        INTEGER DEFAULT 0,
    cerrada_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- FIADOS (cuentas de crédito a clientes)
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fiados (
    id          SERIAL PRIMARY KEY,
    cliente_id  INTEGER REFERENCES clientes(id),
    nombre      VARCHAR(300) NOT NULL,     -- desnormalizado para búsqueda rápida
    deuda       INTEGER DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fiados_historial (
    id          SERIAL PRIMARY KEY,
    fiado_id    INTEGER REFERENCES fiados(id) ON DELETE CASCADE,
    tipo        VARCHAR(20) NOT NULL,      -- 'cargo' o 'abono'
    monto       INTEGER NOT NULL,
    concepto    VARCHAR(300),
    fecha       DATE NOT NULL,
    hora        TIME,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- FACTURAS DE PROVEEDORES (cuentas por pagar)
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facturas_proveedores (
    id              VARCHAR(20) PRIMARY KEY,  -- FAC-001, FAC-002...
    proveedor       VARCHAR(200) NOT NULL,
    descripcion     VARCHAR(500),
    total           INTEGER NOT NULL,
    pagado          INTEGER DEFAULT 0,
    pendiente       INTEGER NOT NULL,
    estado          VARCHAR(20) DEFAULT 'pendiente',  -- pendiente, parcial, pagada
    fecha           DATE NOT NULL,
    foto_url        TEXT DEFAULT '',
    foto_nombre     VARCHAR(300) DEFAULT '',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS facturas_abonos (
    id          SERIAL PRIMARY KEY,
    factura_id  VARCHAR(20) REFERENCES facturas_proveedores(id) ON DELETE CASCADE,
    monto       INTEGER NOT NULL,
    fecha       DATE NOT NULL,
    foto_url    TEXT DEFAULT '',
    foto_nombre VARCHAR(300) DEFAULT '',
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- HISTÓRICO DE VENTAS DIARIAS
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS historico_ventas (
    fecha           DATE PRIMARY KEY,
    ventas          INTEGER DEFAULT 0,
    efectivo        INTEGER DEFAULT 0,
    transferencia   INTEGER DEFAULT 0,
    datafono        INTEGER DEFAULT 0,
    n_transacciones INTEGER DEFAULT 0,
    gastos          INTEGER DEFAULT 0,
    abonos_proveedores INTEGER DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- COMPRAS DE MERCANCÍA
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compras (
    id              SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL,
    hora            TIME,
    proveedor       VARCHAR(200),
    producto_id     INTEGER REFERENCES productos(id),
    producto_nombre VARCHAR(300) NOT NULL,
    cantidad        NUMERIC(10,3) NOT NULL,
    costo_unitario  INTEGER,
    costo_total     INTEGER,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- PRODUCTOS PENDIENTES (no encontrados en catálogo)
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS productos_pendientes (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(300) NOT NULL,
    fecha       DATE NOT NULL,
    hora        TIME,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────
-- CONFIGURACIÓN DEL SISTEMA (reemplaza campos sueltos en memoria.json)
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS config_sistema (
    clave   VARCHAR(100) PRIMARY KEY,
    valor   TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Valores iniciales
INSERT INTO config_sistema (clave, valor) VALUES
    ('keepalive_activo', 'false'),
    ('version', 'v8.0-refactor')
ON CONFLICT (clave) DO NOTHING;
```

---

## Plan de migración por fases

### FASE 1 — Base + Catálogo + Inventario
**Archivos a modificar:** `memoria.py`, `config.py`, `fuzzy_match.py`, `precio_sync.py`

**Tareas:**
- [ ] Agregar `DATABASE_URL` a config.py y crear pool de conexión (`asyncpg` o `psycopg2`)
- [ ] Crear `db.py` — módulo central de acceso a Postgres
- [ ] Migrar catálogo de `memoria.json` → tabla `productos` + `productos_fracciones` + `productos_precio_cantidad`
- [ ] Migrar alias → tabla `productos_alias`
- [ ] Reemplazar `cargar_memoria()["catalogo"]` por queries a `productos`
- [ ] Reemplazar `guardar_memoria()` para catálogo por INSERTs/UPDATEs
- [ ] Actualizar `fuzzy_match.py` para que lea el índice desde Postgres
- [ ] Migrar inventario → tabla `inventario`
- [ ] Script de migración inicial: leer `memoria.json` actual e insertar todo en Postgres

**Criterio de éxito:** `/precios`, `/inventario` y el bot registrando ventas funcionan igual

---

### FASE 2 — Histórico + Gastos + Caja
**Archivos a modificar:** `routers/historico.py`, `routers/gastos.py`, `routers/caja.py`

**Tareas:**
- [ ] Migrar `historico_ventas.json` + `historico_diario.json` → tabla `historico_ventas`
- [ ] Reemplazar `_leer_historico()` / `_guardar_historico()` por queries
- [ ] Migrar gastos de `memoria.json["gastos"]` → tabla `gastos`
- [ ] Migrar caja de `memoria.json["caja_actual"]` → tabla `caja`
- [ ] Eliminar subidas a Drive de archivos JSON de histórico
- [ ] Actualizar `_sync_historico_hoy()` para escribir en Postgres

**Criterio de éxito:** Tab Histórico del dashboard muestra datos desde Postgres

---

### FASE 3 — Ventas (la más compleja)
**Archivos a modificar:** `excel.py`, `sheets.py`, `routers/ventas.py`, `routers/shared.py`, `handlers/comandos.py`

**Tareas:**
- [ ] Crear endpoint de registro de venta que escribe en `ventas` + `ventas_detalle`
- [ ] Modificar el callback de confirmación de pago para escribir en Postgres además de Sheets
- [ ] Migrar `/cerrar`: en lugar de copiar Sheets → Excel, copiar Sheets → Postgres
- [ ] Reemplazar `_leer_excel_rango()` por query a `ventas` + `ventas_detalle`
- [ ] Mantener escritura en Sheets durante la transición (eliminar en Fase 5)
- [ ] Migrar ventas históricas del Excel a Postgres (script de migración)
- [ ] Actualizar endpoints `/ventas/*` para leer desde Postgres

**Criterio de éxito:** Bot registra ventas en Postgres. Dashboard muestra ventas desde Postgres.

---

### FASE 4 — Proveedores + Fiados + Compras
**Archivos a modificar:** `routers/proveedores.py`, `memoria.py` (funciones de fiados y facturas)

**Tareas:**
- [ ] Migrar `cuentas_por_pagar` → tabla `facturas_proveedores` + `facturas_abonos`
- [ ] Migrar `fiados` → tablas `fiados` + `fiados_historial`
- [ ] Migrar compras del Excel (hoja Compras) → tabla `compras`
- [ ] Actualizar routers de proveedores para leer/escribir en Postgres
- [ ] Las fotos de facturas siguen en Drive — no cambiar esa parte

**Criterio de éxito:** Tab Proveedores funciona desde Postgres

---

### FASE 5 — Limpieza + Export Excel + Eliminar Drive/Sheets
**Archivos a modificar:** todos los que aún referencien Drive para JSONs

**Tareas:**
- [ ] Crear endpoint `GET /export/ventas.xlsx` que genera el Excel bajo demanda desde Postgres
- [ ] Crear endpoint `GET /export/historico.xlsx` para el histórico
- [ ] Eliminar todas las subidas a Drive de archivos JSON
- [ ] Eliminar sincronización de Sheets (o mantener solo como lectura en tiempo real)
- [ ] Eliminar `historico_ventas.json`, `historico_diario.json` de Drive
- [ ] Actualizar `start.py` para eliminar `_restaurar_memoria()` o simplificarlo
- [ ] Ejecutar test_suite.py y verificar 1096+ tests pasando

**Criterio de éxito:** cero dependencias de Drive para datos estructurados. Drive solo = fotos de facturas.

---

## Módulo db.py a crear (base para todo)

```python
"""
db.py — Acceso central a PostgreSQL.
Usar este módulo en lugar de psycopg2/asyncpg directamente.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")

@contextmanager
def get_conn():
    """Context manager para conexiones sincrónicas (handlers del bot)."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def query_one(sql: str, params=None) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

def query_all(sql: str, params=None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def execute(sql: str, params=None) -> int:
    """Ejecuta INSERT/UPDATE/DELETE. Retorna rowcount."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

def execute_returning(sql: str, params=None) -> dict | None:
    """Ejecuta INSERT ... RETURNING. Retorna la fila insertada."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
```

---

## Script de migración inicial (Fase 1)

```python
"""
migrate_memoria.py — Ejecutar UNA SOLA VEZ para migrar memoria.json → Postgres
"""
import json
import db

def migrar():
    with open("memoria.json", encoding="utf-8") as f:
        mem = json.load(f)

    catalogo = mem.get("catalogo", {})
    print(f"Migrando {len(catalogo)} productos...")

    for clave, prod in catalogo.items():
        # Insertar producto
        row = db.execute_returning("""
            INSERT INTO productos (clave, nombre, nombre_lower, categoria, precio_unidad)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (clave) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                precio_unidad = EXCLUDED.precio_unidad
            RETURNING id
        """, (
            clave,
            prod["nombre"],
            prod.get("nombre_lower", prod["nombre"].lower()),
            prod.get("categoria", ""),
            prod.get("precio_unidad", 0),
        ))
        prod_id = row["id"]

        # Fracciones
        for frac, datos in prod.get("precios_fraccion", {}).items():
            db.execute("""
                INSERT INTO productos_fracciones (producto_id, fraccion, precio_total, precio_unitario)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (prod_id, frac, datos.get("precio", 0), datos.get("precio_unitario", 0)))

        # Precio por cantidad (tornillos)
        pxc = prod.get("precio_por_cantidad", {})
        if pxc:
            db.execute("""
                INSERT INTO productos_precio_cantidad
                    (producto_id, umbral, precio_bajo_umbral, precio_sobre_umbral)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (producto_id) DO UPDATE SET
                    precio_bajo_umbral = EXCLUDED.precio_bajo_umbral,
                    precio_sobre_umbral = EXCLUDED.precio_sobre_umbral
            """, (
                prod_id,
                pxc.get("umbral", 50),
                pxc.get("precio_bajo_umbral", prod.get("precio_unidad", 0)),
                pxc.get("precio_sobre_umbral", 0),
            ))

    print("✅ Catálogo migrado")

    # Inventario
    inventario = mem.get("inventario", {})
    print(f"Migrando {len(inventario)} items de inventario...")
    for clave, datos in inventario.items():
        prod_row = db.query_one("SELECT id FROM productos WHERE clave = %s", (clave,))
        if prod_row:
            db.execute("""
                INSERT INTO inventario (producto_id, cantidad, minimo, unidad)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (producto_id) DO UPDATE SET
                    cantidad = EXCLUDED.cantidad,
                    minimo = EXCLUDED.minimo
            """, (
                prod_row["id"],
                datos.get("cantidad", 0),
                datos.get("minimo", 0),
                datos.get("unidad", "Unidad"),
            ))
    print("✅ Inventario migrado")

    print("🎉 Migración inicial completa")

if __name__ == "__main__":
    migrar()
```

---

## Dependencias a agregar en requirements.txt

```
psycopg2-binary>=2.9.9
```

---

## Variables de entorno a agregar en Railway

```
DATABASE_URL=postgresql://postgres:password@host:5432/railway
```
Railway la agrega automáticamente al crear la base de datos PostgreSQL en el proyecto.

---

## Notas importantes para Claude Code

1. **Migrar de a una fase** — no mezclar fases. Cada fase debe funcionar de punta a punta antes de avanzar.

2. **Compatibilidad hacia atrás** — durante la transición, algunos módulos leerán de Postgres y otros de `memoria.json`. Esto es intencional.

3. **El bot no puede estar caído** — Railway redespliega automáticamente. Cada commit debe dejar el sistema funcionando.

4. **Mantener la interfaz pública de `memoria.py`** — muchos módulos llaman `cargar_memoria()` y `guardar_memoria()`. Reemplazar la implementación interna pero mantener las firmas de función.

5. **`_leer_excel_rango()` en `routers/shared.py`** — esta función es crítica, la llaman muchos routers. Migrarla a Postgres es el unlock de la Fase 3.

6. **Tests:** después de cada fase ejecutar `python test_suite.py` y verificar 1096+ tests pasando.
