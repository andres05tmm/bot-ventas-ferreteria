package com.ferrebot.voz.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val EsquemaOscuro = darkColorScheme(
    primary = RojoPuntoRojo,
    onPrimary = Color.White,
    secondary = Ambar,
    tertiary = Verde,
    background = GrisFondo,
    surface = GrisSuperficie,
)

private val EsquemaClaro = lightColorScheme(
    primary = RojoPuntoRojo,
    onPrimary = Color.White,
    secondary = Ambar,
    tertiary = Verde,
)

@Composable
fun FerreVozTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) EsquemaOscuro else EsquemaClaro,
        typography = Typography(),
        content = content,
    )
}
