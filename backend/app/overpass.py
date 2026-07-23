"""Récupération des POI bruts d'une zone via l'API Overpass (données OpenStreetMap, gratuit)."""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import requests

from .geo import haversine_m

# Plusieurs mirrors publics : si le premier est surchargé (504/429), on bascule sur le
# suivant plutôt que d'échouer directement. Ce sont les 3 instances publiques les plus
# utilisées de la communauté OSM.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

_HEADERS = {
    "User-Agent": "VisitApp/0.1 (POC personnel, contact: dorsantkint@gmail.com)",
    "Accept": "application/json",
}

# Mapping "type demandé par l'utilisateur" -> filtres de tag Overpass. Chaque fragment
# précise aussi le type d'élément OSM à chercher :
#   - "node"  : recherche simple par point, rapide (utilisé pour ce qui est presque
#     toujours cartographié comme un point : œuvre d'art, point de vue, restaurant...)
#   - "nw"    : cherche aussi les polygones (bâtiments), pour ne pas rater des lieux
#     emblématiques cartographiés comme un contour plutôt qu'un point simple (ex: un
#     hôtel de ville, une église). Plus coûteux, donc réservé aux catégories qui en
#     ont vraiment besoin.
# Volontairement PAS "nwr" (qui inclurait aussi les "relations") : dans un centre
# historique dense, résoudre la géométrie de grosses relations (ex: l'ensemble classé
# "Grand-Place") peut à lui seul saturer le délai de la requête et faire échouer la
# recherche des bâtiments individuels qu'on veut justement trouver.
TYPE_TAG_MAP: Dict[str, List[Tuple[str, str]]] = {
    "monument": [
        ("nw", '["historic"]'),
        ("nw", '["amenity"="townhall"]'),
        ("nw", '["heritage"]'),
        # "wikidata", "wikipedia" et "tourism=attraction" restent en recherche "node"
        # seule : en "way" (bâtiments), ces tags sont bien trop répandus dans un centre
        # historique dense (ça touche énormément de choses, pas seulement les bâtiments
        # notables) et ont fait dépasser le budget temps d'Overpass, avec pour résultat
        # des requêtes qui échouent entièrement (0 résultat) après avoir épuisé les 3
        # mirrors. On accepte de rater ainsi un bâtiment qui n'aurait NI tag
        # historic/heritage/townhall NI présence en tant que node, plutôt que de
        # risquer de tout faire échouer.
        ("node", '["wikidata"]'),
        ("node", '["wikipedia"]'),
        ("node", '["tourism"="attraction"]'),
    ],
    "historic": [
        ("nw", '["historic"]'),
        ("nw", '["heritage"]'),
        ("node", '["wikidata"]'),
        ("node", '["wikipedia"]'),
    ],
    "artwork": [("node", '["tourism"="artwork"]')],
    "street_art": [("node", '["tourism"="artwork"]["artwork_type"~"mural|graffiti|stencil|street_art"]')],
    "museum": [("node", '["tourism"="museum"]')],
    "viewpoint": [("node", '["tourism"="viewpoint"]')],
    "religious": [("nw", '["amenity"="place_of_worship"]')],
    "gastronomie": [("node", '["amenity"~"restaurant|cafe|bar"]')],
}

# Catégories "commerce alimentaire" : si l'utilisateur n'a pas coché "gastronomie", on
# les exclut systématiquement du résultat — même si un café/bar/resto a été remonté par
# la recherche élargie wikidata/wikipedia destinée aux monuments (un café historique ou
# une chaîne connue peut très bien avoir sa propre fiche Wikidata sans être ce que
# l'utilisateur avait demandé).
_FOOD_DRINK_CATEGORIES = {"restaurant", "cafe", "bar", "pub", "fast_food", "biergarten", "food_court", "ice_cream"}

# Tags OSM qui contiennent parfois de vrais faits utilisables tels quels (inscription
# gravée, date, sujet commémoré, lien vers une fiche Wikipedia/Wikidata précise posé à la
# main par un contributeur OSM). On les récupère pour éviter que le LLM ne travaille dans
# le vide sur les POI qui n'ont pas de page Wikipedia dédiée. Ça inclut "name:etymology",
# qui est particulièrement utile sur les rues (way) pour l'anecdote de rue.
RELEVANT_TAG_KEYS = [
    "description",
    "inscription",
    "start_date",
    "subject",
    "memorial",
    "heritage",
    "wikipedia",
    "wikidata",
    "name:etymology",
]


