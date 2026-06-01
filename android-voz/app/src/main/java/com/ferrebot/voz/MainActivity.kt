package com.ferrebot.voz

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import com.ferrebot.voz.conversation.ConversationController
import com.ferrebot.voz.ui.VozScreen
import com.ferrebot.voz.ui.theme.FerreVozTheme

class MainActivity : ComponentActivity() {

    private val vm: ConversationController by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val permisoMic = registerForActivityResult(
            ActivityResultContracts.RequestPermission(),
        ) { /* el usuario vuelve a tocar el botón si concedió el permiso */ }

        setContent {
            FerreVozTheme {
                VozScreen(
                    vm = vm,
                    tienePermisoMic = {
                        ContextCompat.checkSelfPermission(
                            this,
                            Manifest.permission.RECORD_AUDIO,
                        ) == PackageManager.PERMISSION_GRANTED
                    },
                    pedirPermisoMic = { permisoMic.launch(Manifest.permission.RECORD_AUDIO) },
                )
            }
        }
    }
}
