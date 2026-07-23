from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import cache, llm_client, overpass, ranking, wikipedia
from .models import PoiDescription, PoiOut, TourRequest, TourResponse

# Labels lisibles pour les tags OSM qu'on transmet au LLM comme faits fiables.
_OSM_TAG_LABELS = {
    "inscription": "Inscription gravée sur le lieu",
    "description": "Description OSM",
    "start_date": "Date",
    "subject": "Sujet commémoré",
    "memorial": "Type de mémorial",
    "heritage": "Statut patrimonial",
    "name:etymology": "Origine du nom",
}

# Rayon de déclenchement plancher pour le POI virtuel de rue : une anecdote de rue
# concerne toute sa longueur, pas juste un point précis, donc un rayon "normal" de POI
# (souvent 10-40m) serait trop étroit pour se déclencher de façon fiable en marchant.
STREET_POI_MIN_TRIGGER_RADIUS_M = 100


def _describe_osm_tags(osm_tags: Dict[str, str]) -> Optional[str]:
    lines = [
        f"{_OSM_TAG_LABELS[key]} : {value}"
        for key, value in osm_tags.items()
        if key in _OSM_TAG_LABELS
    ]
    return "\n".join(lines) if lines else None


def _fetch_pageviews_for_landmarks(landmarks: List[Dict], primary_lang: str) -> Dict[str, int]:
    """Résout et interroge le nombre de vues Wikipedia (30 derniers jours) pour chaque
    incontournable, en parallèle. Utilisé à la fois pour les incontournables "heritage"
    et pour ceux reconnus/proposés par le LLM (voir generate_tour) : dans les deux cas,
    on ne se fie pas au jugement du modèle pour l'ORDRE de priorité entre eux, seulement
    pour l'identification — le tri final se fait sur un vrai signal de popularité."""
    pageviews: Dict[str, int] = {}
    if not landmarks:
        return pageviews

    with ThreadPoolExecutor(max_workers=min(8, len(landmarks))) as executor:
        futures = {}
        for poi in landmarks:
            resolved = wikipedia.resolve_title(poi.get("osm_facts", {}), lang=primary_lang)
            if resolved:
                lang, title = resolved
                futures[poi["osm_id"]] = executor.submit(wikipedia.get_pageviews, lang, title)

        for osm_id, future in futures.items():
            try:
                pageviews[osm_id] = future.result()
            except Exception:
                pageviews[osm_id] = 0

    return pageviews


def _verify_new_landmark_names(
    names: List[str], lat: float, lon: float, radius_m: int, already_ids: set
) -> List[Dict]:
    """Vérifie géographiquement, en parallèle, les lieux que le LLM a cités de sa propre
    culture générale (voir llm_client.curate_pois, section NOUVEAUX) mais qui n'étaient
    pas dans les candidats déjà trouvés par Overpass. Le LLM ne fournit jamais de
    coordonnées : on les retrouve nous-mêmes via une recherche Overpass ciblée, restreinte
    à la zone exacte demandée par l'utilisateur (avec double vérification de la distance,
    voir overpass.fetch_poi_by_name). Un nom qui ne correspond à rien de réel dans la zone
    est simplement écarté, jamais inventé."""
    if not names:
        return []

    verified: List[Dict] = []
    with ThreadPoolExecutor(max_workers=min(4, len(names))) as executor:
        futures = [
            executor.submit(overpass.fetch_poi_by_name, name, lat, lon, radius_m) for name in names
        ]
        for future in futures:
            try:
                poi = future.result()
            except requests.RequestException:
                poi = None
            if poi and poi["osm_id"] not in already_ids:
                verified.append(poi)
                already_ids.add(poi["osm_id"])

    return verified


def _get_or_generate_description(
    cache_key: str, name: str, category: str, osm_facts: Dict[str, str],
    lat: float, lon: float, lang: str, duration_min: int,
) -> str:
    """Renvoie le texte en cache s'il existe déjà pour (cache_key, langue, durée), sinon
    rassemble les faits disponibles (tags OSM + Wikipedia géolocalisé) et fait rédiger
    le LLM.

    Factorisé pour être utilisé de façon identique par les 3 types de contenu qu'on
    génère maintenant : POI classiques, POI virtuel de rue, anecdote de quartier.
    """
    cached_text = cache.get_cached(cache_key, lang, duration_min)
    if cached_text:
        return cached_text

    osm_facts_text = _describe_osm_tags(osm_facts)
    wiki_extract = wikipedia.fetch_extract_for_poi(name, osm_facts, lat, lon, lang=lang)
    facts_parts = [p for p in (osm_facts_text, wiki_extract) if p]
    facts = "\n".join(facts_parts) if facts_parts else None

    text = llm_client.generate_description(name, category, facts, lang, duration_min)
    cache.save_cache(cache_key, lang, duration_min, text)
    return text


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache.init_db()
    yield


