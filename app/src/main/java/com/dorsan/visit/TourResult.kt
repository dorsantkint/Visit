package com.dorsan.visit

import org.json.JSONObject

// Représentation Kotlin de la réponse de POST /generate-tour (voir backend/app/models.py).
data class PoiResult(
    val id: String,
    val name: String,
    val lat: Double,
    val lon: Double,
    val category: String,
    val triggerRadiusM: Int,
    val descriptions: Map<String, String> // langue -> texte
)

data class TourResult(
    val intro: Map<String, String>, // langue -> texte, vide si pas de quartier résolu
    val pois: List<PoiResult>
)

fun parseTourResult(json: JSONObject): TourResult {
    val introArray = json.optJSONArray("intro")
    val intro = mutableMapOf<String, String>()
    if (introArray != null) {
        for (i in 0 until introArray.length()) {
            val d = introArray.getJSONObject(i)
            intro[d.getString("language")] = d.getString("text")
        }
    }

    val poisArray = json.optJSONArray("pois")
    val pois = mutableListOf<PoiResult>()
    if (poisArray != null) {
        for (i in 0 until poisArray.length()) {
            val p = poisArray.getJSONObject(i)
            val descArray = p.getJSONArray("descriptions")
            val descriptions = mutableMapOf<String, String>()
            for (j in 0 until descArray.length()) {
                val d = descArray.getJSONObject(j)
                descriptions[d.getString("language")] = d.getString("text")
            }
            pois.add(
                PoiResult(
                    id = p.getString("id"),
                    name = p.getString("name"),
                    lat = p.getDouble("lat"),
                    lon = p.getDouble("lon"),
                    category = p.getString("category"),
                    triggerRadiusM = p.getInt("trigger_radius_m"),
                    descriptions = descriptions
                )
            )
        }
    }

    return TourResult(intro = intro, pois = pois)
}
