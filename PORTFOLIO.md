# Portfolio - Mini AI Task Agent

Ce fichier resume **uniquement** les ajouts faits pour rendre le projet
presentable en portfolio et demontrable a un client, puis explique comment tout
tester.

---

## 0. Mise a jour V2 - fini les mocks

Cette version remplace les simulations par de vrais artefacts et un vrai envoi :

- **Rapports reels** : PDF (ReportLab) + HTML stylise, avec resume numerique des
  donnees et tableau des premieres lignes.
- **Email reel** : envoi SMTP si `SMTP_HOST` est configure, sinon fichier `.eml`
  telechargeable (ouvrable dans Outlook/Thunderbird).
- **Upload de donnees** : CSV/TSV/TXT/JSON/MD (200 Ko max) injecte dans le
  rapport.
- **Pieces jointes** : pour l'action `both`, le PDF et le HTML sont attaches a
  l'email.
- **Artefacts telechargeables** : `GET /artifacts/{filename}` cote API et
  `/api/artifacts/[filename]` cote Next.js.
- **Historique enrichi** : chaque run stocke et affiche ses artefacts.
- **Airflow stabilise** : metadonnees dans Postgres (volume `airflow_db`) au
  lieu de SQLite, ce qui evite les erreurs `database is locked`.

---

## 0.bis Mise a jour V3 - outil utilisable au quotidien

Cette version transforme la demo en petit produit utilisable :

- **Taches structurees** : `action` explicite (`auto`, `email`, `report`, `both`)
  + champs `to`, `subject`, `body`, `title`, `content`. Le LLM n'est appele
  qu'en mode `auto`.
- **Rapports enrichis** : graphique en barres (moyennes), insights (meilleure
  moyenne, plage la plus large), tableau avec Count/Missing/Mean/Median/Min/Max/Std.
- **Frontend multi-pages** avec barre laterale :
  - `Dashboard` : stats, runs recents, actions rapides.
  - `New task` : formulaire complet, apercu du dataset, resultat detaille.
  - `History` : recherche texte + filtre par action, page de detail.
  - `Files` : bibliotheque d'artefacts PDF/HTML/EML.
  - `System` : sante, modele, mode email, liens services.
- **Nouveaux endpoints** : `GET /capabilities`, `GET /artifacts`, filtres
  `action`/`q` sur `/dashboard`, `/stats`, `/history`.
- **Validation** : `message` requis en mode `auto`, `to` requis pour un email,
  limites de taille cote API et proxy Next.js.

---

## 1. Ce qui a ete ajoute

### Cote backend

1. **Historique persistant** (`api/history.py`)
   - SQLite local (`data/history.db`), aucun nouveau package.
   - Volume Docker `api_data` : l'historique survit aux redemarrages.
   - Chaque run est enregistre avec : id, message, action, resultats, trace,
     duree, date.

2. **Trace d'execution par etape** (`agent/nodes.py`)
   - Chaque noeud LangGraph est chronometre : `classify`, `email`, `report`,
     `unsupported`, `finalize`.
   - La reponse contient `steps: [{node, status, ms}]` et `duration_ms`.

3. **Nouveaux endpoints**
   - `GET /dashboard?limit=20` : stats + runs recents en un seul appel.
   - `GET /history?limit=20` : liste des runs.
   - `GET /history/{id}` : detail d'un run.
   - `GET /history/{id}/report` : rapport Markdown telechargeable
     (`Content-Disposition: attachment`).

4. **Reponse `/tasks` enrichie**
   - `id`, `created_at`, `duration_ms`, `steps`, `artifacts` en plus de
     `action`, `results`, `final`.

5. **Generation de rapports reels** (`mcp_servers/report_server.py`)
   - PDF via ReportLab + HTML avec styles integres.
   - Parsing CSV/TSV/JSON, resume numerique (moyenne, min, max).
   - Ecriture dans le volume partage `artifacts_data` (`/app/artifacts`).

6. **Email reel** (`mcp_servers/email_server.py`)
   - `smtplib` + `EmailMessage`, TLS/SSL, authentification optionnelle.
   - Fallback `.eml` si `SMTP_HOST` est vide.
   - Pieces jointes PDF/HTML lues depuis `/app/artifacts`.

7. **Artefacts et telechargement**
   - `GET /artifacts/{filename}` renvoie le fichier avec le bon Content-Type.
   - Le state LangGraph transporte `data`, `filename` et `artifacts`.
   - L'ordre `both` est `report -> email` pour pouvoir joindre le PDF.

