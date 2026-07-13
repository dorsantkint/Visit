package com.dorsan.visit

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

// Stockage local des sessions de visite (SharedPreferences, pas de dépendance de plus).
// Un "index" léger (id, nom, date) + le JSON complet de chaque session sous sa propre clé.
data class SavedSession(
    val id: String,
    val name: String,
    val timestamp: Long,
    val tourJson: String
)

object SessionStore {
    private const val PREFS_NAME = "visit_sessions"
    private const val KEY_INDEX = "session_index"

    fun saveSession(context: Context, name: String, tourJson: String): SavedSession {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val id = System.currentTimeMillis().toString()
        val timestamp = System.currentTimeMillis()

        prefs.edit().putString("session_$id", tourJson).apply()

        val index = readIndexMeta(context).toMutableList()
        index.add(0, Triple(id, name, timestamp))
        writeIndexMeta(context, index)

        return SavedSession(id, name, timestamp, tourJson)
    }

    fun listSessions(context: Context): List<SavedSession> {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return readIndexMeta(context).map { (id, name, timestamp) ->
            val json = prefs.getString("session_$id", null) ?: "{}"
            SavedSession(id, name, timestamp, json)
        }
    }

    fun deleteSession(context: Context, id: String) {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().remove("session_$id").apply()
        val index = readIndexMeta(context).filterNot { it.first == id }
        writeIndexMeta(context, index)
    }

    private fun readIndexMeta(context: Context): List<Triple<String, String, Long>> {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val raw = prefs.getString(KEY_INDEX, null) ?: return emptyList()
        val array = JSONArray(raw)
        val result = mutableListOf<Triple<String, String, Long>>()
        for (i in 0 until array.length()) {
            val o = array.getJSONObject(i)
            result.add(Triple(o.getString("id"), o.getString("name"), o.getLong("timestamp")))
        }
        return result
    }

    private fun writeIndexMeta(context: Context, entries: List<Triple<String, String, Long>>) {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val array = JSONArray()
        entries.forEach { (id, name, timestamp) ->
            val o = JSONObject()
            o.put("id", id)
            o.put("name", name)
            o.put("timestamp", timestamp)
            array.put(o)
        }
        prefs.edit().putString(KEY_INDEX, array.toString()).apply()
    }
}
