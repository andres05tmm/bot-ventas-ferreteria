package com.ferrebot.voz.conversation

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.ferrebot.voz.audio.AudioRecorder
import com.ferrebot.voz.net.ApiClient
import com.ferrebot.voz.settings.SettingsStore
import com.ferrebot.voz.tts.TtsManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID

enum class Estado { IDLE, ESCUCHANDO, TRANSCRIBIENDO, PENSANDO, HABLANDO }

data class VozUiState(
    val estado: Estado = Estado.IDLE,
    val transcripcion: String = "",
    val respuesta: String = "",
    val error: String? = null,
    val manosLibres: Boolean = true,
)

/**
 * Máquina de estados del asistente de voz (la "ConversationController" del plan).
 *   IDLE → ESCUCHANDO → TRANSCRIBIENDO → PENSANDO → HABLANDO → (loop / IDLE)
 *
 * Fase 2: una vuelta manual.
 * Fase 3: manos libres — VAD por silencio (corta solo al dejar de hablar),
 *   reanuda la escucha tras responder, y palabras de parada ("para/cancela/chao").
 * Fase 4: pago por voz (esperandoPago → /chat confirmar_pago).
 *
 * Mantiene `sessionId` estable e `historial` para encadenar turnos.
 */
class ConversationController(app: Application) : AndroidViewModel(app) {

    private val settings = SettingsStore(app)
    private val recorder = AudioRecorder(app)
    private val tts = TtsManager(app)

    // sessionId estable entre reinicios (P0.2): lo provee SettingsStore respaldado
    // por SharedPreferences, no un UUID nuevo por arranque. Evita que el server
    // deje huérfana una venta pendiente bajo una llave vieja tras reiniciar la app.
    private val sessionId = settings.sessionId
    // turn_id: UUID por utterance (telemetría P0.1). Se regenera en cada
    // empezarEscucha() — incluso en los reintentos por silencio — y se reusa para
    // TODAS las llamadas de esa utterance (transcribir, chatVoz, confirmarPago).
    private var turnId: String = ""
    private val historial = mutableListOf<Pair<String, String>>()  // (role, content)
    private var esperandoPago = false   // Fase 4: el próximo turno es el método de pago
    private var intentosVacios = 0      // blancos seguidos (silencio) en manos libres

    private var loopActivo = false      // modo manos libres en curso
    private var vadJob: Job? = null
    private var turnoJob: Job? = null

    private val _ui = MutableStateFlow(VozUiState())
    val ui: StateFlow<VozUiState> = _ui.asStateFlow()

    init {
        tts.onDone = { onTtsTermino() }
    }

    val configurado: Boolean get() = settings.configurado
    fun urlActual(): String = settings.serverUrl
    fun vendedorActual(): String = settings.vendedor

    fun guardarAjustes(url: String, vendedor: String) {
        settings.serverUrl = url
        settings.vendedor = vendedor
    }

    fun toggleManosLibres() {
        _ui.value = _ui.value.copy(manosLibres = !_ui.value.manosLibres)
    }

    /**
     * P0.3: al iniciar/reanudar, preguntar al server si quedó una venta esperando
     * pago para este sessionId (estable entre reinicios, P0.2). Si la hay, restaura
     * el estado "esperando pago" y lo avisa por voz, de modo que el próximo turno
     * (en manos libres, tras hablar) sea el método de pago. Recupera ventas que se
     * perdían al cerrar/reabrir la app o si el server de Railway se reinició.
     *
     * Best-effort: si no hay red, server caído o no hay pendiente, no hace nada.
     * No interrumpe un turno en curso (solo actúa desde IDLE).
     */
    fun verificarPendiente() {
        if (!settings.configurado) return
        if (_ui.value.estado != Estado.IDLE) return
        viewModelScope.launch {
            val pend = try {
                withContext(Dispatchers.IO) {
                    ApiClient(settings.serverUrl).consultarPendiente(sessionId)
                }
            } catch (e: Exception) {
                null
            }
            if (pend == null || !pend.pendiente) return@launch
            // Re-chequear tras el await: si el usuario ya arrancó un turno, no pisar.
            if (_ui.value.estado != Estado.IDLE) return@launch
            esperandoPago = true
            loopActivo = _ui.value.manosLibres
            intentosVacios = 0
            val aviso = "Tenés una venta pendiente: ${pend.resumen}. ¿Cómo pagás?"
            _ui.value = _ui.value.copy(estado = Estado.HABLANDO, respuesta = aviso, error = null)
            tts.speak(aviso)
        }
    }

