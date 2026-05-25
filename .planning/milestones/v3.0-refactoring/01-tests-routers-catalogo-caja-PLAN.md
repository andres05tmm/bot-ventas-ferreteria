# Fase 01 — Tests para routers/catalogo.py y routers/caja.py

## Prerequisito
`pytest tests/ -x -q` pasa en verde (97 tests).

## Objetivo
Cobertura mínima en los 2 routers del dashboard con 0 tests hoy.
Este es el net de seguridad para las fases 02 y 03.

## PASO 0 — Agregar dependencias faltantes a requirements.txt

Los tests usan `pytest-mock` (fixture `mocker`) y `httpx` (TestClient).
Verificar que están en requirements.txt:

```bash
grep "pytest\|httpx" requirements.txt
```

Si no están, agregarlos:

```bash
echo "pytest>=8.0.0" >> requirements.txt
echo "pytest-mock>=3.14.0" >> requirements.txt
echo "pytest-asyncio>=0.24.0" >> requirements.txt
echo "httpx>=0.27.0" >> requirements.txt
```

> `httpx` probablemente ya está (anthropic lo usa). Solo agregar lo que falte.

---

## PASO 1 — Crear tests/test_router_catalogo.py

Datos críticos del router real (NO inventar):
- Archivo: `routers/catalogo.py`
- Importa: `import db` (sin alias), `from routers.shared import _hace_n_dias`
- Sin prefix — endpoints montados en raíz: `/productos`, `/catalogo/nav`, etc.
- Endpoints reales:
  - `GET /productos`
  - `GET /inventario/bajo`
  - `GET /catalogo/nav?q=`
  - `GET /kardex`
  - `POST /catalogo` (body: NuevoProducto)
  - `PATCH /catalogo/{key:path}/precio` (body: PrecioUpdate)

```python
"""
tests/test_router_catalogo.py — Cobertura básica de routers/catalogo.py.

Sin DB real. Usa stubs en sys.modules y mocker para parchear db.query_all/query_one.
"""
import sys
import types

# ── Stubs ANTES de cualquier import propio ────────────────────────────────────
# CRÍTICO: el orden importa. Estos módulos deben estar antes del import del router.

if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = __import__("datetime").timezone.utc
    _cfg.claude_client = None
    _cfg.openai_client = None
    sys.modules["config"] = _cfg

if "db" not in sys.modules:
    _db = types.ModuleType("db")
    _db.DB_DISPONIBLE = False
    _db.query_one = lambda *a, **kw: None
    _db.query_all = lambda *a, **kw: []
    _db.execute = lambda *a, **kw: None
    sys.modules["db"] = _db

if "memoria" not in sys.modules:
    _mem = types.ModuleType("memoria")
    _mem.cargar_memoria = lambda: {"catalogo": {}, "inventario": {}}
    _mem.invalidar_cache_memoria = lambda: None
    _mem.buscar_producto_en_catalogo = lambda x: None
    _mem.actualizar_precio_en_catalogo = lambda *a, **kw: None
    _mem.importar_catalogo_desde_excel = lambda *a, **kw: {}
    sys.modules["memoria"] = _mem

# routers.shared es importado por catalogo — stubear antes de importar el router
if "routers.shared" not in sys.modules:
    _shared = types.ModuleType("routers.shared")
    import datetime as _dt
    _shared._hace_n_dias = lambda n: (_dt.datetime.utcnow() - _dt.timedelta(days=n)).isoformat()
    sys.modules["routers.shared"] = _shared

# ── Montar app de test ─────────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.catalogo import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_productos_sin_db(mocker):
    """DB no disponible → 200 con lista vacía (no explota)."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.get("/productos")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_productos_con_db_vacia(mocker):
    """DB disponible pero sin productos → 200 con lista vacía."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/productos")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_inventario_bajo_sin_db(mocker):
    """Sin DB → retorna lista vacía, no 503."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.get("/inventario/bajo")
    assert resp.status_code == 200


def test_inventario_bajo_con_db(mocker):
    """Con DB vacía → 200 con lista."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/inventario/bajo")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_catalogo_nav_query_vacio(mocker):
    """q='' → 200 (no falla con query vacío)."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/catalogo/nav?q=")
    assert resp.status_code == 200


def test_catalogo_nav_con_termino(mocker):
    """q=tornillo → 200 con resultados (puede ser lista vacía)."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/catalogo/nav?q=tornillo")
    assert resp.status_code == 200


def test_kardex_sin_db(mocker):
    """Sin DB → 200 con lista vacía."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", False)
    resp = client.get("/kardex")
    assert resp.status_code == 200


def test_kardex_con_db(mocker):
    """Con DB → 200."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_all", return_value=[])
    resp = client.get("/kardex")
    assert resp.status_code == 200


def test_crear_producto_body_vacio():
    """POST /catalogo sin body → 422 (validación Pydantic)."""
    resp = client.post("/catalogo", json={})
    assert resp.status_code == 422


def test_actualizar_precio_producto_inexistente(mocker):
    """PATCH precio de producto que no existe en DB → 404."""
    mocker.patch("routers.catalogo.db.DB_DISPONIBLE", True)
    mocker.patch("routers.catalogo.db.query_one", return_value=None)
    resp = client.patch("/catalogo/tornillo-inexistente/precio", json={"precio": 1000})
    assert resp.status_code in (404, 422)
```

