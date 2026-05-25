# Análisis de errores de audio — semana del 5 al 11 de mayo de 2026

## Resumen

- **Total de audios procesados:** No disponible — ver nota de ejecución
- **Audios con correcciones aplicadas:** No disponible
- **Errores nuevos identificados:** No disponible
- **Estado de la tarea:** 🔴 Ejecución parcial — base de datos no accesible (**QUINTA semana consecutiva**)

---

## 🔴 ALERTA CRÍTICA — Quinta semana consecutiva sin datos reales

La tarea programada no pudo conectarse a PostgreSQL. El error fue:

```
DATABASE_URL no configurado — DB deshabilitada
RuntimeError: ⚠️ Base de datos no disponible. Verifica DATABASE_URL y reinicia el servicio.
```

**Esta es la QUINTA semana consecutiva con el mismo error** (ocurrencias: 2026-04-16, 2026-04-21, 2026-04-27, 2026-05-04, 2026-05-11).

**El análisis de audio lleva más de un mes sin datos reales.** Las sugerencias acumuladas son exclusivamente de naturaleza fonética/analítica, sin validación estadística contra los `audio_logs` de producción.

**Causa raíz:** Las variables de entorno de Railway no están disponibles en el entorno de sesión de Cowork. El bot y la API obtienen `DATABASE_URL` directamente de Railway en el despliegue, pero las tareas programadas corren en un entorno aislado sin acceso a esas variables.

### ⚠️ Resolución requerida — dos opciones

#### Opción A — Archivo `.env` local (más rápida, ~2 minutos)

1. Ir al panel de Railway → proyecto FerreBot → Variables
2. Copiar el valor de `DATABASE_URL`
3. Crear el archivo `bot-ventas-ferreteria/.env` con:
   ```
   DATABASE_URL=postgres://...
   ```
4. El archivo ya está en `.gitignore` — no se subirá al repo

#### Opción B — Railway CLI

Modificar la tarea para ejecutar vía:
```bash
railway run python3 /ruta/al/script/analisis_audio.py
```
La CLI de Railway inyecta automáticamente todas las variables del proyecto.

**Una vez resuelto, el primer reporte real validará o descartará las ~40 correcciones sugeridas acumuladas durante estas 5 semanas.**

---

## Estado actual del diccionario `_CORRECCIONES_AUDIO`

El archivo `utils.py` contiene las siguientes **25 correcciones activas**. Sin cambios confirmados desde el primer reporte (no es posible verificar si se aplicaron correcciones sugeridas sin acceso a git diff):

| Categoría | Error Whisper | Corrección |
|-----------|--------------|------------|
| Drywall | `driver`, `draiul`, `draibol`, `draiwall`, `draiuol`, `graihol` | `drywall` |
| Thinner | `tiner`, `tinner` | `thinner` |
| Boxer | `boser`, `vocel`, `bocel`, `bóxer` | `boxer` |
| Bisagra | `bisara`, `visagra`, `bisarga` | `bisagra` |
| Puntilla | `pontilla`, `puntia` | `puntilla` |
| Sellador | `cejador`, `sejador` | `sellador` |
| Segueta | `cegueta`, `sagueta` | `segueta` |
| Chazos | `dos hechazos`, `hechazos` | `doce chazos`, `chazos` |
| Latecol | `la tecol`, `latecoll` | `latecol` |

---

## Correcciones sugeridas para `_CORRECCIONES_AUDIO`

> ⚠️ Sin datos reales de `audio_logs` por quinta semana. Sugerencias de naturaleza fonética únicamente.
> Las sugerencias de semanas anteriores se conservan acumuladas. Aplicar o descartar manualmente.

### 🔴 Alta prioridad — 5 semanas pendientes (APLICAR O DESCARTAR HOY)

