# Análisis de errores de audio — semana del 14 al 21 de abril de 2026

## Resumen

- **Total de audios procesados:** No disponible — ver nota de ejecución
- **Audios con correcciones aplicadas:** No disponible
- **Errores nuevos identificados:** No disponible
- **Estado de la tarea:** ⚠️ Ejecución parcial — base de datos no accesible (segunda semana consecutiva)

---

## ⚠️ Nota de ejecución — acción requerida (URGENTE)

La tarea programada no pudo conectarse a PostgreSQL. El error fue:

```
DATABASE_URL no configurado — DB deshabilitada
RuntimeError: ⚠️ Base de datos no disponible. Verifica DATABASE_URL y reinicia el servicio.
```

**Causa raíz:** Esta es la **segunda semana consecutiva** con el mismo error (primera ocurrencia: 2026-04-16). Las variables de entorno de Railway, incluyendo `DATABASE_URL`, no están disponibles en el entorno de sesión de Cowork. El bot y la API las obtienen directamente de Railway en el despliegue, pero las tareas programadas de Cowork corren en un entorno aislado sin acceso a esas variables.

**Acción recomendada (pendiente desde semana anterior):**

Hay dos caminos para resolver esto definitivamente:

1. **Opción A — Railway CLI (recomendada):** Modificar la tarea programada para que ejecute vía `railway run python ...` usando la CLI de Railway, que inyecta automáticamente todas las variables del proyecto.

2. **Opción B — Archivo `.env` local:** Crear un `.env` en la raíz del proyecto con `DATABASE_URL=<postgres_url>`. Este archivo ya está en `.gitignore`. Andrés puede obtener la URL desde el panel de Railway → Variables → `DATABASE_URL`.

**⚠️ Sin resolver, esta tarea seguirá generando reportes vacíos indefinidamente.**

---

## Estado actual del diccionario `_CORRECCIONES_AUDIO`

No hubo cambios al diccionario desde el último reporte (2026-04-16). El archivo `utils.py` (líneas 268–303) contiene las siguientes **25 correcciones activas**:

| Categoría | Error Whisper | Corrección |
|-----------|--------------|------------|
| Drywall | `driver` | `drywall` |
| Drywall | `draiul` | `drywall` |
| Drywall | `draibol` | `drywall` |
| Drywall | `draiwall` | `drywall` |
| Drywall | `draiuol` | `drywall` |
| Drywall | `graihol` | `drywall` |
| Thinner | `tiner` | `thinner` |
| Thinner | `tinner` | `thinner` |
| Boxer | `boser` | `boxer` |
| Boxer | `vocel` | `boxer` |
| Boxer | `bocel` | `boxer` |
| Boxer | `bóxer` | `boxer` |
| Bisagra | `bisara` | `bisagra` |
| Bisagra | `visagra` | `bisagra` |
| Bisagra | `bisarga` | `bisagra` |
| Puntilla | `pontilla` | `puntilla` |
| Puntilla | `puntia` | `puntilla` |
| Sellador | `cejador` | `sellador` |
| Sellador | `sejador` | `sellador` |
| Segueta | `cegueta` | `segueta` |
| Segueta | `sagueta` | `segueta` |
| Chazos | `dos hechazos` | `doce chazos` |
| Chazos | `hechazos` | `chazos` |
| Latecol | `la tecol` | `latecol` |
| Latecol | `latecoll` | `latecol` |

**Nota:** Las sugerencias de la semana anterior (`sicaflex`, `guarda escoba`, `macilla`, `inchape`) **no fueron aplicadas** aún — están pendientes de validación contra datos reales.

---

## Correcciones sugeridas para `_CORRECCIONES_AUDIO`

> ⚠️ Sin datos de `audio_logs` esta semana. Las sugerencias son **candidatos proactivos** basados en patrones fonéticos conocidos de Whisper con vocabulario de ferretería colombiana.
> Las sugerencias de la semana anterior se repiten con mayor prioridad por acumulación.

### Alta prioridad (segunda semana sin validar — implementar con cautela)

| Error Whisper probable | Corrección sugerida | Justificación | Semanas pendiente |
|------------------------|--------------------|----|---|
| `sicaflex` | `sikaflex` | Ocurre cuando Whisper sigue ortografía fonética española | 2ª |
| `sica flex` | `sikaflex` | Whisper segmenta marca compuesta en dos palabras | 2ª |
| `guarda escoba` | `guardaescoba` | Whisper separa compuestos; muy común en ferretería | 2ª |
| `guarda escova` | `guardaescoba` | Variante fonética de la separación anterior | 2ª |
| `macilla` | `masilla` | S→C es error fonético frecuente de Whisper en español | 2ª |
| `mazilla` | `masilla` | Z→S es alternativa fonética igualmente frecuente | 2ª |
| `inchape` | `enchape` | Apertura vocálica E→I es error típico de Whisper | 2ª |
| `enchappe` | `enchape` | Doble P es error de transliteración fonética | 2ª |

