package com.ferrebot.voz.tts

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale

/**
 * Voz de salida con el TextToSpeech nativo de Android (es-CO, fallback es-ES).
 * Gratis y offline. La Fase 7 (opcional) puede cambiar a voz premium sin tocar
 * el resto del flujo: basta reemplazar esta clase.
 */
class TtsManager(context: Context) {

    private var tts: TextToSpeech? = null
    private var ready = false

    /** Se invoca cuando termina de hablar (o si falla). Lo usa el controlador para volver a IDLE. */
    var onDone: (() -> Unit)? = null

    // ── Watchdog del TTS (P0.6) ──────────────────────────────────────────────
    // onDone/onError del TextToSpeech a veces NO disparan → el loop se cuelga en
    // HABLANDO para siempre. Como red de seguridad, al hablar armamos un timeout
    // estimado por el largo del texto; si onDone real no llegó al vencer, forzamos
    // la salida. Single-fire: lo primero que ocurra (onDone real o timeout) gana y
    // cancela al otro vía el flag `pendiente`.
    private val handler = Handler(Looper.getMainLooper())
    private var watchdog: Runnable? = null
    private var pendiente = false

    init {
        tts = TextToSpeech(context.applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val res = tts?.setLanguage(Locale("es", "CO"))
                if (res == TextToSpeech.LANG_MISSING_DATA || res == TextToSpeech.LANG_NOT_SUPPORTED) {
                    tts?.setLanguage(Locale("es", "ES"))
                }
                ready = true
            }
        }
        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) {
                finalizar()
            }

            @Deprecated("Requerido por la API antigua")
            override fun onError(utteranceId: String?) {
                finalizar()
            }
        })
    }

    fun speak(text: String) {
        if (!ready || text.isBlank()) {
            onDone?.invoke()
            return
        }
        pendiente = true
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, UTTERANCE_ID)
        armarWatchdog(text)
    }

    fun stop() {
        cancelarWatchdog()
        pendiente = false   // corte manual: el controlador maneja la transición a IDLE
        tts?.stop()
    }

    fun shutdown() {
        cancelarWatchdog()
        pendiente = false
        tts?.stop()
        tts?.shutdown()
        tts = null
    }

    /**
     * Salida única del estado HABLANDO. La invoca lo PRIMERO que ocurra: el
     * onDone/onError real del TTS o el watchdog. El flag `pendiente` garantiza
     * que solo el primero dispare `onDone` (single-fire).
     */
    private fun finalizar() {
        if (!pendiente) return
        pendiente = false
        cancelarWatchdog()
        onDone?.invoke()
    }

    /** Arma el timeout de seguridad estimado por el largo del texto. */
    private fun armarWatchdog(text: String) {
        cancelarWatchdog()
        val timeout = (text.length * MS_POR_CHAR).coerceIn(WATCHDOG_PISO_MS, WATCHDOG_TECHO_MS)
        val r = Runnable { finalizar() }
        watchdog = r
        handler.postDelayed(r, timeout)
    }

    private fun cancelarWatchdog() {
        watchdog?.let { handler.removeCallbacks(it) }
        watchdog = null
    }

    private companion object {
        const val UTTERANCE_ID = "ferrevoz"
        // Estimación de duración del habla: ~90 ms/carácter (es-CO en TTS nativo),
        // acotada entre un piso y un techo para que el watchdog sea una red de
        // seguridad generosa, no un cortador prematuro de frases reales.
        const val MS_POR_CHAR = 90L
        const val WATCHDOG_PISO_MS = 3_000L
        const val WATCHDOG_TECHO_MS = 20_000L
    }
}
