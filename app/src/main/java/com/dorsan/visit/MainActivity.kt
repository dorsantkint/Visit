package com.dorsan.visit

import android.Manifest
import android.content.Intent
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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

    // On garde une référence pour pouvoir mettre à jour le texte de statut
    // depuis le callback de la demande de permissions.
    private var onPermissionsResult: ((Map<String, Boolean>) -> Unit)? = null

    private val requestPermissions =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
            onPermissionsResult?.invoke(results)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        CrashHandler.install(this)
        val lastCrash = CrashHandler.readLastCrash(this)

        setContent {
            var statusText by remember { mutableStateOf("Prêt") }
            var crashText by remember { mutableStateOf(lastCrash) }

            onPermissionsResult = { results ->
                val denied = results.filterValues { granted -> !granted }.keys
                statusText = if (denied.isEmpty()) {
                    "Permissions accordées."
                } else {
                    "Refusées : ${denied.joinToString { it.substringAfterLast('.') }}"
                }
            }

            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp)
                            .verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(text = "Visit — POC hackathon")
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(text = statusText)

                        crashText?.let { crash ->
                            Spacer(modifier = Modifier.height(16.dp))
                            Text(text = "Dernier crash détecté :")
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(text = crash)
                            Spacer(modifier = Modifier.height(8.dp))
                            Button(onClick = {
                                CrashHandler.clearLastCrash(this@MainActivity)
                                crashText = null
                            }) {
                                Text("Effacer ce message")
                            }
                        }

                        Spacer(modifier = Modifier.height(24.dp))
                        Button(onClick = { requestNeededPermissions() }) {
                            Text("1. Demander les permissions")
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(onClick = {
                            GeofenceHelper(this@MainActivity).registerGeofences(PoiRepository.testPois) { error ->
                                statusText = if (error == null) {
                                    "${PoiRepository.testPois.size} géofence(s) enregistrée(s)."
                                } else {
                                    "Erreur géofence : $error"
                                }
                            }
                        }) {
                            Text("2. Activer les points de test (réel, par géoloc)")
                        }

                        Spacer(modifier = Modifier.height(24.dp))
                        Text(text = "3. Tester sans marcher (simulation) :")
                        Spacer(modifier = Modifier.height(8.dp))

                        // Un bouton par POI : déclenche directement la notification (et donc
                        // la lecture vocale au tap) sans passer par le GPS. Pratique pour
                        // tester l'UI, la notif et le TTS où que tu sois.
                        PoiRepository.testPois.forEach { poi ->
                            Button(onClick = {
                                NotificationHelper(this@MainActivity).showPoiNotification(poi)
                                statusText = "Notification simulée pour : ${poi.name}"
                            }) {
                                Text("Simuler l'arrivée : ${poi.name}")
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                        }

                        Spacer(modifier = Modifier.height(24.dp))
                        Text(text = "4. Configurer une vraie visite (backend IA) :")
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(onClick = {
                            startActivity(Intent(this@MainActivity, PreferencesActivity::class.java))
                        }) {
                            Text("Ouvrir les préférences de visite")
                        }

                        Spacer(modifier = Modifier.height(12.dp))
                        Button(onClick = {
                            startActivity(Intent(this@MainActivity, SessionsActivity::class.java))
                        }) {
                            Text("Mes sessions sauvegardées")
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
