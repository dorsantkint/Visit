package com.dorsan.visit

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class SessionsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Mode "picker" (appelé depuis l'écran de résultats pour choisir une session à
        // fusionner) vs mode normal (parcourir/supprimer ses sessions depuis l'accueil).
        val pickerMode = intent.getBooleanExtra("picker_mode", false)

        setContent {
            SessionsScreen(
                pickerMode = pickerMode,
                onSessionChosen = { session ->
                    if (pickerMode) {
                        val result = Intent().apply {
                            putExtra("tour_json", session.tourJson)
                        }
                        setResult(RESULT_OK, result)
                        finish()
                    } else {
                        val intent = Intent(this, ResultsActivity::class.java).apply {
                            putExtra("tour_json", session.tourJson)
                        }
                        startActivity(intent)
                    }
                }
            )
        }
    }
}

@Composable
fun SessionsScreen(pickerMode: Boolean, onSessionChosen: (SavedSession) -> Unit) {
    val context = LocalContext.current
    var sessions by remember { mutableStateOf(SessionStore.listSessions(context)) }
    val dateFormat = remember { SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.FRANCE) }

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp)
            ) {
                Text(
                    if (pickerMode) "Choisis une session à ajouter" else "Mes sessions sauvegardées",
                    style = MaterialTheme.typography.headlineSmall
                )
                Spacer(Modifier.height(16.dp))

                if (sessions.isEmpty()) {
                    Text("Aucune session sauvegardée pour l'instant.")
                }

                LazyColumn {
                    items(sessions) { session ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onSessionChosen(session) }
                                .padding(vertical = 12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column {
                                Text(session.name, style = MaterialTheme.typography.titleMedium)
                                Text(
                                    dateFormat.format(Date(session.timestamp)),
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                            if (!pickerMode) {
                                Button(onClick = {
                                    SessionStore.deleteSession(context, session.id)
                                    sessions = SessionStore.listSessions(context)
                                }) {
                                    Text("Supprimer")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