def _query_overpass(query: str, timeout: int = 35) -> Dict[str, Any]:
    """POST la requête Overpass QL, avec bascule sur un mirror de secours en cas
    d'erreur (l'instance publique principale est parfois surchargée : 429/504).

    `timeout` est le délai HTTP maximum PAR mirror tenté (pas le total). Par défaut 35s,
    adapté à la recherche principale de POI (fetch_pois), qui peut légitimement prendre
    du temps sur une requête large/dense. Les fonctions secondaires (nom de quartier,
    rues, vérification d'un lieu par nom) passent un timeout beaucoup plus court : ce
    sont des compléments, pas le cœur de la sélection, et un mirror lent sur l'un de ces
    appels ne doit jamais faire attendre l'utilisateur 30-50 secondes pour un simple nom
    de quartier ou une rue en plus. Avec 3 mirrors, le pire cas reste borné à environ
    3 × timeout + 2s de pause entre tentatives."""
    last_error: Exception = RuntimeError("Aucun mirror Overpass disponible")
    for attempt, url in enumerate(OVERPASS_URLS):
        try:
            response = requests.post(url, data={"data": query}, timeout=timeout, headers=_HEADERS)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < len(OVERPASS_URLS) - 1:
                time.sleep(1)  # petite pause avant de basculer sur le mirror suivant
            continue
    raise last_error


# Timeout court pour les appels Overpass "secondaires" (nom de quartier, rues,
# vérification d'un nom proposé par le LLM) : ce sont des compléments à la visite, pas
# le cœur de la sélection de POI, donc pas question de laisser un mirror lent faire
# attendre l'utilisateur des dizaines de secondes pour ça.
_SECONDARY_QUERY_TIMEOUT = 8


# Plafond du nombre de POI bruts renvoyés par Overpass. Volontairement large et fixe
# (indépendant de nb_poi) : "out ... {limit}" ne fait que tronquer la RÉPONSE renvoyée,
# le serveur Overpass calcule le résultat complet dans tous les cas — augmenter ce
# plafond ne coûte donc rien en performance côté Overpass, juste une réponse un peu
# plus grosse. L'ancien calcul (nb_poi * 5) tronquait le résultat AVANT tout tri, ce qui
# pouvait faire perdre des lieux pertinents dans une zone dense (ex: Grand-Place) avant
# même que l'algorithme de sélection n'ait son mot à dire.
DEFAULT_RAW_POI_LIMIT = 200


def _fetch_fragment(
    lat: float, lon: float, radius_m: int, elem_type: str, tag_filter: str, limit: int
) -> List[Dict[str, Any]]:
    """Exécute UN SEUL fragment de recherche (un type d'élément + un filtre de tag),
    plutôt que de le fusionner dans la requête combinée habituelle. Sert uniquement à
    mesurer précisément le temps de CHAQUE filtre pris isolément (voir fetch_pois) — sans
    ça, on ne voit qu'un temps total agrégé et on doit deviner quel filtre est en cause.

    Une panne réseau sur un fragment ne fait pas échouer les autres : on log l'échec et
    on renvoie une liste vide pour celui-là, comme un simple "0 résultat" pour ce filtre."""
    query = f"""
    [out:json][timeout:30];
    {elem_type}{tag_filter}(around:{radius_m},{lat},{lon});
    out center {limit};
    """
    label = f"{elem_type}{tag_filter}"
    started_at = time.perf_counter()
    try:
        data = _query_overpass(query)
        elements = data.get("elements", [])
        print(f"[timing][overpass-fragment] {label} : {time.perf_counter() - started_at:.2f}s ({len(elements)} éléments)")
        return elements
    except requests.RequestException as exc:
        print(f"[timing][overpass-fragment] {label} : ÉCHEC après {time.perf_counter() - started_at:.2f}s ({exc})")
        return []


