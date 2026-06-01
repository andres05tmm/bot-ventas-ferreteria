# Asistente de voz tipo Siri para FerreBot — App nativa Android (Kotlin)

> Plan liviano (sin GSD multi-agente). Se trabaja fase por fase, inline.
> Commits por avance. `python test_suite.py` antes de cerrar cada fase de backend.

## Objetivos máximos (toda decisión se mide contra esto)
1. **Manos libres con pantalla bloqueada** — hablar al asistente como Siri/Hey Google, app cerrada.
2. **Precisión muy alta** — transcripción + confirmación hablada antes de registrar.
3. **Rapidez considerable** — más rápido que sacar el celular y escribir.

## Decisiones tomadas
- **Plataforma:** solo Android (iOS no deja interceptar el botón del audífono ni escuchar en background).
- **Construcción:** app nativa **Kotlin**, en `android-voz/` dentro del repo (independiente del build de Railway, distribución por APK sideload).
- **Disparador:** botón del audífono Bluetooth (principal) + abrir la app (alternativa manual). Validación del hardware: fase posterior, no bloquea las tempranas.
- **El cerebro NO se reimplementa en Kotlin:** la app llama por HTTP a los endpoints que ya usa el dashboard.
- **Metodología:** plan liviano en markdown, sin GSD pesado (costo de tokens) ni superpowers (es metodología, no aporta código).

## Canal de voz `##VOZ##` (clave del diseño)
El bot responde para pantalla (emojis, markdown, `$4.000`, botones). Por TTS eso suena pésimo.
Solución: tercer canal `##VOZ##` (junto a `##DASHBOARD##`/`##BOT##`) con persona hablada:
frases cortas, cero símbolos, montos en palabras, confirmación hablada antes de registrar,
desambiguación activa, método de pago entendido hablado. No toca bot ni dashboard.

## Contrato HTTP (lo que consumirá la app Kotlin)
- `POST /chat/transcribir` — audio → Whisper español (con vocabulario de ferretería) → `{ok, texto}`. Sin auth.
- `POST /chat/stream` — cerebro completo vía SSE. Body `{mensaje, nombre, historial, session_id, tab_activo, modelo_preferido, canal:"voz"}`; emite `chunk` y `done` con `{respuesta, acciones, pendiente, opciones_pago, modelo}`.
- `POST /chat` con `confirmar_pago` — cierra la venta pendiente (`efectivo|transferencia|datafono`). Estado por `session_id`.

---

## Fases

### Fase 1 — Backend: canal de voz `##VOZ##` + Whisper afinado  ✅ (en cierre)
- [x] `VOZ_INSTRUCCIONES` en `ai/prompts.py` (estilo hablado, confirmación previa).
- [x] Detección `##VOZ##` + skip bypass en `ai/__init__.py` (sync y stream).
- [x] Modelo en voz: **auto-router** (`_elegir_modelo`), no Sonnet forzado. El costo por turno es ínfimo (Whisper domina); la precisión la da la confirmación hablada. Medir en campo y subir a Sonnet solo si Haiku falla.
- [x] Campo `canal` + inyección `##VOZ##` en `/chat` y `/chat/stream`.
- [x] Texto de venta pendiente sin emojis/`$` en voz.
- [x] Vocabulario de ferretería a Whisper en `/chat/transcribir` (reusa `_build_whisper_prompt`).
- [ ] Verificación por curl + `python test_suite.py` (regresión bot/dashboard).

