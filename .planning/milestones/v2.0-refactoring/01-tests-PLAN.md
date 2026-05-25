# Fase 01 — Tests para handlers/callbacks.py y routers sin cobertura

## Objetivo
Agregar cobertura de tests a los 4 archivos más expuestos que hoy tienen 0 tests.
Esto crea el net de seguridad que hace seguras las fases 02 y 03.

## Archivos a testear (en este orden)

1. `handlers/callbacks.py` — 650 líneas, flujo de botones inline y pago
2. `routers/ventas.py` — 812 líneas, endpoints REST de ventas
3. `routers/chat.py` — 954 líneas, endpoints de chat y stream
4. `routers/historico.py` — 567 líneas, endpoints de histórico

## Archivos a crear

```
tests/test_callbacks.py
tests/test_router_ventas.py
tests/test_router_chat.py
tests/test_router_historico.py
```

---

## FASE 01-A — test_callbacks.py

### Dependencias que hay que stubear (en este orden al tope del archivo)

```python
import sys, types, threading

for mod, attrs in [
    ("config",       {"COLOMBIA_TZ": None, "claude_client": None}),
    ("memoria",      {"cargar_memoria": lambda: {}, "invalidar_cache_memoria": lambda: None}),
    ("ventas_state", {
        "ventas_pendientes": {},
        "clientes_en_proceso": {},
        "mensajes_standby": {},
        "esperando_correccion": {},
        "ventas_esperando_cliente": {},
        "_estado_lock": threading.Lock(),
        "registrar_ventas_con_metodo": lambda *a, **kw: [],
        "get_chat_lock": lambda cid: __import__("contextlib").asynccontextmanager(lambda: (yield))(),
        "agregar_a_standby": lambda *a: None,
        "limpiar_pendientes_expirados": lambda: None,
    }),
    ("db",           {"DB_DISPONIBLE": False, "query_one": lambda *a: None, "execute": lambda *a: None}),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[mod] = m
```

### Funciones a testear en callbacks.py

| Función | Línea | Qué testear |
|---|---|---|
| `_enviar_botones_pago` | L370 | Genera InlineKeyboardMarkup con los 3 botones de pago |
| `manejar_metodo_pago` | L105 | callback_data `pago_efectivo_<id>` registra venta y limpia pendientes |
| `manejar_metodo_pago` | L105 | callback_data `pago_transferencia_<id>` hace lo mismo |
| `manejar_callback_cliente` | L418 | `cli_tipoid_CC_<chat_id>` setea tipo_id y avanza paso |
| `_formato_cantidad` | L545 | 1.0 → "1", 0.5 → "½", 1.5 → "1½" |
| `_procesar_siguiente_standby` | L41 | con lista vacía → no llama a bot |

### Tests mínimos (copiar patrón de test_catalogo_service.py)

```python
@pytest.mark.asyncio
async def test_enviar_botones_pago_genera_teclado(mocker):
    msg_mock = mocker.AsyncMock()
    msg_mock.reply_text = mocker.AsyncMock()
    ventas = [{"producto": "Tornillo", "cantidad": 10, "total": 5000}]
    # No llama a Telegram real — solo verifica que reply_text fue llamado
    # con parse_mode="Markdown" y un InlineKeyboardMarkup
    from handlers.callbacks import _enviar_botones_pago
    await _enviar_botones_pago(msg_mock, chat_id=123, ventas=ventas)
    msg_mock.reply_text.assert_called_once()
    _, kwargs = msg_mock.reply_text.call_args
    assert "reply_markup" in kwargs

def test_formato_cantidad_entero():
    from handlers.callbacks import _formato_cantidad
    assert _formato_cantidad(1.0, "tornillo") == "1"

def test_formato_cantidad_fraccion():
    from handlers.callbacks import _formato_cantidad
    assert _formato_cantidad(0.5, "pintura") == "½"
```

---

## FASE 01-B — test_router_ventas.py

### Setup con TestClient de FastAPI

