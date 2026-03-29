# TAREA F — `handlers/cmd_*.py` (split de comandos.py)

| Campo | Valor |
|---|---|
| **Fase** | 2 — después de Fase 1 |
| **Prioridad** | 🟠 ALTA |
| **Estado** | #pendiente |
| **Agente** | — |
| **Depende de** | [[TAREA-A]] ✅ |
| **Desbloquea** | nada (Fase 2 completa) |

---

## 📁 Archivos a CREAR

- [ ] `handlers/cmd_ventas.py`
- [ ] `handlers/cmd_inventario.py`
- [ ] `handlers/cmd_clientes.py`
- [ ] `handlers/cmd_caja.py`
- [ ] `handlers/cmd_proveedores.py`
- [ ] `handlers/cmd_admin.py`

## 📝 Archivos a EDITAR

- [ ] `handlers/comandos.py` — convertir en hub de re-exportación + aplicar `@protegido`

---

## 🎯 Propósito

`handlers/comandos.py` tiene **2450 líneas** (no 2200 — el conteo del plan era aproximado).
Dividirlo en 6 archivos temáticos y aplicar el decorador `@protegido` de Tarea A en cada handler.
`main.py` **no debe cambiar ni una línea** — todos los nombres siguen importables desde `handlers.comandos`.

---

## ⚠️ NOTAS PRE-TRABAJO — leer antes de escribir cualquier código

> Este mapa fue preparado manualmente antes de iniciar la tarea. No re-descubrir lo que ya está resuelto.

### 1. Conteo real
`comandos.py` tiene **2450 líneas**, no 2200. El plan original subestimó.

### 2. `upload_foto_cloudinary` (línea 46) es un helper compartido
Lo usa `cmd_proveedores`. Va en `cmd_proveedores.py`. Si más de un archivo lo necesita, moverlo a `handlers/_upload.py` y que ambos lo importen desde ahí.

### 3. Los flujos conversacionales NO son CommandHandlers
`manejar_flujo_agregar_producto` (línea 1588) y `manejar_mensaje_precio` (línea 1994) son funciones llamadas desde `handlers/mensajes.py`, no registradas en `main.py`. Deben seguir siendo importables desde el hub `comandos.py` sin cambiar `mensajes.py`.

### 4. Los aliases `/inventario` e `/inv` llaman a `comando_stock`
`comando_inventario` y `comando_inv` (líneas 476 y 504) simplemente hacen `await comando_stock(update, context)`. Mantener ese patrón — no colapsar en uno solo.

### 5. Actualmente NO existe ningún check de admin en ningún comando
`@protegido` se introduce por primera vez en esta tarea. Todos los handlers deben llevarlo — no solo los "peligrosos". El decorador ya es fail-open si `AUTHORIZED_CHAT_IDS` está vacío.

### 6. `cmd_proveedores.py` es un archivo nuevo no listado en el plan original
El plan decía 4 archivos (`cmd_ventas`, `cmd_inventario`, `cmd_clientes`, `cmd_caja`, `cmd_admin`). El análisis real muestra que los handlers de proveedores (facturas, abonos, deudas) merecen su propio archivo. Son 5 comandos + 1 helper de Cloudinary.

### 7. Orden seguro de ejecución
Crear los 6 archivos nuevos primero (sin tocar `comandos.py`), verificar imports, y solo después convertir `comandos.py` en hub. Nunca borrar una función de `comandos.py` antes de que el re-export esté en su lugar y verificado.

---

## 🗺️ Mapa completo de handlers → archivo destino

### `cmd_ventas.py`
| Función | Comando en main.py | Línea |
|---|---|---|
| `comando_inicio` | `/start`, `/ayuda` | 116 |
| `comando_ventas` | `/ventas` | 165 |
| `comando_borrar` | `/borrar` | 288 |
| `comando_pendientes` | `/pendientes` | 834 |
| `comando_grafica` | `/grafica` | 1052 |
| `manejar_callback_grafica` | *(callback interno, no en main.py)* | 1060 |
| `comando_cerrar_dia` | `/cerrar` | 1099 |
| `comando_reset_ventas` | `/resetventas` | 1257 |

### `cmd_inventario.py`
| Función | Comando en main.py | Línea |
|---|---|---|
| `comando_buscar` | `/buscar` | 228 |
| `comando_precios` | `/precios` | 359 |
| `comando_inventario` | `/inventario` *(alias → stock)* | 476 |
| `comando_inv` | `/inv` *(alias → stock)* | 504 |
| `comando_stock` | `/stock` | 569 |
| `comando_ajuste` | `/ajuste` | 624 |
| `comando_compra` | `/compra` | 655 |
| `comando_margenes` | `/margenes` | 791 |
| `comando_agregar_producto` | `/agregar_producto`, `/nuevo_producto` | 1567 |
| `comando_actualizar_precio` | `/actualizar_precio` | 1849 |
| `comando_actualizar_catalogo` | `/catalogo`, `/actualizar_catalogo` | 1349 |
| `manejar_flujo_agregar_producto` | *(flujo conversacional — importado por mensajes.py)* | 1588 |
| `manejar_mensaje_precio` | *(flujo conversacional — importado por mensajes.py)* | 1994 |
| `_resolver_grm` | *(helper privado)* | 485 |
| `_texto_categoria_prompt` | *(helper privado)* | 1578 |
| `_mostrar_confirmacion` | *(helper privado)* | 1761 |
| `_guardar_producto` | *(helper privado)* | 1781 |
| `_procesar_linea_precio` | *(helper privado)* | 1875 |

