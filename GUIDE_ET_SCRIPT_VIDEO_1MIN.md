# Mini AI Task Agent — guide de test et script vidéo 1 minute

## État actuel

L’application est démarrée :

- Interface web : http://localhost:3000
- API FastAPI / Swagger : http://localhost:8000/docs
- Santé backend : http://localhost:8000/health
- Suite d’évaluation : http://localhost:8000/eval

Le backend utilise l’Ollama installé sur la machine hôte sur le port `11434`. Si tu redémarres les conteneurs, évite de lancer le service Docker `ollama` tant que ce port est occupé.

## Redémarrage rapide

Depuis `C:\Users\YAHYA\Desktop\ai-stack\mini-ai-agent` :

```powershell
$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$env:OLLAMA_HOST = "http://host.docker.internal:11434"
& $docker compose up -d --no-deps api search-mcp report-mcp email-mcp
```

Depuis `C:\Users\YAHYA\Desktop\ai-stack\frontend` :

```powershell
npm run dev
```

## Comment tester l’application

### 1. Dashboard

Ouvre http://localhost:3000. Tu dois voir les statistiques des runs, le nombre d’artifacts et les dernières exécutions.

### 2. Nouvelle tâche — météo avec streaming

Va sur **New task**, laisse l’action sur **Auto**, et colle :

```text
Quelle est la météo actuelle à Paris ?
```

Clique sur **Run task**. Tu dois voir :

- un panneau **Live progress** apparaître pendant l’exécution ;
- les étapes `classify`, `research`, `synthesize`, `report` ou `finalize` défiler ;
- une réponse structurée avec **Direct answer** et **Key facts** ;
- des sources météo Open-Meteo cliquables dans **Cited sources** si le rapport est généré.

### 3. Nouvelle tâche — rapport CSV

Va sur **New task**, choisis **Report**, puis :

- titre : `Rapport Q3`
- contenu : `Résume les données et mets en évidence les colonnes numériques.`
- dépose un fichier CSV, par exemple :

```csv
team,score
Alpha,12
Beta,19
Gamma,25
```

Clique sur **Run task**. Tu dois obtenir deux artifacts : PDF et HTML. Ouvre l’HTML pour voir le résumé, les insights, le graphique, les sources et les citations.

### 4. Email + rapport

Choisis **Email + report**, renseigne un destinataire, un sujet et un corps. Le rapport est généré puis attaché à l’email.

Sans SMTP configuré, l’application génère un fichier `.eml` téléchargeable depuis **Files**. Ouvre-le avec un client mail pour voir les pièces jointes.

### 5. Comptes et historique isolé

Va sur **Account**, crée un compte puis connecte-toi. Lance une tâche, puis ouvre **History** : seules tes exécutions apparaissent. Sans connexion, tu utilises l’espace `public`.

### 6. API et jobs asynchrones

Swagger : http://localhost:8000/docs

Endpoints utiles :

- `GET /health`
- `GET /capabilities`
- `GET /eval`
- `POST /tasks`
- `GET /tasks/stream` : flux SSE avec les étapes en direct
- `POST /tasks/async` : crée un job
- `GET /tasks/{id}/status` : suit le job
- `GET /history`
- `GET /files`

Exemple de test météo via SSE :

```powershell
curl.exe -N "http://localhost:8000/tasks/stream?message=Quelle%20est%20la%20m%C3%A9t%C3%A9o%20%C3%A0%20Paris"
```

Exemple de suite d’évaluation :

```powershell
(Invoke-RestMethod "http://localhost:8000/eval") | ConvertTo-Json
```

Résultat attendu : `passed: 5`, `failed: 0`.

## Dépannage rapide

Si tu vois `Unsupported` pour une question comme la météo :

- recharge la page ;
- relance exactement `Quelle est la météo actuelle à Paris ?` ;
- le routeur local doit afficher `classify` en quelques millisecondes, puis `research` via `open-meteo` ;
- le rapport doit apparaître en moins de 2 secondes environ.

Le routeur traite maintenant les questions générales comme un rapport sans appeler le LLM, et le flux SSE envoie immédiatement les événements `start`, `status`, puis chaque étape.

## Script vidéo — 1 minute

### 0:00 — 0:08

« Bonjour. Voici Mini AI Task Agent : un agent local qui peut répondre à des questions en direct, analyser des données, générer des rapports PDF et HTML, et préparer des emails avec pièces jointes. »

**Écran** : montre brièvement le dashboard sur http://localhost:3000.

### 0:08 — 0:20

« Toute l’interface parle à une API FastAPI. Le graphique LangGraph décide de l’action, puis les serveurs MCP appellent la recherche web, la génération de rapport et l’envoi d’email. Le modèle tourne localement avec Ollama. »

**Écran** : ouvre http://localhost:8000/docs, reviens vite sur l’interface.

### 0:20 — 0:35

« Je teste d’abord une question en direct : “Quelle est la météo à Paris ?”. Je lance la tâche, et là vous voyez le streaming : les étapes apparaissent pendant que l’agent travaille. La réponse finale est structurée, avec une réponse directe, des faits clés, et des sources citées. »

**Écran** : onglet **New task**, message météo, lance, laisse le panneau **Live progress** et le résultat apparaître.

### 0:35 — 0:46

« Ensuite, je génère un rapport. Je choisis Report, je dépose un CSV, et l’agent produit un PDF et un HTML avec les statistiques numériques, les insights, un graphique et les références utilisées. Les fichiers sont téléchargeables depuis l’onglet Files. »

**Écran** : montre le rapport HTML généré puis l’onglet **Files**.

### 0:46 — 0:56

« Pour un vrai usage, j’ai aussi ajouté les comptes utilisateurs : chaque compte a son propre historique. Il y a également des jobs asynchrones avec suivi de statut, pour les tâches plus longues. »

**Écran** : montre **Account**, puis **History**, puis un endpoint `/tasks/{id}/status` dans Swagger si le temps le permet.

### 0:56 — 1:00

« Enfin, la suite d’évaluation est disponible sur `/eval` : cinq tests automatisés passent. C’est une base propre, locale et extensible pour un portfolio. Merci. »

**Écran** : montre rapidement `passed: 5`, `failed: 0` sur http://localhost:8000/eval.

## Conseils pour la vidéo

- Parle vite mais pose la voix : environ 140 à 160 mots par minute.
- Prépare les onglets à l’avance : Dashboard, New task, Files, Swagger, `/eval`.
- Utilise la météo comme démo principale : elle est rapide et montre bien le streaming.
- Garde une seule tâche lourde dans la vidéo : le rapport CSV.
- Si le streaming est trop rapide, ralentis le défilement en montrant le panneau **Live progress** quelques secondes.
- Coupe nettement après la dernière phrase, sans « euh » ni conclusion supplémentaire.
