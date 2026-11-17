# Mini AI Task Agent

A small, fully Dockerized demonstration of **FastAPI + LangGraph + Ollama + MCP + Airflow**.

You send a natural-language task to the API. A LangGraph agent asks the local
`qwen2.5-coder:3b` model (running in Ollama) to classify the request, branches to
the correct MCP tool(s), and returns the result.

The agent produces **real artifacts**:

- **Reports** are generated as real **PDF + HTML** files (ReportLab), with a
  bar chart, key insights, a data preview and a numeric summary
  (count, missing, mean, median, min, max, std). Web text is normalized,
  de-duplicated and stripped of navigation/ad boilerplate, then synthesized into
  a direct answer before it is laid out as paragraphs and source tables.
- **Emails** are sent over **SMTP** when configured, otherwise saved as a real
  **`.eml`** file you can open in any mail client.
- Optional **data upload** (CSV/TSV/TXT/JSON/MD) is parsed and rendered inside
  the report.
- Tasks can be **structured** (explicit `action`, `to`, `subject`, `body`,
  `title`, `content`) or left to the LLM with `action: "auto"`.

No cloud API and no API key are required. Web research uses public search pages
(DuckDuckGo Lite, Jina Reader, Bing RSS, Wikipedia fallback). SMTP is optional.

---

## 1. Architecture

```
                         POST /tasks {action?, message?, fields...}
PowerShell / Airflow ─────────────────► FastAPI (api:8000)
                                             │
                                             │ LangGraph StateGraph
                                             ▼
                                    ┌─────────────────┐
                                    │    classify     │  explicit action or
                                    └────────┬────────┘  Ollama qwen2.5-coder:3b
                       ┌─────────────────────┼─────────────────────┐
                       ▼                     ▼                     ▼
                     email          research (report/both)        both
                       │                     │              research → report → email
                       ▼                     ▼
                email-mcp:8001      search-mcp:8003
                SMTP or .eml        web sources
                                             │
                                             ▼
                                       synthesize
                                    grounded answer
                                             │
                                             ▼
                                     report-mcp:8002
                                     PDF + HTML files
                                             │
                                             ▼
                                      finalize → JSON + URLs
```

Reports that have no uploaded dataset and no user-supplied content are enriched
with public web research. The `research` node calls `search-mcp`, which searches
DuckDuckGo Lite with retries, then falls back to Jina Reader, Bing RSS and
Wikipedia, extracting snippets and page text. The `synthesize` node turns those
extracts into a grounded answer (`Direct answer`, `Key facts`, `Details`):
extractive when numeric facts are present, otherwise Ollama with every model
number checked against the sources. `report-mcp` then renders the answer and a
**Web sources** table, so the report is never an empty shell.

Airflow is a separate orchestrator: its `task_workflow` DAG calls the same
`POST /tasks` endpoint. LangGraph makes the agent decisions; Airflow only
schedules and sequences the workflow. Airflow stores its metadata in the
`postgres` service (volume `airflow_db`).

If the request mentions neither `email` nor `report`, the agent returns
`action: "unknown"` and an `[unsupported]` message instead of inventing a task.

Explicit intent keywords are detected deterministically before Ollama, including
French (`rapport`, `courriel`, `compte rendu`) and common typos
(`geenrate a rapport`). This makes obvious requests fast and reliable; the LLM
is only used for ambiguous messages.

## 2. Services

| Service | Responsibility |
|---|---|
| `ollama` | Runs the local LLM server and stores models in a persistent volume. |
| `ollama-pull` | One-shot container that pulls `qwen2.5-coder:3b` before the API starts. |
| `api` | FastAPI app exposing `/health`, `/capabilities`, `/tasks`, `/dashboard`, `/history`, `/artifacts`; hosts the LangGraph agent. |
| `email-mcp` | MCP server exposing `send_email`: real SMTP or `.eml` fallback, with attachments. |
| `report-mcp` | MCP server exposing `generate_report`: real PDF + HTML files. |
| `search-mcp` | MCP server exposing `web_search`: DuckDuckGo Lite, Jina Reader, Bing RSS, Wikipedia fallback, page extracts. |
| `postgres` | PostgreSQL metadata database for Airflow (avoids SQLite lock issues). |
| `airflow` | Airflow standalone (scheduler + webserver) running the `task_workflow` DAG. |

Artifacts (PDF, HTML, EML) are written to the shared Docker volume
`artifacts_data` mounted at `/app/artifacts` in `api`, `email-mcp`, and
`report-mcp`.

## 3. How services communicate

- The API reaches Ollama at `http://ollama:11434`.
- The agent reaches the MCP servers with the **MCP protocol** over
  **Streamable HTTP**: `http://email-mcp:8001/mcp`,
  `http://report-mcp:8002/mcp`, and `http://search-mcp:8003/mcp`.
  It never imports the MCP server Python functions.
- The Airflow DAG calls the API at `http://api:8000/tasks`.
- All names (`ollama`, `api`, `email-mcp`, `report-mcp`, `search-mcp`) are Docker
  Compose service names resolved on the default Compose network.

## 4. Start everything

From the `mini-ai-agent` folder:

```powershell
docker compose up --build
```

The first run downloads the Airflow image, builds the Python image, and pulls the
`qwen2.5-coder:3b` model (about 2 GB). Later runs are much faster.

If PowerShell opens the empty `C:\Windows\System32\docker` file instead of Docker,
use:

```powershell
docker.exe compose up --build
```

Wait until the API is healthy (the `ollama-pull` container must finish first):

```powershell
docker compose ps
```

### Optional: real email delivery

Copy `.env.example` to `.env` and fill in the SMTP values:

