package com.ferrebot.voz.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.ferrebot.voz.conversation.ConversationController
import com.ferrebot.voz.conversation.Estado

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VozScreen(
    vm: ConversationController,
    tienePermisoMic: () -> Boolean,
    pedirPermisoMic: () -> Unit,
) {
    val ui by vm.ui.collectAsState()
    var mostrarAjustes by remember { mutableStateOf(!vm.configurado) }
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(ui.error) {
        ui.error?.let { snackbar.showSnackbar(it) }
    }

    // P0.3: al abrir la app, recuperar una venta que quedó esperando pago
    // (perdida al cerrar/reabrir o por reinicio del server).
    LaunchedEffect(Unit) {
        vm.verificarPendiente()
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            TopAppBar(
                title = { Text("FerreVoz") },
                actions = {
                    Text("Manos libres", style = MaterialTheme.typography.labelMedium)
                    Switch(
                        checked = ui.manosLibres,
                        onCheckedChange = { vm.toggleManosLibres() },
                        modifier = Modifier.padding(horizontal = 8.dp),
                    )
                    IconButton(onClick = { mostrarAjustes = true }) {
                        Icon(Icons.Filled.Settings, contentDescription = "Ajustes")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = ui.transcripcion.ifBlank { " " },
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
            )

            MicButton(
                estado = ui.estado,
                onTap = { if (!tienePermisoMic()) pedirPermisoMic() else vm.onMicTap() },
            )

            Text(
                text = ui.respuesta.ifBlank { etiquetaEstado(ui.estado, ui.manosLibres) },
                style = MaterialTheme.typography.titleMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp),
            )
        }
    }

    if (mostrarAjustes) {
        AjustesDialog(
            urlInicial = vm.urlActual(),
            vendedorInicial = vm.vendedorActual(),
            onGuardar = { url, vend ->
                vm.guardarAjustes(url, vend)
                mostrarAjustes = false
            },
            onCerrar = { mostrarAjustes = false },
        )
    }
}

@Composable
private fun MicButton(estado: Estado, onTap: () -> Unit) {
    val cargando = estado == Estado.TRANSCRIBIENDO || estado == Estado.PENSANDO
    val activo = estado == Estado.ESCUCHANDO

    val color by animateColorAsState(
        targetValue = when (estado) {
            Estado.ESCUCHANDO -> MaterialTheme.colorScheme.primary
            Estado.TRANSCRIBIENDO, Estado.PENSANDO -> MaterialTheme.colorScheme.secondary
            Estado.HABLANDO -> MaterialTheme.colorScheme.tertiary
            Estado.IDLE -> MaterialTheme.colorScheme.primary
        },
        label = "micColor",
    )

    val pulso = rememberInfiniteTransition(label = "pulso")
    val escalaAnim by pulso.animateFloat(
        initialValue = 1f,
        targetValue = 1.12f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse),
        label = "escala",
    )

    Box(
        modifier = Modifier
            .size(180.dp)
            .scale(if (activo) escalaAnim else 1f)
            .clip(CircleShape)
            .background(color)
            .clickable(enabled = !cargando) { onTap() },
        contentAlignment = Alignment.Center,
    ) {
        if (cargando) {
            CircularProgressIndicator(color = Color.White)
        } else {
            Icon(
                Icons.Filled.Mic,
                contentDescription = "Hablar",
                tint = Color.White,
                modifier = Modifier.size(72.dp),
            )
        }
    }
}

private fun etiquetaEstado(estado: Estado, manosLibres: Boolean): String = when (estado) {
    Estado.IDLE -> if (manosLibres) "Tocá para empezar a conversar" else "Tocá para hablar"
    Estado.ESCUCHANDO -> if (manosLibres) "Hablá… (se envía solo al callar · tocá para parar)"
                         else "Escuchando… tocá para enviar"
    Estado.TRANSCRIBIENDO -> "Transcribiendo…"
    Estado.PENSANDO -> "Pensando…"
    Estado.HABLANDO -> "Hablando… (tocá para cortar)"
}

@Composable
private fun AjustesDialog(
    urlInicial: String,
    vendedorInicial: String,
    onGuardar: (String, String) -> Unit,
    onCerrar: () -> Unit,
) {
    var url by remember { mutableStateOf(urlInicial) }
    var vendedor by remember { mutableStateOf(vendedorInicial) }

    AlertDialog(
        onDismissRequest = onCerrar,
        title = { Text("Ajustes") },
        text = {
            Column {
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    label = { Text("URL del servidor") },
                    placeholder = { Text("https://...railway.app") },
                    singleLine = true,
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = vendedor,
                    onValueChange = { vendedor = it },
                    label = { Text("Nombre del vendedor") },
                    singleLine = true,
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onGuardar(url, vendedor) },
                enabled = url.isNotBlank(),
            ) { Text("Guardar") }
        },
        dismissButton = {
            TextButton(onClick = onCerrar) { Text("Cancelar") }
        },
    )
}
