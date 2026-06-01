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

### Fase 2 — App Kotlin, una vuelta manual
`MainActivity` + botón "tocar para hablar" → grabar → `/chat/transcribir` → `/chat/stream` (`canal:"voz"`) → hablar la respuesta (TTS `es-CO`). Crear `android-voz/CLAUDE.md`.

### Fase 3 — Loop conversacional + VAD
Corte por silencio, reanudar escucha al terminar de hablar, barge-in, frases de control ("para/cancela/listo"), confirmación hablada antes de registrar. No grabar mientras habla el TTS.

### Fase 4 — Pago por voz
Detectar `pendiente`, preguntar método, entender efectivo/transferencia/datáfono, confirmar vía `/chat` (`confirmar_pago`).

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
