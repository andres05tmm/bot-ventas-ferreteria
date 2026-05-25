# Fase 03 — Split de _construir_parte_dinamica en ai/prompts.py

## Prerequisito
Fase 01 completa. `pytest tests/ -x -q` pasa en verde.

## Objetivo
Bajar `ai/prompts.py` de 1370 a ≤400 líneas extrayendo `_construir_parte_dinamica`
(L215-L1283, 1069 líneas) a dos módulos dedicados.

## Firma real confirmada

```python
def _construir_parte_dinamica(
    mensaje_usuario: str,
    nombre_usuario: str,
    memoria: dict,
    dashboard_mode: bool = False
) -> str:
```

Hay **dos call sites** en `ai/__init__.py`:
- L303: `_construir_parte_dinamica(mensaje_usuario, nombre_usuario, memoria)` — sin dashboard_mode
- L606: `_construir_parte_dinamica(mensaje_usuario, nombre_usuario, memoria, dashboard_mode=_dashboard_mode)` — con dashboard_mode

Ambos deben seguir funcionando sin cambios.

---

## PASO 1 — Leer el mapa de secciones antes de escribir nada

```bash
# Ver secciones y funciones internas de _construir_parte_dinamica
sed -n '215,1283p' ai/prompts.py | grep -n "# ──\|    def \|^    # "
```

Las funciones anidadas (nested defs) confirmadas dentro de `_construir_parte_dinamica`:
- L278: `def _es_keyword_relevante(p)` → pertenece a sección candidatos (prompt_products.py)
- L313: `def _extraer_cantidad_mixta(msg)` → pertenece a sección candidatos (prompt_products.py)
- L418: `def _norm_seg(s)` → pertenece a sección candidatos (prompt_products.py)
- L681: `def _linea_candidato(p)` → pertenece a sección candidatos (prompt_products.py)
- L742: `def _stem(w)` → pertenece a sección candidatos (prompt_products.py)
- L911: `def _stem_simple(w)` → pertenece a sección candidatos (prompt_products.py)
- L922: `def _es_relevante_resto(prod)` → pertenece a sección candidatos (prompt_products.py)

**Estas funciones viajan con su sección — no son funciones de módulo independientes.**

---

## PASO 2 — Crear ai/prompt_context.py

Responsabilidad: datos del negocio (ventas, clientes, operaciones, cuentas por pagar).

```python
"""
ai/prompt_context.py — Contexto de negocio para el system prompt.

Carga y formatea datos dinámicos que cambian entre mensajes:
  - Resumen de ventas del mes e histórico
  - Clientes recientes y búsqueda de cliente en el mensaje
  - Inventario, caja, gastos del día
  - Cuentas por pagar (facturas de proveedores)

Retorna strings ya formateados listos para insertar en el prompt.

TODOS los imports de ai, memoria y db son LAZY (dentro de función).
Esto es obligatorio — evita ciclos ai/__init__.py ↔ ai/prompt_context.py.
"""
import logging

logger = logging.getLogger("ferrebot.ai.prompt_context")


def construir_seccion_ventas(dashboard_mode: bool = False) -> tuple[str, str]:
    """
    Retorna (resumen_texto, datos_historicos_texto).
    [Copiar L237-L474 de _construir_parte_dinamica íntegro]

    resumen_texto: ej. "$1.200.000 en 45 ventas este mes"
    datos_historicos_texto: tabla de ventas históricas para análisis
    """
    ...


def construir_seccion_clientes(mensaje_usuario: str) -> str:
    """
    Retorna texto con clientes recientes y cliente encontrado en el mensaje.
    [Copiar L957-L1036 de _construir_parte_dinamica íntegro]
    """
    ...


def construir_seccion_operaciones() -> str:
    """
    Retorna texto con inventario bajo stock, caja del día, gastos y facturas pendientes.
    [Copiar L1037-L1081 de _construir_parte_dinamica íntegro]
    """
    ...
```

---

## PASO 3 — Crear ai/prompt_products.py

Responsabilidad: matching de catálogo y precálculos de productos especiales.

