package com.dorsan.visit

import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import java.util.Locale

// Activité "silencieuse" : elle ne sert qu'à lancer la lecture vocale de la description
// du POI touché dans la notification, puis se ferme toute seule à la fin de la lecture.
class TtsReaderActivity : ComponentActivity() {

    private var tts: TextToSpeech? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val poiId = intent.getStringExtra("poi_id")
        val poi = PoiRepository.testPois.find { it.id == poiId }

        if (poi == null) {
            finish()
            return
        }

        setContent {
            var isSpeaking by remember { mutableStateOf(true) }

            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    Box(modifier = Modifier.fillMaxSize().padding(24.dp)) {
                        Text(text = if (isSpeaking) "Lecture en cours : ${poi.name}" else "Terminé")
                    }
                }
            }

            LaunchedEffect(Unit) {
                tts = TextToSpeech(this@TtsReaderActivity) { status ->
                    if (status == TextToSpeech.SUCCESS) {
                        tts?.language = Locale.FRENCH
                        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                            override fun onStart(utteranceId: String?) {}
                            override fun onDone(utteranceId: String?) {
                                isSpeaking = false
                                finish()
                            }
                            @Deprecated("Deprecated in Java")
                            override fun onError(utteranceId: String?) {
                                isSpeaking = false
                                finish()
                            }
                        })
                        tts?.speak(poi.descriptionFr, TextToSpeech.QUEUE_FLUSH, null, "poi_desc_${poi.id}")
                    } else {
                        finish()
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }
}