```python
import sys, types, threading

# Stubs igual que 01-A, más:
if "ai" not in sys.modules:
    _ai = types.ModuleType("ai")
    _ai.procesar_con_claude = lambda *a, **kw: ""
    _ai.procesar_acciones = lambda *a, **kw: ("", [], [])
    sys.modules["ai"] = _ai

# DESPUÉS de los stubs:
from fastapi.testclient import TestClient
from routers.ventas import router
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)
client = TestClient(app)
```

### Endpoints a testear

| Endpoint | Método | Test mínimo |
|---|---|---|
| `/ventas/hoy` | GET | Responde 200, retorna lista (puede ser vacía con db stub) |
| `/ventas/semana` | GET | Responde 200 |
| `/ventas/top` | GET | Responde 200 con `periodo=semana` |
| `/venta-rapida` | POST | Con body válido retorna 200 o 422 (validación Pydantic) |
| `/ventas/{numero}` | DELETE | Con db stub retorna 404 o 200 |

### Patrón para stubear db en router tests

```python
from unittest.mock import patch

def test_ventas_hoy_devuelve_lista(mocker):
    mocker.patch("routers.ventas.db.query_all", return_value=[])
    mocker.patch("routers.ventas.db.DB_DISPONIBLE", True)
    resp = client.get("/ventas/hoy")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_ventas_hoy_sin_db_retorna_lista_vacia(mocker):
    mocker.patch("routers.ventas.db.DB_DISPONIBLE", False)
    resp = client.get("/ventas/hoy")
    assert resp.status_code == 200
```

---

## FASE 01-C — test_router_chat.py

### Endpoints prioritarios (los más riesgosos)

| Endpoint | Línea | Qué testear |
|---|---|---|
| `POST /chat` | L535 | Body mínimo `{"mensaje": "hola", "session_id": "test"}` → 200 |
| `POST /chat/memoria` | L488 | Guarda configuración de negocio |
| `GET /chat/briefing` | L831 | Responde sin DB disponible |
| `POST /chat/transcribir` | L902 | Archivo de audio inválido → 422 |

```python
def test_chat_endpoint_responde(mocker):
    mocker.patch("routers.chat.procesar_con_claude", return_value="respuesta test")
    mocker.patch("routers.chat.db.DB_DISPONIBLE", False)
    resp = client.post("/chat", json={"mensaje": "hola", "session_id": "abc123"})
    assert resp.status_code == 200
```

---

## FASE 01-D — test_router_historico.py

### Endpoints a testear

`routers/historico.py` son principalmente GETs de consulta. Con `db.query_all` mockeado a `[]` todos deben responder 200.

```python
@pytest.mark.parametrize("path", [
    "/historico/ventas",
    "/historico/gastos",
    "/historico/fiados",
])
def test_historico_endpoints_devuelven_200(path, mocker):
    mocker.patch("routers.historico.db.query_all", return_value=[])
    mocker.patch("routers.historico.db.DB_DISPONIBLE", True)
    resp = client.get(path)
    assert resp.status_code == 200
```

---

## Comandos de verificación final

```bash
# Correr solo los tests nuevos
pytest tests/test_callbacks.py tests/test_router_ventas.py tests/test_router_chat.py tests/test_router_historico.py -v

# Verificar que no se rompieron los tests existentes
pytest tests/ -x -q --tb=short

# Imports limpios
python -c "import handlers.callbacks; import routers.ventas; import routers.chat; print('OK')"
```

## Criterio de éxito

- Al menos 3 tests por archivo (12 tests nuevos total mínimo)
- `pytest tests/ -x -q` pasa en verde
- Ningún test usa conexión real a DB o Telegram

## Herramienta recomendada

Usar GSD: el planner puede deducir el patrón desde `test_catalogo_service.py` automáticamente.
```
/gsd:plan-phase "generar tests para handlers/callbacks.py y routers/ según fase 01 en .planning/phases/01-tests.md"
/gsd:execute-phase 1
```
