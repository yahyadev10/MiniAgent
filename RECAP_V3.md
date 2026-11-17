# Recap V3 - Mini AI Task Agent utilisable

Ce fichier resume ce qui a change dans la V3 et comment le tester de bout en
bout.

---

## 1. Objectif de la V3

La V2 produisait deja de vrais artefacts (PDF, HTML, `.eml`). La V3 transforme
la demo en petit outil utilisable :

- l'utilisateur choisit une action explicite au lieu de dependre uniquement d'un
  prompt ;
- les rapports contiennent un graphique, des insights et des statistiques ;
- le frontend ressemble a un vrai produit multi-pages ;
- l'historique, les fichiers et l'etat du systeme sont consultables.

---

## 2. Backend

### 2.1 Taches structurees (`api/main.py`)

`TaskRequest` accepte maintenant :

| Champ | Usage |
|---|---|
| `action` | `auto`, `email`, `report`, `both` |
| `message` | requise seulement en mode `auto` |
| `to` | destinataire (requis pour `email` et `both`) |
| `subject` | sujet de l'email |
| `body` | corps de l'email |
| `title` | titre du rapport |
| `content` | instructions du rapport |
| `data` | dataset CSV/TSV/JSON (200 000 caracteres max) |
| `filename` | nom du fichier uploade |

Si `action` est explicite, `classify_node` n'appelle pas le LLM. En mode `auto`,
le classifieur Ollama fonctionne comme avant.

Validation : erreurs 422 pour `auto` sans message ou email sans destinataire.

### 2.2 Nouveaux endpoints

| Methode | Route | Description |
|---|---|---|
| `GET` | `/capabilities` | version, modele, actions, mode email, nombre d'artefacts |
| `GET` | `/artifacts?limit=100` | liste des fichiers generes, plus recents d'abord |
| `GET` | `/dashboard?action=&q=` | stats + runs filtres |
| `GET` | `/stats?action=&q=` | statistiques filtrees |
| `GET` | `/history?action=&q=` | historique filtre |

`StatsResponse` expose aussi `artifacts_total`.

### 2.3 Rapports enrichis (`mcp_servers/report_server.py`)

- PDF et HTML avec :
  - graphique en barres des moyennes (`reportlab.graphics`) ;
  - insights : meilleure moyenne, plage la plus large, colonnes numeriques ;
  - tableau de donnees ;
  - resume numerique : Count, Missing, Mean, Median, Min, Max, Std.
- Parsing CSV/TSV/JSON inchange.
- Sortie JSON avec `summary` (rows, columns, numeric, insights) et `files`.

### 2.4 Etat LangGraph (`agent/state.py`, `agent/nodes.py`)

Nouveaux champs : `action_hint`, `to`, `subject`, `body`, `title`, `content`.
`classify_node` priorise les champs du formulaire et ne sollicite le LLM qu'en
mode `auto`.

### 2.5 Correctif Airflow

Un redemarrage de conteneur pouvait laisser
`/opt/airflow/airflow-webserver.pid` perime. Le PID etant reutilise, Airflow
croyait que le webserver tournait deja et ne repondait plus. Le compose supprime
desormais ce fichier au demarrage :

```yaml
entrypoint: ["/bin/sh", "-c"]
command: ["rm -f /opt/airflow/airflow-webserver.pid && exec airflow standalone"]
```

Verifie : `mini-airflow` passe `healthy` et `http://localhost:8081/health`
renvoie `200`.

### 2.6 Routage tolerant aux fautes et au francais

`agent/llm.py` detecte maintenant les intentions avant d'appeler Ollama :

- normalisation des accents et de la ponctuation ;
- mots-cles anglais et francais (`rapport`, `courriel`, `compte rendu`,
  `analyse`, `synthese`, etc.) ;
- correspondance approximative pour les fautes courantes
  (`geenrate` / `generate`, `raport` / `rapport`, `emial` / `email`) ;
- extraction du destinataire si un email est present dans le message ;
- titre derive de la demande (`generate a report about sales` -> `Sales`).

Quand une intention explicite est trouvee, le LLM est ignore : la reponse est
immediate et deterministe. Ollama ne sert plus qu'aux demandes ambigues.

Exemple corrige : `geenrate a rapport about whether` -> action `report`,
artefacts PDF + HTML, environ 70 ms (avant : `unsupported` apres 34 s).

### 2.7 Recherche web automatique pour les rapports

Un rapport sans dataset ni contenu fourni etait trop pauvre (PDF quasi vide).
Un nouveau serveur MCP `search-mcp` (port 8003) expose `web_search` :

- recherche DuckDuckGo Lite, sans cle API, avec 2 essais ;
- fallback Jina Reader -> DuckDuckGo HTML quand l'acces direct est bloque
  (handshake SSL/timeout), puis Bing RSS, puis Wikipedia ;
