from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# Paliers fixes plutôt qu'un curseur libre : ça maximise les hits du cache partagé
# entre utilisateurs (2.0 et 2.3 min ne génèrent plus deux entrées différentes).
DurationMinutes = Literal[1, 2, 3, 4, 5]


class TourRequest(BaseModel):
    lat: float
    lon: float
    radius_m: int = Field(default=500, ge=50, le=5000)
    poi_types: List[str] = Field(default_factory=lambda: ["monument", "historic"])
    nb_poi: int = Field(default=5, ge=1, le=20)
    languages: List[str] = Field(default_factory=lambda: ["fr"])
    duration_min: DurationMinutes = 2
    trigger_radius_m: int = Field(default=40, ge=10, le=100)


class PoiDescription(BaseModel):
    language: str
    text: str


class PoiOut(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    category: str
    trigger_radius_m: int
    descriptions: List[PoiDescription]


class TourResponse(BaseModel):
    # Anecdote de quartier : PAS géofencée, à lire une fois au lancement de la visite.
    # Liste vide si aucun nom de quartier n'a pu être résolu pour ce point.
    intro: List[PoiDescription]
    # POI réels + POI virtuel de rue (category="rue", rayon de déclenchement plus large) :
    # tous géofencés, traités de la même façon côté app.
    pois: List[PoiOut]
