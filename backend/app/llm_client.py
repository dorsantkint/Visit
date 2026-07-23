"""Appel à l'API Groq (inférence rapide sur modèles ouverts) pour rédiger la
description d'un POI et pour la curation des POI sélectionnés.

Le modèle ne fait que RÉDIGER à partir des faits fournis (extrait Wikipedia) : il
n'invente pas les faits eux-mêmes. Ça limite fortement les hallucinations.

Sécurité : la clé API est lue depuis la variable d'environnement GROQ_API_KEY,
jamais codée en dur ici. Le repo GitHub associé à ce projet est public — une clé
en dur dans le code y serait exposée publiquement. Voir SETUP.md pour la définir
sur ta machine.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"

# Débit oral moyen pour une lecture naturelle en FR/EN.
WORDS_PER_MINUTE = 130


def _api_key() -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY n'est pas définie. Configure cette variable d'environnement "
            "avant de lancer le backend (voir backend/SETUP.md)."
        )
    return key


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _build_prompt(poi_name: str, category: str, facts: Optional[str], language: str, duration_min: float) -> str:
    target_words = int(WORDS_PER_MINUTE * duration_min)

    if language == "fr":
        lang_label = "français"
        language_rule = (
            "Rédige INTÉGRALEMENT en français, du début à la fin, sans aucun mot ni "
            "expression dans une autre langue. Traduis systématiquement les noms de lieux "
            "qui ont un équivalent français usuel (dis \"Hôtel de Ville\", jamais \"City "
            "Hall\" ni \"ville hall\" ; dis \"Grand-Place\", pas \"Great Market\"). "
            "N'utilise un terme étranger que s'il s'agit d'un nom propre qui n'a "
            "réellement aucune traduction française."
        )
    else:
        lang_label = "English"
        language_rule = (
            "Write ENTIRELY in English, from start to finish, with no words or phrases "
            "in another language. Translate place names that have a common English "
            "equivalent. Only keep a foreign term if it's a proper name with no real "
            "English equivalent."
        )

    if facts:
        facts_block = facts
        grounding_rule = (
            "Base-toi UNIQUEMENT sur les faits ci-dessus. Tu peux les reformuler et les mettre "
            "en contexte, mais n'ajoute aucune date, aucun style architectural, aucun nom de "
            "personne ou anecdote qui ne figure pas explicitement dans ces faits."
        )
    else:
        facts_block = "Aucune information fiable disponible sur ce lieu précis."
        grounding_rule = (
            "IMPORTANT : tu n'as aucun fait vérifié sur ce lieu précis. Il est STRICTEMENT "
            "INTERDIT d'inventer un siècle, une date, un style architectural (ex: baroque, "
            "gothique), un nom de personne ou une anecdote historique — même au conditionnel "
            "ou avec des formules comme \"peut-être\" ou \"probablement\", qui restent de "
            "l'invention déguisée. N'invente pas non plus de détails sensoriels ou de décor "
            "(couleurs des murs, odeurs, sons, ambiance intérieure) que tu ne peux pas "
            "connaître. Décris uniquement ce qui est déductible du nom et de la catégorie du "
            "lieu, et l'ambiance générale de ce type d'endroit dans une ville, sans jamais "
            "donner l'impression que c'est un fait vérifié sur CE lieu précis."
        )

    return f"""Tu es un guide touristique qui rédige des commentaires audio pour une visite de ville.
Rédige en {lang_label} une description orale du point d'intérêt suivant, à lire à voix haute,
d'environ {target_words} mots.

Nom du lieu : {poi_name}
Catégorie : {category}
Faits disponibles : {facts_block}

Règle de langue : {language_rule}

Règle de fiabilité : {grounding_rule}