```python
"""
ai/prompt_products.py — Precálculos de productos para el system prompt.

Matching de catálogo y cálculo de precios para productos con reglas especiales:
  - Candidatos del catálogo (sección MATCH) — la más grande (~300 líneas)
  - Tornillos (precio mayorista, drywall)
  - Puntillas (precio por gramos y por pesos)
  - Pinturas: Acronal, Thinner, Varsol (fracciones de galón)

Retorna strings ya formateados listos para incluir en el system prompt.

TODOS los imports de memoria, ai y db son LAZY (dentro de función).
"""
import logging
import re

logger = logging.getLogger("ferrebot.ai.prompt_products")


def construir_seccion_match(
    mensaje_usuario: str,
    nombre_usuario: str,
    memoria: dict,
) -> str:
    """
    Retorna el bloque MATCH con candidatos del catálogo para el mensaje.
    Es la sección más grande (~300 líneas, L655-L956).

    Incluye las nested defs:
      _es_keyword_relevante, _extraer_cantidad_mixta, _norm_seg,
      _linea_candidato, _stem, _stem_simple, _es_relevante_resto

    [Copiar L475-L956 de _construir_parte_dinamica íntegro — incluye
     precalculos de tornillos/puntillas que preceden al MATCH]
    """
    ...


def construir_precalculos_especiales(
    mensaje_usuario: str,
    memoria: dict,
) -> str:
    """
    Retorna texto con precálculos de productos especiales:
    Acronal, Thinner, Varsol, tornillos drywall.
    [Copiar L1082-L1278 de _construir_parte_dinamica íntegro]
    """
    ...
```

---

## PASO 4 — Reemplazar _construir_parte_dinamica en prompts.py

La función queda como orquestador de ~30 líneas:

```python
def _construir_parte_dinamica(
    mensaje_usuario: str,
    nombre_usuario: str,
    memoria: dict,
    dashboard_mode: bool = False,
) -> str:
    """
    Orquesta la parte dinámica del system prompt.
    Delega en ai.prompt_context y ai.prompt_products.
    """
    # Lazy imports — evita ciclo con ai/__init__.py
    from ai.prompt_context import (
        construir_seccion_ventas,
        construir_seccion_clientes,
        construir_seccion_operaciones,
    )
    from ai.prompt_products import (
        construir_seccion_match,
        construir_precalculos_especiales,
    )

    resumen_texto, datos_texto = construir_seccion_ventas(dashboard_mode=dashboard_mode)
    match_texto = construir_seccion_match(mensaje_usuario, nombre_usuario, memoria)
    especiales_texto = construir_precalculos_especiales(mensaje_usuario, memoria)
    clientes_texto = construir_seccion_clientes(mensaje_usuario)
    operaciones_texto = construir_seccion_operaciones()

    partes = [p for p in [
        resumen_texto,
        datos_texto,
        match_texto,
        especiales_texto,
        clientes_texto,
        operaciones_texto,
    ] if p]

    return "\n\n".join(partes)
```

---

## PASO 5 — Verificar imports

```bash
python -c "
import sys, types

for mod, attrs in [
    ('config', {'COLOMBIA_TZ': None, 'claude_client': None}),
    ('db', {'DB_DISPONIBLE': False, 'query_one': lambda *a: None, 'query_all': lambda *a: []}),
    ('memoria', {
        'cargar_memoria': lambda: {},
        'cargar_inventario': lambda: {},
        'cargar_gastos_hoy': lambda: [],
        'obtener_resumen_caja': lambda: {},
        'buscar_producto_en_catalogo': lambda x: None,
        'buscar_multiples_en_catalogo': lambda *a: [],
        'buscar_multiples_con_alias': lambda *a: [],
    }),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items(): setattr(m, k, v)
        sys.modules[mod] = m

from ai.prompt_context import construir_seccion_ventas, construir_seccion_clientes, construir_seccion_operaciones
from ai.prompt_products import construir_seccion_match, construir_precalculos_especiales
from ai.prompts import _construir_parte_dinamica
print('prompts OK')
"
```

---

## PASO 6 — Crear tests/test_prompt_context.py