    /** Tap del micrófono. */
    fun onMicTap() {
        when (_ui.value.estado) {
            Estado.IDLE -> iniciarTurno()
            Estado.ESCUCHANDO ->
                // Manos libres: el tap detiene todo el loop. Manual: envía ya.
                if (_ui.value.manosLibres) detener() else { cancelarVad(); procesar() }
            Estado.HABLANDO -> detener()   // cortar la voz
            else -> { /* TRANSCRIBIENDO / PENSANDO: ocupado */ }
        }
    }

    /** Detiene por completo (manual o por palabra de parada). */
    private fun detener() {
        loopActivo = false
        cancelarVad()
        recorder.cancel()
        tts.stop()
        _ui.value = _ui.value.copy(estado = Estado.IDLE)
    }

    private fun iniciarTurno() {
        if (!settings.configurado) {
            _ui.value = _ui.value.copy(error = "Configurá la URL del servidor en Ajustes.")
            return
        }
        loopActivo = _ui.value.manosLibres   // en manos libres el loop sigue tras responder
        intentosVacios = 0
        empezarEscucha()
    }

    private fun empezarEscucha() {
        // Nuevo turn_id por utterance: correlaciona la fila de /chat/transcribir
        // con la de /chat de este mismo turno (P0.1).
        turnId = UUID.randomUUID().toString()
        try {
            recorder.start()
            _ui.value = _ui.value.copy(
                estado = Estado.ESCUCHANDO, error = null, transcripcion = "", respuesta = "",
            )
            // El VAD (corte automático por silencio) solo en manos libres.
            // En manual, el usuario toca para enviar.
            if (_ui.value.manosLibres) iniciarVad()
        } catch (e: Exception) {
            loopActivo = false
            _ui.value = _ui.value.copy(estado = Estado.IDLE, error = "No se pudo iniciar el micrófono: ${e.message}")
        }
    }

    /**
     * VAD por energía: corta cuando el usuario deja de hablar.
     * - Detecta inicio de voz (amplitud > UMBRAL).
     * - Tras voz, si hay SILENCIO_MS de silencio → procesa.
     * - Si nadie habla en ESPERA_INICIAL_MS → termina el loop (silencio = fin).
     * - Tope duro MAX_GRABACION_MS.
     */
    private fun iniciarVad() {
        cancelarVad()
        vadJob = viewModelScope.launch {
            val inicio = System.currentTimeMillis()
            var huboVoz = false
            var ultimaVozTs = inicio
            var vozSeguida = 0        // muestras consecutivas por encima del umbral
            recorder.maxAmplitude()   // descartar primer sample (suele ser 0)
            while (isActive && _ui.value.estado == Estado.ESCUCHANDO) {
                delay(POLL_MS)
                val amp = recorder.maxAmplitude()
                val ahora = System.currentTimeMillis()
                // Para EMPEZAR a contar voz exigir sonido SOSTENIDO (varias muestras):
                // un clic/eco transitorio del TTS no debe contar como voz y disparar
                // una grabación que Whisper luego alucina. Ya hablando, cualquier pico cuenta.
                if (amp > UMBRAL_VOZ) {
                    if (huboVoz) {
                        ultimaVozTs = ahora
                    } else {
                        vozSeguida++
                        if (vozSeguida >= VOZ_MIN_MUESTRAS) {
                            huboVoz = true
                            ultimaVozTs = ahora
                        }
                    }
                } else if (!huboVoz) {
                    vozSeguida = 0
                }
                when {
                    huboVoz && ahora - ultimaVozTs > SILENCIO_MS -> { procesar(); return@launch }
                    !huboVoz && ahora - inicio > ESPERA_INICIAL_MS -> {
                        // Silencio total → cerrar el loop sin ruido.
                        recorder.cancel()
                        loopActivo = false
                        _ui.value = _ui.value.copy(estado = Estado.IDLE)
                        return@launch
                    }
                    ahora - inicio > MAX_GRABACION_MS -> { procesar(); return@launch }
                }
            }
        }
    }

    private fun cancelarVad() {
        vadJob?.cancel()
        vadJob = null
    }