Consignes : ton engageant et naturel à l'oral, pas de listes à puces, pas de titre,
uniquement le texte à lire, sans guillemets autour, en un seul bloc de texte continu
(pas de sauts de ligne entre des paragraphes)."""


def _clean_for_speech(text: str) -> str:
    """Nettoie le texte avant de l'envoyer au TTS : les sauts de ligne ne posent pas de
    vrai risque à l'oral (le moteur TTS les traite comme un espace/une pause), mais on
    les normalise quand même par propreté et pour éviter tout comportement inattendu
    selon le moteur TTS utilisé côté téléphone."""
    text = re.sub(r"\s*\n+\s*", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def generate_description(
    poi_name: str, category: str, facts: Optional[str], language: str, duration_min: float
) -> str:
    prompt = _build_prompt(poi_name, category, facts, language, duration_min)

    # Plafond dur sur le nombre de tokens générés, cohérent avec la durée demandée
    # (avec une bonne marge). Groq étant très rapide, ce plafond sert surtout à éviter
    # tout dérapage plutôt qu'à contrôler le temps de réponse.
    target_words = int(WORDS_PER_MINUTE * duration_min)
    max_tokens = int(target_words * 1.6) + 50

    response = requests.post(
        GROQ_URL,
        headers=_headers(),
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        },
        timeout=60,  # Groq est rapide : un timeout large n'est plus nécessaire
    )
    response.raise_for_status()
    raw_text = response.json()["choices"][0]["message"]["content"].strip()
    return _clean_for_speech(raw_text)


@dataclass
class CurationResult:
    """Résultat de la curation étendue : le modèle ne fait plus seulement "choisir dans
    une liste", il (1) reconnaît les incontournables parmi les candidats déjà localisés,
    (2) sélectionne les meilleurs pour remplir les places restantes, (3) cite d'éventuels
    lieux incontournables qu'il connaît mais qu'Overpass n'a pas trouvés (nom seul,
    jamais de coordonnées — c'est à l'appelant de les vérifier géographiquement avant de
    leur faire confiance), et (4) choisit 0 à 2 rues à raconter parmi les candidates."""

    recognized_ids: List[str] = field(default_factory=list)
    selected_ids: List[str] = field(default_factory=list)
    new_landmark_names: List[str] = field(default_factory=list)
    street_ids: List[str] = field(default_factory=list)


def _facts_summary(poi: Dict) -> str:
    facts = poi.get("osm_facts", {})
    if not facts:
        return "aucune"
    return "; ".join(f"{k}={v}" for k, v in facts.items())


def _build_curation_prompt(
    candidates: List[Dict],
    nb_poi: int,
    street_candidates: List[Dict],
    lat: float,
    lon: float,
    radius_m: int,
    poi_types: List[str],
) -> str:
    candidate_lines = [
        f"- id={poi['osm_id']} | {poi['name']} | catégorie: {poi['category']} | faits: {_facts_summary(poi)}"
        for poi in candidates
    ]
    candidates_block = "\n".join(candidate_lines) if candidate_lines else "(aucun candidat)"

    street_lines = [
        f"- id={s['osm_id']} | {s['name']} | faits: {_facts_summary(s)}" for s in street_candidates
    ]
    street_block = "\n".join(street_lines) if street_lines else "(aucune rue candidate)"

    themes = ", ".join(poi_types) if poi_types else "tous types"

    return f"""Tu es un guide touristique local expert, avec une très bonne connaissance des lieux
réellement emblématiques des villes.

Zone de recherche précise : un rayon de {radius_m} mètres autour du point de coordonnées
({lat}, {lon}). Thèmes demandés par l'utilisateur : {themes}.

Voici les lieux déjà localisés dans cette zone (trouvés via OpenStreetMap) :
{candidates_block}

Voici des rues nommées disponibles dans la même zone :
{street_block}

Effectue ces 4 tâches, dans cet ordre :

1) INCONTOURNABLES : parmi les lieux listés ci-dessus (pas les rues), lesquels reconnais-tu,
avec ta connaissance générale, comme des lieux vraiment célèbres/incontournables — pas
seulement "présents sur la carte", mais réellement connus pour être visités ? Ne considère
que les lieux correspondant aux thèmes demandés.

