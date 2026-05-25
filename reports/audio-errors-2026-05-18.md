# Análisis de errores de audio — semana del 12 al 18 de mayo de 2026

## Resumen

- **Total de audios procesados:** No disponible — ver nota de ejecución
- **Audios con correcciones aplicadas:** No disponible
- **Errores nuevos identificados:** No disponible
- **Estado de la tarea:** 🔴 Ejecución parcial — base de datos no accesible (**SEXTA semana consecutiva**)

---

## 🔴 ALERTA CRÍTICA — Sexta semana consecutiva sin datos reales

La tarea programada no pudo conectarse a PostgreSQL. El error fue:

```
DATABASE_URL no configurado — DB deshabilitada
RuntimeError: ⚠️ Base de datos no disponible. Verifica DATABASE_URL y reinicia el servicio.
```

**Esta es la SEXTA semana consecutiva con el mismo error** (ocurrencias: 2026-04-16, 2026-04-21, 2026-04-27, 2026-05-04, 2026-05-11, 2026-05-18).

**El análisis de audio lleva más de mes y medio sin datos reales.** Las sugerencias acumuladas siguen sin validación estadística.

**⚠️ Adicionalmente: ninguna de las ~41 correcciones sugeridas en semanas anteriores ha sido aplicada al diccionario `_CORRECCIONES_AUDIO` en `utils.py`.** El código permanece sin cambios respecto a las 25 entradas originales.

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

#### Opción B — Pausar la tarea hasta resolver el acceso

Si el `.env` local no es viable, considerar pausar esta tarea programada y reemplazarla por un análisis manual mensual ejecutado directamente desde Railway.

---

## Estado actual del diccionario `_CORRECCIONES_AUDIO`

El archivo `utils.py` contiene las mismas **25 correcciones originales**. **Ninguna corrección sugerida en las semanas anteriores ha sido aplicada.**

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

> ⚠️ Sin datos reales de `audio_logs` por sexta semana consecutiva. Todas las sugerencias son de naturaleza fonética/analítica sin validación estadística.

### 🔴 Alta prioridad — 6 semanas pendientes (APLICAR O DESCARTAR HOY)

Estas sugerencias llevan 6 semanas sin validación. Se recomienda que Andrés aplique o descarte cada una directamente:

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

### 🟡 Prioridad media — acumuladas semanas 2–5

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
| `istuco` | `estuco` | Whisper usa I pretónica por hipercorrección |
| `espatola` | `espátula` | Deformación italiana que Whisper puede aplicar |
| `licha` | `lija` | CH por J — error fonético frecuente en español |
| `ochapado` | `ochavado` | Confusión V→P en terminación |
| `interrutor` | `interruptor` | Whisper simplifica grupos consonánticos RR |
| `toma corriente` | `tomacorriente` | Whisper separa el compuesto |
| `cable duplex` | `cable dúplex` | Whisper omite tilde en palabra técnica |
| `breiker` | `breaker` | Whisper transcribe fonética española del anglicismo |
| `brequer` | `breaker` | Variante alternativa con fonética española |
| `taipe` | `tape` | Transcripción española del anglicismo (cinta de enmascarar) |

### 🟢 Nuevas sugerencias esta semana (semana 6)

Enfocadas en ferretería de plomería y acabados de piso — categorías con alta densidad de términos técnicos no cubiertos:

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `ceramica` | `cerámica` | Whisper omite tildes consistentemente |
| `porcelanato` | `porcelanato` | Correcto, pero `porcenato` puede aparecer |
| `porcenato` | `porcelanato` | Síncopa del grupo consonántico `lan` |
| `tulipan` | `tulipa` | Whisper añade N final (hipercorrección) |
| `maselina` | `vaselina` | M/V intercambio — error frecuente |
| `vaselina` | `vaselina` | Correcto — verificar si aparece como `baselina` |
| `baselina` | `vaselina` | B/V intercambio castellano estándar |
| `llave de paso` | `llave de paso` | Correcto; `yave de paso` puede aparecer |
| `yave de paso` | `llave de paso` | Yeísmo + LL→Y |
| `bushin` | `buje` | Anglicismo que Whisper puede transcribir así |
| `empaque` | `empaque` | Correcto; `inpaque` puede aparecer |
| `inpaque` | `empaque` | E→I en sílaba pretónica |
| `caucho` | `caucho` | Correcto; `cauchos` OK. `cauccho` puede aparecer |
| `cauccho` | `caucho` | Doble C por hipercorrección |
| `teflon` | `teflón` | Falta tilde en anglicismo técnico |
| `codo de noventa` | `codo 90°` | Descripción oral del fitting — no necesita dict, sino normalización |

