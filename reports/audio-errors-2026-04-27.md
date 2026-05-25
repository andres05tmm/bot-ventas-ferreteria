# Análisis de errores de audio — semana del 21 al 27 de abril de 2026

## Resumen

- **Total de audios procesados:** No disponible — ver nota de ejecución
- **Audios con correcciones aplicadas:** No disponible
- **Errores nuevos identificados:** No disponible
- **Estado de la tarea:** 🔴 Ejecución parcial — base de datos no accesible (**tercera semana consecutiva**)

---

## 🔴 Nota de ejecución — acción requerida (CRÍTICO)

La tarea programada no pudo conectarse a PostgreSQL. El error fue:

```
DATABASE_URL no configurado — DB deshabilitada
RuntimeError: ⚠️ Base de datos no disponible. Verifica DATABASE_URL y reinicia el servicio.
```

**Esta es la tercera semana consecutiva con el mismo error** (ocurrencias anteriores: 2026-04-16, 2026-04-21). Cada semana que pasa sin datos reales, el diccionario `_CORRECCIONES_AUDIO` pierde cobertura ante errores nuevos de Whisper.

**Causa raíz:** Las variables de entorno de Railway, incluyendo `DATABASE_URL`, no están disponibles en el entorno de sesión de Cowork. El bot y la API las obtienen directamente de Railway en el despliegue, pero las tareas programadas de Cowork corren en un entorno aislado sin acceso a esas variables.

**Dos opciones para resolver (pendientes desde la semana del 16 de abril):**

### Opción A — Archivo `.env` local (más rápida, ~2 minutos)

1. Ir al panel de Railway → proyecto FerreBot → Variables
2. Copiar el valor de `DATABASE_URL`
3. Crear el archivo `bot-ventas-ferreteria/.env` con el contenido:
   ```
   DATABASE_URL=postgres://...
   ```
4. El archivo ya está en `.gitignore` — no se subirá al repo

### Opción B — Railway CLI (más robusta)

Modificar la tarea programada para ejecutar vía:
```bash
railway run python3 /ruta/al/script/analisis_audio.py
```
La CLI de Railway inyecta automáticamente todas las variables del proyecto en tiempo de ejecución.

**⚠️ Sin resolver una de estas opciones, esta tarea seguirá generando reportes vacíos indefinidamente.**

---

## Estado actual del diccionario `_CORRECCIONES_AUDIO`

El archivo `utils.py` (líneas 268–303) contiene las siguientes **25 correcciones activas** (sin cambios desde el primer reporte del 2026-04-16):

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

---

## Correcciones sugeridas para `_CORRECCIONES_AUDIO`

> ⚠️ Sin datos reales de `audio_logs` por tercera semana. Las sugerencias son **candidatos fonéticos proactivos** para vocabulario de ferretería colombiana.
>
> Las sugerencias de las semanas anteriores se priorizan aún más al acumularse sin validación.

### 🔴 Alta prioridad (tres semanas sin validar — aplicar o descartar manualmente)

Las siguientes sugerencias fueron generadas el 2026-04-16 y repetidas el 2026-04-21. Con tres semanas de acumulación, se recomienda que Andrés las evalúe directamente y decida cuáles aplicar basándose en el uso real del bot:

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `sicaflex` | `sikaflex` | Ortografía fonética española de marca Sika |
| `sica flex` | `sikaflex` | Whisper segmenta la marca en dos palabras |
| `guarda escoba` | `guardaescoba` | Whisper separa compuestos; muy común en ferretería |
| `guarda escova` | `guardaescoba` | Variante fonética de la separación anterior |
| `macilla` | `masilla` | S→C es error fonético frecuente de Whisper en español |
| `mazilla` | `masilla` | Z→S alternativa igualmente frecuente |
| `inchape` | `enchape` | Apertura vocálica E→I es error típico de Whisper |
| `enchappe` | `enchape` | Doble P por transliteración fonética |

