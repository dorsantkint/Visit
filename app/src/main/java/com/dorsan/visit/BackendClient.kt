package com.dorsan.visit

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

// Client réseau minimal, volontairement sans Retrofit/OkHttp : org.json et
// HttpURLConnection sont déjà dans le SDK Android, ça évite d'ajouter une dépendance
// de plus (donc un risque de compilation de plus) pour ce POC.
object BackendClient {
    private val mainHandler = Handler(Looper.getMainLooper())

    // La génération IA peut être lente (plusieurs POI générés en séquence côté
    // backend) : on laisse jusqu'à 5 minutes avant de considérer que ça a échoué.
    private const val READ_TIMEOUT_MS = 5 * 60 * 1000
    private const val CONNECT_TIMEOUT_MS = 15_000

    // onSuccess/onError sont toujours appelés sur le thread principal : pas besoin de
    // gérer le threading côté appelant pour mettre à jour l'UI Compose.
    fun generateTour(
        baseUrl: String,
        requestJson: String,
        onSuccess: (JSONObject) -> Unit,
        onError: (String) -> Unit
    ) {
        Thread {
            try {
                val url = URL("$baseUrl/generate-tour")
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.setRequestProperty("Content-Type", "application/json")
                connection.doOutput = true
                connection.connectTimeout = CONNECT_TIMEOUT_MS
                connection.readTimeout = READ_TIMEOUT_MS

                OutputStreamWriter(connection.outputStream).use { it.write(requestJson) }

                val responseCode = connection.responseCode
                val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
                val body = stream?.let { BufferedReader(InputStreamReader(it)).use { reader -> reader.readText() } } ?: ""

                if (responseCode in 200..299) {
                    val json = JSONObject(body)
                    mainHandler.post { onSuccess(json) }
                } else {
                    mainHandler.post { onError("Erreur HTTP $responseCode : $body") }
                }
            } catch (e: Exception) {
                mainHandler.post { onError("${e::class.java.simpleName}: ${e.message}") }
            }
        }.start()
    }
}