Estas sugerencias llevan 5 semanas sin validación estadística. Se recomienda que Andrés evalúe directamente si alguna ha aparecido en audios del bot:

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `sicaflex` | `sikaflex` | Fonética española de marca Sika |
| `sica flex` | `sikaflex` | Whisper segmenta la marca en dos palabras |
| `guarda escoba` | `guardaescoba` | Compuesto que Whisper separa frecuentemente |
| `guarda escova` | `guardaescoba` | Variante fonética de la separación anterior |
| `macilla` | `masilla` | S→C es error fonético frecuente de Whisper en español |
| `mazilla` | `masilla` | Z→S alternativa igualmente frecuente |
| `inchape` | `enchape` | Apertura vocálica E→I típica de Whisper |
| `enchappe` | `enchape` | Doble P por transliteración fonética |

### 🟡 Prioridad media — acumuladas semanas 2–4

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `tornio` | `tornillo` | Whisper omite la LL en grupos consonánticos |
| `torniyo` | `tornillo` | Yeísmo colombiano → `y` por `ll` |
| `crabos` | `clavos` | BL→BR con acento regional |
| `impermiabilizante` | `impermeabilizante` | Síncopa de la vocal media E |
| `inpermeabilizante` | `impermeabilizante` | Alternancia I/E en prefijos latinos |
| `cemento vlanco` | `cemento blanco` | V/B intercambio con acento colombiano |
| `waya` | `guaya` | Whisper usa fonética inglesa para GU+A |
| `yave inglesa` | `llave inglesa` | LL→Y (yeísmo) aplicado por Whisper |
| `polidora` | `pulidora` | O/U intercambio en sílaba átona |
| `tinplador` | `templador` | E→I en sílaba átona |
| `mortedo` | `mortero` | R final → D por asimilación |
| `ismalte` | `esmalte` | E→I en sílaba pretónica |
| `flange` | `flanche` | Whisper usa término inglés para este fitting |
| `vuje` | `buje` | B/V intercambio |
| `neplo` | `niple` | Transcripción alternativa por acento regional |
| `pbc` | `PVC` | Whisper confunde V con B en la sigla oral |

### 🟢 Nuevas sugerencias esta semana (semana 5)

Enfocadas en materiales de acabado y eléctricos — categorías con nombres técnicos de alta probabilidad de error:

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `estuco` | `estuco` | Correcto; `istuco` puede aparecer |
| `istuco` | `estuco` | Whisper usa I pretónica por hipercorrección |
| `espátula` | `espátula` | Correcto; `espantula` / `espatola` pueden aparecer |
| `espatola` | `espátula` | Deformación italiana que Whisper puede aplicar |
| `lija grano` | `lija grano` | Correcto pero `licha grano` puede aparecer |
| `licha` | `lija` | CH por J — error fonético muy frecuente de Whisper en español |
| `ochavado` | `ochavado` | Correcto; `ochapado` puede aparecer |
| `ochapado` | `ochavado` | Confusión V→P en terminación |
| `interruptor` | `interruptor` | Correcto; `interrutor` (doble R omitida) puede aparecer |
| `interrutor` | `interruptor` | Whisper simplifica grupos consonánticos RR |
| `toma corriente` | `tomacorriente` | Whisper separa el compuesto |
| `tomacorriente` | `tomacorriente` | Ya correcto — verificar si el bypass lo entiende unido |
| `cable dúplex` | `cable dúplex` | Correcto; `cable duplex` (sin tilde) puede aparecer |
| `cable duplex` | `cable dúplex` | Whisper omite tilde en palabra técnica |
| `breiker` | `breaker` | Whisper transcribe fonética española del anglicismo |
| `brequer` | `breaker` | Variante alternativa con fonética española |
| `taipe` | `tape` | Transcripción española del anglicismo (cinta de enmascarar) |

---

## Código listo para copiar en `utils.py`

### Bloque de alta prioridad (5 semanas — evaluar e implementar ya)

```python
# Agregar a _CORRECCIONES_AUDIO en utils.py
# ── Alta prioridad — 5 semanas pendiente de validación ──

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

### Bloque de prioridad media (validar antes de agregar)

```python
# ── Prioridad media — acumuladas semanas 2–4 ──

