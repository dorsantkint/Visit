package com.dorsan.visit

import android.content.Context

// Comme on n'a pas de logcat dans ce workflow (pas d'Android Studio), on capture les
// crashs nous-mêmes : le message + la stack trace sont sauvegardés avant que l'app ne
// meure, et MainActivity les affiche au prochain lancement.
object CrashHandler {
    private const val PREFS_NAME = "visit_crash_prefs"
    private const val KEY_LAST_CRASH = "last_crash"

    fun install(context: Context) {
        val appContext = context.applicationContext
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()

        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                val prefs = appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                val details = "${throwable::class.java.name}: ${throwable.message}\n\n${throwable.stackTraceToString()}"
                prefs.edit().putString(KEY_LAST_CRASH, details).apply()
            } catch (_: Exception) {
                // Ne surtout pas empêcher le crash normal si l'enregistrement échoue.
            }
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }

    fun readLastCrash(context: Context): String? {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_LAST_CRASH, null)
    }

    fun clearLastCrash(context: Context) {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().remove(KEY_LAST_CRASH).apply()
    }
}
