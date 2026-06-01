package com.ferrebot.voz.audio

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import java.io.File

/**
 * Graba el micrófono a un .m4a (AAC) en el cache de la app.
 * Fase 2: control manual (start/stop). El VAD por silencio llega en Fase 3.
 * 16 kHz mono: suficiente para voz y más liviano para subir a Whisper.
 */
class AudioRecorder(private val context: Context) {

    private var recorder: MediaRecorder? = null
    private var outputFile: File? = null

    @Suppress("DEPRECATION")
    fun start() {
        val file = File(context.cacheDir, "voz_${System.currentTimeMillis()}.m4a")
        val rec = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            MediaRecorder()
        }
        rec.apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setAudioEncodingBitRate(64_000)
            setAudioSamplingRate(16_000)
            setOutputFile(file.absolutePath)
            prepare()
            start()
        }
        recorder = rec
        outputFile = file
    }

    /** Detiene y devuelve el archivo grabado, o null si falló (audio muy corto, etc.). */
    fun stop(): File? {
        val rec = recorder ?: return null
        return try {
            rec.stop()
            outputFile
        } catch (e: Exception) {
            outputFile?.delete()
            null
        } finally {
            rec.release()
            recorder = null
        }
    }

    /** Cancela y descarta cualquier grabación en curso. */
    fun cancel() {
        try {
            recorder?.stop()
        } catch (_: Exception) {
        }
        recorder?.release()
        recorder = null
        outputFile?.delete()
        outputFile = null
    }
}