### Fase 2 — App Kotlin, una vuelta manual  ⏳ (scaffold hecho, falta build en device)
`MainActivity` + botón "tocar para hablar" → grabar → `/chat/transcribir` → `/chat/stream` (`canal:"voz"`) → hablar la respuesta (TTS `es-CO`). Crear `android-voz/CLAUDE.md`.
- [x] Proyecto Android en `android-voz/`: Compose + Material 3, minSdk 26 / target 34, Kotlin 2.0.20 / AGP 8.6.1.
- [x] Módulos: `MainActivity`, `ui/VozScreen` (+tema), `conversation/ConversationController` (máquina de estados), `audio/AudioRecorder` (m4a), `net/ApiClient` (OkHttp + SSE), `tts/TtsManager` (TTS nativo es-CO), `settings/SettingsStore` (URL configurable).
- [x] `android-voz/CLAUDE.md` + `README.md` (instrucciones de build/sideload).
- [x] Abrir en Android Studio, sync Gradle OK, **corrida en celular real** (wireless debugging).
- [x] E2E validado: "dame un kilo de acronal" → transcribe bien → reconoce producto → dice total y pide método hablando. ✅
- Nota: el build/compilación se verifica en Android Studio (esta repo no tiene SDK Android).

### Fase 3 — Loop conversacional + VAD  ⏳ (hecho, falta probar en device)
Corte por silencio, reanudar escucha al terminar de hablar, frases de control, confirmación hablada antes de registrar.
- [x] VAD por energía (`MediaRecorder.getMaxAmplitude()`): corta solo al dejar de hablar (UMBRAL_VOZ / SILENCIO_MS tunables).
- [x] Loop manos libres: tras responder (TTS done) reanuda la escucha sola; silencio inicial cierra el loop.
- [x] Palabras de parada ("para/cancela/chao/…") + tap para detener.
- [x] Toggle "Manos libres" en la UI (off = modo manual de Fase 2, tap para enviar).
- [ ] Barge-in (interrumpir hablando encima) — DIFERIDO (riesgo de eco; grabar mientras suena el TTS).
- [ ] Probar en device: los umbrales del VAD pueden requerir ajuste según micrófono/ruido del local.

### Capacidades del asistente (= cerebro del chat `/chat/stream`)
Hoy por charla natural: **ventas, gastos, fiados, abonos, consultas/reportes**. NO soporta aún:
- **Crear cliente**: wizard solo del bot Telegram (`cliente_flujo.py`); el chat emite `INICIAR_FLUJO_CLIENTE` pero los pasos no están cableados fuera del bot. → futura **Fase 4.5**.
- **Emitir factura electrónica DIAN**: NO expuesto en el cerebro (a propósito — legal/sensible). → futura **Fase 8** con doble confirmación hablada obligatoria.

### Robustez del cerebro (en curso) — decisiones
- **Modelo:** auto-router Haiku/Sonnet (NO Sonnet fijo — costo). Tool-calling hace a Haiku confiable.
- **RAG (hecho):** SOLO el útil → búsqueda **semántica del catálogo** como *fallback* del fuzzy. `ai/semantic_catalog.py`: embeddings OpenAI (`text-embedding-3-small`), índice en RAM sin base vectorial, se reconstruye solo si cambian los NOMBRES (firma). Cero costo/latencia en el caso común (solo embebe la query cuando el léxico+fuzzy ya fallaron). Fail-safe (cualquier error→None). Solo SUGIERE ("¿Quisiste decir X?") cableado en el riel R2 de existencia — no auto-corrige (desincronizaría la prosa). Flag `IA_SEMANTIC_CATALOGO` (default ON, apagable). 12 tests en `tests/test_semantic_catalog.py`. NO un RAG genérico de "conocimiento" (redundante con el prompt). Umbral coseno 0.45 — tunear en campo.
- **Tool-calling (hecho):** `ai/tools.py` ahora tiene `registrar_venta/gasto/fiado/abono` con descripciones claras (resuelve misclasificación tipo "gasto→venta"). Se activa para VOZ siempre (`config.IA_TOOL_CALLING or _voz_mode`), sin tocar el flag global (bot/dashboard intactos). **La voz ahora rutea por `POST /chat` (no-stream)** porque el tool-calling solo vive en ese path; la app habla la respuesta completa igual.
- **R1 (hecho):** prompt de voz DELGADO — `VOZ_REGLAS` (compacto) reemplaza los ~16k de skills del bot (core/precios_base/granel/thinner). Vía `solo_voz=_voz_mode` en `_construir_parte_estatica/_dinamica` (default False → bot/dashboard intactos). Conserva catálogo + MATCH de productos (con `⚠️ AMBIGUO`).
- **R2 (núcleo hecho):** detección determinista de ambigüedad habilitada para voz (`config.IA_TOOL_CALLING or _voz_mode` en el short-circuit). El prompt delgado además exige "no inventes producto/precio; ante ambigüedad preguntá".
- **R2 existencia (hecho):** `ai/tools.py::ventas_con_producto_desconocido` — si un producto no resuelve ni con fuzzy, no se registra y se pregunta hablado (commit `db80bdd`).
- **R2 precio (hecho):** `ai/tools.py::ventas_con_precio_dudoso` — riel scoped a voz. Si el vendedor NO declaró precio (campo nuevo `precio_declarado` en el schema de `registrar_venta`) y el `total` que puso Claude NO cuadra con `obtener_precio_para_cantidad` (catálogo×cantidad, respeta fracciones/granel, tolerancia 1%), es alucinación de precio: NO se registra, se confirma hablado con el precio real ("Para un kilo de acronal el precio es 8000. ¿Lo registro así o el precio es otro?"). NO se auto-corrige porque la prosa hablada de Claude ya dijo el monto → quedaría desincronizada. Corre tras la existencia (solo productos conocidos). 12 tests nuevos en `tests/test_ai_tools.py`. Se recupera solo en el siguiente turno (el vendedor confirma o corrige). Falta probar en device.
- **Pendiente:** confirmar-antes-de-registrar en gasto/fiado/abono, normalización de transcripción (`_normalizar_con_haiku`), afinar VAD.

