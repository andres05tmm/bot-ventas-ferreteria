package com.ferrebot.voz.conversation

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.ferrebot.voz.audio.AudioRecorder
import com.ferrebot.voz.net.ApiClient
import com.ferrebot.voz.settings.SettingsStore
import com.ferrebot.voz.tts.TtsManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID

enum class Estado { IDLE, ESCUCHANDO, TRANSCRIBIENDO, PENSANDO, HABLANDO }

data class VozUiState(
    val estado: Estado = Estado.IDLE,
    val transcripcion: String = "",
    val respuesta: String = "",
    val error: String? = null,
)

/**
 * Máquina de estados del asistente de voz (la "ConversationController" del plan).
 *   IDLE → ESCUCHANDO → TRANSCRIBIENDO → PENSANDO → HABLANDO → IDLE
 *
 * Fase 2: una vuelta manual — tocar para empezar a escuchar, tocar para enviar.
 * Mantiene `sessionId` estable e `historial` para encadenar turnos.
 * Fases siguientes: VAD por silencio (3), pago por voz (4), botón del audífono (5).
 */
class ConversationController(app: Application) : AndroidViewModel(app) {

    private val settings = SettingsStore(app)
    private val recorder = AudioRecorder(app)
    private val tts = TtsManager(app)

    private val sessionId = UUID.randomUUID().toString()
    private val historial = mutableListOf<Pair<String, String>>()  // (role, content)

    private val _ui = MutableStateFlow(VozUiState())
    val ui: StateFlow<VozUiState> = _ui.asStateFlow()

    init {
        tts.onDone = {
            // Solo volver a IDLE si seguimos en HABLANDO (evita pisar un nuevo turno).
            if (_ui.value.estado == Estado.HABLANDO) {
                _ui.value = _ui.value.copy(estado = Estado.IDLE)
            }
        }
    }

    val configurado: Boolean get() = settings.configurado

    fun urlActual(): String = settings.serverUrl
    fun vendedorActual(): String = settings.vendedor

    fun guardarAjustes(url: String, vendedor: String) {
        settings.serverUrl = url
        settings.vendedor = vendedor
    }

    /** Tap del micrófono: arranca a escuchar, o procesa lo grabado, o corta el habla. */
    fun onMicTap() {
        when (_ui.value.estado) {
            Estado.IDLE -> empezarEscucha()
            Estado.ESCUCHANDO -> procesar()
            Estado.HABLANDO -> {
                tts.stop()
                _ui.value = _ui.value.copy(estado = Estado.IDLE)
            }
            else -> { /* TRANSCRIBIENDO / PENSANDO: ocupado, ignorar */ }
        }
    }

    private fun empezarEscucha() {
        if (!settings.configurado) {
            _ui.value = _ui.value.copy(error = "Configurá la URL del servidor en Ajustes.")
            return
        }
        try {
            recorder.start()
            _ui.value = VozUiState(estado = Estado.ESCUCHANDO)
        } catch (e: Exception) {
            _ui.value = _ui.value.copy(error = "No se pudo iniciar el micrófono: ${e.message}")
        }
    }

    private fun procesar() {
        val audio = recorder.stop()
        if (audio == null) {
            _ui.value = _ui.value.copy(estado = Estado.IDLE, error = "No se grabó audio.")
            return
        }
        _ui.value = _ui.value.copy(estado = Estado.TRANSCRIBIENDO, error = null)
        viewModelScope.launch {
            try {
                val api = ApiClient(settings.serverUrl)
                val texto = withContext(Dispatchers.IO) { api.transcribir(audio) }
                audio.delete()
                if (texto.isBlank()) {
                    _ui.value = _ui.value.copy(estado = Estado.IDLE, error = "No te entendí, repetí.")
                    return@launch
                }
                _ui.value = _ui.value.copy(estado = Estado.PENSANDO, transcripcion = texto)

                val result = withContext(Dispatchers.IO) {
                    api.chatVoz(
                        mensaje = texto,
                        nombre = settings.vendedor,
                        sessionId = sessionId,
                        historial = historial.toList(),
                        onChunk = { /* Fase 3: feedback incremental hablado */ },
                    )
                }

                historial.add("user" to texto)
                historial.add("assistant" to result.respuesta)
                // Acotar el historial a los últimos 6 turnos (12 mensajes).
                while (historial.size > 12) historial.removeAt(0)

                _ui.value = _ui.value.copy(estado = Estado.HABLANDO, respuesta = result.respuesta)
                tts.speak(result.respuesta)
            } catch (e: Exception) {
                _ui.value = _ui.value.copy(estado = Estado.IDLE, error = e.message ?: "Error de red")
            }
        }
    }

    override fun onCleared() {
        recorder.cancel()
        tts.shutdown()
        super.onCleared()
    }
}
