package com.dorsan.visit

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingClient
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices

class GeofenceHelper(private val context: Context) {

    private val geofencingClient: GeofencingClient = LocationServices.getGeofencingClient(context)

    private val geofencePendingIntent: PendingIntent by lazy {
        val intent = Intent(context, GeofenceBroadcastReceiver::class.java)
        PendingIntent.getBroadcast(
            context,
            0,
            intent,
            // FLAG_MUTABLE est obligatoire ici : Google Play Services doit pouvoir ajouter
            // des extras à l'intent au moment du déclenchement de la géofence.
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        )
    }

    @SuppressLint("MissingPermission")
    fun registerGeofences(pois: List<Poi>) {
        val geofences = pois.map { poi ->
            Geofence.Builder()
                .setRequestId(poi.id)
                .setCircularRegion(poi.lat, poi.lon, poi.radiusMeters)
                .setExpirationDuration(Geofence.NEVER_EXPIRE)
                .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER)
                .build()
        }

        val request = GeofencingRequest.Builder()
            // INITIAL_TRIGGER_ENTER : si le téléphone est déjà dans une zone au moment de
            // l'enregistrement, la notification part immédiatement (pratique pour tester
            // avec la position simulée de l'émulateur, sans avoir à marcher).
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofences(geofences)
            .build()

        geofencingClient.addGeofences(request, geofencePendingIntent)
    }
}