### Fase 4 — Pago por voz  ✅ (hecho, falta confirmar E2E en device)
Detectar `pendiente`, preguntar método, entender efectivo/transferencia/datáfono, confirmar vía `/chat` (`confirmar_pago`).
- [x] App: estado `esperandoPago`; el turno siguiente a una venta pendiente se parsea como método y va a `/chat` con `confirmar_pago` (no a `/chat/stream`).
- [x] App: `parsearMetodo` (efectivo/transferencia/datáfono); si no reconoce, re-pregunta hablando.
- [x] Backend: rama `confirmar_pago` con `canal:"voz"` responde hablada ("Listo, venta registrada en efectivo"), sin emojis ni `$`.
- [ ] Confirmar E2E: registrar venta completa por voz (producto → método → "venta registrada").

### Fase 5 — Foreground service + botón del audífono
`VozForegroundService` + `MediaSessionCompat`: disparo con app cerrada / pantalla apagada. Notificación persistente, audio focus, exención de batería. **Aquí se valida el hardware del botón** (riesgo: audífonos que mandan el botón directo a Google Assistant por firmware; manejar `KEYCODE_HEADSETHOOK` explícito).

### Fase 6 — Pulido + despliegue
Ajustes, permisos/errores, build de APK, pruebas de campo (ruido del local, multiproducto).

### Fase 7 — (Opcional) Voz premium + auth
`POST /chat/synthesize` (OpenAI TTS/ElevenLabs) + JWT por vendedor (habilita RBAC y budget por `vendedor_id`).

---

## Verificación
- **Fase 1:** curl con `canal:"voz"` → respuesta sin emojis/markdown/símbolos, frases habladas, números en palabras, confirmación antes de registrar. Audios con "drywall/thinner/puntillas" a `/chat/transcribir` (antes/después del vocabulario).
- **E2E Android (Fases 2-4):** "dos bultos de cemento" → transcribe, lee de vuelta, registra al confirmar, pide y entiende método por voz.
- **Cruce dashboard:** la venta por voz aparece en tiempo real (`venta_registrada`).
- **Background (Fase 5):** pantalla apagada 10+ min, botón del audífono, responde.
- **Regresión:** `python test_suite.py`. Cambios aditivos — bot y dashboard responden igual.
- **NO tocar numeración DIAN ni endpoints fiscales.**