### 🟡 Prioridad media (sugeridas semana anterior — pendientes de validación)

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `tornio` | `tornillo` | Whisper omite la L en grupos consonánticos `ll` |
| `torniyo` | `tornillo` | Yeísmo colombiano → `y` por `ll` |
| `crabos` | `clavos` | BL→BR, frecuente con acento regional |
| `impermiabilizante` | `impermeabilizante` | Síncopa de la vocal media E |
| `inpermeabilizante` | `impermeabilizante` | Alternancia I/E en prefijos latinos |
| `cemento vlanco` | `cemento blanco` | V/B intercambio con acento colombiano |
| `waya` | `guaya` | Whisper usa fonética inglesa para GU+A |
| `yave inglesa` | `llave inglesa` | LL→Y (yeísmo) aplicado por Whisper |
| `polidora` | `pulidora` | O/U intercambio en sílaba átona |

### 🟢 Nuevas sugerencias esta semana

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `angulo` | `ángulo` | Whisper omite tildes en agudas/esdrújulas de ferretería |
| `angulos` | `ángulos` | Plural del anterior |
| `niple` | `niple` | Ya correcto; `nipple` (inglés) puede aparecer |
| `nipple` | `niple` | Whisper usa ortografía inglesa para este término |
| `tanke` | `tanque` | Simplificación fonética de "qu" |
| `tanque` | `tanque` | Correcto — `tanke` es la variante problemática |
| `platina` | `platina` | Correcto; `platyna` puede aparecer |
| `platyna` | `platina` | Y por I, común con Whisper en español |
| `varilla` | `varilla` | Correcto; `variya` puede aparecer |
| `variya` | `varilla` | LL→Y por yeísmo |
| `machuelo` | `machuelo` | Correcto; `machelo` sin U puede aparecer |
| `machelo` | `machuelo` | Omisión de U en grupos CU |

---

## Código listo para copiar en `utils.py`

### Bloque de alta prioridad (semana 3 — evaluar e implementar)

```python
# Agregar a _CORRECCIONES_AUDIO en utils.py (entre líneas 268–303)
# ── Alta prioridad — 3 semanas pendiente de validación ──

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
# ── Prioridad media — sugeridas semana anterior, validar con audio_logs ──

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

### Bloque de nuevas sugerencias (requieren validación)

```python
# ── Nuevas sugerencias 2026-04-27 — requieren validación real ──

# Niple
"nipple":            "niple",

# Tanque
"tanke":             "tanque",

# Platina
"platyna":           "platina",

# Varilla
"variya":            "varilla",

# Machuelo
"machelo":           "machuelo",
```

---

## Patrones sin corrección automática

Patrones que el regex de `\b` (word boundary) no puede capturar correctamente, o que requieren lógica adicional:

| Patrón problemático | Razón | Solución sugerida |
|---|---|---|
| `"sica flex"`, `"guarda escoba"`, `"cemento vlanco"`, `"yave inglesa"` | Frases con espacio — el dict ya las soporta pero el `\b` de `corregir_texto_audio()` puede fallar en frases | El código usa `re.sub(rf'\b{error}\b', ...)` — para frases con espacios el `\b` en la palabra interna funciona correctamente en Python |
| Nombres de vendedores propios | Whisper a veces transcribe "Andrés" como "Andrea" o "Andres" — no corregible con dict | Requeriría post-proceso separado |
| Números en fracciones habladas | Ya cubiertos por `normalizar_numeros_audio()` | Sin acción requerida |

---

## Top 10 productos más mencionados esta semana

> Sin datos disponibles — base de datos no accesible durante esta ejecución.
> **Acción:** Resolver `DATABASE_URL` para obtener este dato la próxima semana.

---

## Historial de ejecuciones

| Fecha | Estado | DB accesible | Sugerencias alta prioridad aplicadas |
|---|---|---|---|
| 2026-04-16 | ⚠️ Parcial | ❌ No | ❌ Pendiente |
| 2026-04-21 | ⚠️ Parcial | ❌ No | ❌ Pendiente |
| 2026-04-27 | 🔴 Parcial | ❌ No | ❌ Pendiente |

---

## Próxima ejecución

- **Fecha programada:** 4 de mayo de 2026
- **Acción crítica pendiente:** Resolver acceso a `DATABASE_URL` (ver sección "Nota de ejecución" arriba) — **3 semanas consecutivas sin datos reales**.
- **Si se resuelve el acceso:** El análisis real de `audio_logs` validará o descartará las 17 correcciones sugeridas acumuladas en estas tres semanas.

---

*Reporte generado automáticamente el 2026-04-27 por la tarea programada `audio-error-analysis-weekly`.*
