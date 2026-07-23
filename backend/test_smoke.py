"""Test de fumée : vérifie que l'app démarre et que /generate-tour fonctionne de bout
en bout, avec Overpass/Wikipedia/Groq mockés (pas de réseau dans ce sandbox).
ranking.py et geo.py ne sont PAS mockés : pas d'appel réseau, donc on teste le vrai code."""
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

from app.main import app
from app import overpass, ranking
from app.llm_client import CurationResult

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


FAKE_POIS = [
    {"osm_id": "node/1", "name": "Café A", "lat": 50.800, "lon": 4.340, "category": "restaurant", "osm_facts": {}},
    {"osm_id": "node/2", "name": "Café B", "lat": 50.801, "lon": 4.341, "category": "restaurant", "osm_facts": {}},
    {"osm_id": "node/3", "name": "Café C", "lat": 50.802, "lon": 4.342, "category": "restaurant", "osm_facts": {}},
    {"osm_id": "node/4", "name": "Café D", "lat": 50.803, "lon": 4.343, "category": "restaurant", "osm_facts": {}},
    {
        "osm_id": "node/5", "name": "Monument aux Morts", "lat": 50.804, "lon": 4.344,
        "category": "monument", "osm_facts": {"wikidata": "Q12345"},
    },
]

FAKE_STREET_POI = {
    "osm_id": "way/99", "name": "Rue de la Paix", "lat": 50.8025, "lon": 4.3425,
    "category": "rue", "osm_facts": {"name:etymology": "en hommage à la paix"},
}

# Reproduit la crainte "on rate l'Hôtel de Ville" : plein de POI ordinaires, un seul
# incontournable réel (tag heritage = classé), noyé dans la liste.
GRAND_PLACE_STYLE_POIS = [
    {"osm_id": f"way/{i}", "name": f"Maison {i}", "lat": 50.8467 + i * 0.0001, "lon": 4.3525,
     "category": "shop", "osm_facts": {}}
    for i in range(10)
] + [
    {
        "osm_id": "way/townhall", "name": "Hôtel de Ville", "lat": 50.8466, "lon": 4.3528,
        "category": "townhall", "osm_facts": {"heritage": "1", "wikidata": "Q1567329"},
    }
]


def test_ranking_diversifies_categories():
    shortlist = ranking.rank_and_diversify(FAKE_POIS, center_lat=50.8, center_lon=4.34, radius_m=1000, nb_poi=2)
    top_2_ids = {p["osm_id"] for p in shortlist[:2]}
    assert "node/5" in top_2_ids, f"Le monument devrait être dans le top 2, shortlist={shortlist}"


def test_split_landmarks_separates_documented_pois():
    landmarks, regular = ranking.split_landmarks(GRAND_PLACE_STYLE_POIS)
    assert len(landmarks) == 1
    assert landmarks[0]["osm_id"] == "way/townhall"
    assert len(regular) == 10


def test_wikidata_only_is_not_an_automatic_landmark():
    """Un simple tag wikidata (sans heritage) ne suffit plus à contourner le tri
    algorithmique : ça reste un signal fort dans le score normal, et ça peut désormais
    être confirmé par la reconnaissance LLM dans curate_pois, mais pas un passe-droit
    purement mécanique via split_landmarks."""
    poi_wikidata_only = {
        "osm_id": "node/chain", "name": "Chaîne Quelconque", "lat": 50.846, "lon": 4.352,
        "category": "restaurant", "osm_facts": {"wikidata": "Q999"},
    }
    landmarks, regular = ranking.split_landmarks([poi_wikidata_only])
    assert landmarks == []
    assert regular == [poi_wikidata_only]


def test_fetch_poi_by_name_rejects_result_outside_radius():
    """Le LLM cite parfois un nom sans savoir précisément où il se trouve (il ne fournit
    jamais de coordonnées). Si la recherche Overpass par nom renvoie malgré tout un
    élément physiquement hors du rayon demandé, on doit le rejeter — garde-fou explicite,
    indépendant du filtre `around` d'Overpass lui-même."""
    far_away_response = {
        "elements": [
            {"type": "node", "id": 1, "lat": 51.5074, "lon": -0.1278, "tags": {"name": "Big Ben"}}
        ]
    }
    with patch("app.overpass._query_overpass", return_value=far_away_response):
        # Centre à Bruxelles, rayon de 500m : Londres est à des centaines de km.
        result = overpass.fetch_poi_by_name("Big Ben", 50.8466, 4.3528, 500)
        assert result is None, "Un résultat hors du rayon demandé ne doit jamais être accepté"


