"""Récupération d'un extrait Wikipedia pour ancrer les faits donnés au LLM.

Règle de sécurité importante : on ne fait JAMAIS de recherche Wikipedia par nom seul.
Un nom de POI générique (ex: un restaurant "Le Parvis") peut correspondre à un article
Wikipedia totalement différent et sans rapport (ex: une salle de spectacle dans une autre
ville, un autre pays). On ne retient un article que s'il est rattaché au lieu de façon
fiable : soit via un tag OSM explicite (wikipedia/wikidata, posé par un contributeur),
soit via une recherche géolocalisée où l'article doit être physiquement proche du POI.
Mieux vaut ne pas avoir de fait que d'en avoir un faux.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from urllib.parse import quote

import requests

_HEADERS = {"User-Agent": "VisitApp/0.1 (POC personnel, contact: dorsantkint@gmail.com)"}


def _fetch_summary(lang: str, title: str) -> Optional[str]:
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        resp = requests.get(url, timeout=10, headers=_HEADERS)
        if resp.status_code == 200:
            return resp.json().get("extract")
    except requests.RequestException:
        pass
    return None


def _resolve_wikidata_title(qid: str, lang: str) -> Optional[str]:
    """Résout un identifiant Wikidata (ex: Q12345) vers le titre de la page Wikipedia
    dans la langue demandée, via les sitelinks de l'entité."""
    try:
        resp = requests.get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
            timeout=10,
            headers=_HEADERS,
        )
        if resp.status_code != 200:
            return None
        entity = resp.json()["entities"][qid]
        sitelink = entity.get("sitelinks", {}).get(f"{lang}wiki")
        return sitelink["title"] if sitelink else None
    except (requests.RequestException, KeyError, ValueError):
        return None


def _geosearch(lat: float, lon: float, lang: str, radius_m: int = 100) -> Optional[str]:
    """Cherche un article Wikipedia géolocalisé à proximité immédiate du POI. Contrairement
    à une recherche par nom, ça garantit que l'article correspond bien à CE lieu physique
    précis, pas à un homonyme sans rapport ailleurs dans le monde."""
    try:
        resp = requests.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "geosearch",
                "gscoord": f"{lat}|{lon}",
                "gsradius": radius_m,
                "gslimit": 1,
                "format": "json",
            },
            timeout=10,
            headers=_HEADERS,
        )
        if resp.status_code != 200:
            return None
        results = resp.json().get("query", {}).get("geosearch", [])
        if not results:
            return None
        return _fetch_summary(lang, results[0]["title"])
    except requests.RequestException:
        return None


def fetch_extract_for_poi(
    name: str, osm_tags: Dict[str, str], lat: float, lon: float, lang: str = "fr"
) -> Optional[str]:
    """Cherche un extrait Wikipedia fiable, par ordre de confiance décroissant :
    1) tag OSM "wikipedia" explicite (posé à la main par un contributeur, donc fiable)
    2) tag OSM "wikidata" -> résolution du titre dans la langue demandée
    3) recherche géolocalisée (l'article doit être physiquement proche du POI)

    Volontairement PAS de recherche par nom seul (voir le docstring du module).
    """
    wikipedia_tag = osm_tags.get("wikipedia")
    if wikipedia_tag and ":" in wikipedia_tag:
        tag_lang, title = wikipedia_tag.split(":", 1)
        extract = _fetch_summary(tag_lang, title)
        if extract:
            return extract

    wikidata_id = osm_tags.get("wikidata")
    if wikidata_id:
        title = _resolve_wikidata_title(wikidata_id, lang)
        if title:
            extract = _fetch_summary(lang, title)
            if extract:
                return extract

    return _geosearch(lat, lon, lang)


def resolve_title(osm_tags: Dict[str, str], lang: str = "fr") -> Optional[Tuple[str, str]]:
    """Résout (langue_article, titre_article) à partir des tags OSM d'un POI, en se
    limitant aux tags explicites (wikipedia/wikidata) — pas de géo-recherche ici, cette
    fonction sert uniquement au classement des "incontournables", qui par construction
    ont déjà l'un de ces deux tags."""
    wikipedia_tag = osm_tags.get("wikipedia")
    if wikipedia_tag and ":" in wikipedia_tag:
        tag_lang, title = wikipedia_tag.split(":", 1)
        return tag_lang, title

    wikidata_id = osm_tags.get("wikidata")
    if wikidata_id:
        title = _resolve_wikidata_title(wikidata_id, lang)
        if title:
            return lang, title

    return None


def get_pageviews(lang: str, title: str, days: int = 30) -> int:
    """Nombre de vues de l'article Wikipedia sur les `days` derniers jours (API
    Wikimedia Pageviews, gratuite et publique, aucune clé requise). Sert à départager
    plusieurs "incontournables" entre eux par popularité réelle, pas juste par présence
    d'un tag. Renvoie 0 en cas d'échec (jamais d'exception : ce signal est un bonus,
    pas un point de défaillance)."""
    end = datetime.utcnow().date() - timedelta(days=1)  # hier : les données du jour même sont incomplètes
    start = end - timedelta(days=days)
    encoded_title = quote(title.replace(" ", "_"), safe="")

    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{lang}.wikipedia/all-access/user/{encoded_title}/daily/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    try:
        resp = requests.get(url, timeout=10, headers=_HEADERS)
        if resp.status_code != 200:
            return 0
        items = resp.json().get("items", [])
        return sum(item.get("views", 0) for item in items)
    except Exception:
        # Volontairement large : ce signal est un bonus de classement, jamais un point
        # de défaillance (erreur réseau, JSON malformé, structure de réponse inattendue...).
        return 0