- recuperation des titres, URLs et snippets ; extraction du texte des 4
  premieres pages ;
- aucune dependance Python supplementaire (`urllib`, `html.parser`,
  `xml.etree.ElementTree`).

Le graphe LangGraph ajoute `research` puis `synthesize` avant `report`
uniquement si `data` et `content` sont vides. `synthesize` transforme les
extraits de pages en vraie reponse (`Direct answer`, `Key facts`, `Details`) :
extraction locale ancree dans les textes si des faits chiffres existent, sinon
Ollama. Les nombres produits par le modele sont verifies contre les sources ;
une valeur absente declenche le fallback extractif. Les sources apparaissent
dans une table **Web sources** du PDF et du HTML.

Resultats mesures :

```text
Generate a report about the weather in Rabat Morocco tomorrow
classify 7 ms -> research 1895 ms -> synthesize 3 ms -> report 108 ms
reponse : Tomorrow 20 °C / 13 °C, 10 km/h, 9 h d'ensoleillement

Generate a report about sickle cell disease biomarkers
classify 8 ms -> research 1846 ms -> synthesize 81601 ms -> report 144 ms
reponse synthetisee par Ollama a partir des pages
```

Avec un dataset CSV, `research` et `synthesize` sont ignores (`0 ms`) et le
rapport garde ses statistiques et son graphique.

### 2.8 Nettoyage et mise en forme des rapports

Les PDF contenaient parfois des blocs bruts du type `Request`, des extraits de
pages web avec navigation, publicites (`AD FREE`, `Remove ads`) et des suites de
`????` issues d'encodages casses. `report_server.py` applique maintenant :

- normalisation Unicode et suppression des caracteres de controle / mojibake ;
- suppression des URLs, prefixes `Source:` / `Extract:` et doublons de phrases ;
- filtrage des blocs de navigation et publicite ;
- rendu de la reponse `synthesize` en section **Research overview** ;
- rendu en vrais paragraphes (plus de `<pre>` ni de section `Request`) ;
- tableau **Web sources** avec titre, snippet et URL ;
- conservation des `?` dans les URLs (les parametres `?day=2` ne sont plus
  supprimes par le nettoyage mojibake) ;
- echappement XML/HTML des titres et cellules pour eviter les PDF casses.

Verifie sur `Generate a report about the weather in Rabat Morocco tomorrow` :
PDF structure en `Research overview` -> `Web sources` -> `Key insights`, avec
`Tomorrow 20 °C / 13 °C`, sans `Extract:`, sans `AD FREE`, sans `????`, et sans
URL dans le corps du texte.

---

## 3. Frontend

Le frontend est maintenant une application multi-pages avec barre laterale.

| Page | Contenu |
|---|---|
| `/` | Dashboard : stats, runs recents, actions rapides, etat backend |
| `/new` | Formulaire complet : action, email, rapport, dataset, apercu, resultat |
| `/history` | Recherche texte + filtre par action |
| `/history/[id]` | Detail d'un run : trace, resultats, artefacts, reponse finale |
| `/files` | Bibliotheque PDF/HTML/EML avec telechargement |
| `/system` | Sante API, modele, mode email, liens services |

Nouveaux composants : `components/AppShell.tsx`, `components/RunView.tsx`,
`lib/types.ts`.

Nouveaux proxys Next.js : `capabilities`, `files`, `health`, `history`,
`history/[id]`. Le proxy `tasks` valide et transmet les champs structures.

Le style a ete etendu dans `app/globals.css` (sidebar, hero, formulaires,
tableaux, grilles de fichiers, page systeme, responsive).

---

## 4. Tests effectues

### 4.1 Compilation

```powershell
cd C:\Users\YAHYA\Desktop\ai-stack\mini-ai-agent
python -m py_compile agent\state.py agent\nodes.py agent\graph.py api\main.py api\history.py mcp_servers\report_server.py

cd C:\Users\YAHYA\Desktop\ai-stack\frontend
npx tsc --noEmit
npm run build
```

Resultats : compilation Python OK, TypeScript OK, build Next.js OK (14 routes).

### 4.2 API - rapport structure

```powershell
$body = @{
  action = "report"
  title = "Sales analysis"
  content = "Summarize the data and highlight revenue."
  data = "region,revenue,units`nNorth,1200,30`nSouth,800,20`nEast,1500,45`nWest,950,22"
  filename = "sales.csv"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType "application/json" -Body $body
```

Verifie : `action=report`, artefacts `pdf` + `html`, PDF commence par `%PDF-`,
HTML contient `Median`, `Numeric summary` et `bar-fill`.

### 4.3 API - email et both

