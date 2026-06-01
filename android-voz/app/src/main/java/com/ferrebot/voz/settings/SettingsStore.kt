package com.ferrebot.voz.settings

import android.content.Context

/**
 * Persistencia simple de ajustes con SharedPreferences:
 *   - URL del servidor (API de FerreBot en Railway) — configurable, NO hardcodeada.
 *   - Nombre del vendedor (se envía como `nombre` al backend).
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

    private companion object {
        const val KEY_URL = "server_url"
        const val KEY_VENDEDOR = "vendedor"
    }
}