# Tornillo
"tornio":            "tornillo",
"torniyo":           "tornillo",

# Clavos
"crabos":            "clavos",

# Impermeabilizante
"impermiabilizante": "impermeabilizante",
"inpermeabilizante": "impermeabilizante",

# Cemento blanco
"cemento vlanco":    "cemento blanco",

# Guaya
"waya":              "guaya",

# Llave inglesa
"yave inglesa":      "llave inglesa",

# Pulidora
"polidora":          "pulidora",

# Templador
"tinplador":         "templador",

# Mortero
"mortedo":           "mortero",

# Esmalte
"ismalte":           "esmalte",

# Flanche
"flange":            "flanche",

# Buje
"vuje":              "buje",

# Niple
"neplo":             "niple",
"nipple":            "niple",

# PVC oral
"pbc":               "PVC",
```

### Bloque de nuevas sugerencias semana 5

```python
# ── Nuevas sugerencias 2026-05-11 — requieren validación real ──

# Estuco
"istuco":            "estuco",

# Espátula
"espatola":          "espátula",

# Lija
"licha":             "lija",

# Ochavado
"ochapado":          "ochavado",

# Interruptor
"interrutor":        "interruptor",

# Tomacorriente
"toma corriente":    "tomacorriente",

# Cable dúplex
"cable duplex":      "cable dúplex",

# Breaker
"breiker":           "breaker",
"brequer":           "breaker",

# Tape
"taipe":             "tape",
```

---

## Patrones sin corrección automática

| Patrón problemático | Razón | Solución sugerida |
|---|---|---|
| Frases con espacios (`"guarda escoba"`, `"sica flex"`) | `\b` en Python funciona con espacios dentro de la frase | Sin acción — el dict ya las soporta |
| Siglas habladas (`"pvc"` → `"PVC"`) | El reemplazo con `IGNORECASE` no capitaliza la salida | Requiere lógica `upper()` post-reemplazo |
| Cantidades con unidades pegadas (`"3metros"`) | Whisper a veces omite el espacio | `normalizar_numeros_audio()` no cubre este caso |
| Marcas con guion (`"pre-mezclado"`) | Whisper puede transcribir `"premezclado"` o `"pre mezclado"` | Agregar ambas variantes al dict |
| Números de referencia de tornillos (`"6 por 1"`, `"6x1"`) | Whisper transcribe `"seis por uno"` — cubierto por `normalizar_numeros_audio()` | Sin acción — ya cubierto |

---

## Top 10 productos más mencionados esta semana

> Sin datos disponibles — base de datos no accesible durante esta ejecución.

---

## Historial de ejecuciones

| Semana | Fecha | Estado | DB accesible | Sugerencias alta prioridad aplicadas |
|--------|-------|--------|---|---|
| 1 | 2026-04-16 | ⚠️ Parcial | ❌ No | ❌ Pendiente |
| 2 | 2026-04-21 | ⚠️ Parcial | ❌ No | ❌ Pendiente |
| 3 | 2026-04-27 | 🔴 Parcial | ❌ No | ❌ Pendiente |
| 4 | 2026-05-04 | 🔴 Parcial | ❌ No | ❌ Pendiente |
| 5 | 2026-05-11 | 🔴 Parcial | ❌ No | ❌ Pendiente |

---

## Próxima ejecución

- **Fecha programada:** 18 de mayo de 2026
- **Acción crítica:** Resolver `DATABASE_URL` (ver sección arriba) — **5 semanas sin datos reales**.
- **Sugerencias acumuladas sin validar:** ~41 entradas en tres niveles de prioridad.
- **Recomendación:** Considerar pausar esta tarea programada hasta que el acceso a la base de datos esté resuelto, o implementar un canal alternativo (Railway CLI, endpoint API propio) para obtener los logs sin depender del entorno de Cowork.

---

*Reporte generado automáticamente el 2026-05-11 por la tarea programada `audio-error-analysis-weekly`.*