app = FastAPI(title="Visit backend", lifespan=lifespan)

# CORS ouvert : POC en réseau local, pas d'exposition publique pour l'instant.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/generate-tour", response_model=TourResponse)
def generate_tour(req: TourRequest) -> TourResponse:
    # Ces 3 appels réseau sont indépendants entre eux (POI classiques, rues, quartier) :
    # on les lance en parallèle plutôt que les uns après les autres. Ça ne change rien
    # aux générations IA qui suivent (toujours séquentielles sur ce modèle), mais évite
    # d'attendre inutilement sur les appels Overpass.
    with ThreadPoolExecutor(max_workers=3) as executor:
        raw_pois_future = executor.submit(
            overpass.fetch_pois, req.lat, req.lon, req.radius_m, req.poi_types
        )
        street_candidates_future = executor.submit(
            overpass.fetch_street_candidates, req.lat, req.lon, req.radius_m
        )
        neighborhood_future = executor.submit(overpass.fetch_neighborhood_place, req.lat, req.lon)

        try:
            raw_pois = raw_pois_future.result()
        except requests.RequestException:
            raw_pois = []

        try:
            street_candidates = street_candidates_future.result()
        except requests.RequestException:
            street_candidates = []

        try:
            neighborhood_name = neighborhood_future.result()
        except requests.RequestException:
            neighborhood_name = None

    # --- POI "attraction" classiques (monuments, musées, etc.) ---
    # Étape 0 : les incontournables "heritage" (statut patrimonial officiel, tag posé par
    # un contributeur OSM) sont toujours inclus en priorité, jamais soumis au tri de
    # diversité ni à la curation IA — un fait officiel reste un fait officiel, indépendant
    # de ce que le LLM aura pensé à reconnaître ou non.
    landmarks, regular_candidates = ranking.split_landmarks(raw_pois)

    primary_lang = req.languages[0] if req.languages else "fr"
    pageviews_heritage = (
        _fetch_pageviews_for_landmarks(landmarks, primary_lang) if len(landmarks) > req.nb_poi else {}
    )

    priority_landmarks = ranking.rank_landmarks(landmarks, req.lat, req.lon, pageviews_heritage)[: req.nb_poi]
    selected: List[Dict] = list(priority_landmarks)
    already_ids = {p["osm_id"] for p in selected}

    chosen_streets: List[Dict] = []
    remaining_slots = req.nb_poi - len(selected)

    if remaining_slots > 0:
        # Couche 1 (algorithmique, gratuite) : score + diversité entre catégories,
        # appliquée seulement au reste des candidats (pas déjà pris comme incontournable
        # "heritage"). Sert aussi de repli si la curation IA échoue.
        shortlist = ranking.rank_and_diversify(
            regular_candidates, req.lat, req.lon, req.radius_m, remaining_slots
        )
        fallback_ids = [p["osm_id"] for p in shortlist if p["osm_id"] not in already_ids]
        by_id = {p["osm_id"]: p for p in shortlist}

        # Couche 2 (IA, un seul appel) : reconnaît les incontournables parmi le vivier,
        # sélectionne le reste, propose d'éventuels lieux connus absents du vivier, et
        # choisit les rues à raconter. Exception large (pas juste requests.RequestException) :
        # une clé GROQ_API_KEY manquante lève une RuntimeError, qui doit retomber sur le
        # repli algorithmique comme n'importe quelle autre panne de ce service.
        try:
            curation = llm_client.curate_pois(
                shortlist, remaining_slots, street_candidates,
                req.lat, req.lon, req.radius_m, req.poi_types,
            )
        except Exception:
            curation = llm_client.CurationResult()

        # Vérification géographique des "NOUVEAUX" lieux proposés par le LLM (jamais de
        # coordonnées fournies par le modèle — on les retrouve nous-mêmes, restreint à la
        # zone exacte, avec double vérification du rayon). Ce qui ne correspond à rien de
        # réel dans la zone est écarté silencieusement.
        verified_new = _verify_new_landmark_names(
            curation.new_landmark_names, req.lat, req.lon, req.radius_m, already_ids | set(by_id.keys())
        )
        for poi in verified_new:
            by_id[poi["osm_id"]] = poi

        # Les incontournables reconnus dans le vivier + les nouveaux vérifiés forment un
        # même groupe, trié ENTRE EUX par vraies vues Wikipedia (pas par l'ordre dans
        # lequel le LLM les a cités) — priorisé avant le reste de la sélection.
        llm_landmark_ids = {i for i in curation.recognized_ids if i in by_id} | {
            p["osm_id"] for p in verified_new
        }
        llm_landmarks = [by_id[i] for i in llm_landmark_ids]
        pageviews_llm = _fetch_pageviews_for_landmarks(llm_landmarks, primary_lang) if llm_landmarks else {}
        prioritized_llm_landmarks = ranking.rank_landmarks(llm_landmarks, req.lat, req.lon, pageviews_llm)

        for poi in prioritized_llm_landmarks:
            if len(selected) >= req.nb_poi:
                break
            if poi["osm_id"] not in already_ids:
                selected.append(poi)
                already_ids.add(poi["osm_id"])

        # Complète avec le reste de la sélection de l'IA (hors incontournables déjà pris),
        # puis avec le repli algorithmique si toujours insuffisant.
        still_needed = req.nb_poi - len(selected)
        if still_needed > 0:
            ordered_fill_ids = [
                i for i in curation.selected_ids if i not in already_ids and i in by_id
            ]
            if len(ordered_fill_ids) < still_needed:
                extra = [i for i in fallback_ids if i not in already_ids and i not in ordered_fill_ids]
                ordered_fill_ids += extra
            for i in ordered_fill_ids[:still_needed]:
                selected.append(by_id[i])
                already_ids.add(i)

        street_by_id = {s["osm_id"]: s for s in street_candidates}
        chosen_streets = [street_by_id[i] for i in curation.street_ids if i in street_by_id]

    result_pois: List[PoiOut] = []
    for poi in selected:
        descriptions = [
            PoiDescription(
                language=lang,
                text=_get_or_generate_description(
                    poi["osm_id"], poi["name"], poi["category"], poi.get("osm_facts", {}),
                    poi["lat"], poi["lon"], lang, req.duration_min,
                ),
            )
            for lang in req.languages
        ]
        result_pois.append(
            PoiOut(
                id=poi["osm_id"],
                name=poi["name"],
                lat=poi["lat"],
                lon=poi["lon"],
                category=poi["category"],
                trigger_radius_m=req.trigger_radius_m,
                descriptions=descriptions,
            )
        )

    # --- POI virtuel : anecdote(s) sur la/les rue(s) elle(s)-même(s) ---
    # (chosen_streets déjà sélectionnées par la curation IA ci-dessus, 0 à 2, additives :
    # elles ne consomment pas le budget nb_poi, comme avant.)
    for street in chosen_streets:
        descriptions = [
            PoiDescription(
                language=lang,
                text=_get_or_generate_description(
                    street["osm_id"], street["name"], "rue", street.get("osm_facts", {}),
                    street["lat"], street["lon"], lang, req.duration_min,
                ),
            )
            for lang in req.languages
        ]
        result_pois.append(
            PoiOut(
                id=street["osm_id"],
                name=street["name"],
                lat=street["lat"],
                lon=street["lon"],
                category="rue",
                trigger_radius_m=max(req.trigger_radius_m, STREET_POI_MIN_TRIGGER_RADIUS_M),
                descriptions=descriptions,
            )
        )

    # --- Anecdote de quartier : PAS géofencée, livrée une fois au lancement ---
    # (neighborhood_name déjà résolu en parallèle plus haut, via Overpass)
    intro: List[PoiDescription] = []
    if neighborhood_name:
        intro = [
            PoiDescription(
                language=lang,
                text=_get_or_generate_description(
                    f"neighborhood/{neighborhood_name}", neighborhood_name, "quartier", {},
                    req.lat, req.lon, lang, req.duration_min,
                ),
            )
            for lang in req.languages
        ]

    return TourResponse(intro=intro, pois=result_pois)
