# Fase 04 — Documentar memoria.py y resolver imports lazy de catalogo_service

## Esta fase es de 10 minutos. No requiere Claude Code.

---

## TAREA 1 — Agregar advertencia al inicio de memoria.py

Insertar esto INMEDIATAMENTE después del docstring existente (antes de `import logging`):

```python
# ═══════════════════════════════════════════════════════════════════════════════
# ⚠️  ADVERTENCIA DE ARQUITECTURA — LEER ANTES DE MODIFICAR ESTE ARCHIVO
# ═══════════════════════════════════════════════════════════════════════════════
#
# memoria.py es un THIN WRAPPER de re-export sobre los services reales.
# Existen ~151 callers de `from memoria import X` en el proyecto.
# Cambiar una firma aquí sin actualizar el service original rompe todo
# silenciosamente, sin error de importación.
#
# TABLA DE RE-EXPORTS:
#   cargar_memoria, buscar_producto_*, buscar_multiples_*,
#   obtener_precios_como_texto, obtener_info_fraccion_producto,
#   importar_catalogo_desde_excel, actualizar_precio_en_catalogo
#       → services/catalogo_service.py
#
#   cargar_inventario
#       → services/inventario_service.py
#
#   cargar_caja, guardar_gasto, obtener_resumen_caja, cargar_gastos_hoy
#       → services/caja_service.py
#
#   guardar_fiado_movimiento, abonar_fiado
#       → services/fiados_service.py
#
# MIGRACIÓN PROGRESIVA (no hacer todo de una vez):
#   Preferir importar directamente desde el service en código nuevo:
#     ✅  from services.catalogo_service import buscar_producto_en_catalogo
#     ⚠️  from memoria import buscar_producto_en_catalogo  (funciona pero oculta dependencia)
#
# ═══════════════════════════════════════════════════════════════════════════════
```

---

## TAREA 2 — Documentar los imports lazy en catalogo_service.py

En `services/catalogo_service.py`, el docstring al inicio dice:

> "cargar_memoria() se importa de forma lazy dentro de las funciones para evitar ciclo"

Agregar más contexto debajo de esa línea:

```python
# Por qué lazy y no nivel de módulo:
#   memoria.py importa a config e inicia el cliente de Claude al importarse.
#   Si catalogo_service importara memoria al nivel de módulo, cualquier test
#   que haga `import catalogo_service` necesitaría variables de entorno reales.
#   El lazy import permite mockear memoria por test sin patching complejo.
#
# El patrón correcto para tests es el stub en sys.modules (ver tests/test_catalogo_service.py).
```

---

## TAREA 3 — Agregar al CLAUDE.md el inventario de imports lazy

Ya está cubierto en la sección 1 del CLAUDE.md. No hacer nada más.

---

## Criterio de éxito

- `memoria.py` tiene el bloque de advertencia visible al inicio
- `catalogo_service.py` tiene el comentario explicando por qué los imports son lazy
- `git diff --stat` muestra solo cambios en esos dos archivos
- `python -c "import memoria; import services.catalogo_service"` pasa

## Commit

```bash
git add memoria.py services/catalogo_service.py
git commit -m "docs(memoria): documentar patrón thin-wrapper y razón de imports lazy

- Advertencia visible con tabla de re-exports en memoria.py
- Explicación del patrón lazy import en catalogo_service.py
- Sin cambios funcionales"
```