### `cmd_clientes.py`
| Función | Comando en main.py | Línea |
|---|---|---|
| `comando_clientes` | `/clientes` | 961 |
| `comando_nuevo_cliente` | `/nuevo_cliente` | 992 |
| `comando_fiados` | `/fiados` | 1011 |
| `comando_abono` | `/abono` | 1020 |

### `cmd_caja.py`
| Función | Comando en main.py | Línea |
|---|---|---|
| `comando_caja` | `/caja` | 408 |
| `comando_gastos` | `/gastos` | 462 |
| `comando_dashboard` | `/dashboard`, `/puntorojo` | 454 |

### `cmd_proveedores.py`
| Función | Comando en main.py | Línea |
|---|---|---|
| `upload_foto_cloudinary` | *(helper compartido — no en main.py)* | 46 |
| `comando_factura` | `/factura` | 2062 |
| `comando_abonar` | `/abonar` | 2134 |
| `comando_deudas` | `/deudas` | 2204 |
| `comando_facturas` | `/facturas` | 2241 |
| `comando_borrar_factura` | `/borrar_factura` | 2371 |

### `cmd_admin.py`
| Función | Comando en main.py | Línea |
|---|---|---|
| `comando_consistencia` | `/consistencia` | 1369 |
| `comando_exportar_precios` | `/exportar_precios` | 1421 |
| `comando_keepalive` | `/keepalive` | 1509 |
| `comando_modelo` | `/modelo` | 2021 |

---

## 🔁 Patrón `@protegido` a aplicar en cada handler

```python
# Al inicio de cada cmd_*.py:
from middleware import protegido

# En cada función handler:
@protegido
async def comando_ventas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ...
```

Los helpers privados (`_resolver_grm`, `_procesar_linea_precio`, etc.) **no llevan `@protegido`** — son funciones internas, no handlers de Telegram.

Los flujos conversacionales (`manejar_flujo_agregar_producto`, `manejar_mensaje_precio`) tampoco llevan `@protegido` — el control de acceso ya lo aplica el handler de mensajes que los llama.

---

## 🔁 Estructura del hub `comandos.py` después de la tarea

```python
# handlers/comandos.py — hub de re-exportación (no borrar este archivo)
# main.py importa todo desde aquí — no debe cambiar.

from handlers.cmd_ventas import (
    comando_inicio, comando_ventas, comando_borrar,
    comando_pendientes, comando_grafica, manejar_callback_grafica,
    comando_cerrar_dia, comando_reset_ventas,
)
from handlers.cmd_inventario import (
    comando_buscar, comando_precios, comando_inventario, comando_inv,
    comando_stock, comando_ajuste, comando_compra, comando_margenes,
    comando_agregar_producto, comando_actualizar_precio,
    comando_actualizar_catalogo,
    manejar_flujo_agregar_producto, manejar_mensaje_precio,
)
from handlers.cmd_clientes import (
    comando_clientes, comando_nuevo_cliente, comando_fiados, comando_abono,
)
from handlers.cmd_caja import (
    comando_caja, comando_gastos, comando_dashboard,
)
from handlers.cmd_proveedores import (
    upload_foto_cloudinary,
    comando_factura, comando_abonar, comando_deudas,
    comando_facturas, comando_borrar_factura,
)
from handlers.cmd_admin import (
    comando_consistencia, comando_exportar_precios,
    comando_keepalive, comando_modelo,
)

__all__ = [
    "comando_inicio", "comando_ventas", "comando_borrar",
    "comando_pendientes", "comando_grafica", "manejar_callback_grafica",
    "comando_cerrar_dia", "comando_reset_ventas",
    "comando_buscar", "comando_precios", "comando_inventario", "comando_inv",
    "comando_stock", "comando_ajuste", "comando_compra", "comando_margenes",
    "comando_agregar_producto", "comando_actualizar_precio",
    "comando_actualizar_catalogo",
    "manejar_flujo_agregar_producto", "manejar_mensaje_precio",
    "comando_clientes", "comando_nuevo_cliente", "comando_fiados", "comando_abono",
    "comando_caja", "comando_gastos", "comando_dashboard",
    "upload_foto_cloudinary",
    "comando_factura", "comando_abonar", "comando_deudas",
    "comando_facturas", "comando_borrar_factura",
    "comando_consistencia", "comando_exportar_precios",
    "comando_keepalive", "comando_modelo",
]
```

---

## ✅ Checklist de entrega

- [ ] 6 archivos `cmd_*.py` creados con sus handlers
- [ ] `@protegido` aplicado en todos los handlers públicos
- [ ] `handlers/comandos.py` convertido en hub de re-exportación puro
- [ ] `python -c "from handlers.comandos import *; print(len([x for x in dir() if not x.startswith('_')]))"` — mismo número que antes
- [ ] `python -c "import main; print('OK')"` — sin errores
- [ ] `python -m pytest tests/ -v --ignore=test_suite.py` — sin regresiones
- [ ] Commit: `git commit -m "refactor: split comandos.py en 6 cmd_*.py + apply @protegido (Tarea F)"`

---

## 📋 Prompt para Claude Code

```
Lee _obsidian/01-Proyecto/TAREA-F.md completo antes de escribir cualquier código.
El mapa de handlers ya está resuelto en la sección "Mapa completo" — no re-analizar comandos.py,
usar el mapa directamente. El hub final de comandos.py también está pre-escrito en la sección
"Estructura del hub". Ejecutar en este orden:
1. Crear los 6 cmd_*.py con sus handlers y @protegido
2. Verificar imports de cada archivo nuevo
3. Reemplazar el contenido de comandos.py con el hub de re-exportación
4. Verificar que python -c "import main; print('OK')" pasa
5. Commit
```

---

## 📓 Log / Notas

<!-- Pega aquí los outputs de Claude Code -->

---

← [[TAREA-A]] | [[MAPA]]