```powershell
Copy-Item .env.example .env
```

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=you@gmail.com
SMTP_TLS=true
SMTP_SSL=false
```

With `SMTP_HOST` empty, emails are saved as `.eml` artifacts instead of being
sent. This keeps the demo runnable offline.

## 5. Test the API with PowerShell

Report with uploaded data:

```powershell
$body = @{
  message  = "Create a quarterly revenue report"
  data     = "region,revenue`nNorth,120`nSouth,95`nEast,130"
  filename = "sales.csv"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType "application/json" -Body $body
```

The response contains `artifacts` with downloadable URLs such as
`/artifacts/report-xxxx.pdf` and `/artifacts/report-xxxx.html`.

Report with automatic web research (no dataset or content supplied):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType "application/json" `
  -Body '{"message":"Generate a report about sickle cell disease biomarkers"}'
```

The trace then contains `classify -> research -> synthesize -> report -> finalize`,
and the PDF/HTML report includes a synthesized answer plus a **Web sources** table
with titles, URLs and snippets.

Email branch (SMTP or `.eml` fallback):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType "application/json" `
  -Body '{"message":"Send an email to John"}'
```

Both branches (report first, then email with the PDF/HTML attached):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType "application/json" `
  -Body '{"message":"Send an email to John and generate a report about Q3 sales"}'
```

Unsupported request (no email/report keyword):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tasks `
  -ContentType "application/json" `
  -Body '{"message":"What is the weather today?"}'
```

Download an artifact:

```powershell
Invoke-WebRequest http://localhost:8000/artifacts/report-xxxx.pdf -OutFile report.pdf
```

Health check:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/health
```

The response contains `action`, the per-tool `results`, the joined `final`
answer, the `steps` trace, and `artifacts`.

### API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe. |
| `GET` | `/capabilities` | Version, model, actions, email mode, artifact count. |
| `POST` | `/tasks` | Run the agent. Structured fields: `action` (`auto`, `email`, `report`, `both`), `to`, `subject`, `body`, `title`, `content`, `data`, `filename`. |
| `GET` | `/dashboard?limit=20&action=&q=` | Stats + recent runs, filterable. |
| `GET` | `/stats?action=&q=` | Aggregated stats, filterable. |
| `GET` | `/history?limit=20&action=&q=` | Recent runs, filterable. |
| `GET` | `/history/{id}` | One run with trace and artifacts. |
| `GET` | `/history/{id}/report` | Markdown run report (download). |
| `GET` | `/artifacts?limit=100` | List generated artifacts, newest first. |
| `GET` | `/artifacts/{filename}` | Download a PDF, HTML, or EML artifact. |

With `action: "auto"`, `message` is required and the local LLM classifies it.
With an explicit action, the matching fields are used directly and the LLM is
skipped. When a report has neither `data` nor `content`, the agent performs web
research, synthesizes an answer, and embeds both in the PDF/HTML.

## 6. Airflow UI

Open <http://localhost:8081>.

The standalone container creates an `admin` user with a generated password.
Read it from the password file:

```powershell
docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt
```

Then unpause and trigger the `task_workflow` DAG (it is created unpaused but has
no schedule, so trigger it manually with the play button).

If the webserver does not answer after a container restart, recreate it (the
Compose command removes the stale `/opt/airflow/airflow-webserver.pid`):

```powershell
docker compose up -d --force-recreate airflow
```

## 7. Inspect logs

```powershell
docker compose logs -f api
docker compose logs -f email-mcp
docker compose logs -f report-mcp
docker compose logs -f search-mcp
docker compose logs -f ollama
docker compose logs -f airflow
```

The `email-mcp` logs show `[EMAIL SENT]`, `[EMAIL SAVED]`, or `[EMAIL ERROR]`
with the transport used. The `report-mcp` logs show the generated PDF/HTML files,
and `search-mcp` logs the search engine, query and number of results.

## 8. Stop everything

```powershell
docker compose down
```

Remove the downloaded Ollama model, history, and artifacts too:

```powershell
docker compose down -v
```

## 9. Mini frontend (Next.js)

A separate Next.js app lives in the sibling folder `../frontend` (no Docker). It
proxies `POST /api/tasks` to the FastAPI service, so no CORS change is needed.

```powershell
cd ..\frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The proxy target defaults to
`http://localhost:8000`; override it with `API_URL` / `API_BASE` in `.env.local`
(see `.env.local.example`).

The UI is a multi-page app with a sidebar:

- **Dashboard**: stats, recent runs and quick actions.
- **New task**: explicit action selector (`auto`, `email`, `report`, `both`),
  recipient/subject/body, report title/content, optional dataset upload with
  preview.
- **History**: text search + action filter, run detail pages.
- **Files**: artifact library (PDF/HTML/EML) with downloads.
- **System**: health, model, email mode, artifact count and service links.
- Execution timeline (`classify`, `research`, `synthesize`, `report`, `email`, `finalize`).
- Downloadable PDF/HTML/EML artifacts and a Markdown run report.

Production mode:

```powershell
npm run build
npm run start
```

## Project layout

```
mini-ai-agent/
├── docker-compose.yml
├── .env.example
├── README.md
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── history.py
│   └── main.py
├── agent/
│   ├── __init__.py
│   ├── graph.py
│   ├── nodes.py
│   ├── state.py
│   └── llm.py
├── mcp_servers/
│   ├── email_server.py
│   ├── report_server.py
│   └── search_server.py
└── airflow/
    ├── Dockerfile
    └── dags/
        └── task_workflow.py

../frontend/            (sibling Next.js UI, not Dockerized)
├── package.json
├── next.config.mjs
├── tsconfig.json
├── lib/
│   └── types.ts
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
