package com.dorsan.visit

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {

    private val requestPermissions =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { _ ->
            // On ne bloque rien ici : l'utilisateur peut relancer l'enregistrement des géofences
            // depuis le bouton 2 une fois les permissions accordées.
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            var statusText by remember { mutableStateOf("Prêt") }

            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    Column(
                        modifier = Modifier.fillMaxSize().padding(24.dp),
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(text = "Visit — POC hackathon")
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(text = statusText)
                        Spacer(modifier = Modifier.height(24.dp))
                        Button(onClick = { requestNeededPermissions() }) {
                            Text("1. Demander les permissions")
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(onClick = {
                            GeofenceHelper(this@MainActivity).registerGeofences(PoiRepository.testPois)
                            statusText = "${PoiRepository.testPois.size} géofence(s) enregistrée(s)"
                        }) {
                            Text("2. Activer les points de test")
                        }
                    }
                }
            }
        }
    }

    private fun requestNeededPermissions() {
        val permissions = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        requestPermissions.launch(permissions.toTypedArray())
    }
}
