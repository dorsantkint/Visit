package com.dorsan.visit

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.google.android.gms.location.LocationServices

class PreferencesActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PreferencesScreen()
        }
    }
}

@SuppressLint("MissingPermission") // permission déjà demandée depuis MainActivity
@Composable
fun PreferencesScreen() {
    val context = LocalContext.current

    var lat by remember { mutableStateOf<Double?>(null) }
    var lon by remember { mutableStateOf<Double?>(null) }
    var locationStatus by remember { mutableStateOf("Position non définie") }

    val mapPickerLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            result.data?.let { data ->
                val pickedLat = data.getDoubleExtra("lat", Double.NaN)
                val pickedLon = data.getDoubleExtra("lon", Double.NaN)
                if (!pickedLat.isNaN() && !pickedLon.isNaN()) {
                    lat = pickedLat
                    lon = pickedLon
                    locationStatus = "Position : %.5f, %.5f".format(pickedLat, pickedLon)
                }
            }
        }
    }

    var radiusM by remember { mutableStateOf(500f) }
    var selectedTypes by remember { mutableStateOf(setOf("monument", "historic")) }
    var nbPoi by remember { mutableStateOf(5f) }
    var frSelected by remember { mutableStateOf(true) }
    var enSelected by remember { mutableStateOf(false) }
    var durationMin by remember { mutableStateOf(2) }
    var triggerRadiusM by remember { mutableStateOf(40) }
    var previewJson by remember { mutableStateOf<String?>(null) }

    var backendUrl by remember { mutableStateOf("http://192.168.1.42:8000") }
    var isLoading by remember { mutableStateOf(false) }
    var resultSummary by remember { mutableStateOf<String?>(null) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(24.dp)
            ) {
                Text("Préférences de visite", style = MaterialTheme.typography.headlineSmall)
                Spacer(Modifier.height(16.dp))

                Text(locationStatus)
                Spacer(Modifier.height(8.dp))
                Button(onClick = {
                    val fusedLocationClient = LocationServices.getFusedLocationProviderClient(context)
                    fusedLocationClient.lastLocation.addOnSuccessListener { location ->
                        if (location != null) {
                            lat = location.latitude
                            lon = location.longitude
                            locationStatus = "Position : %.5f, %.5f".format(location.latitude, location.longitude)
                        } else {
                            locationStatus = "Position indisponible (active le GPS et réessaie)"
                        }
                    }
                }) {
                    Text("Utiliser ma position actuelle")
                }
                Spacer(Modifier.height(8.dp))
                Button(onClick = {
                    val intent = Intent(context, MapPickerActivity::class.java).apply {
                        putExtra("start_lat", lat ?: 50.8503)
                        putExtra("start_lon", lon ?: 4.3517)
                    }
                    mapPickerLauncher.launch(intent)
                }) {
                    Text("Choisir sur la carte")
                }
                Spacer(Modifier.height(24.dp))

                Text("Rayon de recherche : ${radiusM.toInt()} m")
                Slider(value = radiusM, onValueChange = { radiusM = it }, valueRange = 50f..2000f)
                Spacer(Modifier.height(16.dp))

                Text("Types de points d'intérêt", style = MaterialTheme.typography.titleMedium)
                AVAILABLE_POI_TYPES.forEach { option ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = option.key in selectedTypes,
                            onCheckedChange = { checked ->
                                selectedTypes = if (checked) selectedTypes + option.key else selectedTypes - option.key
                            }
                        )
                        Text(option.label)
                    }
                }
                Spacer(Modifier.height(16.dp))

                Text("Nombre de points : ${nbPoi.toInt()}")
                Slider(value = nbPoi, onValueChange = { nbPoi = it }, valueRange = 1f..20f, steps = 18)
                Spacer(Modifier.height(16.dp))

                Text("Langue(s)", style = MaterialTheme.typography.titleMedium)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = frSelected, onCheckedChange = { frSelected = it })
                    Text("Français")
                    Spacer(Modifier.width(16.dp))
                    Checkbox(checked = enSelected, onCheckedChange = { enSelected = it })
                    Text("English")
                }
                Spacer(Modifier.height(16.dp))

                Text("Durée de lecture par description", style = MaterialTheme.typography.titleMedium)
                Row {
                    (1..5).forEach { minute ->
                        FilterChip(
                            selected = durationMin == minute,
                            onClick = { durationMin = minute },
                            label = { Text("$minute min") },
                            modifier = Modifier.padding(end = 8.dp)
                        )
                    }
                }
                Spacer(Modifier.height(16.dp))

                Text("Zone de déclenchement", style = MaterialTheme.typography.titleMedium)
                Row {
                    listOf(20, 40, 60).forEach { radius ->
                        FilterChip(
                            selected = triggerRadiusM == radius,
                            onClick = { triggerRadiusM = radius },
                            label = { Text("$radius m") },
                            modifier = Modifier.padding(end = 8.dp)
                        )
                    }
                }
                Spacer(Modifier.height(24.dp))

                Text("Adresse du backend", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Ton PC et ce téléphone doivent être sur le même Wi-Fi. Trouve l'IP de ton PC avec " +
                        "\"ipconfig\" dans PowerShell (Adresse IPv4).",
                    style = MaterialTheme.typography.bodySmall
                )
                Spacer(Modifier.height(4.dp))
                OutlinedTextField(
                    value = backendUrl,
                    onValueChange = { backendUrl = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(Modifier.height(24.dp))

                Button(
                    onClick = {
                        val languages = buildSet {
                            if (frSelected) add("fr")
                            if (enSelected) add("en")
                        }
                        val prefs = TourPreferences(
                            lat = lat,
                            lon = lon,
                            radiusM = radiusM.toInt(),
                            poiTypes = selectedTypes,
                            nbPoi = nbPoi.toInt(),
                            languages = languages,
                            durationMin = durationMin,
                            triggerRadiusM = triggerRadiusM
                        )
                        previewJson = prefs.toRequestJson()
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Aperçu de la requête")
                }

                previewJson?.let { json ->
                    Spacer(Modifier.height(16.dp))
                    Text("Ceci sera envoyé à /generate-tour :", style = MaterialTheme.typography.titleSmall)
                    Spacer(Modifier.height(4.dp))
                    Text(json, style = MaterialTheme.typography.bodySmall)
                }

                Spacer(Modifier.height(16.dp))

                Button(
                    enabled = lat != null && lon != null && !isLoading,
                    onClick = {
                        val languages = buildSet {
                            if (frSelected) add("fr")
                            if (enSelected) add("en")
                        }
                        val prefs = TourPreferences(
                            lat = lat,
                            lon = lon,
                            radiusM = radiusM.toInt(),
                            poiTypes = selectedTypes,
                            nbPoi = nbPoi.toInt(),
                            languages = languages,
                            durationMin = durationMin,
                            triggerRadiusM = triggerRadiusM
                        )

                        isLoading = true
                        errorMessage = null
                        resultSummary = null

                        BackendClient.generateTour(
                            baseUrl = backendUrl.trimEnd('/'),
                            requestJson = prefs.toRequestJson(),
                            onSuccess = { json ->
                                isLoading = false
                                val pois = json.getJSONArray("pois")
                                val intro = json.getJSONArray("intro")
                                resultSummary = "${pois.length()} POI reçu(s)" +
                                    if (intro.length() > 0) " + anecdote de quartier reçue." else "."
                            },
                            onError = { message ->
                                isLoading = false
                                errorMessage = message
                            }
                        )
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        when {
                            isLoading -> "Génération en cours (peut prendre plusieurs minutes)..."
                            lat == null || lon == null -> "Définis d'abord une position"
                            else -> "Envoyer au backend"
                        }
                    )
                }

                resultSummary?.let { summary ->
                    Spacer(Modifier.height(16.dp))
                    Text("Résultat : $summary")
                }

                errorMessage?.let { error ->
                    Spacer(Modifier.height(16.dp))
                    Text("Erreur : $error")
                }
            }
        }
    }
}
