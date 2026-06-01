package com.ferrebot.voz.net

import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Resultado final de un turno de chat (evento SSE "done"). */
data class ChatResult(
    val respuesta: String,
    val ventas: Int,
    val gastos: Int,
    val pendiente: Boolean,
)

/**
 * Cliente HTTP del cerebro de FerreBot. NO reimplementa IA: solo llama a los
 * endpoints que ya usa el dashboard.
 *   - POST /chat/transcribir : audio -> {ok, texto}
 *   - POST /chat/stream      : SSE con eventos chunk/done/error (canal "voz")
 *   - POST /chat (confirmar_pago) : Fase 4
 */
class ApiClient(baseUrl: String) {

    private val base = baseUrl.trim().trimEnd('/')

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)   // la respuesta del modelo puede tardar
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    private fun url(path: String) = base + path

    /** Sube el audio a /chat/transcribir y devuelve el texto transcrito. */
    suspend fun transcribir(audio: File): String = suspendCancellableCoroutine { cont ->
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "audio",
                audio.name,
                audio.asRequestBody("audio/mp4".toMediaType()),
            )
            .build()
        val req = Request.Builder().url(url("/chat/transcribir")).post(body).build()
        val call = client.newCall(req)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (cont.isActive) cont.resumeWithException(e)
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val txt = it.body?.string().orEmpty()
                    if (!it.isSuccessful) {
                        if (cont.isActive) {
                            cont.resumeWithException(RuntimeException("HTTP ${it.code}"))
                        }
                        return
                    }
                    val texto = runCatching { JSONObject(txt).optString("texto", "") }
                        .getOrDefault("")
                    if (cont.isActive) cont.resume(texto)
                }
            }
        })
    }

    /**
     * Envía el mensaje a /chat (no-streaming) con canal "voz" y devuelve el
     * ChatResult. `onChunk` se conserva por compatibilidad pero no se usa (la voz
     * habla la respuesta completa al final). Ver nota en el cuerpo sobre por qué
     * /chat y no /chat/stream.
     */
    suspend fun chatVoz(
        mensaje: String,
        nombre: String,
        sessionId: String,
        historial: List<Pair<String, String>>,
        @Suppress("UNUSED_PARAMETER") onChunk: (String) -> Unit,
    ): ChatResult = suspendCancellableCoroutine { cont ->
        val histArray = JSONArray()
        historial.forEach { (role, content) ->
            histArray.put(JSONObject().put("role", role).put("content", content))
        }
        val payload = JSONObject()
            .put("mensaje", mensaje)
            .put("nombre", nombre.ifBlank { "Vendedor" })
            .put("session_id", sessionId)
            .put("canal", "voz")
            .put("historial", histArray)

        // Voz usa el endpoint NO-streaming /chat: la app habla la respuesta completa
        // recién al final (no usa los chunks), y /chat soporta tool-calling (más
        // robusto para clasificar intención: venta vs gasto vs fiado).
        val req = Request.Builder()
            .url(url("/chat"))
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()
        val call = client.newCall(req)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (cont.isActive) cont.resumeWithException(e)
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val txt = it.body?.string().orEmpty()
                    if (!it.isSuccessful) {
                        if (cont.isActive) cont.resumeWithException(RuntimeException("HTTP ${it.code}"))
                        return
                    }
                    val json = runCatching { JSONObject(txt) }.getOrNull()
                    if (json == null) {
                        if (cont.isActive) cont.resumeWithException(RuntimeException("Respuesta inválida"))
                        return
                    }
                    val acc = json.optJSONObject("acciones")
                    val res = ChatResult(
                        respuesta = json.optString("respuesta", ""),
                        ventas = acc?.optInt("ventas", 0) ?: 0,
                        gastos = acc?.optInt("gastos", 0) ?: 0,
                        pendiente = json.optBoolean("pendiente", false),
                    )
                    if (cont.isActive) cont.resume(res)
                }
            }
        })
    }

    /**
     * Confirma el pago de la venta pendiente vía POST /chat (rama confirmar_pago).
     * `metodo`: "efectivo" | "transferencia" | "datafono". canal "voz" para que la
     * respuesta venga hablada. La venta pendiente se ubica por `sessionId`.
     */
    suspend fun confirmarPago(
        metodo: String,
        nombre: String,
        sessionId: String,
    ): ChatResult = suspendCancellableCoroutine { cont ->
        val payload = JSONObject()
            .put("mensaje", "")               // requerido por el modelo; no se usa en esta rama
            .put("nombre", nombre.ifBlank { "Vendedor" })
            .put("session_id", sessionId)
            .put("canal", "voz")
            .put("confirmar_pago", metodo)
        val req = Request.Builder()
            .url(url("/chat"))
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()
        val call = client.newCall(req)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (cont.isActive) cont.resumeWithException(e)
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val txt = it.body?.string().orEmpty()
                    if (!it.isSuccessful) {
                        if (cont.isActive) cont.resumeWithException(RuntimeException("HTTP ${it.code}"))
                        return
                    }
                    val json = runCatching { JSONObject(txt) }.getOrNull()
                    if (json == null) {
                        if (cont.isActive) cont.resumeWithException(RuntimeException("Respuesta inválida"))
                        return
                    }
                    val acc = json.optJSONObject("acciones")
                    val res = ChatResult(
                        respuesta = json.optString("respuesta", ""),
                        ventas = acc?.optInt("ventas", 0) ?: 0,
                        gastos = acc?.optInt("gastos", 0) ?: 0,
                        pendiente = json.optBoolean("pendiente", false),
                    )
                    if (cont.isActive) cont.resume(res)
                }
            }
        })
    }
}
