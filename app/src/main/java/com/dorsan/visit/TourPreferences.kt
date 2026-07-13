package com.dorsan.visit

// Reflète exactement le corps JSON attendu par POST /generate-tour côté backend
// (voir backend/app/models.py : TourRequest). Garder les noms de champs synchronisés.
data class TourPreferences(
    val lat: Double?,
    val lon: Double?,
    val radiusM: Int = 500,
    val poiTypes: Set<String> = setOf("monument", "historic"),
    val nbPoi: Int = 5,
    val languages: Set<String> = setOf("fr"),
    val durationMin: Int = 2,
    val triggerRadiusM: Int = 40
) {
    fun toRequestJson(): String {
        val typesJson = poiTypes.joinToString(",") { "\"$it\"" }
        val langsJson = languages.joinToString(",") { "\"$it\"" }
        return """
            {
              "lat": ${lat ?: "null"},
              "lon": ${lon ?: "null"},
              "radius_m": $radiusM,
              "poi_types": [$typesJson],
              "nb_poi": $nbPoi,
              "languages": [$langsJson],
              "duration_min": $durationMin,
              "trigger_radius_m": $triggerRadiusM
            }
        """.trimIndent()
    }
}

data class PoiTypeOption(val key: String, val label: String)

// Doit rester synchronisé avec TYPE_TAG_MAP dans backend/app/overpass.py.
val AVAILABLE_POI_TYPES = listOf(
    PoiTypeOption("monument", "Monuments"),
    PoiTypeOption("historic", "Lieux historiques"),
    PoiTypeOption("religious", "Édifices religieux"),
    PoiTypeOption("museum", "Musées"),
    PoiTypeOption("artwork", "Art / sculptures"),
    PoiTypeOption("street_art", "Street art"),
    PoiTypeOption("viewpoint", "Points de vue"),
    PoiTypeOption("gastronomie", "Gastronomie"),
)
