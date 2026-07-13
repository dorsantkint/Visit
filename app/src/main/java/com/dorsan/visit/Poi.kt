package com.dorsan.visit

data class Poi(
    val id: String,
    val name: String,
    val lat: Double,
    val lon: Double,
    val radiusMeters: Float = 40f,
    val descriptionFr: String,
    val descriptionEn: String
)

object PoiRepository {
    // TODO Dorsan : remplace ces coordonnées par de vrais points près de l'endroit où tu testes.
    // Pour récupérer des coordonnées : clic droit sur un point dans Google Maps -> elles s'affichent en haut,
    // clique dessus pour les copier (format "48.8566, 2.3522").
    val testPois = listOf(
        Poi(
            id = "poi_1",
            name = "Point de test 1",
            lat = 48.8566,
            lon = 2.3522,
            radiusMeters = 40f,
            descriptionFr = "Ceci est la description de test du premier point d'intérêt. " +
                "Remplace ce texte par une vraie description écrite à la main pour ton premier test.",
            descriptionEn = "This is the test description for the first point of interest. " +
                "Replace this text with a real hand-written description for your first test."
        ),
        Poi(
            id = "poi_2",
            name = "Point de test 2",
            lat = 48.8580,
            lon = 2.3540,
            radiusMeters = 40f,
            descriptionFr = "Deuxième point de test. À remplacer par un vrai lieu.",
            descriptionEn = "Second test point. To be replaced with a real place."
        )
    )
}