### Nuevas sugerencias esta semana

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `tornio` | `tornillo` | Whisper omite la L en grupos consonánticos `ll` |
| `tornillo` | `tornillo` | Correcto, pero `tornio`, `torniyo` son variantes comunes |
| `torniya` | `tornilla` | Yeísmo colombiano → Whisper escribe `y` por `ll` |
| `clavos` | `clavos` | Correcto; `crabos`, `clavoz` son variantes posibles de Whisper |
| `crabos` | `clavos` | BL→BR es error frecuente de Whisper con acento regional |
| `impermiabilizante` | `impermeabilizante` | Síncopa de la vocal media E |
| `inpermeabilizante` | `impermeabilizante` | Alternancia I/E en prefijos latinos |
| `cemento blanco` | `cemento blanco` | Correcto; `cemento vlanco` puede aparecer |
| `cemento vlanco` | `cemento blanco` | V/B intercambio, frecuente en Whisper con acento colombiano |
| `guaya` | `guaya` | Correcto; `waya` es la versión anglófona |
| `waya` | `guaya` | Whisper usa fonética inglesa para palabras con GU+A |
| `llave inglesa` | `llave inglesa` | Correcto; `yave inglesa` puede aparecer |
| `yave inglesa` | `llave inglesa` | LL→Y (yeísmo) aplicado por Whisper |
| `espatula` | `espátula` | Whisper omite la tilde en paroxítonas |
| `espatula` | `espátula` | Mismo error sin tilde |
| `pulidora` | `pulidora` | Correcto; `polidora` puede aparecer |
| `polidora` | `pulidora` | O/U intercambio en sílaba átona |

---

## Código listo para copiar en `utils.py`

### Bloque de alta prioridad (semana 2 — considerar agregar)

```python
# Agregar a _CORRECCIONES_AUDIO en utils.py (líneas 268–303)
# ── Alta prioridad — sin validar 2 semanas, aplicar con cautela ──

# Sikaflex
"sicaflex":          "sikaflex",
"sica flex":         "sikaflex",

# Guardaescoba
"guarda escoba":     "guardaescoba",
"guarda escova":     "guardaescoba",

# Masilla
"macilla":           "masilla",
"mazilla":           "masilla",

# Enchape
"inchape":           "enchape",
"enchappe":          "enchape",
```

### Bloque de nuevas sugerencias (validar primero)

```python
# ── Nuevas sugerencias 2026-04-21 — validar con audio_logs antes de agregar ──

# Tornillo
"tornio":            "tornillo",
"torniyo":           "tornillo",
"torniya":           "tornilla",

# Clavos
"crabos":            "clavos",

# Impermeabilizante
"impermiabilizante": "impermeabilizante",
"inpermeabilizante": "impermeabilizante",

# Cemento
"cemento vlanco":    "cemento blanco",

# Guaya
"waya":              "guaya",

# Llave inglesa
"yave inglesa":      "llave inglesa",

# Pulidora
"polidora":          "pulidora",
```

---

## Patrones sin corrección automática

Sin datos de `audio_logs` disponibles. Los siguientes patrones son candidatos que **el regex de `\b` (word boundary) no atrapará** correctamente y pueden requerir lógica diferente:

| Patrón problemático | Razón | Solución sugerida |
|---|---|---|
| `"sica flex"` | Dos palabras — `\bsica flex\b` funciona, pero debe estar en el dict sin `\b` especial | Agregar como frase exacta — el código ya maneja frases con espacios |
| `"guarda escoba"` | Ídem — frase con espacio | Agregar como frase exacta |
| `"cemento vlanco"` | Ídem | Agregar como frase exacta |
| `"yave inglesa"` | Ídem | Agregar como frase exacta |
| Números hablados + producto | "dos metros y medio de guaya" → la función `normalizar_numeros_audio()` ya lo maneja | Sin acción requerida |

---

## Top 10 productos más mencionados esta semana

> Sin datos disponibles — base de datos no accesible durante esta ejecución.

---

## Historial de ejecuciones

| Fecha | Estado | DB accesible | Correcciones sugeridas aplicadas |
|---|---|---|---|
| 2026-04-16 | ⚠️ Parcial | ❌ No | ❌ Pendiente |
| 2026-04-21 | ⚠️ Parcial | ❌ No | ❌ Pendiente |

---

## Próxima ejecución

- **Fecha programada:** 28 de abril de 2026
- **Acción crítica pendiente:** Resolver acceso a `DATABASE_URL` antes de la próxima ejecución (ver sección "Nota de ejecución" arriba).
- **Si se resuelve el acceso:** El reporte de la semana siguiente contendrá datos reales y las sugerencias proactivas se validarán o descartarán según frecuencia real.

---

*Reporte generado automáticamente el 2026-04-21 por la tarea programada `audio-error-analysis-weekly`.*
