package com.dorsan.visit

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker
import org.osmdroid.views.overlay.MapEventsOverlay

// Centre par défaut si aucune position n'est encore connue (Bruxelles).
private const val DEFAULT_LAT = 50.8503
private const val DEFAULT_LON = 4.3517

class MapPickerActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Obligatoire pour respecter la politique d'usage des tuiles OpenStreetMap :
        // elles bloquent les requêtes sans user-agent identifiable.
        Configuration.getInstance().userAgentValue = packageName

        val startLat = intent.getDoubleExtra("start_lat", DEFAULT_LAT)
        val startLon = intent.getDoubleExtra("start_lon", DEFAULT_LON)

        setContent {
            MapPickerScreen(
                startLat = startLat,
                startLon = startLon,
                onValidate = { lat, lon ->
                    val result = Intent().apply {
                        putExtra("lat", lat)
                        putExtra("lon", lon)
                    }
                    setResult(RESULT_OK, result)
                    finish()
                }
            )
        }
    }
}

@Composable
fun MapPickerScreen(startLat: Double, startLon: Double, onValidate: (Double, Double) -> Unit) {
    var selectedPoint by remember { mutableStateOf<GeoPoint?>(null) }

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(modifier = Modifier.fillMaxSize()) {
                Text(
                    text = "Touche la carte pour choisir un point" +
                        (selectedPoint?.let {
                            " — sélectionné : %.5f, %.5f".format(it.latitude, it.longitude)
                        } ?: ""),
                    modifier = Modifier.padding(16.dp)
                )

                Box(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                ) {
                    AndroidView(
                        modifier = Modifier.fillMaxSize(),
                        factory = { ctx ->
                            MapView(ctx).apply {
                                setTileSource(TileSourceFactory.MAPNIK)
                                setMultiTouchControls(true)
                                controller.setZoom(15.0)
                                controller.setCenter(GeoPoint(startLat, startLon))

                                val receiver = object : MapEventsReceiver {
                                    override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                                        selectedPoint = p
                                        overlays.removeAll { it is Marker }
                                        val marker = Marker(this@apply)
                                        marker.position = p
                                        overlays.add(marker)
                                        invalidate()
                                        return true
                                    }

                                    override fun longPressHelper(p: GeoPoint): Boolean = false
                                }
                                overlays.add(MapEventsOverlay(receiver))
                            }
                        }
                    )
                }

                Button(
                    onClick = {
                        selectedPoint?.let { onValidate(it.latitude, it.longitude) }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp)
                ) {
                    Text(if (selectedPoint != null) "Valider ce point" else "Touche la carte d'abord")
                }
            }
        }
    }
}
