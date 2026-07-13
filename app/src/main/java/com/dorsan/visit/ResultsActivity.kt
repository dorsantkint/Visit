package com.dorsan.visit

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONObject
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.mylocation.GpsMyLocationProvider
import org.osmdroid.views.overlay.mylocation.MyLocationNewOverlay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class ResultsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        Configuration.getInstance().userAgentValue = packageName

        val rawJson = intent.getStringExtra("tour_json") ?: "{}"
        val initialTour = parseTourResult(JSONObject(rawJson))

        setContent {
            ResultsScreen(initialTour)
        }
    }
}

private enum class ResultsTab { MAP, LIST }

@SuppressLint("MissingPermission") // permission déjà demandée depuis MainActivity
@Composable
fun ResultsScreen(initialTour: TourResult) {
    val context = LocalContext.current
    var tour by remember { mutableStateOf(initialTour) }
    var tab by remember { mutableStateOf(ResultsTab.MAP) }
    var expandedPoiId by remember { mutableStateOf<String?>(null) }
    var ttsHelper by remember { mutableStateOf<SimpleTts?>(null) }

    val defaultName = remember {
        "Visite du " + SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.FRANCE).format(Date())
    }
    var sessionName by remember { mutableStateOf(defaultName) }
    var savedMessage by remember { mutableStateOf<String?>(null) }

    val addSessionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            result.data?.getStringExtra("tour_json")?.let { json ->
                val added = parseTourResult(JSONObject(json))
                val existingIds = tour.pois.map { it.id }.toSet()
                val newPois = added.pois.filter { it.id !in existingIds }
                tour = tour.copy(pois = tour.pois + newPois)
            }
        }
    }

    DisposableEffect(Unit) {
        onDispose { ttsHelper?.shutdown() }
    }

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(modifier = Modifier.fillMaxSize()) {
                TabRow(selectedTabIndex = if (tab == ResultsTab.MAP) 0 else 1) {
                    Tab(
                        selected = tab == ResultsTab.MAP,
                        onClick = { tab = ResultsTab.MAP },
                        text = { Text("Carte") }
                    )
                    Tab(
                        selected = tab == ResultsTab.LIST,
                        onClick = { tab = ResultsTab.LIST },
                        text = { Text("Liste") }
                    )
                }

                val introText = tour.intro.values.firstOrNull()
                if (introText != null) {
                    val preview = if (introText.length > 150) introText.take(150) + "…" else introText
                    Text(
                        text = "Anecdote de quartier : $preview",
                        modifier = Modifier.padding(12.dp),
                        style = MaterialTheme.typography.bodySmall
                    )
                }

                OutlinedTextField(
                    value = sessionName,
                    onValueChange = { sessionName = it },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp),
                    singleLine = true
                )
                Spacer(Modifier.height(8.dp))
                Row(modifier = Modifier.padding(horizontal = 12.dp)) {
                    Button(onClick = {
                        SessionStore.saveSession(context, sessionName, buildTourJson(tour))
                        savedMessage = "Session sauvegardée."
                    }) {
                        Text("Sauvegarder cette session")
                    }
                    Spacer(Modifier.width(8.dp))
                    Button(onClick = {
                        val intent = Intent(context, SessionsActivity::class.java).apply {
                            putExtra("picker_mode", true)
                        }
                        addSessionLauncher.launch(intent)
                    }) {
                        Text("Ajouter des POI d'une session")
                    }
                }
                savedMessage?.let {
                    Text(it, modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp))
                }
                Spacer(Modifier.height(8.dp))

                when (tab) {
                    ResultsTab.MAP -> ResultsMapView(tour)
                    ResultsTab.LIST -> ResultsListView(
                        tour = tour,
                        expandedPoiId = expandedPoiId,
                        onToggle = { id -> expandedPoiId = if (expandedPoiId == id) null else id },
                        onRead = { text ->
                            if (ttsHelper == null) ttsHelper = SimpleTts(context)
                            ttsHelper?.speak(text)
                        }
                    )
                }
            }
        }
    }
}

// Reconstruit un JSON dans le même format que la réponse backend, pour que
// SessionStore stocke quelque chose qui se re-parse exactement comme un tour normal
// (y compris après une fusion de plusieurs sessions).
private fun buildTourJson(tour: TourResult): String {
    val root = JSONObject()

    val introArray = org.json.JSONArray()
    tour.intro.forEach { (lang, text) ->
        val o = JSONObject()
        o.put("language", lang)
        o.put("text", text)
        introArray.put(o)
    }
    root.put("intro", introArray)

    val poisArray = org.json.JSONArray()
    tour.pois.forEach { poi ->
        val o = JSONObject()
        o.put("id", poi.id)
        o.put("name", poi.name)
        o.put("lat", poi.lat)
        o.put("lon", poi.lon)
        o.put("category", poi.category)
        o.put("trigger_radius_m", poi.triggerRadiusM)
        val descArray = org.json.JSONArray()
        poi.descriptions.forEach { (lang, text) ->
            val d = JSONObject()
            d.put("language", lang)
            d.put("text", text)
            descArray.put(d)
        }
        o.put("descriptions", descArray)
        poisArray.put(o)
    }
    root.put("pois", poisArray)

    return root.toString()
}

@Composable
private fun ResultsMapView(tour: TourResult) {
    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { ctx ->
            MapView(ctx).apply {
                setTileSource(TileSourceFactory.MAPNIK)
                setMultiTouchControls(true)

                val locationOverlay = MyLocationNewOverlay(GpsMyLocationProvider(ctx), this)
                locationOverlay.enableMyLocation()
                overlays.add(locationOverlay)
            }
        },
        update = { mapView ->
            // Retire les anciens repères de POI (pas le point de position, qui reste
            // toujours le premier overlay ajouté) et remet ceux à jour à chaque fois
            // que la liste change (ex: après une fusion de session).
            mapView.overlays.removeAll { it is Marker }

            val firstPoi = tour.pois.firstOrNull()
            val center = if (firstPoi != null) {
                GeoPoint(firstPoi.lat, firstPoi.lon)
            } else {
                GeoPoint(50.8503, 4.3517)
            }
            mapView.controller.setZoom(16.0)
            mapView.controller.setCenter(center)

            tour.pois.forEach { poi ->
                val marker = Marker(mapView)
                marker.position = GeoPoint(poi.lat, poi.lon)
                marker.title = poi.name
                marker.snippet = poi.category
                mapView.overlays.add(marker)
            }

            mapView.invalidate()
        }
    )
}

@Composable
private fun ResultsListView(
    tour: TourResult,
    expandedPoiId: String?,
    onToggle: (String) -> Unit,
    onRead: (String) -> Unit
) {
    if (tour.pois.isEmpty()) {
        Text("Aucun point d'intérêt dans cette visite.", modifier = Modifier.padding(16.dp))
        return
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp)
    ) {
        items(tour.pois) { poi ->
            val isExpanded = expandedPoiId == poi.id
            val description = poi.descriptions.values.firstOrNull() ?: "Pas de description disponible."

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onToggle(poi.id) }
                    .padding(vertical = 12.dp)
            ) {
                Text(poi.name, style = MaterialTheme.typography.titleMedium)
                Text(poi.category, style = MaterialTheme.typography.bodySmall)

                if (isExpanded) {
                    Spacer(Modifier.height(8.dp))
                    Text(description, style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { onRead(description) }) {
                        Text("Lire à voix haute")
                    }
                }
            }
        }
    }
}