### Cote frontend

5. **Dashboard refondu** (`frontend/app/page.tsx`)
   - Cartes de stats : nombre de runs, latence moyenne, dernier run,
     email/report.
   - Composer + exemples en un clic.
   - Panneau resultat avec badge d'action, id, duree, date.
   - **Timeline visuelle** de la trace d'execution.
   - **Historique cliquable** des runs recents.
   - Bouton **"Rapport .md"** pour telecharger le run.

8. **Upload de donnees dans le composer**
   - Fichier CSV/TSV/TXT/JSON/MD, 200 Ko max, lu cote client.
   - Envoye avec `message`, `data`, `filename` via le proxy Next.js.

9. **Liste d'artefacts dans le panneau resultat**
   - Boutons de telechargement PDF / HTML / EML avec type et taille.
   - Message explicite quand SMTP n'est pas configure.

10. **Nouvelles routes proxy Next.js**
    - `app/api/dashboard/route.ts` -> `GET /dashboard`
    - `app/api/report/[id]/route.ts` -> `GET /history/{id}/report`
    - `app/api/artifacts/[filename]/route.ts` -> `GET /artifacts/{filename}`

### Documentation

11. Ce fichier `PORTFOLIO.md` : ce qui a ete ajoute + procedure de test.
12. `PLAN_PRODUIT.md` : la suite (auth, Postgres, approbations, connecteurs).

---

## 2. Pourquoi c'est "wow" pour un portfolio

- **Agent observable** : on voit chaque etape et sa duree, pas juste une reponse.
- **Persistance** : l'historique reste apres redemarrage.
- **Vrais livrables** : PDF, HTML et `.eml` telechargeables, pas des messages
  simules.
- **Email reel** : SMTP des que le client fournit ses identifiants.
- **Donnees du client** : upload CSV/JSON pris en compte dans le rapport.
- **Full-stack** : FastAPI + LangGraph + MCP + Next.js + Docker.
- **LLM prive** : Ollama en local, argument fort pour un client sensible.
- **Garde-fou** : une demande hors sujet renvoie `unknown`, pas une action inventee.

---

## 3. Comment tester (pas a pas)

### Prerequis

- Docker Desktop demarre.
- Node.js 22+ et npm.
- PowerShell.

Rappel : si `docker` ouvre un fichier vide, utiliser le chemin complet :

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
```

### Etape 1 - Demarrer le backend

```powershell
cd C:\Users\YAHYA\Desktop\ai-stack\mini-ai-agent
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose up -d --build
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose ps
```

Attendre que `mini-api` soit `healthy`.

```powershell
Invoke-RestMethod http://localhost:8000/health
# {"status":"ok"}
```

### Etape 2 - Demarrer le frontend

```powershell
cd C:\Users\YAHYA\Desktop\ai-stack\frontend
npm install
npm run build
npm run start
```

Ouvrir <http://localhost:3000>.

### Etape 3 - Scenarios a montrer

1. **Email** : cliquer sur `Email`.
   - Attendu : badge `Email`, trace `classify -> email -> finalize`.
2. **Report** : cliquer sur `Report`.
   - Attendu : badge `Report`, trace `classify -> report -> finalize`.
3. **Email + Report** : cliquer sur `Email + Report`.
   - Attendu : badge `Email + Report`, trace
     `classify -> report -> email -> finalize`, 2 resultats et 3 artefacts
     (PDF, HTML, EML ou envoi SMTP).
4. **Rapport avec donnees** : choisir un fichier CSV, ecrire
   "Create a report from the uploaded data", lancer.
   - Attendu : artefacts PDF + HTML, resume numerique et tableau visibles dans
     le PDF.
5. **Telechargement** : cliquer sur un artefact PDF ou HTML.
   - Attendu : le fichier s'ouvre ou se telecharge avec le bon type.
6. **Email** : cliquer sur `Email`.
   - Attendu : sans SMTP, un `.eml` est telechargeable ; avec SMTP, l'email est
     reellement envoye.
7. **Unsupported** : cliquer sur `Unsupported` (meteo).
   - Attendu : badge `Unsupported`, action `unknown`, message d'aide.
8. **Historique** : cliquer sur un run dans la colonne de droite.
   - Attendu : le panneau resultat se recharge avec la trace et les artefacts.
9. **Rapport Markdown** : cliquer sur `Rapport .md`.
   - Attendu : telechargement d'un fichier `agent-run-<id>.md` contenant la
     demande, la trace, les resultats, les artefacts et la reponse finale.

### Etape 4 - Verifier la persistance

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose restart api
```

