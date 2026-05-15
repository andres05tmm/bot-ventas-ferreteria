# Análisis de errores de audio — semana del 10 al 16 de abril de 2026

## Resumen

- **Total de audios procesados:** No disponible — ver nota de ejecución
- **Audios con correcciones aplicadas:** No disponible
- **Errores nuevos identificados:** No disponible
- **Estado de la tarea:** ⚠️ Ejecución parcial — base de datos no accesible

---

## ⚠️ Nota de ejecución — acción requerida

La tarea programada no pudo conectarse a PostgreSQL. El error fue:

```
DATABASE_URL no configurado — DB deshabilitada
RuntimeError: ⚠️ Base de datos no disponible. Verifica DATABASE_URL y reinicia el servicio.
```

**Causa raíz:** La tarea fue originalmente configurada apuntando a la sesión `dreamy-kind-knuth`, pero se ejecutó en la sesión activa `awesome-blissful-albattani`. Las variables de entorno (incluida `DATABASE_URL`) viven en el `.env` del proyecto y solo están disponibles cuando el servidor API/Bot está corriendo en Railway, no en sesiones de Cowork locales sin el archivo `.env`.

**Acción recomendada:**

Para que esta tarea pueda acceder a la base de datos en futuras ejecuciones, hay dos opciones:

1. **Opción A — Railway CLI (recomendada):** Configurar la tarea para que corra vía `railway run python ...` usando la CLI de Railway, que inyecta las variables de entorno del proyecto automáticamente.

2. **Opción B — Archivo `.env` local:** Crear un archivo `.env` en el directorio del proyecto con `DATABASE_URL=<url>` para ejecución local. **No commitear este archivo** (ya está en `.gitignore`).

---

## Estado actual del diccionario `_CORRECCIONES_AUDIO`

El archivo `utils.py` (líneas 268–303) contiene las siguientes correcciones activas:

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

**Total:** 25 correcciones activas en 9 categorías de productos.

---

## Correcciones sugeridas para `_CORRECCIONES_AUDIO`

> ⚠️ Sin datos de `audio_logs` esta semana. Las sugerencias a continuación son candidatos **proactivos** basados en patrones fonéticos conocidos de Whisper con vocabulario de ferretería colombiana — no están respaldadas por datos de esta semana.

| Error Whisper probable | Corrección sugerida | Justificación |
|------------------------|--------------------|----|
| `angulo` | `ángulo` | Whisper omite tildes frecuentemente en palabras agudas |
| `sikaflex` | `sikaflex` | Ya correcto, pero `sicaflex` o `sica flex` podría aparecer |
| `enchape` | `enchape` | `enchappe`, `inchape` son variantes fonéticas comunes |
| `guardaescoba` | `guardaescoba` | `guarda escoba` (separado) es error frecuente de Whisper |
| `impermeabilizante` | `impermeabilizante` | `impermiabilizante`, `inpermeabilizante` |
| `masilla` | `masilla` | `macilla`, `mazilla` son variantes de Whisper |
| `estuco` | `estuco` | `estuco` vs `estuque` — revisar cuál usa el negocio |
| `galón` | `galón` | `galones` sin tilde: `galones` → correcto; `galones` → ok |

**Nota:** Estas sugerencias deben validarse contra datos reales de `audio_logs` cuando la conexión a la base de datos esté disponible.

---

## Código listo para copiar en `utils.py`

Las siguientes entradas son candidatas para agregar. **Validar contra datos reales antes de agregar** para evitar falsos positivos:

```python
# Candidatos proactivos — validar con audio_logs antes de agregar a _CORRECCIONES_AUDIO
# (Agregar dentro del diccionario en utils.py, líneas 268–303)

# Sikaflex
"sicaflex":      "sikaflex",
"sica flex":     "sikaflex",

# Guardaescoba
"guarda escoba": "guardaescoba",
"guarda escova": "guardaescoba",

# Masilla
"macilla":       "masilla",
"mazilla":       "masilla",

# Enchape
"inchape":       "enchape",
"enchappe":      "enchape",
```

---

## Patrones sin corrección automática

> Sin datos de `audio_logs` disponibles esta semana. Esta sección se completará automáticamente en la próxima ejecución exitosa con acceso a la base de datos.

---

## Top 10 productos más mencionados esta semana

> Sin datos disponibles — base de datos no accesible durante esta ejecución.

---

## Próxima ejecución

- **Fecha programada:** 23 de abril de 2026
- **Acción pendiente antes:** Verificar que `DATABASE_URL` esté accesible en el entorno de ejecución de la tarea programada.
- **Contacto:** Andrés — revisar configuración de la tarea en Cowork.

---

*Reporte generado automáticamente el 2026-04-16 por la tarea programada `audio-error-analysis-weekly`.*