def test_fetch_poi_by_name_accepts_result_inside_radius():
    nearby_response = {
        "elements": [
            {"type": "node", "id": 2, "lat": 50.8467, "lon": 4.3529, "tags": {"name": "Manneken Pis"}}
        ]
    }
    with patch("app.overpass._query_overpass", return_value=nearby_response):
        result = overpass.fetch_poi_by_name("Manneken Pis", 50.8466, 4.3528, 500)
        assert result is not None
        assert result["osm_id"] == "node/2"


def test_generate_tour_never_drops_a_landmark_even_with_many_regular_pois():
    """Le cœur de la demande : même avec 10 boutiques ordinaires et un nb_poi bas,
    l'Hôtel de Ville (incontournable "heritage") doit toujours apparaître dans le
    résultat, même si la curation IA "l'oublie"."""
    with patch("app.main.overpass.fetch_pois", return_value=GRAND_PLACE_STYLE_POIS), \
         patch("app.main.overpass.fetch_street_candidates", return_value=[]), \
         patch("app.main.overpass.fetch_neighborhood_place", return_value=None), \
         patch("app.main.wikipedia.fetch_extract_for_poi", return_value=None), \
         patch("app.main.llm_client.generate_description", return_value="Texte."), \
         patch("app.main.llm_client.curate_pois", return_value=CurationResult(selected_ids=["way/0", "way/1"])) as mock_curate:
        # La curation IA mockée "oublie" volontairement le townhall, pour vérifier
        # qu'il est réinjecté de force en amont, indépendamment de son choix.

        payload = {"lat": 50.8466, "lon": 4.3528, "nb_poi": 3, "languages": ["fr"], "duration_min": 1}
        r = client.post("/generate-tour", json=payload)

        assert r.status_code == 200, r.text
        data = r.json()
        ids = {p["id"] for p in data["pois"]}
        assert "way/townhall" in ids, f"L'Hôtel de Ville a été perdu ! ids={ids}"
        # La curation ne devait être appelée que pour les places restantes (3 - 1 landmark = 2)
        mock_curate.assert_called_once()
        called_args = mock_curate.call_args[0]
        called_shortlist, called_nb = called_args[0], called_args[1]
        assert called_nb == 2
        assert all(p["osm_id"] != "way/townhall" for p in called_shortlist)


def test_generate_tour_includes_street_and_intro():
    with patch("app.main.overpass.fetch_pois", return_value=FAKE_POIS), \
         patch("app.main.overpass.fetch_street_candidates", return_value=[FAKE_STREET_POI]), \
         patch("app.main.overpass.fetch_neighborhood_place", return_value="Uccle"), \
         patch("app.main.wikipedia.fetch_extract_for_poi", return_value="Extrait factice."), \
         patch("app.main.wikipedia.resolve_title", return_value=None), \
         patch("app.main.llm_client.generate_description", return_value="Texte généré factice."), \
         patch(
             "app.main.llm_client.curate_pois",
             return_value=CurationResult(
                 recognized_ids=["node/5"], selected_ids=["node/5", "node/1"], street_ids=["way/99"]
             ),
         ):

        payload = {
            "lat": 50.8, "lon": 4.34, "radius_m": 1000,
            "poi_types": ["historic", "gastronomie"], "nb_poi": 2,
            "languages": ["fr"], "duration_min": 2, "trigger_radius_m": 40,
        }
        r = client.post("/generate-tour", json=payload)

        assert r.status_code == 200, r.text
        data = r.json()

        # node/5 (reconnu incontournable par le LLM) + node/1 (reste de la sélection) + rue
        assert len(data["pois"]) == 3
        ids = {p["id"] for p in data["pois"]}
        assert "node/5" in ids
        assert "node/1" in ids
        street_entry = next(p for p in data["pois"] if p["id"] == "way/99")
        assert street_entry["category"] == "rue"
        assert street_entry["trigger_radius_m"] == 100

        assert len(data["intro"]) == 1
        assert data["intro"][0]["language"] == "fr"
        assert data["intro"][0]["text"] == "Texte généré factice."


def test_generate_tour_works_without_street_or_neighborhood():
    with patch("app.main.overpass.fetch_pois", return_value=FAKE_POIS[:1]), \
         patch("app.main.overpass.fetch_street_candidates", return_value=[]), \
         patch("app.main.overpass.fetch_neighborhood_place", return_value=None), \
         patch("app.main.wikipedia.fetch_extract_for_poi", return_value=None), \
         patch("app.main.llm_client.generate_description", return_value="Texte."), \
         patch("app.main.llm_client.curate_pois", return_value=CurationResult(selected_ids=["node/1"])):

        payload = {"lat": 50.8, "lon": 4.34, "nb_poi": 1, "languages": ["fr"], "duration_min": 1}
        r = client.post("/generate-tour", json=payload)

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["pois"]) == 1
        assert data["intro"] == []