- `action=email` avec `to` -> artefact `eml`.
- `action=both` avec `to` + dataset -> artefacts `pdf`, `html`, `eml`.
- L'`.eml` contient les parties MIME `text/plain`, `application/pdf`,
  `text/html`.

### 4.4 API - validation et mode auto

- `action=email` sans `to` -> HTTP 422.
- `action=auto` sans message -> HTTP 422.
- `action=auto` avec `"Generate a report about Q3 sales"` -> `action=report`,
  artefacts `pdf` + `html`.

### 4.5 Filtres et fichiers

```powershell
Invoke-RestMethod "http://localhost:8000/history?action=both&q=Weekly"
Invoke-RestMethod "http://localhost:8000/artifacts?limit=3"
Invoke-RestMethod "http://localhost:8000/capabilities"
```

Verifie : le filtre retourne le bon run, la liste d'artefacts est triee du plus
recent au plus ancien.

### 4.6 Frontend et proxys

- `/`, `/new`, `/history`, `/files`, `/system` -> HTTP 200.
- `/api/capabilities`, `/api/files`, `/api/history?action=both&q=Weekly` -> OK.
- `POST /api/tasks` avec un rapport structure -> 200, artefacts PDF/HTML.
- `GET /api/artifacts/<fichier>.pdf` -> `200 application/pdf`, en-tete `%PDF-`.
- `GET /api/history/<id>` -> detail du run.
- `POST /api/tasks` email sans destinataire -> HTTP 400 (proxy).

### 4.7 Etat final verifie

```text
mini-airflow    Up (healthy)     http://localhost:8081/health -> 200
mini-api        Up (healthy)     http://localhost:8000/health -> 200
mini-ollama     Up (healthy)
mini-postgres   Up (healthy)
mini-email-mcp  Up
mini-report-mcp Up
mini-search-mcp Up
frontend        Up               http://localhost:3000 -> 200
```

Les pages Dashboard, New task, History, Files et System rendent bien le nouveau
contenu (barre laterale, formulaires, bibliotheque d'artefacts).

### 4.8 Routage et fautes de frappe

```text
geenrate a rapport about whether        -> report | Whether        | 73 ms
Genere un rapport sur les ventes        -> report | Ventes         | < 5 ms
envoie un courriel a test@example.com   -> email  | to=test@...    | < 5 ms
fais un compte rendu des ventes         -> report | Ventes         | < 5 ms
analyse this dataset                    -> report | Dataset        | < 5 ms
What is the weather today?              -> unknown                  | LLM
```

Le rapport genere contient bien le titre `Whether` et le texte de la demande.

---

## 5. Comment relancer le projet

### Backend

```powershell
cd C:\Users\YAHYA\Desktop\ai-stack\mini-ai-agent
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose up -d --build
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose ps
```

Attendre que `mini-api`, `mini-ollama`, `mini-postgres` et `mini-airflow` soient
healthy. Verifier :

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/capabilities
```

### Frontend

```powershell
cd C:\Users\YAHYA\Desktop\ai-stack\frontend
npm install
npm run build
npm run start
```

Ouvrir <http://localhost:3000>.

### Test manuel rapide

1. Ouvrir `/new`.
2. Choisir `Report`.
3. Titre : `Test report`.
4. Coller un CSV ou joindre un fichier.
5. Lancer : la page affiche la trace et deux artefacts PDF/HTML.
6. Ouvrir `/files` : les fichiers apparaissent.
7. Ouvrir `/history` : rechercher `Test report`.
8. Ouvrir `/system` : verifier `API status = ok` et le mode email.

Test sans dataset (recherche web) :

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType 'application/json' `
  -Body '{"message":"Generate a report about sickle cell disease biomarkers"}'
```
Attendu : trace `classify -> research -> synthesize -> report -> finalize`,
5 sources, PDF/HTML avec une reponse dans **Research overview** et un tableau
**Web sources**.

---

## 6. Limites assumees

- Pas encore d'authentification ni de multi-tenant.
- Execution synchrone : une tache longue bloque la requete.
- SQLite pour l'historique (Postgres uniquement pour Airflow).
- SMTP optionnel : sans configuration, l'email est un `.eml`.
- Le graphique PDF est volontairement simple (moyennes par colonne).
- La recherche web depend de DuckDuckGo Lite / Jina Reader / Bing RSS /
  Wikipedia et de l'acces reseau du conteneur ; certains sites bloquent
  l'extraction de texte, mais leurs snippets restent disponibles.
- La synthese Ollama peut prendre ~80 s sur un sujet sans fait chiffre ; les
  requetes avec des nombres utilisent l'extraction locale (~3 ms).
- Pas de tests automatises frontend (build + verification manuelle).
