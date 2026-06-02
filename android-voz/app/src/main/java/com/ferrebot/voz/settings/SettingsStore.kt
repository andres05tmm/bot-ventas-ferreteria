package com.ferrebot.voz.settings

import android.content.Context
import java.util.UUID

/**
 * Persistencia simple de ajustes con SharedPreferences:
 *   - URL del servidor (API de FerreBot en Railway) — configurable, NO hardcodeada.
 *   - Nombre del vendedor (se envía como `nombre` al backend).
 *   - sessionId estable entre reinicios del proceso (P0.2).
 */
class SettingsStore(context: Context) {
    private val prefs = context.applicationContext
        .getSharedPreferences("ferrevoz", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_URL, "") ?: ""
        set(value) {
            prefs.edit().putString(KEY_URL, value.trim().trimEnd('/')).apply()
        }

    var vendedor: String
        get() = prefs.getString(KEY_VENDEDOR, "") ?: ""
        set(value) {
            prefs.edit().putString(KEY_VENDEDOR, value.trim()).apply()
        }

    val configurado: Boolean get() = serverUrl.isNotBlank()

    /**
     * Identificador de sesión estable entre reinicios del proceso (P0.2).
     * La primera vez que se lee genera un UUID, lo persiste y lo devuelve; en
     * adelante devuelve siempre el mismo. Así una venta pendiente sobrevive a un
     * reinicio de la app y el backend la encuentra bajo la misma llave en vez de
     * dejarla huérfana ("No hay ventas pendientes").
     */
    val sessionId: String
        get() {
            val actual = prefs.getString(KEY_SESSION, "") ?: ""
            if (actual.isNotBlank()) return actual
            val nuevo = UUID.randomUUID().toString()
            prefs.edit().putString(KEY_SESSION, nuevo).apply()
            return nuevo
        }

    private companion object {
        const val KEY_URL = "server_url"
        const val KEY_VENDEDOR = "vendedor"
        const val KEY_SESSION = "session_id"
    }
}