---

## Código listo para copiar en `utils.py`

### Bloque de alta prioridad (6 semanas — aplicar ahora)

```python
# Agregar a _CORRECCIONES_AUDIO en utils.py
# ── Alta prioridad — 6 semanas pendiente de validación ──

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

### Bloque de prioridad media

```python
# ── Prioridad media — acumuladas semanas 2–5 ──

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

# PVC oral
"pbc":               "PVC",

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

### Bloque nuevas sugerencias semana 6

```python
# ── Nuevas sugerencias 2026-05-18 — requieren validación real ──

# Porcelanato
"porcenato":         "porcelanato",

# Tulipa
"tulipan":           "tulipa",

# Vaselina
"maselina":          "vaselina",
"baselina":          "vaselina",

# Llave de paso
"yave de paso":      "llave de paso",

# Empaque
"inpaque":           "empaque",

# Caucho
"cauccho":           "caucho",

# Teflón
"teflon":            "teflón",
```

---

## Patrones sin corrección automática

| Patrón problemático | Razón | Solución sugerida |
|---|---|---|
| Frases con espacios (`"guarda escoba"`, `"sica flex"`) | `\b` en Python funciona con espacios dentro de la frase | Sin acción — el dict ya las soporta |
| Siglas habladas (`"pvc"` → `"PVC"`) | El reemplazo con `IGNORECASE` no capitaliza la salida | Requiere lógica `upper()` post-reemplazo |
| Cantidades con unidades pegadas (`"3metros"`) | Whisper a veces omite el espacio | `normalizar_numeros_audio()` no cubre este caso |
| Descripciones de fittings (`"codo de noventa"`) | Expresión oral que no mapea a producto directamente | Normalización post-corrección, no diccionario |
| Marcas con guion (`"pre-mezclado"`) | Whisper puede transcribir `"premezclado"` o `"pre mezclado"` | Agregar ambas variantes al dict |

---

## Top 10 productos más mencionados esta semana

> Sin datos disponibles — base de datos no accesible durante esta ejecución.

---

## Historial de ejecuciones

| Semana | Fecha | Estado | DB accesible | Correcciones aplicadas |
|--------|-------|--------|---|---|
| 1 | 2026-04-16 | ⚠️ Parcial | ❌ No | ❌ Pendiente |
| 2 | 2026-04-21 | ⚠️ Parcial | ❌ No | ❌ Pendiente |
| 3 | 2026-04-27 | 🔴 Parcial | ❌ No | ❌ Pendiente |
| 4 | 2026-05-04 | 🔴 Parcial | ❌ No | ❌ Pendiente |
| 5 | 2026-05-11 | 🔴 Parcial | ❌ No | ❌ Pendiente |
| 6 | 2026-05-18 | 🔴 Parcial | ❌ No | ❌ Pendiente |

---

## Próxima ejecución

- **Fecha programada:** 25 de mayo de 2026
- **Acción crítica:** Crear `.env` con `DATABASE_URL` o pausar la tarea — **6 semanas sin datos reales**.
- **Sugerencias acumuladas sin aplicar:** ~49 entradas en tres niveles de prioridad.
- **Recomendación:** Si el `.env` no se crea antes del 25 de mayo, **considerar pausar esta tarea** y reemplazarla por una revisión manual trimestral. El costo de oportunidad (1 hora/semana de tiempo de IA sin valor real) supera el beneficio de seguir generando sugerencias sin validación.

---

*Reporte generado automáticamente el 2026-05-18 por la tarea programada `audio-error-analysis-weekly`.*