def test_generate_tour_falls_back_when_curation_fails():
    with patch("app.main.overpass.fetch_pois", return_value=FAKE_POIS), \
         patch("app.main.overpass.fetch_street_candidates", return_value=[]), \
         patch("app.main.overpass.fetch_neighborhood_place", return_value=None), \
         patch("app.main.wikipedia.fetch_extract_for_poi", return_value=None), \
         patch("app.main.llm_client.generate_description", return_value="Texte."), \
         patch("app.main.llm_client.curate_pois", side_effect=requests.exceptions.ConnectionError("down")):

        payload = {"lat": 50.8, "lon": 4.34, "nb_poi": 2, "languages": ["fr"], "duration_min": 1}
        r = client.post("/generate-tour", json=payload)

        assert r.status_code == 200, r.text
        assert len(r.json()["pois"]) == 2


def test_generate_tour_includes_verified_new_landmark_from_llm():
    """Le LLM peut citer un lieu qu'il connaît mais qu'Overpass n'a pas trouvé dans les
    candidats de base (section NOUVEAUX de la curation). Il ne fournit jamais de
    coordonnées : celles-ci doivent être retrouvées et vérifiées géographiquement
    (overpass.fetch_poi_by_name) avant que le lieu soit inclus dans le résultat."""
    new_poi = {
        "osm_id": "node/999", "name": "Lieu Mystère", "lat": 50.8001, "lon": 4.3401,
        "category": "attraction", "osm_facts": {},
    }
    with patch("app.main.overpass.fetch_pois", return_value=FAKE_POIS[:1]), \
         patch("app.main.overpass.fetch_street_candidates", return_value=[]), \
         patch("app.main.overpass.fetch_neighborhood_place", return_value=None), \
         patch("app.main.overpass.fetch_poi_by_name", return_value=new_poi) as mock_fetch_by_name, \
         patch("app.main.wikipedia.fetch_extract_for_poi", return_value=None), \
         patch("app.main.llm_client.generate_description", return_value="Texte."), \
         patch(
             "app.main.llm_client.curate_pois",
             return_value=CurationResult(selected_ids=["node/1"], new_landmark_names=["Lieu Mystère"]),
         ):

        payload = {"lat": 50.8, "lon": 4.34, "nb_poi": 2, "languages": ["fr"], "duration_min": 1}
        r = client.post("/generate-tour", json=payload)

        assert r.status_code == 200, r.text
        mock_fetch_by_name.assert_called_once()
        ids = {p["id"] for p in r.json()["pois"]}
        assert "node/999" in ids, "Le lieu proposé par le LLM et vérifié géographiquement doit être inclus"
        assert "node/1" in ids


def test_generate_tour_uses_cache_on_second_call():
    with patch("app.main.overpass.fetch_pois", return_value=FAKE_POIS[:1]), \
         patch("app.main.overpass.fetch_street_candidates", return_value=[]), \
         patch("app.main.overpass.fetch_neighborhood_place", return_value=None), \
         patch("app.main.wikipedia.fetch_extract_for_poi", return_value="Extrait."), \
         patch("app.main.llm_client.curate_pois", return_value=CurationResult(selected_ids=["node/1"])), \
         patch("app.main.llm_client.generate_description", return_value="Texte généré.") as mock_llm:

        payload = {"lat": 50.8, "lon": 4.34, "nb_poi": 1, "languages": ["fr"], "duration_min": 3}
        r1 = client.post("/generate-tour", json=payload)
        r2 = client.post("/generate-tour", json=payload)

        assert r1.status_code == 200 and r2.status_code == 200
        assert mock_llm.call_count == 1


if __name__ == "__main__":
    test_health()
    test_ranking_diversifies_categories()
    test_split_landmarks_separates_documented_pois()
    test_wikidata_only_is_not_an_automatic_landmark()
    test_fetch_poi_by_name_rejects_result_outside_radius()
    test_fetch_poi_by_name_accepts_result_inside_radius()
    test_generate_tour_never_drops_a_landmark_even_with_many_regular_pois()
    test_generate_tour_includes_street_and_intro()
    test_generate_tour_works_without_street_or_neighborhood()
    test_generate_tour_falls_back_when_curation_fails()
    test_generate_tour_includes_verified_new_landmark_from_llm()
    test_generate_tour_uses_cache_on_second_call()
    print("Tous les tests sont passés.")