def fetch_pois(
    lat: float, lon: float, radius_m: int, poi_types: List[str], limit: int = DEFAULT_RAW_POI_LIMIT
) -> List[Dict[str, Any]]:
    filters: List[Tuple[str, str]] = [
        f for t in poi_types if t in TYPE_TAG_MAP for f in TYPE_TAG_MAP[t]
    ]
    filters = list(dict.fromkeys(filters))  # dédoublonne en gardant l'ordre
    if not filters:
        filters = [("nw", '["historic"]')]

    # "nw" est développé en deux fragments séparés (node + way), syntaxe Overpass
    # garantie standard, plutôt que de parier sur un raccourci combiné.
    fragments: List[Tuple[str, str]] = []
    for elem_type, tag_filter in filters:
        elem_types = ("node", "way") if elem_type == "nw" else (elem_type,)
        for et in elem_types:
            fragments.append((et, tag_filter))

    # Étape de diagnostic (temporaire, demandée explicitement) : chaque fragment part
    # dans SA PROPRE requête Overpass, en parallèle, plutôt que fusionnés en une seule
    # requête combinée comme avant. Ça permet de voir dans les logs quel filtre précis
    # est lent pour un type de POI donné, plutôt qu'un seul temps total agrégé. En
    # parallèle pour ne pas payer la somme de tous les fragments un par un.
    raw_elements_by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(fragments))) as executor:
        futures = [
            executor.submit(_fetch_fragment, lat, lon, radius_m, et, tag_filter, limit)
            for et, tag_filter in fragments
        ]
        for future in futures:
            for el in future.result():
                # Un même élément peut être retrouvé par plusieurs fragments (ex: un
                # nœud avec à la fois wikidata et wikipedia) — dédoublonné ici puisque
                # ce n'est plus fait automatiquement par un seul bloc "union" Overpass.
                raw_elements_by_key[(el["type"], el["id"])] = el

    pois: List[Dict[str, Any]] = []
    for el in raw_elements_by_key.values():
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue  # on ignore les POI sans nom, pas exploitables pour une description

        category = next(
            (tags[k] for k in ("historic", "tourism", "amenity") if k in tags),
            "poi",
        )

        osm_facts = {k: tags[k] for k in RELEVANT_TAG_KEYS if k in tags}

        pois.append(
            {
                "osm_id": f"{el['type']}/{el['id']}",
                "name": name,
                "lat": el.get("lat") or el.get("center", {}).get("lat"),
                "lon": el.get("lon") or el.get("center", {}).get("lon"),
                "category": category,
                "osm_facts": osm_facts,
            }
        )

    if "gastronomie" not in poi_types:
        pois = [p for p in pois if p["category"] not in _FOOD_DRINK_CATEGORIES]

    return pois


def fetch_street_candidates(
    lat: float, lon: float, radius_m: int, max_candidates: int = 8
) -> List[Dict[str, Any]]:
    """Cherche les rues nommées disponibles autour du centre, et les renvoie comme des
    "POI virtuels" (même forme qu'un POI classique, mais ça représente la rue elle-même,
    pas un lieu ponctuel) — pour porter une anecdote sur une rue plutôt que sur un bâtiment.

    Renvoie PLUSIEURS candidates (au lieu d'une seule rue choisie ici par proximité) :
    c'est la couche de curation (LLM, dans main.py) qui décide ensuite laquelle (ou
    lesquelles, 0 à 2) valent vraiment la peine d'être racontées. Triées par pertinence
    probable (fait exploitable d'abord, puis proximité) pour garder le prompt de curation
    court même si beaucoup de rues sont trouvées.
    """
    query = f"""
    [out:json][timeout:25];
    way[highway][name](around:{radius_m},{lat},{lon});
    out center 20;
    """

    try:
        data = _query_overpass(query, timeout=_SECONDARY_QUERY_TIMEOUT)
    except requests.RequestException:
        return []

    candidates: List[Dict[str, Any]] = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        center = el.get("center")
        if not name or not center:
            continue

        osm_facts = {k: tags[k] for k in RELEVANT_TAG_KEYS if k in tags}

        candidates.append(
            {
                "osm_id": f"way/{el['id']}",
                "name": name,
                "lat": center["lat"],
                "lon": center["lon"],
                "category": "rue",
                "osm_facts": osm_facts,
            }
        )

    candidates.sort(key=lambda c: (0 if c["osm_facts"] else 1, haversine_m(lat, lon, c["lat"], c["lon"])))
    return candidates[:max_candidates]