```python
"""
tests/test_prompt_context.py — Tests básicos para ai/prompt_context.py y ai/prompt_products.py.
"""
import sys
import types

for mod, attrs in [
    ("config", {"COLOMBIA_TZ": None, "claude_client": None}),
    ("db", {"DB_DISPONIBLE": False, "query_one": lambda *a: None, "query_all": lambda *a: []}),
    ("memoria", {
        "cargar_memoria": lambda: {},
        "cargar_inventario": lambda: {},
        "cargar_gastos_hoy": lambda: [],
        "obtener_resumen_caja": lambda: {},
        "buscar_producto_en_catalogo": lambda x: None,
        "buscar_multiples_en_catalogo": lambda *a: [],
        "buscar_multiples_con_alias": lambda *a: [],
    }),
]:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        for k, v in attrs.items(): setattr(m, k, v)
        sys.modules[mod] = m

# Stub ai con los helpers que prompt_context importa lazy
if "ai" not in sys.modules:
    import os as _os
    _ai = types.ModuleType("ai")
    _ai.__path__ = [_os.path.abspath("ai")]
    _ai.__package__ = "ai"
    _ai._pg_resumen_ventas = lambda: None
    _ai._pg_todos_los_datos = lambda limite=300: []
    _ai._pg_clientes_recientes = lambda limite=5: []
    _ai._pg_buscar_cliente = lambda termino: (None, [])
    _ai._get_precios_recientes_activos = lambda: {}
    sys.modules["ai"] = _ai


def test_construir_seccion_ventas_sin_db():
    """Sin DB → retorna tupla de strings vacíos sin explotar."""
    from ai.prompt_context import construir_seccion_ventas
    resumen, datos = construir_seccion_ventas()
    assert isinstance(resumen, str)
    assert isinstance(datos, str)


def test_construir_seccion_ventas_dashboard_mode():
    """dashboard_mode=True no explota."""
    from ai.prompt_context import construir_seccion_ventas
    resumen, datos = construir_seccion_ventas(dashboard_mode=True)
    assert isinstance(resumen, str)


def test_construir_seccion_operaciones_sin_db():
    """Sin DB → retorna string (vacío o con fallback)."""
    from ai.prompt_context import construir_seccion_operaciones
    resultado = construir_seccion_operaciones()
    assert isinstance(resultado, str)


def test_construir_seccion_clientes_mensaje_vacio():
    """Mensaje vacío → no explota."""
    from ai.prompt_context import construir_seccion_clientes
    resultado = construir_seccion_clientes("")
    assert isinstance(resultado, str)


def test_construir_seccion_clientes_con_termino():
    """Mensaje con nombre → no explota aunque no haya resultados."""
    from ai.prompt_context import construir_seccion_clientes
    resultado = construir_seccion_clientes("buscar cliente juan perez")
    assert isinstance(resultado, str)


def test_construir_seccion_match_catalogo_vacio():
    """Catálogo vacío en memoria → retorna string (puede ser vacío)."""
    from ai.prompt_products import construir_seccion_match
    resultado = construir_seccion_match("quiero tornillos", "vendedor", {})
    assert isinstance(resultado, str)


def test_construir_precalculos_especiales_sin_mensaje():
    """Mensaje vacío → no explota."""
    from ai.prompt_products import construir_precalculos_especiales
    resultado = construir_precalculos_especiales("", {})
    assert isinstance(resultado, str)


def test_construir_parte_dinamica_orquesta():
    """El orquestador ensambla partes sin error."""
    from ai.prompts import _construir_parte_dinamica
    resultado = _construir_parte_dinamica("vender tornillos", "vendedor", {})
    assert isinstance(resultado, str)
```

---

## PASO 7 — Correr tests

```bash
pytest tests/test_prompt_context.py -v --tb=short
pytest tests/ -x -q --tb=short
```

---

## PASO 8 — Verificar reducción de líneas

```bash
wc -l ai/prompts.py ai/prompt_context.py ai/prompt_products.py
# prompts.py target: ≤400 (antes: 1370)
# prompt_context.py: ~300
# prompt_products.py: ~700
```

---

## Criterio de éxito
- `ai/prompt_context.py` con 3 funciones, imports lazy
- `ai/prompt_products.py` con 2 funciones, imports lazy
- `ai/prompts.py` baja de 1370 a ≤400 líneas
- `_construir_parte_dinamica` sigue recibiendo los mismos 4 parámetros
- Ambos call sites en `ai/__init__.py` (L303 y L606) funcionan sin cambios
- `pytest tests/ -x -q` pasa en verde
