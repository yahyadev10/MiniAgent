# Mini AI Task Agent - Guide complet du projet

Ce document explique l'architecture, chaque fichier, chaque fonction, puis donne
la procédure de test de A a Z.

---

## 1. But du projet

Un petit agent IA qui recoit une demande en langage naturel, decide quoi faire,
puis appelle de vrais serveurs MCP (Model Context Protocol) :

- `email` : envoie un email via SMTP si configure, sinon sauvegarde un `.eml`.
- `report` : genere un vrai PDF (ReportLab) + un fichier HTML.
- `both` : genere le rapport puis l'attache a l'email.
- `unsupported` : aucune action reconnue.

Tout tourne en local dans Docker :

- **FastAPI** expose l'API HTTP.
- **LangGraph** implemente la machine a etats (routage deterministe).
- **Ollama** fait tourner le modele `qwen2.5-coder:3b` en local.
- **MCP** est utilise pour la communication agent -> outils (vrai protocole
  Streamable HTTP, pas d'import direct des fonctions).
- **Airflow** orchestre un workflow qui appelle l'API.

Aucune API cloud ni cle API obligatoire. L'email reel est optionnel via SMTP
(sinon un `.eml` est produit).

---

## 2. Architecture

```
                        +----------------------+
   Utilisateur  ----->  |  FastAPI  (api)      |  POST /tasks
   (PowerShell,         |  port 8000           |
    navigateur,         +----------+-----------+
    Airflow)                       |
                                   | agent_graph.ainvoke(...)
                                   v
                        +----------------------+
                        |  LangGraph           |
                        |  START -> classify   |
                        |     |                |
                        |     +--> email ---------> MCP email   (port 8001)
                        |     +--> report --------+--> MCP report  (port 8002)
                        |     +--> research ------+--> MCP search  (port 8003)
                        |            |            +--> synthesize (reponse)
                        |            |            +--> MCP report  (port 8002)
                        |     +--> both: research -> synthesize -> report -> email
                        |     +--> unsupported
                        |     v                |
                        |  finalize -> END     |
                        +----------+-----------+
                                   |
                                   | ollama.Client (HTTP)
                                   v
                        +----------------------+
                        |  Ollama (port 11434) |
                        |  qwen2.5-coder:3b    |
                        +----------------------+

   Airflow (port hote 8081 -> conteneur 8080)
   DAG task_workflow : prepare -> call_agent -> summarize
   call_agent fait un POST http://api:8000/tasks
```

Points importants :

- L'agent ne connait **que** les URLs MCP. Il ne fait jamais
  `from mcp_servers.email_server import send_email`.
- Si un rapport n'a ni dataset ni contenu fourni, le noeud `research` interroge
  `search-mcp`, puis `synthesize` transforme les extraits de pages en vraie
  reponse (chiffres, faits, contexte). Les sources web sont ajoutees au PDF/HTML.
- Le routage LangGraph est **deterministe** : c'est l'action classee qui decide
  de la branche, pas un LLM qui piloterait le graphe.
- Airflow est **independant** de LangGraph : il ne fait qu'appeler l'API HTTP.

---

## 3. Arborescence du projet

```
mini-ai-agent/
├── docker-compose.yml
├── .env.example
├── README.md
├── GUIDE_PROJET.md
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── history.py
│   └── main.py
├── agent/
│   ├── __init__.py
│   ├── state.py
│   ├── llm.py
│   ├── nodes.py
│   └── graph.py
├── mcp_servers/
│   ├── email_server.py
│   ├── report_server.py
│   └── search_server.py
└── airflow/
    ├── Dockerfile
    └── dags/
        └── task_workflow.py
```

Le frontend Next.js est un dossier frere, hors de `mini-ai-agent/` :
`../frontend/` (voir section 9).

---

## 4. Explication de chaque fichier

### 4.1 `docker-compose.yml`

Orchestre les 8 services :

| Service | Image / build | Role | Port |
|---|---|---|---|
| `ollama` | `ollama/ollama:latest` | Serveur LLM local | 11434 |
| `ollama-pull` | `ollama/ollama:latest` | Telecharge le modele puis s'arrete | aucun |
| `email-mcp` | build `api/Dockerfile` | Serveur MCP email | 8001 interne |
| `report-mcp` | build `api/Dockerfile` | Serveur MCP report | 8002 interne |
| `search-mcp` | build `api/Dockerfile` | Serveur MCP recherche web | 8003 interne |
| `api` | build `api/Dockerfile` | FastAPI + LangGraph | 8000 |
| `postgres` | `postgres:16-alpine` | Metadonnees Airflow | interne |
| `airflow` | build `airflow/Dockerfile` | Airflow standalone | 8081 -> 8080 |

Details :

- `x-app` : ancre YAML partagee par les 4 services Python (meme image, commande
  differente). Pas de `image:` fixe pour eviter un conflit de tag entre services.
- `ollama` a un `healthcheck` qui attend que le serveur reponde.
- `ollama-pull` depend de `ollama` (`service_healthy`) et s'arrete avec code 0
  quand le modele est present.
- `api` depend de :
  - `ollama-pull` : `service_completed_successfully`
  - `email-mcp`, `report-mcp` et `search-mcp` : `service_started`
- `api` et `airflow` ont un `healthcheck` HTTP.
- Volumes nommes :
  - `ollama_data` : modele telecharge ;
  - `api_data` : historique SQLite de l'agent ;
  - `artifacts_data` : PDF/HTML/EML partages entre `api`, `email-mcp`,
    `report-mcp` ;
  - `airflow_db` : metadonnees Airflow dans Postgres.
- `airflow` monte `./airflow/dags` en lecture seule et depend de `postgres`
  (`service_healthy`).

Pourquoi Airflow sur `8081` et pas `8080` : sur ce poste Windows, une regle
`netsh portproxy` d'un autre projet intercepte deja `0.0.0.0:8080`. Le port hote
`8081` evite le conflit. Le port interne du conteneur reste `8080`.

### 4.2 `.env.example`

Variables optionnelles (copier en `.env` pour surcharger) :

```
OLLAMA_MODEL=qwen2.5-coder:3b
OLLAMA_HOST=http://ollama:11434
EMAIL_MCP_URL=http://email-mcp:8001/mcp
REPORT_MCP_URL=http://report-mcp:8002/mcp
SEARCH_MCP_URL=http://search-mcp:8003/mcp

# Email reel (optionnel). Vide = sauvegarde .eml.
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_TLS=true
SMTP_SSL=false
```

### 4.3 `api/Dockerfile`

- Base `python:3.11-slim`.
- `PYTHONPATH=/app` pour que `import agent...` et `import mcp_servers...`
  fonctionnent.
- Installe `api/requirements.txt` avant de copier le code (cache Docker).
- Copie `api/`, `agent/`, `mcp_servers/` dans `/app`.
- Image unique reutilisee par l'API et les 3 serveurs MCP, avec une commande
  differente dans Compose.

### 4.4 `api/requirements.txt`

Versions epinglees :

```
fastapi==0.115.12
uvicorn[standard]==0.34.3
mcp==1.30.0
langgraph==1.2.20
langchain-core==1.4.7
ollama==0.6.3
pydantic==2.11.7
reportlab==4.2.5
```

### 4.5 `api/main.py`

- `TaskRequest` : `action` (`auto`, `email`, `report`, `both`), `message`
  (obligatoire seulement en mode `auto`), `to`, `subject`, `body`, `title`,
  `content`, `data` (max 200 000 caracteres), `filename` (max 200).
- `TaskResponse` : `id`, `message`, `action`, `results`, `final`, `steps`,
  `duration_ms`, `created_at`, `artifacts`.
- `agent_graph = build_graph()` : graphe compile une seule fois au demarrage.
- `GET /health` : renvoie `{"status": "ok"}`.
- `GET /capabilities` : version, modele, actions, mode email (`smtp`/`eml`),
  nombre d'artefacts.
- `POST /tasks` :
  - recoit les champs structures ou `{"message": "..."}` en mode `auto` ;
  - appelle `await agent_graph.ainvoke({...})` avec tous les champs ;
  - si `action` est explicite, le LLM n'est pas appele ;
  - calcule les URLs `/artifacts/{filename}` ;
  - persiste le run via `api/history.py` ;
  - renvoie l'action, les resultats, la trace, les artefacts et la reponse.
  - en cas d'exception : log + HTTP 500.
- `GET /dashboard`, `GET /stats`, `GET /history` : filtres `action` et `q`.
- `GET /history/{id}`, `GET /history/{id}/report`.
- `GET /artifacts?limit=100` : liste des artefacts, plus recents d'abord.
- `GET /artifacts/{filename}` : `FileResponse` avec le bon Content-Type
  (PDF, HTML, EML).

Exemple d'appel structure :

```json
{
  "action": "both",
  "to": "john@example.com",
  "subject": "Rapport Q3",
  "body": "Bonjour John, voici le rapport.",
  "title": "Rapport Q3",
  "content": "Mettre en avant la meilleure region.",
  "data": "region,revenue\nNorth,120\nSouth,95",
  "filename": "sales.csv"
}
```

`api/history.py` stocke chaque run dans SQLite (`data/history.db`, volume
`api_data`), avec migration automatique de la colonne `artifacts` pour les
anciennes bases.

### 4.6 `agent/state.py`

`AgentState` est le dictionnaire d'etat partage entre les noeuds :

- `message` : demande utilisateur (mode `auto` ou fallback).
- `data` / `filename` : contenu et nom du fichier uploade (optionnels).
- `action_hint` : action explicite choisie dans le formulaire.
- `to`, `subject`, `body` : champs email structures.
- `title`, `content` : champs rapport structures.
- `action` : `email`, `report`, `both` ou `unknown`.
- `search_query` : sujet court utilise pour la recherche web.
- `sources` : sources web retournees par `search-mcp`.
- `email_args` : arguments prepares pour l'outil email.
- `report_args` : arguments prepares pour l'outil report.
- `results` : `Annotated[list[str], operator.add]` -> les sorties des branches
  s'accumulent au lieu de s'ecraser (important pour la branche `both`).
- `artifacts` : `Annotated[list[dict], operator.add]` -> PDF/HTML/EML produits.
- `steps` : `Annotated[list[dict], operator.add]` -> trace chronometree.
- `final` : texte final concatene.

### 4.7 `agent/llm.py`

- Lit `OLLAMA_HOST` et `OLLAMA_MODEL`.
- Cree un `ollama.Client`.
- `SYSTEM_PROMPT` : demande au modele de renvoyer uniquement un JSON avec
  `action`, `to`, `subject`, `body`, `title`, `content`, et interdit d'inventer
  une action quand la demande ne parle ni d'email ni de rapport.
- `_detect_intents(message)` : detection tolerante aux fautes et au francais
  (`rapport`, `courriel`, `compte rendu`, `analyse`, `synthese`, etc.).
  Normalisation des accents, correspondance approximative (`geenrate` ->
  `generate`, `raport` -> `rapport`, `emial` -> `email`).
- `_fallback_action(message)` : utilise `_detect_intents` pour choisir
  `email`, `report`, `both` ou `unknown`.
- `_validate_action(action, message)` : rejette une action inventee par le LLM
  si les mots-cles correspondants sont absents (ex: "What is the weather today?"
  -> `unknown`).
- `classify_request(message)` :
  - si une intention explicite est detectee, renvoie immediatement un resultat
    deterministe sans appeler Ollama (titre et destinataire extraits) ;
  - sinon appelle `_client.chat(..., format="json", temperature=0)` ;
  - parse le JSON ;
  - passe l'action dans `_validate_action` (qui retombe sur `_fallback_action`) ;
  - renvoie `{"action": ..., "data": {...}}`.
- `topic_from_message(message)` : derive un titre court
  (`generate a report about sales` -> `Sales`).

### 4.8 `agent/nodes.py`

- `_call_mcp_tool(url, tool_name, arguments, attempts=3)` :
  - ouvre `streamablehttp_client(url)` ;
  - cree une `ClientSession` MCP ;
  - `session.initialize()` ;
  - `session.call_tool(...)` ;
  - si `result.isError`, leve une erreur ;
  - concatene le texte des blocs de contenu ;
  - reessaie jusqu'a 3 fois avec un backoff `1.5 * attempt`.
- `_timed(name)` : decorateur qui mesure chaque noeud et ajoute
  `{node, status, ms}` a `steps`.
- `_parse_payload(text)` : parse le JSON renvoye par les outils MCP.
- `classify_node` : appelle `classify_request`, prepare `email_args` et
  `report_args` (avec `data`/`filename`), calcule `search_query`, ecrit `action`
  dans l'etat.
- `research_node` : si le rapport n'a ni `data` ni `content`, appelle l'outil MCP
  `web_search` avec `fetch_pages=True`, conserve les extraits de pages dans
  `sources` et prepare un contenu de secours.
- `synthesize_node` : transforme les sources en reponse structuree
  (`Direct answer`, `Key facts`, `Details`). Il utilise d'abord une extraction
  locale ancree dans les textes ; si aucun fait chiffre n'est trouve, il appelle
  Ollama. Les nombres produits par le modele sont verifies contre les sources :
  toute valeur absente declenche le fallback extractif.
- `email_node` : appelle l'outil MCP `send_email` avec les artefacts PDF/HTML en
  pieces jointes, ajoute `[email] ...` aux `results` et le `.eml` aux
  `artifacts`.
- `report_node` : appelle l'outil MCP `generate_report` avec les sources web,
  ajoute `[report] ...` et les fichiers PDF/HTML aux `artifacts`.
- `unsupported_node` : ajoute un message explicatif.
- `finalize_node` : joint tous les `results` en un seul `final`.

### 4.9 `agent/graph.py`

- `_route_after_classify` : renvoie l'action si elle est valide, sinon
  `unknown`.
- `_route_after_report` : renvoie `email` si l'action est `both`, sinon
  `finalize`.
- `build_graph()` :
  - noeuds : `classify`, `research`, `synthesize`, `email`, `report`,
    `unsupported`, `finalize` ;
  - `START -> classify` ;
  - `report` et `both` passent par `research`, puis `synthesize`, puis `report` ;
  - `both` passe ensuite par `email` ;
  - `email` et `unsupported` vont vers `finalize` ;
  - `finalize -> END`.

Graphe resultant :

```
START -> classify -> email -> finalize -> END
                  -> research -> synthesize -> report -> finalize -> END
                  -> research -> synthesize -> report -> email -> finalize -> END   (both)
                  -> unsupported -> finalize -> END
```

### 4.10 `mcp_servers/email_server.py`

- `FastMCP("email-server", host=..., port=8001)`.
- `TransportSecuritySettings(enable_dns_rebinding_protection=False)` pour
  accepter les noms de services Docker.
- Outil `send_email(to, subject, body, attachments)` :
  - envoie via `smtplib` si `SMTP_HOST` est defini (TLS/SSL, auth optionnelle) ;
  - sinon ecrit un fichier `.eml` dans `/app/artifacts` ;
  - joint les PDF/HTML presents dans `/app/artifacts` ;
  - renvoie un JSON `{status, transport, to, subject, attachments, ...}`.
- Logs : `[EMAIL SENT]`, `[EMAIL SAVED]` ou `[EMAIL ERROR]`.
- `mcp.run(transport="streamable-http")`.

### 4.11 `mcp_servers/report_server.py`

- `FastMCP("report-server", host=..., port=8002)`.
- Nettoyage : `_clean_text` normalise Unicode, retire les caracteres de controle,
  les mojibake (`????`), les URLs et les espaces multiples.
- `_clean_paragraphs` decoupe le texte en phrases, supprime les doublons et les
  blocs de navigation/publicite (`AD FREE`, `Remove ads`, cookies, etc.).
- `_research_paragraphs` reconstruit une introduction propre a partir des
  snippets web, sans les extraits de pages bruts. Quand `synthesize` a produit
  une reponse, ce sont ses paragraphes (`Direct answer`, `Key facts`, `Details`)
  qui sont rendus.
- Outil `generate_report(title, content, data, source_filename, sources)` :
  - parse les donnees CSV/TSV/JSON ;
  - calcule un resume numerique (count, missing, mean, median, min, max, std) ;
  - rend une section **Research overview** / **Overview** en paragraphes ;
  - ajoute un tableau **Web sources** (titre, snippet, URL) quand `sources` est
    fourni ;
  - ecrit un PDF (ReportLab) et un HTML dans `/app/artifacts` ;
  - renvoie un JSON `{status, title, summary, sources, files:[...]}`.
- `mcp.run(transport="streamable-http")`.

### 4.12 `mcp_servers/search_server.py`

- `FastMCP("search-server", host=..., port=8003)`.
- Outil `web_search(query, max_results=5, fetch_pages=True)` :
  - interroge `https://lite.duckduckgo.com/lite/` sans cle API, avec 2 essais ;
  - fallback `https://r.jina.ai/http://duckduckgo.com/html/` quand l'acces
    direct est bloque (SSL/timeout), puis Bing RSS, puis Wikipedia ;
  - decode les liens de redirection DuckDuckGo (`uddg=`) ;
  - extrait les titres, URLs et snippets ;
  - telecharge les 4 premieres pages et extrait le texte lisible ;
  - renvoie `{status, engine, query, count, results:[{title,url,snippet,text}]}`.
- Aucune dependance supplementaire : `urllib`, `html.parser`, `json`,
  `xml.etree.ElementTree`.
- `mcp.run(transport="streamable-http")`.

### 4.13 `airflow/Dockerfile`

```dockerfile
FROM apache/airflow:2.10.5-python3.11
USER airflow
```

L'image officielle contient deja `requests`, utilise par le DAG.

### 4.14 `airflow/dags/task_workflow.py`

- `API_URL` = `http://api:8000/tasks` (surchargeable par la variable `API_URL`).
- `prepare_task()` : simple log de preparation.
- `call_agent()` :
  - `requests.post(API_URL, json={"message": "..."}, timeout=180)` ;
  - `raise_for_status()` ;
  - log l'action et le resultat final ;
  - renvoie le JSON (stocke dans XCom).
- `summarize(**context)` : recupere le resultat via `xcom_pull` et l'affiche.
- DAG `task_workflow` :
  - `schedule=None` (declenchement manuel) ;
  - `catchup=False` ;
  - chaine `prepare >> call_agent >> summarize`.

---

## 5. Flux d'execution detaille

### Cas `email`

1. `POST /tasks` avec `{"message": "Send an email to John"}`.
2. `classify` -> Ollama renvoie `{"action": "email", ...}` (ou fallback mots-cles).
3. `email` -> appel MCP `send_email`.
4. `finalize` -> `final` contient `[email] Email sent to ...`.

### Cas `report`

1. `classify` -> action `report` et `search_query`.
2. Si aucun `data` ni `content` : `research` -> appel MCP `web_search`.
3. `synthesize` -> reponse ancree dans les extraits de pages.
4. `report` -> appel MCP `generate_report` avec la reponse et les sources web.
5. `finalize` -> `[research] ...`, `[synthesize] ...`, puis `[report] ...`.

### Cas `both`

1. `classify` -> action `both`.
2. Si aucun `data` ni `content` : `research` -> appel MCP `web_search`.
3. `synthesize` -> reponse structuree.
4. `report` -> appel MCP report (PDF/HTML avec sources).
5. `email` -> appel MCP email avec les PDF/HTML en pieces jointes.
6. `finalize` -> les resultats sont concatenes (grace a `operator.add`).

### Cas `unsupported`

1. `classify` -> aucun mot-cle email/report, ou action du LLM non corroboree
   par le texte (garde-fou `_validate_action`).
2. `unsupported` -> message d'aide.
3. `finalize`.

---

## 6. Prerequis

- Windows 10/11 avec Docker Desktop (WSL2 active).
- Docker Desktop demarre.
- Environ 4 Go d'espace libre pour l'image Ollama + le modele (~2 Go).
- PowerShell.

Note propre a ce poste : dans PowerShell, la commande `docker` peut pointer vers
un fichier vide dans `C:\Windows\System32`. Si `docker` ne fonctionne pas,
utiliser le chemin complet :

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' version
```

Dans la suite, `docker` designe cette commande (ou le chemin complet).

---

## 7. Test de A a Z

### Etape 1 - Se placer dans le projet

```powershell
cd C:\Users\YAHYA\Desktop\ai-stack\mini-ai-agent
```

### Etape 2 - Verifier la configuration Compose

```powershell
docker compose config --quiet
```

Aucune sortie = OK.

### Etape 3 - Construire et demarrer

```powershell
docker compose up --build -d
```

- Le premier build installe les dependances (plusieurs minutes).
- `ollama-pull` telecharge `qwen2.5-coder:3b` (~2 Go) la premiere fois.
- Le modele est conserve dans le volume `ollama_data`.

### Etape 4 - Verifier les conteneurs

```powershell
docker compose ps
```

Attendu :

- `mini-api` : `Up ... (healthy)`
- `mini-ollama` : `Up ... (healthy)`
- `mini-airflow` : `Up ... (healthy)`
- `mini-email-mcp`, `mini-report-mcp` et `mini-search-mcp` : `Up`
- `mini-ollama-pull` : `Exited (0)` (normal, c'est un one-shot)

### Etape 5 - Health check API

```powershell
Invoke-RestMethod -Uri http://localhost:8000/health
```

Attendu :

```json
{ "status": "ok" }
```

### Etape 6 - Tester la branche email

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType 'application/json' `
  -Body '{"message":"Send an email to John"}'
```

Attendu :

```json
{
  "id": "942dbf000a18",
  "message": "Send an email to John",
  "action": "email",
  "results": ["[email] SMTP is not configured, so the email was saved as email-xxxx.eml (ready to send)."],
  "final": "[email] SMTP is not configured, so the email was saved as email-xxxx.eml (ready to send).",
  "steps": [{"node": "classify", "status": "ok", "ms": 1200}],
  "artifacts": [{"kind": "eml", "filename": "email-xxxx.eml", "size": 222, "url": "/artifacts/email-xxxx.eml"}]
}
```

Avec `SMTP_HOST` configure, le resultat devient
`[email] Email sent to ... with subject '...'.`

### Etape 7 - Tester la branche report

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType 'application/json' `
  -Body '{"message":"Generate a report about Q3 sales"}'
```

Attendu : `"action": "report"`, les etapes `research`, `synthesize`, puis
`[research] N web sources found ...`, `[synthesize] Answer built from ...` et
`[report] Report generated: report-xxxx.pdf, report-xxxx.html (... with N web sources)`.
Le PDF/HTML contient une section **Research overview** avec la reponse, puis un
tableau **Web sources**. Les fichiers sont telechargeables via
`GET /artifacts/{filename}`.

Avec un dataset, la recherche web est ignoree :

```powershell
$body = @{
  message = "Create a quarterly revenue report"
  data = "region,revenue`nNorth,120`nSouth,95`nEast,130"
  filename = "sales.csv"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType 'application/json' -Body $body
```

### Etape 8 - Tester la branche both

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType 'application/json' `
  -Body '{"message":"Send an email to John and generate a report about Q3 sales"}'
```

Attendu : `"action": "both"` et **deux** elements dans `results`
(un `[report]` puis un `[email]`), avec le PDF/HTML attache a l'email.

### Etape 9 - Tester le cas unsupported (optionnel)

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType 'application/json' `
  -Body '{"message":"What is the weather today?"}'
```

Attendu : `"action": "unknown"` et un message `[unsupported] ...`.

### Etape 10 - Verifier le vrai trafic MCP

```powershell
docker compose logs --tail 30 email-mcp
docker compose logs --tail 30 report-mcp
docker compose logs --tail 30 search-mcp
```

Attendu :

- `[EMAIL SAVED] ...` ou `[EMAIL SENT] ...` dans `email-mcp`.
- `[REPORT GENERATED] ...` dans `report-mcp`.
- `[SEARCH] duckduckgo-lite query=... results=N` dans `search-mcp`.
- Des lignes MCP du type `Processing request of type CallToolRequest` /
  `POST /mcp HTTP/1.1 200 OK` / `DELETE /mcp HTTP/1.1 200 OK`.

Cela prouve que l'agent parle aux serveurs via le protocole MCP.

### Etape 11 - Ouvrir Airflow

Dans le navigateur :

```
http://localhost:8081
```

Recuperer le mot de passe admin genere :

```powershell
docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt
```

Connexion : utilisateur `admin`, mot de passe affiche ci-dessus.

### Etape 12 - Verifier que le DAG est charge

```powershell
docker compose exec airflow airflow dags list
```

Attendu : une ligne `task_workflow` avec `is_paused` = `False`.

### Etape 13 - Declencher le DAG et verifier

Via l'interface : bouton "Trigger DAG" sur `task_workflow`.

Ou en ligne de commande :

```powershell
docker compose exec airflow airflow dags trigger task_workflow
```

Puis verifier les etats des taches (remplacer `<RUN_ID>` par l'identifiant
affiche, par exemple `manual__2026-11-07T22:31:48+00:00`) :

```powershell
docker compose exec airflow airflow tasks states-for-dag-run task_workflow "<RUN_ID>"
```

Attendu : `prepare`, `call_agent` et `summarize` en `success`.

### Etape 14 - Inspecter les logs

```powershell
docker compose logs -f api
docker compose logs -f email-mcp
docker compose logs -f report-mcp
docker compose logs -f search-mcp
docker compose logs -f ollama
docker compose logs -f airflow
```

`Ctrl+C` pour quitter le suivi.

### Etape 15 - Arreter

```powershell
docker compose down
```

Pour supprimer aussi le modele telecharge (volume Ollama) :

```powershell
docker compose down -v
```

---

## 8. Depannage

### `localhost:8080` renvoie 404

Cause : une regle `netsh portproxy` existante sur Windows intercepte le port
8080. C'est pour cela qu'Airflow est publie sur `8081`.

Verifier :

```powershell
netsh interface portproxy show all
```

Utiliser `http://localhost:8081`.

### `docker` ne fonctionne pas dans PowerShell

Utiliser le chemin complet :

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose ps
```

### Le modele n'est pas encore pret

```powershell
docker compose logs ollama-pull
```

Attendre `Exited (0)`. Le modele reste dans le volume `ollama_data`.

### Erreurs de connexion Airflow au demarrage

Airflow utilise maintenant `postgres` (volume `airflow_db`), donc le probleme
`database is locked` de SQLite n'apparait plus. Si Airflow ne demarre pas :

```powershell
docker compose ps postgres
docker compose logs --tail=50 postgres
```

Attendre que `mini-postgres` soit `healthy`, puis que `mini-airflow` soit
`healthy` avant de declencher le DAG.

### Airflow redemarre mais le webserver ne repond pas

Un redemarrage de conteneur peut laisser un fichier
`/opt/airflow/airflow-webserver.pid` perime : le PID est reutilise par un autre
processus et Airflow croit que le webserver tourne deja. Le `docker-compose.yml`
supprime ce fichier au demarrage (`entrypoint` + `command`). Si besoin, forcer :

```powershell
docker compose up -d --force-recreate airflow
```

Puis verifier <http://localhost:8081/health>.

### Airflow redemarre et le mot de passe change

Les metadonnees Airflow sont dans Postgres, mais le mot de passe standalone est
regenere a chaque recreation du conteneur. Apres recreation, relire :

```powershell
docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt
```

---

## 9. Frontend Next.js

Le frontend se trouve dans `C:\Users\YAHYA\Desktop\ai-stack\frontend` et ne
tourne pas dans Docker. C'est une application multi-pages avec barre laterale
(Dashboard, New task, History, Files, System) et des proxys serveur vers l'API
(pas de probleme CORS).

### Structure

```
frontend/
├── package.json
├── next.config.mjs
├── tsconfig.json
├── .env.local.example
├── lib/types.ts
├── components/
│   ├── AppShell.tsx
│   └── RunView.tsx
└── app/
    ├── layout.tsx
    ├── page.tsx
    ├── globals.css
    ├── new/page.tsx
    ├── history/page.tsx
    ├── history/[id]/page.tsx
    ├── files/page.tsx
    ├── system/page.tsx
    └── api/
        ├── tasks/route.ts
        ├── dashboard/route.ts
        ├── capabilities/route.ts
        ├── files/route.ts
        ├── health/route.ts
        ├── history/route.ts
        ├── history/[id]/route.ts
        ├── report/[id]/route.ts
        └── artifacts/[filename]/route.ts
```

### Demarrage

```powershell
cd C:\Users\YAHYA\Desktop\ai-stack\frontend
npm install
npm run dev
```

Ouvrir <http://localhost:3000>. Le formulaire permet de choisir l'action
(`auto`, `email`, `report`, `both`), de remplir les champs structures, de
joindre un dataset et de telecharger les artefacts. Les pages History, Files et
System s'appuient sur `/api/history`, `/api/files` et `/api/capabilities`.

### Test rapide du proxy

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:3000/api/tasks `
  -ContentType "application/json" `
  -Body '{"action":"report","title":"Test","content":"Resume les donnees","data":"a,b\n1,2\n3,4","filename":"test.csv"}'
```

Le resultat doit etre identique a l'appel direct sur le port 8000, avec deux
artefacts PDF et HTML.

### Mode production

```powershell
npm run build
npm run start
```

### Configurer l'URL du backend

Copier `.env.local.example` vers `.env.local` et modifier `API_URL` si l'API
n'est pas sur `http://localhost:8000/tasks`.

### Arreter le frontend

Si lance avec `npm run dev` ou `npm run start` dans un terminal : `Ctrl+C`.
Si lance en arriere-plan :

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen |
  Select-Object -ExpandProperty OwningProcess |
  ForEach-Object { Stop-Process -Id $_ }
```

---

## 10. Checklist de validation

- [ ] `docker compose config --quiet` sans erreur
- [ ] `docker compose up --build -d` termine
- [ ] `docker compose ps` : `api`, `ollama`, `airflow` en `healthy`
- [ ] `GET /health` renvoie `{"status":"ok"}`
- [ ] `email` -> `action = email`
- [ ] `report` -> `action = report`
- [ ] `both` -> `action = both` avec 2 resultats (`report` puis `email`)
- [ ] `What is the weather today?` -> `action = unknown` (`[unsupported]`)
- [ ] rapport : artefacts PDF + HTML telechargeables
- [ ] email : `.eml` (sans SMTP) ou envoi SMTP confirme
- [ ] logs MCP : `[EMAIL SAVED]`/`[EMAIL SENT]`, `[REPORT GENERATED]`, `POST /mcp 200`
- [ ] Airflow accessible sur `http://localhost:8081`
- [ ] DAG `task_workflow` visible et non pause
- [ ] Run du DAG : `prepare`, `call_agent`, `summarize` en `success`
- [ ] `npm run build` dans `frontend` sans erreur
- [ ] Frontend accessible sur `http://localhost:3000`
- [ ] `POST http://localhost:3000/api/tasks` renvoie les memes actions que l'API

Si toutes les cases sont cochees, le projet est complet et fonctionnel de bout
en bout.
