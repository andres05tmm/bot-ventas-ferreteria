# FerreVoz — App Android (asistente de voz para FerreBot)

App nativa **Kotlin + Jetpack Compose** que actúa como asistente de voz manos libres
para la ferretería: el vendedor habla y la app registra ventas/gastos/consultas
**reusando el cerebro de FerreBot por HTTP**. Objetivo: tipo Siri/Hey Google, con la
**app cerrada y pantalla bloqueada** (eso llega en la Fase 5), disparado por el botón
de un audífono Bluetooth o tocando la app.

> Subproyecto **independiente** del build de Railway. Distribución por **APK sideload**.
> Plan completo y fases: `../.planning/voz-asistente/PLAN.md`.

## Regla de oro: la IA NO se reimplementa acá
El cerebro (catálogo, registro de ventas, fuzzy match, tags `[VENTA]`) vive en el backend
Python. Esta app **solo llama endpoints**. No metas lógica de negocio en Kotlin.

## Contrato HTTP (backend FerreBot)
Base URL configurable en Ajustes (no hardcodear). Todos sin auth en v1 (JWT en Fase 7).

- `POST /chat/transcribir` — multipart campo `audio` (.m4a) → `{ ok: bool, texto: string }`.
- `POST /chat/stream` — JSON `{ mensaje, nombre, session_id, canal:"voz", historial:[{role,content}] }`
  → **SSE**, líneas `data: {json}\n\n`:
  - `{ type:"chunk", text }` — texto incremental.
  - `{ type:"done", respuesta, acciones:{ventas,gastos}, pendiente, opciones_pago, modelo }`.
  - `{ type:"error", message }`.
  - **`canal:"voz"` es obligatorio** — activa el estilo hablado (sin emojis/símbolos,
    montos en palabras, confirmación antes de registrar) en `ai/prompts.py` del backend.
- `POST /chat` — JSON `{ confirmar_pago:"efectivo|transferencia|datafono", session_id, nombre }`
  → cierra la venta pendiente. **(Fase 4.)**

## Arquitectura (módulos)
```
MainActivity            UI host Compose + permiso RECORD_AUDIO.
ui/VozScreen            Pantalla: botón mic central por estado, transcripción, respuesta, Ajustes.
ui/theme/               Tema Material 3 (rojo #C8200E Punto Rojo).
conversation/
  ConversationController ViewModel. Máquina de estados del loop + sessionId + historial.
                         IDLE→ESCUCHANDO→TRANSCRIBIENDO→PENSANDO→HABLANDO→IDLE.
audio/AudioRecorder     MediaRecorder → .m4a (AAC 16 kHz). VAD por silencio: Fase 3.
net/ApiClient           OkHttp: multipart a /chat/transcribir; SSE de /chat/stream.
tts/TtsManager          TextToSpeech nativo (es-CO). Voz premium: Fase 7 (reemplazar esta clase).
settings/SettingsStore  SharedPreferences: URL servidor + nombre vendedor.
```

## Reglas Android
- **minSdk 26**, target/compile 34. JDK 17. Kotlin 2.0.20, AGP 8.6.1, Compose BOM 2024.09.02.
- Compose puro (Material 3). No agregar la librería de Views de Material salvo necesidad real.
- Parsing/serialización JSON con `org.json` (incluido en Android) — no kotlinx-serialization.
- No grabar mientras el TTS habla (evitar auto-escucharse) — relevante en el loop de Fase 3.
- El servidor debe ser **https** (Railway lo es); no se habilita cleartext.
- Strings de UI en español.

## Estado por fase
- **Fase 2 (actual):** una vuelta manual — tocar para hablar → transcribir → /chat/stream →
  hablar la respuesta con TTS. **Hecho** (este scaffold).
- **Fase 3:** loop + VAD por silencio + barge-in + confirmación hablada.
- **Fase 4:** pago por voz (`confirmar_pago`).
- **Fase 5:** ForegroundService + MediaSession + botón del audífono (app cerrada).
  Aquí se añaden permisos FOREGROUND_SERVICE(_MICROPHONE), POST_NOTIFICATIONS,
  BLUETOOTH_CONNECT, MODIFY_AUDIO_SETTINGS y se valida el hardware del botón.
- **Fase 6:** pulido + APK + pruebas de campo. **Fase 7 (opcional):** voz premium + JWT.

## Build
Ver `README.md`. Resumen: abrir `android-voz/` en Android Studio (sync resuelve el wrapper),
poner la URL del servidor en Ajustes, conceder permiso de micrófono, Run.