Rafraichir <http://localhost:3000> : l'historique et les stats sont toujours la.
L'historique est stocke dans le volume Docker `api_data`.

### Etape 5 - Verifier l'API directement

```powershell
# Dashboard (stats + runs)
Invoke-RestMethod http://localhost:8000/dashboard?limit=5 | ConvertTo-Json -Depth 5

# Liste des runs
Invoke-RestMethod http://localhost:8000/history?limit=5 | ConvertTo-Json -Depth 5

# Detail + rapport d'un run (remplacer <ID>)
Invoke-RestMethod http://localhost:8000/history/<ID> | ConvertTo-Json -Depth 5
Invoke-WebRequest http://localhost:8000/history/<ID>/report
```

Documentation interactive : <http://localhost:8000/docs>.

### Etape 6 - Arreter

- Frontend : `Ctrl+C` dans le terminal `npm run start`.
- Backend :

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose down
```

Pour supprimer aussi l'historique :

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose down -v
```

---

## 4. Script de demo client (5 a 10 minutes)

1. Ouvrir <http://localhost:3000> : montrer les cartes de stats.
2. Charger un CSV, lancer un rapport : montrer le PDF et le HTML generes.
3. Montrer la **timeline** et les durees par etape.
4. Lancer `Email + Report` : montrer le `.eml` (ou l'envoi SMTP) avec pieces
   jointes PDF/HTML.
5. Cliquer sur **Rapport .md** et ouvrir le fichier telecharge.
6. Cliquer sur un run precedent dans l'historique : trace + artefacts conserves.
7. Lancer `Unsupported` : montrer que l'agent refuse d'inventer une action.
8. Ouvrir <http://localhost:8000/docs> : montrer les endpoints.
9. Expliquer l'architecture : LLM local, LangGraph, serveurs MCP, proxy Next.js.

Phrase de pitch :

> "C'est un agent d'automatisation de taches metier, execute en local, avec une
> trace complete de chaque etape, un historique persistant et des rapports
> telechargeables. La base est prete pour ajouter de vrais connecteurs, des
> approbations humaines et du multi-utilisateur."

---

## 5. Limites assumees (a dire au client)

- Email : reel **si** `SMTP_HOST` est configure ; sinon `.eml` (pas d'envoi).
- Les rapports sont des PDF/HTML simples (pas encore de graphiques matplotlib).
- L'historique agent utilise SQLite (suffisant pour une demo) ; Airflow utilise
  deja Postgres pour ses metadonnees.
- Pas encore d'authentification ni de multi-tenant.
- La latence depend du modele local et de la machine (le premier appel peut
  etre plus lent : chargement du modele).

La suite est decrite dans `PLAN_PRODUIT.md` : Postgres, Celery, auth, RBAC,
approbations, vrais connecteurs, observabilite.

---

## 6. Fichiers ajoutes ou modifies

```
mini-ai-agent/
├── api/
│   ├── __init__.py          (ajoute)
│   ├── history.py           (ajoute : artefacts + migration)
│   ├── main.py              (modifie : endpoints + artefacts + upload)
│   └── requirements.txt     (modifie : reportlab)
├── agent/
│   ├── graph.py             (modifie : both = report -> email)
│   ├── nodes.py             (modifie : parsing JSON + artefacts)
│   └── state.py             (modifie : data, filename, artefacts)
├── mcp_servers/
│   ├── email_server.py      (refonte : SMTP reel + .eml + pieces jointes)
│   └── report_server.py     (refonte : PDF ReportLab + HTML)
├── docker-compose.yml       (modifie : artefacts_data + SMTP + postgres)
└── .env.example             (modifie : variables SMTP)

frontend/
├── app/
│   ├── page.tsx             (refonte dashboard + upload + artefacts)
│   ├── globals.css          (styles dashboard/timeline/artefacts)
│   └── api/
│       ├── tasks/route.ts           (modifie : data/filename)
│       ├── dashboard/route.ts       (ajoute)
│       ├── report/[id]/route.ts     (ajoute)
│       └── artifacts/[filename]/route.ts (ajoute)
└── .env.local.example       (modifie : API_BASE)
```
