package com.dorsan.visit

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

// TTS à la demande pour l'écran de résultats (indépendant du flux notification ->
// TtsReaderActivity, qui reste dédié au déclenchement par géofence).
class SimpleTts(context: Context) {
    private var tts: TextToSpeech? = null
    private var ready = false
    private var pendingText: String? = null

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.FRENCH
                ready = true
                pendingText?.let { speak(it) }
                pendingText = null
            }
        }
    }

    fun speak(text: String) {
        if (ready) {
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, text.hashCode().toString())
        } else {
            pendingText = text
        }
    }

    fun shutdown() {
        tts?.stop()
        tts?.shutdown()
    }
}