2) SELECTION : choisis au total {nb_poi} lieux parmi la liste ci-dessus pour une visite à pied
intéressante et diversifiée, en priorité ceux identifiés en (1), puis les plus pertinents
parmi le reste selon les thèmes demandés.

3) NOUVEAUX : si tu connais, avec ta culture générale, d'AUTRES lieux vraiment incontournables
correspondant aux thèmes demandés et situés PRÉCISÉMENT dans cette zone (ce rayon exact
autour de ces coordonnées, pas la ville en général) mais qui n'apparaissent PAS dans la
liste ci-dessus, cite leur nom uniquement (jamais de coordonnées, tu ne les connais pas avec
certitude). Maximum 3 propositions. Si tu n'es pas certain qu'un lieu soit précisément dans
cette zone, ne le propose pas — mieux vaut ne rien dire qu'une suggestion hors zone.

4) RUES : parmi les rues listées, choisis 0, 1 ou 2 rues qui ont une vraie anecdote ou un
intérêt touristique à raconter (pas juste une rue quelconque).

Réponds STRICTEMENT dans ce format, une ligne par section, sans aucun autre texte :
INCONTOURNABLES: id1, id2
SELECTION: id1, id2, id3
NOUVEAUX: Nom du lieu 1, Nom du lieu 2
RUES: id1

Si une section est vide, écris juste "aucun" après les deux-points. N'utilise que les
identifiants listés ci-dessus (commençant par "id="), n'en invente aucun."""


def _parse_curation_response(raw: str, valid_ids: set, valid_street_ids: set) -> CurationResult:
    result = CurationResult()
    for line in raw.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        label, _, content = line.partition(":")
        label = label.strip().upper()
        items = [c.strip() for c in content.split(",") if c.strip() and c.strip().lower() != "aucun"]

        if label == "INCONTOURNABLES":
            result.recognized_ids = [i for i in items if i in valid_ids]
        elif label == "SELECTION":
            result.selected_ids = [i for i in items if i in valid_ids]
        elif label == "NOUVEAUX":
            result.new_landmark_names = items[:3]
        elif label == "RUES":
            result.street_ids = [i for i in items if i in valid_street_ids][:2]

    return result


def curate_pois(
    candidates: List[Dict],
    nb_poi: int,
    street_candidates: List[Dict],
    lat: float,
    lon: float,
    radius_m: int,
    poi_types: List[str],
) -> CurationResult:
    """Demande au modèle de (1) reconnaître les incontournables parmi le vivier déjà
    pré-filtré/diversifié par l'algorithme (ranking.py), (2) sélectionner les nb_poi
    meilleurs, (3) citer d'éventuels incontournables connus mais absents du vivier
    (nom seul — jamais de coordonnées inventées), (4) choisir 0-2 rues à raconter.

    Le modèle ne peut choisir des identifiants QUE parmi les listes fermées fournies :
    il ne peut pas inventer de POI ni de rue. Les "NOUVEAUX" lieux ne sont que des noms ;
    c'est à l'appelant (main.py) de les vérifier géographiquement via
    overpass.fetch_poi_by_name avant de leur faire confiance. Le risque d'erreur ici,
    c'est au pire une réponse mal formée ou incomplète (jamais une hallucination de
    coordonnées) — géré par l'appelant qui complète avec le classement algorithmique si
    la réponse est insuffisante.
    """
    if not candidates and not street_candidates:
        return CurationResult()

    prompt = _build_curation_prompt(candidates, nb_poi, street_candidates, lat, lon, radius_m, poi_types)

    response = requests.post(
        GROQ_URL,
        headers=_headers(),
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        },
        timeout=30,
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"].strip()

    valid_ids = {poi["osm_id"] for poi in candidates}
    valid_street_ids = {s["osm_id"] for s in street_candidates}
    result = _parse_curation_response(raw, valid_ids, valid_street_ids)
    result.selected_ids = result.selected_ids[:nb_poi]
    return result