    private fun procesar() {
        cancelarVad()
        val audio = recorder.stop()
        if (audio == null) {
            loopActivo = false
            _ui.value = _ui.value.copy(estado = Estado.IDLE, error = "No se grabó audio.")
            return
        }
        _ui.value = _ui.value.copy(estado = Estado.TRANSCRIBIENDO, error = null)
        turnoJob = viewModelScope.launch {
            try {
                val api = ApiClient(settings.serverUrl)
                // turn_id de esta utterance: el mismo para transcribir y para la
                // llamada de /chat que dispare (chatVoz o confirmarPago).
                val turnoId = turnId
                val texto = withContext(Dispatchers.IO) { api.transcribir(audio, turnoId) }
                audio.delete()

                if (texto.isBlank()) {
                    // Vacío = el backend descartó silencio/alucinación (o no hubo voz).
                    // En manos libres NO matamos el loop por un blanco: reanudamos la
                    // escucha (acotado, para no machacar Whisper si hay ruido constante).
                    if (loopActivo && intentosVacios < MAX_VACIOS) {
                        intentosVacios++
                        empezarEscucha()
                    } else {
                        finalizarSinLoop(error = "No te entendí, repetí.")
                    }
                    return@launch
                }
                intentosVacios = 0   // hubo texto real
                if (esPalabraDeParada(texto)) {
                    detener()
                    return@launch
                }

                // ── Fase 4: confirmar método de pago ──
                if (esperandoPago) {
                    val metodo = parsearMetodo(texto)
                    if (metodo == null) {
                        val aviso = "No te entendí el método. Decí efectivo, transferencia o datáfono."
                        _ui.value = _ui.value.copy(estado = Estado.HABLANDO, transcripcion = texto, respuesta = aviso)
                        tts.speak(aviso)   // sigue esperando el método
                        return@launch
                    }
                    _ui.value = _ui.value.copy(estado = Estado.PENSANDO, transcripcion = texto)
                    val result = withContext(Dispatchers.IO) {
                        api.confirmarPago(metodo, settings.vendedor, sessionId, turnoId)
                    }
                    esperandoPago = false
                    recordarTurno(texto, result.respuesta)
                    _ui.value = _ui.value.copy(estado = Estado.HABLANDO, respuesta = result.respuesta)
                    tts.speak(result.respuesta)
                    return@launch
                }

                // ── Turno normal ──
                _ui.value = _ui.value.copy(estado = Estado.PENSANDO, transcripcion = texto)
                val result = withContext(Dispatchers.IO) {
                    api.chatVoz(
                        mensaje = texto,
                        nombre = settings.vendedor,
                        sessionId = sessionId,
                        turnId = turnoId,
                        historial = historial.toList(),
                        onChunk = { /* feedback incremental opcional */ },
                    )
                }
                recordarTurno(texto, result.respuesta)
                esperandoPago = result.pendiente
                _ui.value = _ui.value.copy(estado = Estado.HABLANDO, respuesta = result.respuesta)
                tts.speak(result.respuesta)
            } catch (e: Exception) {
                finalizarSinLoop(error = e.message ?: "Error de red")
            }
        }
    }

    /** Tras terminar de hablar: reanuda la escucha si el loop sigue activo. */
    private fun onTtsTermino() {
        if (_ui.value.estado != Estado.HABLANDO) return
        if (loopActivo) empezarEscucha()
        else _ui.value = _ui.value.copy(estado = Estado.IDLE)
    }

    private fun finalizarSinLoop(error: String) {
        loopActivo = false
        _ui.value = _ui.value.copy(estado = Estado.IDLE, error = error)
    }

    private fun recordarTurno(usuario: String, asistente: String) {
        historial.add("user" to usuario)
        historial.add("assistant" to asistente)
        while (historial.size > 12) historial.removeAt(0)
    }

    /** Interpreta el método de pago dicho por voz. Null si no lo reconoce. */
    private fun parsearMetodo(texto: String): String? {
        val t = texto.lowercase()
        return when {
            "efectiv" in t -> "efectivo"
            "transfer" in t -> "transferencia"
            "datafon" in t || "dataf" in t || "tarjet" in t -> "datafono"
            else -> null
        }
    }

    /** Frases cortas que cierran el asistente. */
    private fun esPalabraDeParada(texto: String): Boolean {
        val t = texto.trim().lowercase().trimEnd('.', ',', '!', '¡', '?', '¿')
        return t in PALABRAS_PARADA
    }

    override fun onCleared() {
        cancelarVad()
        turnoJob?.cancel()
        recorder.cancel()
        tts.shutdown()
        super.onCleared()
    }

    private companion object {
        const val POLL_MS = 150L
        const val UMBRAL_VOZ = 1800            // getMaxAmplitude: umbral de voz (tunable por device)
        const val VOZ_MIN_MUESTRAS = 2         // muestras sostenidas (~300ms) para contar como voz
        const val SILENCIO_MS = 1300L          // silencio tras hablar → enviar
        const val ESPERA_INICIAL_MS = 6000L    // sin voz al arrancar → cerrar loop
        const val MAX_GRABACION_MS = 30000L    // tope duro de grabación
        const val MAX_VACIOS = 2               // blancos seguidos antes de cerrar el loop

        val PALABRAS_PARADA = setOf(
            "para", "parar", "pará", "detente", "detener", "cancela", "cancelar",
            "chao", "chau", "silencio", "apágate", "apagate", "basta", "ya basta",
        )
    }
}
