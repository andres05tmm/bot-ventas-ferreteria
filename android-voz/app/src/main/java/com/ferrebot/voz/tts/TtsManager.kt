package com.ferrebot.voz.tts

import android.content.Context
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
                onDone?.invoke()
            }

            @Deprecated("Requerido por la API antigua")
            override fun onError(utteranceId: String?) {
                onDone?.invoke()
            }
        })
    }

    fun speak(text: String) {
        if (!ready || text.isBlank()) {
            onDone?.invoke()
            return
        }
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, UTTERANCE_ID)
    }

    fun stop() {
        tts?.stop()
    }

    fun shutdown() {
        tts?.stop()
        tts?.shutdown()
        tts = null
    }

    private companion object {
        const val UTTERANCE_ID = "ferrevoz"
    }
}