# Tags "place" utilisés pour résoudre un nom de quartier/ville, en remplacement de
# Nominatim (dont la politique d'usage public impose une limite stricte de 1 requête/
# seconde, documentée — un vrai risque de blocage à l'échelle). Cascade en deux temps :
# rayon serré d'abord pour du fin (quartier), rayon large ensuite si rien trouvé (ville).
_PLACE_TAGS_FINE = ("suburb", "neighbourhood", "quarter", "city_district")
_PLACE_TAGS_BROAD = ("town", "city", "village")


def _fetch_place_name(lat: float, lon: float, place_tags: Tuple[str, ...], radius_m: int) -> Optional[str]:
    tag_pattern = "|".join(place_tags)
    query = f"""
    [out:json][timeout:20];
    node["place"~"^({tag_pattern})$"](around:{radius_m},{lat},{lon});
    out;
    """
    try:
        data = _query_overpass(query, timeout=_SECONDARY_QUERY_TIMEOUT)
    except requests.RequestException:
        return None

    candidates = [
        (tags["name"], el["lat"], el["lon"])
        for el in data.get("elements", [])
        for tags in [el.get("tags", {})]
        if tags.get("name") and el.get("lat") is not None and el.get("lon") is not None
    ]
    if not candidates:
        return None

    closest = min(candidates, key=lambda c: haversine_m(lat, lon, c[1], c[2]))
    return closest[0]


def fetch_neighborhood_place(lat: float, lon: float) -> Optional[str]:
    """Résout un nom de quartier/ville à partir de coordonnées, via des nœuds Overpass
    `place=*` plutôt que Nominatim. Essaie d'abord un niveau fin (quartier) sur un rayon
    serré, puis retombe sur un niveau plus large (ville) avec un rayon plus généreux si
    rien n'a été trouvé — toutes les zones n'ont pas un `place=suburb` bien cartographié.
    """
    fine = _fetch_place_name(lat, lon, _PLACE_TAGS_FINE, radius_m=1500)
    if fine:
        return fine
    return _fetch_place_name(lat, lon, _PLACE_TAGS_BROAD, radius_m=8000)


def fetch_poi_by_name(name: str, lat: float, lon: float, radius_m: int) -> Optional[Dict[str, Any]]:
    """Recherche ciblée par nom, restreinte STRICTEMENT à la zone de recherche de
    l'utilisateur — sert à vérifier un lieu que le LLM a cité de sa propre culture
    générale (voir llm_client.curate_pois) avant de lui faire confiance. Le LLM ne
    fournit jamais de coordonnées lui-même : on les retrouve nous-mêmes ici, ou on
    rejette la proposition si rien de correspondant n'existe réellement dans la zone.

    Double vérification de la distance : le filtre `around` d'Overpass est censé déjà
    garantir que le résultat est dans le rayon, mais on revérifie nous-mêmes
    explicitement par prudence (même logique que la géo-vérification déjà appliquée à
    Wikipedia) — un résultat hors rayon est rejeté même si Overpass l'a renvoyé.
    """
    escaped = re.escape(name)
    query = f"""
    [out:json][timeout:20];
    (
      node["name"~"{escaped}",i](around:{radius_m},{lat},{lon});
      way["name"~"{escaped}",i](around:{radius_m},{lat},{lon});
    );
    out center 5;
    """
    try:
        data = _query_overpass(query, timeout=_SECONDARY_QUERY_TIMEOUT)
    except requests.RequestException:
        return None

    best: Optional[Dict[str, Any]] = None
    best_distance: Optional[float] = None
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        el_name = tags.get("name")
        if not el_name:
            continue
        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lon = el.get("lon") or el.get("center", {}).get("lon")
        if el_lat is None or el_lon is None:
            continue

        distance = haversine_m(lat, lon, el_lat, el_lon)
        if distance > radius_m:
            # Garde-fou explicite : on ne fait confiance ni au LLM (aucune coordonnée
            # fournie) ni au filtre `around` seul — on rejette tout résultat qui, une
            # fois sa position réelle vérifiée, tombe hors de la zone demandée.
            continue

        if best is None or distance < best_distance:
            category = next((tags[k] for k in ("historic", "tourism", "amenity") if k in tags), "poi")
            osm_facts = {k: tags[k] for k in RELEVANT_TAG_KEYS if k in tags}
            best = {
                "osm_id": f"{el['type']}/{el['id']}",
                "name": el_name,
                "lat": el_lat,
                "lon": el_lon,
                "category": category,
                "osm_facts": osm_facts,
            }
            best_distance = distance

    return best