---

## PASO 2 — Crear tests/test_router_caja.py

Datos críticos del router real:
- Archivo: `routers/caja.py`
- Importa: `import db as _db` (con alias), `import config`, `from memoria import registrar_compra`
- Sin prefix — endpoints en raíz: `/caja`, `/gastos`, `/compras`
- Endpoints reales:
  - `GET /caja`
  - `POST /caja/abrir` (body: CajaAbrirBody)
  - `POST /caja/cerrar`
  - `GET /gastos?dias=7`
  - `POST /gastos` (body: NuevoGastoBody)
  - `GET /compras?dias=30`

```python
"""
tests/test_router_caja.py — Cobertura básica de routers/caja.py.

Sin DB real. Nota: el router usa `import db as _db` — los patches
deben usar el alias: mocker.patch("routers.caja._db.DB_DISPONIBLE", ...).
"""
import sys
import types

# ── Stubs ANTES de cualquier import propio ────────────────────────────────────

if "config" not in sys.modules:
    _cfg = types.ModuleType("config")
    _cfg.COLOMBIA_TZ = __import__("datetime").timezone.utc
    _cfg.claude_client = None
    _cfg.openai_client = None
    sys.modules["config"] = _cfg

if "db" not in sys.modules:
    _db = types.ModuleType("db")
    _db.DB_DISPONIBLE = False
    _db.query_one = lambda *a, **kw: None
    _db.query_all = lambda *a, **kw: []
    _db.execute = lambda *a, **kw: None
    sys.modules["db"] = _db

if "memoria" not in sys.modules:
    _mem = types.ModuleType("memoria")
    _mem.cargar_caja = lambda: {}
    _mem.guardar_gasto = lambda *a, **kw: None
    _mem.cargar_gastos_hoy = lambda: []
    _mem.obtener_resumen_caja = lambda: {}
    _mem.cargar_memoria = lambda: {}
    _mem.registrar_compra = lambda *a, **kw: (True, "ok", {})
    sys.modules["memoria"] = _mem

# ── Montar app de test ─────────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.caja import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ── Tests ─────────────────────────────────────────────────────────────────────
# IMPORTANTE: el router usa `import db as _db` — parchear "routers.caja._db.*"

def test_caja_sin_db(mocker):
    """Sin DB → responde 200 con datos vacíos (no 503)."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", False)
    resp = client.get("/caja")
    assert resp.status_code == 200


def test_caja_con_db_vacia(mocker):
    """Con DB → 200 aunque no haya registros."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_one", return_value=None)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/caja")
    assert resp.status_code == 200


def test_gastos_sin_db(mocker):
    """Sin DB → 200 con lista vacía."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", False)
    resp = client.get("/gastos")
    assert resp.status_code == 200


def test_gastos_con_db(mocker):
    """Con DB → 200 con lista."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/gastos")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_gastos_param_dias(mocker):
    """?dias=30 → acepta el parámetro sin error."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/gastos?dias=30")
    assert resp.status_code == 200


def test_compras_con_db(mocker):
    """GET /compras → 200."""
    mocker.patch("routers.caja._db.DB_DISPONIBLE", True)
    mocker.patch("routers.caja._db.query_all", return_value=[])
    resp = client.get("/compras")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_abrir_caja_body_vacio():
    """POST /caja/abrir sin body → 422."""
    resp = client.post("/caja/abrir", json={})
    assert resp.status_code == 422


def test_registrar_gasto_body_vacio():
    """POST /gastos sin body → 422."""
    resp = client.post("/gastos", json={})
    assert resp.status_code == 422
```

---

## PASO 3 — Verificar

```bash
pytest tests/test_router_catalogo.py tests/test_router_caja.py -v --tb=short
```

Si algún test falla por ImportError, el error indicará qué stub falta.
Agregar el stub que corresponda al bloque de stubs del archivo afectado.

```bash
# Suite completa
pytest tests/ -x -q --tb=short
```

## Criterio de éxito
- ≥10 tests en `test_router_catalogo.py`, ≥8 en `test_router_caja.py`
- `pytest tests/ -x -q` pasa en verde
- Ningún test hace conexión real a DB ni Telegram
