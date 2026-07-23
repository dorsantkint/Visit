"""Sélection algorithmique des POI : diversité entre les types demandés + priorité aux
POI qui ont de vraies chances de produire une description factuelle (tag wikidata/wikipedia
ou tags OSM descriptifs), plutôt que l'ordre arbitraire renvoyé par Overpass.

Cette couche ne fait aucun appel réseau ni IA : c'est un tri/filtre pur en mémoire,
donc gratuit et instantané. Elle sert de base fiable, et aussi de filet de sécurité si
la curation IA (couche suivante, dans ollama_client.py) échoue ou est indisponible.
"""
from typing import Dict, List, Optional, Tuple

from .geo import haversine_m

# Tags qui indiquent un POI "documenté", donc plus susceptible de donner une bonne
# description factuelle plutôt que du remplissage générique.
_RICH_TAG_KEYS = ("inscription", "start_date", "subject", "description", "heritage", "name:etymology")

# Seul un statut patrimonial officiel (heritage = classé/inventorié) déclenche
# l'inclusion garantie, automatique, sans passer par le tri de diversité ni l'IA.
# Volontairement PAS wikidata/wikipedia seuls ici : ces tags signalent juste "quelqu'un
# a documenté ce truc quelque part" (une chaîne de restaurant, un arrêt de bus...), pas
# forcément un intérêt touristique réel. Les inclure dans le contournement automatique
# a laissé passer du bruit sans intérêt dès que la zone de recherche s'agrandissait.
# Ils restent un signal fort (voir le bonus dans _score ci-dessous) mais continuent de
# passer par le tri + la curation IA, qui peuvent légitimement les écarter.
_LANDMARK_TAG_KEYS = ("heritage",)


def _score(poi: Dict, center_lat: float, center_lon: float, max_distance_m: float) -> float:
    osm_facts = poi.get("osm_facts", {})
    score = 0.0

    # Gros bonus si le POI a un lien Wikidata/Wikipedia explicite : signal fort qu'il
    # existe de vraies informations fiables dessus (pas juste un point anonyme).
    if "wikidata" in osm_facts or "wikipedia" in osm_facts:
        score += 5.0

    # Petit bonus par tag descriptif présent (inscription, date, sujet...).
    score += sum(1.0 for k in _RICH_TAG_KEYS if k in osm_facts)

    # Léger malus proportionnel à la distance : à richesse égale, on préfère les POI
    # plus proches du centre pour garder une balade compacte.
    if max_distance_m > 0:
        distance = haversine_m(center_lat, center_lon, poi["lat"], poi["lon"])
        score -= (distance / max_distance_m) * 2.0

    return score


def is_landmark(poi: Dict) -> bool:
    osm_facts = poi.get("osm_facts", {})
    return any(k in osm_facts for k in _LANDMARK_TAG_KEYS)


def split_landmarks(candidates: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Sépare les "incontournables" (statut patrimonial officiel, heritage) du reste.

    Signal volontairement étroit et purement factuel (voir _LANDMARK_TAG_KEYS) : mieux
    vaut rater occasionnellement une inclusion automatique méritée que systématiquement
    laisser passer du bruit sans intérêt touristique dès que la zone de recherche
    s'agrandit.
    """
    landmarks = [p for p in candidates if is_landmark(p)]
    regular = [p for p in candidates if not is_landmark(p)]
    return landmarks, regular


def rank_landmarks(
    landmarks: List[Dict],
    center_lat: float,
    center_lon: float,
    pageviews: Optional[Dict[str, int]] = None,
) -> List[Dict]:
    """Trie les incontournables (tous déjà "heritage" par construction, voir
    _LANDMARK_TAG_KEYS) par priorité :
    1) popularité réelle (vues Wikipedia sur les 30 derniers jours, si disponible) —
       départage plusieurs incontournables entre eux quand il y en a plus que de
       places disponibles (ex: plusieurs bâtiments classés sur une même place)
    2) proximité, en dernier recours

    `pageviews` est optionnel (dict osm_id -> nombre de vues) : cette fonction reste
    utilisable sans appel réseau si on ne l'a pas calculé (ex: en test).
    """
    pageviews = pageviews or {}

    def priority(poi: Dict) -> Tuple[int, float]:
        views = pageviews.get(poi["osm_id"], 0)
        distance = haversine_m(center_lat, center_lon, poi["lat"], poi["lon"])
        return (-views, distance)

    return sorted(landmarks, key=priority)


def rank_and_diversify(
    candidates: List[Dict], center_lat: float, center_lon: float, radius_m: float, nb_poi: int
) -> List[Dict]:
    """Trie les candidats par score de pertinence, puis les répartit en alternant entre
    les différentes catégories présentes (round-robin) pour éviter qu'un seul type de POI
    ne monopolise la sélection.

    Renvoie un vivier pré-filtré plus grand que nb_poi (jusqu'à 3x) : ce n'est pas encore
    la sélection finale, la couche suivante (IA ou juste [:nb_poi]) choisit dedans.
    """
    if not candidates:
        return []

    scored = sorted(
        candidates,
        key=lambda p: _score(p, center_lat, center_lon, radius_m),
        reverse=True,
    )

    buckets: Dict[str, List[Dict]] = {}
    for poi in scored:
        buckets.setdefault(poi["category"], []).append(poi)

    categories = list(buckets.keys())
    diversified: List[Dict] = []
    # Plafond relevé (auparavant nb_poi * 3) : depuis qu'overpass.fetch_pois() ne tronque
    # plus le résultat brut en amont, ce vivier est construit à partir d'un ensemble de
    # candidats beaucoup plus complet. Une valeur fixe généreuse laisse la couche de
    # curation LLM (qui reconnaît aussi les incontournables, voir llm_client.curate_pois)
    # voir un choix vraiment représentatif de la zone, tout en gardant le prompt borné.
    shortlist_size = min(len(candidates), max(nb_poi * 3, 60))

    i = 0
    while len(diversified) < shortlist_size and any(buckets.values()):
        category = categories[i % len(categories)]
        if buckets[category]:
            diversified.append(buckets[category].pop(0))
        i += 1

    return diversified
