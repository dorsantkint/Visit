# Backend Visit — installation locale (Windows)

Ce backend tourne sur ta machine (décision prise plus tôt). Il fait 3 choses : récupérer
les POI d'un quartier (Overpass/OSM, gratuit), récupérer un extrait Wikipedia pour ancrer
les faits, et faire rédiger la description par un modèle IA local (Ollama).

Testé dans un environnement isolé : le serveur démarre, répond en HTTP, et la logique de
génération + cache est validée avec des appels externes simulés. Les vrais appels réseau
(Overpass, Wikipedia, Ollama) n'ont pas pu être testés depuis mon environnement (accès
réseau restreint) — ce sera le premier vrai test chez toi.

## 1. Installer Python (si pas déjà fait)

Télécharge Python 3.11+ sur python.org, installe en cochant "Add python.exe to PATH".

## 2. Installer les dépendances du backend

Ouvre un terminal (PowerShell) dans le dossier `backend/` de ton projet :

```powershell
cd backend
pip install -r requirements.txt
```

## 3. Installer Ollama et le modèle

1. Télécharge et installe Ollama pour Windows : https://ollama.com/download
2. Une fois installé, dans un terminal :

```powershell
ollama pull qwen2.5:7b
```

Ça télécharge le modèle (~4-5 Go). Ollama tourne ensuite en arrière-plan automatiquement
et écoute sur `http://localhost:11434`.

## 4. Lancer le backend

Toujours dans le dossier `backend/` :

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`--host 0.0.0.0` est important : ça permet à ton téléphone (sur le même Wi-Fi) de joindre
le serveur, pas seulement ta machine.

## 5. Vérifier que ça tourne

Dans un navigateur, va sur `http://localhost:8000/health` → doit afficher `{"status":"ok"}`.

Puis `http://localhost:8000/docs` → interface Swagger auto-générée, tu peux tester
`/generate-tour` directement depuis le navigateur avec un vrai payload, par exemple :

```json
{
  "lat": 50.8022,
  "lon": 4.3383,
  "radius_m": 500,
  "poi_types": ["historic", "religious"],
  "nb_poi": 3,
  "languages": ["fr"],
  "duration_min": 2,
  "trigger_radius_m": 40
}
```

(coordonnées d'exemple : rue Edith Cavell, Uccle)

La première génération sera lente (le LLM tourne en local, comptez 10-30 secondes par
description selon ta machine). Les appels suivants sur les mêmes POI/langue/durée seront
instantanés grâce au cache SQLite (`app/cache.db`).

## 6. Connecter le téléphone

- Récupère l'IP locale de ton PC : `ipconfig` dans PowerShell, cherche "Adresse IPv4"
  (ex: 192.168.1.42).
- Le téléphone doit être sur le même Wi-Fi.
- L'app pourra appeler `http://192.168.1.42:8000/generate-tour`.

(Le câblage de l'app Android vers ce backend n'est pas encore fait — prochaine étape une
fois que tu confirmes que le backend tourne bien de ton côté.)

## Si ça ne marche pas

- `ollama pull` bloqué / lent : normal la première fois, le modèle fait plusieurs Go.
- Erreur de connexion à `localhost:11434` : vérifie qu'Ollama tourne (icône dans la barre
  des tâches Windows, ou `ollama list` dans un terminal doit lister `qwen2.5:7b`).
- Erreur Overpass (timeout, 429) : l'API publique est parfois surchargée, réessaie dans
  quelques secondes. Normal pour un POC, on gérera le retry proprement plus tard si besoin.
