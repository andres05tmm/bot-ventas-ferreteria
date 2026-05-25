# Análisis de errores de audio — semana del 28 de abril al 4 de mayo de 2026

## Resumen

- **Total de audios procesados:** No disponible — ver nota de ejecución
- **Audios con correcciones aplicadas:** No disponible
- **Errores nuevos identificados:** No disponible
- **Estado de la tarea:** 🔴 Ejecución parcial — base de datos no accesible (**CUARTA semana consecutiva**)

---

## 🔴 ALERTA CRÍTICA — Cuarta semana consecutiva sin datos reales

La tarea programada no pudo conectarse a PostgreSQL. El error fue:

```
DATABASE_URL no configurado — DB deshabilitada
RuntimeError: ⚠️ Base de datos no disponible. Verifica DATABASE_URL y reinicia el servicio.
```

**Esta es la CUARTA semana consecutiva con el mismo error** (ocurrencias: 2026-04-16, 2026-04-21, 2026-04-27, 2026-05-04).

**El análisis de audio lleva un mes sin datos reales.** Las sugerencias de este reporte son exclusivamente de naturaleza fonética/analítica, sin validación estadística de los `audio_logs` de producción. El valor de esta tarea programada se está degradando semana a semana.

**Causa raíz:** Las variables de entorno de Railway no están disponibles en el entorno de sesión de Cowork. El bot y la API obtienen `DATABASE_URL` directamente de Railway en el despliegue, pero las tareas programadas corren en un entorno aislado sin acceso a esas variables.

### ⚠️ Resolución requerida — dos opciones (sin cambios desde semana 1)

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

**Una vez resuelto, el primer reporte real validará o descartará las ~25 correcciones sugeridas acumuladas durante estas 4 semanas.**

---

## Estado actual del diccionario `_CORRECCIONES_AUDIO`

El archivo `utils.py` (líneas 268–303) contiene las siguientes **25 correcciones activas**, sin cambios desde el primer reporte:

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

> ⚠️ Sin datos reales de `audio_logs` por cuarta semana. Sugerencias de naturaleza fonética únicamente.

### 🔴 Alta prioridad — 4 semanas pendientes (APLICAR O DESCARTAR MANUALMENTE)

Estas sugerencias llevan 4 semanas sin validación estadística. Se recomienda que Andrés evalúe directamente en el chat del bot si alguna de estas variantes ha aparecido en audios recientes:

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `sicaflex` | `sikaflex` | Fonética española de marca Sika — muy probable en ferretería |
| `sica flex` | `sikaflex` | Whisper segmenta la marca en dos palabras |
| `guarda escoba` | `guardaescoba` | Compuesto que Whisper separa frecuentemente |
| `guarda escova` | `guardaescoba` | Variante fonética de la separación anterior |
| `macilla` | `masilla` | S→C es error fonético frecuente de Whisper en español |
| `mazilla` | `masilla` | Z→S alternativa igualmente frecuente |
| `inchape` | `enchape` | Apertura vocálica E→I típica de Whisper |
| `enchappe` | `enchape` | Doble P por transliteración fonética |

### 🟡 Prioridad media — acumuladas semanas 2–3

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

### 🟢 Nuevas sugerencias esta semana (semana 4)

Productos de ferretería con alta probabilidad de error por ser nombres técnicos o de marca poco comunes en corpus de entrenamiento de Whisper:

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `anclaje quimico` | `anclaje químico` | Whisper omite tilde en "químico" |
| `ancla quimica` | `ancla química` | Variante sin tilde |
| `templador` | `templador` | Correcto; `tinplador` puede aparecer |
| `tinplador` | `templador` | E→I en sílaba átona |
| `mortero` | `mortero` | Correcto; `mortedo` puede aparecer |
| `mortedo` | `mortero` | R final → D por asimilación |
| `esmalte` | `esmalte` | Correcto; `ismalte` puede aparecer |
| `ismalte` | `esmalte` | E→I en sílaba pretónica |
| `flanche` | `flanche` | Correcto; `flange` (inglés) puede aparecer |
| `flange` | `flanche` | Whisper usa término inglés para este fitting |
| `buje` | `buje` | Correcto; `vuje` puede aparecer |
| `vuje` | `buje` | B/V intercambio |
| `neplo` | `niple` | Transcripción alternativa por acento regional |
| `tuberia pvc` | `tubería PVC` | Whisper no capitaliza siglas |
| `pbc` | `PVC` | Whisper confunde V con B en la sigla oral |

---

## Código listo para copiar en `utils.py`

### Bloque de alta prioridad (4 semanas — evaluar e implementar)

```python
# Agregar a _CORRECCIONES_AUDIO en utils.py (entre líneas 268–303)
# ── Alta prioridad — 4 semanas pendiente de validación ──

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
# ── Prioridad media — acumuladas semanas 2–3, validar con audio_logs ──

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
```

### Bloque de nuevas sugerencias semana 4

```python
# ── Nuevas sugerencias 2026-05-04 — requieren validación real ──

# Anclaje químico
"anclaje quimico":   "anclaje químico",
"ancla quimica":     "ancla química",

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

# Niple (variante adicional)
"neplo":             "niple",
"nipple":            "niple",

# PVC oral
"pbc":               "PVC",
```

---

## Patrones sin corrección automática

| Patrón problemático | Razón | Solución sugerida |
|---|---|---|
| Frases con espacios (`"guarda escoba"`, `"sica flex"`, etc.) | `\b` en Python funciona correctamente con espacios dentro de la frase | Sin acción — el dict actual ya las soporta |
| Siglas habladas (`"pvc"` → `"PVC"`) | El reemplazo con `IGNORECASE` puede no capitalizar la salida | Requiere lógica de `upper()` post-reemplazo |
| Cantidades con unidades pegadas (`"3metros"`) | Whisper a veces omite el espacio | `normalizar_numeros_audio()` no cubre este caso |
| Marcas con guion (`"pre-mezclado"`) | Whisper puede transcribir `"premezclado"` o `"pre mezclado"` | Agregar ambas variantes al dict |

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

---

## Próxima ejecución

- **Fecha programada:** 11 de mayo de 2026
- **Acción crítica:** Resolver `DATABASE_URL` (ver sección arriba) — **4 semanas sin datos reales**.
- **Sugerencias acumuladas sin validar:** ~32 entradas en tres niveles de prioridad.

---

*Reporte generado automáticamente el 2026-05-04 por la tarea programada `audio-error-analysis-weekly`.*
