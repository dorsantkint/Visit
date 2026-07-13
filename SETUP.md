# Visit — POC hackathon : ce que tu dois faire

Workflow sans Android Studio : tu pousses sur GitHub, une Action compile l'APK et le publie
en Release. Tu télécharges le lien sur ton téléphone, comme ton ancien projet.

Ce POC v0 n'a **pas de backend ni d'IA** : 2 points d'intérêt en dur, pour valider le mécanisme
géofence → notification → lecture vocale. L'IA arrivera une fois ce socle validé sur le terrain.

## Étape 1 — Créer le repo GitHub

1. Sur github.com, crée un nouveau repo vide (ex: `visit-poc`), sans README/gitignore (on les a déjà).
2. En local, dans un terminal, à l'endroit où tu as ce dossier `repo/` :

```bash
cd repo
git init
git add .
git commit -m "POC v0 : geofencing + notification + TTS"
git branch -M main
git remote add origin https://github.com/<ton-user>/visit-poc.git
git push -u origin main
```

## Étape 2 — Laisser la CI tourner

1. Va dans l'onglet **Actions** de ton repo GitHub. Le workflow "Build APK" démarre automatiquement
   après le push. Ça prend 3-6 minutes (installation du SDK Android + compilation).
2. S'il passe au vert : va dans l'onglet **Releases** de ton repo → une release `latest-poc`
   contient `visit-debug.apk`. C'est ton lien stable — il se met à jour à chaque push sur `main`.
3. **S'il passe au rouge** : clique sur le job qui a échoué, lis l'erreur en bas des logs, et
   colle-la moi. C'est presque toujours un souci de version de dépendance (une ligne à changer
   dans un des `build.gradle.kts`), je corrige direct.

## Étape 3 — Installer l'APK sur ton téléphone

1. Depuis ton téléphone, ouvre le lien de la release GitHub, télécharge `visit-debug.apk`.
2. Si c'est la première fois : Android va demander d'autoriser "Installer des applications
   inconnues" pour ton navigateur/gestionnaire de fichiers — accepte.
3. Installe l'APK, ouvre l'app "Visit".

## Étape 4 — Mettre de vraies coordonnées de test

Édite `app/src/main/java/com/dorsan/visit/Poi.kt` (en local, avec n'importe quel éditeur de
texte — VS Code, Notepad++, même l'éditeur web de GitHub) et remplace les `lat`/`lon` des deux
POI de test par de vrais points proches de l'endroit où tu vas tester.

Pour récupérer des coordonnées : Google Maps, clic droit sur un point → elles s'affichent en
haut, clique dessus pour les copier. Puis :

```bash
git add app/src/main/java/com/dorsan/visit/Poi.kt
git commit -m "Coordonnées de test réelles"
git push
```

Ça relance la CI et met à jour la release automatiquement.

## Étape 5 — Tester

1. Dans l'app : "1. Demander les permissions" — accorde la localisation (choisis "Toujours
   autoriser" si le choix est proposé) et les notifications.
2. Marche jusqu'à moins de 40 m d'une des coordonnées mises dans `Poi.kt`.
3. Une notification doit apparaître → tape dessus → la voix lit la description.
4. Si "2. Activer les points de test" affiche un message d'erreur au lieu de "géofence(s)
   enregistrée(s)", l'app te dit directement pourquoi (permission manquante, Play Services
   indisponible, etc.) — pas besoin de logs, envoie-moi juste le message affiché.

## Limites connues de cette v0 (normal, pas un bug)

- Fonctionne de manière fiable seulement pendant que l'app est ouverte au premier plan. Le mode
  "app fermée" nécessite un flux de permission séparé pour `ACCESS_BACKGROUND_LOCATION` — prévu
  pour une itération suivante.
- Descriptions en dur, pas de génération IA, pas de sélecteur de langue à l'écran.
- Pas d'itinéraire ni de carte — juste le déclenchement + la lecture.
- Sans Android Studio, on n'a pas de logcat : c'est pour ça que l'app affiche maintenant les
  erreurs de permissions et de géofencing directement à l'écran plutôt que dans des logs.

## Si la CI échoue

Colle-moi l'erreur exacte des logs GitHub Actions (onglet Actions > le run rouge > le step qui
a un ❌). Les causes les plus probables : une version de dépendance à ajuster dans
`app/build.gradle.kts` ou `build.gradle.kts` — un correctif d'une ligne dans 90% des cas.
