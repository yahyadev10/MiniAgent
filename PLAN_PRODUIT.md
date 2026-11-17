# Plan produit - De POC a plateforme utilisable

> Objectif : transformer le POC `mini-ai-agent` en un produit qu'un client peut
> acheter, installer et utiliser au quotidien. Ce document decrit la cible, la
> conception, les fonctions a creer, l'ordre des travaux et les criteres
> d'acceptation. Aucun code n'est modifie ici : c'est le plan de reference.

---

## 1. Resume executif

Aujourd'hui le projet demontre une boucle technique :

- un utilisateur envoie une demande en langage naturel ;
- un LLM local classe la demande ;
- LangGraph choisit une branche ;
- des serveurs MCP generent de vrais artefacts (PDF/HTML) et envoient l'email
  via SMTP (ou sauvegardent un `.eml`) ;
- Airflow declenche le meme endpoint.

Pour un client, cela reste une demo. Un produit utilisable doit repondre a
quatre questions :

1. **Qui fait quoi ?** -> authentification, tenants, roles, audit.
2. **Est-ce fiable ?** -> execution asynchrone durable, retries, idempotence,
   approbations humaines, tracabilite.
3. **Est-ce integre a mes outils ?** -> connecteurs (SMTP, Slack, Teams, Drive,
   CRM, webhooks), au-dela de SMTP + PDF/HTML deja en place.
4. **Est-ce exploitable ?** -> dashboard, historique, couts LLM, observabilite,
   sauvegardes, deploiement on-prem ou cloud.

**Positionnement recommande** : "Agent d'automatisation de taches metier,
executable en local/on-prem, avec validation humaine et piste d'audit."

**Difference cle** : LLM prive (Ollama) + connecteurs MCP + approbations +
audit. C'est ce qui rassure un client qui ne veut pas envoyer ses donnees a un
LLM public.

---

## 2. Etat actuel vs cible

| Sujet | Aujourd'hui (POC) | Cible produit |
|---|---|---|
| Utilisateurs | Aucun | Auth OIDC, sessions, multi-tenant |
| Roles | Aucun | owner / admin / operator / viewer |
| Persistance | SQLite (runs, steps, artifacts) | PostgreSQL (tasks, runs, steps, artifacts) |
| Execution | Synchrone dans la requete | Asynchrone, durable, avec reprise |
| Fiabilite | Retry MCP simple | Retries, timeouts, DLQ, idempotence |
| Validation | Champs requis + limites API | Approbation humaine avant action sensible |
| Connecteurs | SMTP + PDF/HTML reels avec graphiques | SMTP/SendGrid, Slack, Teams, S3, PDF, CRM, webhooks |
| LLM | Ollama uniquement, mode `auto` optionnel | Abstraction Ollama / OpenAI / Azure / Mistral |
| Couts | Non mesures | Tokens, cout par run, quotas par tenant |
| Audit | Logs Docker | Audit immuable consultable dans l'UI |
| Frontend | Dashboard, New task, History, Files, System | Dashboard, composer, timeline, approbations, admin |
| Scheduling | Airflow standalone + Postgres (demo) | Celery beat ou Airflow + Postgres, multi-tenant |
| Observabilite | Logs | Logs structures, traces OTel, metriques, SLO |
| Tests | Manuels + scenarios verifies | Unit, integration, e2e, evals LLM, charge |
| Deploiement | Docker Compose | Compose on-prem + Helm/K8s cloud |
| Securite | Secrets en env | Coffre de secrets, chiffrement, RBAC, RLS |

---

## 3. Personas et cas d'usage

### Personas

- **Operateur** : lance des taches, suit les runs, approuve les actions.
- **Manager** : consulte l'historique, les couts, les SLA.
- **Admin** : gere les connecteurs, les utilisateurs, les quotas.
- **Developpeur integration** : ajoute des connecteurs MCP et des templates.

### Cas d'usage a vendre (par ordre de valeur)

1. **Rapport hebdomadaire automatique** : agrege des donnees, genere un PDF,
   l'envoie par email avec approbation.
2. **Triage de boite mail** : classe les emails, cree des taches, notifie Slack.
3. **Onboarding client** : cree un dossier, envoie un email, planifie un rappel.
4. **Veille concurrentielle** : collecte des sources, resume, publie un rapport.
5. **Mise a jour CRM** : extrait les informations d'un email et met a jour le CRM.
6. **Reponse a incident** : cree un canal Slack, ouvre un ticket, notifie l'astreinte.

---

## 4. Architecture cible

```
                        ┌──────────────────────────────┐
                        │  Next.js (App Router)        │
                        │  Dashboard / Composer / UI   │
                        └──────────────┬───────────────┘
                                       │ HTTPS + cookie de session
                                       ▼
                        ┌──────────────────────────────┐
                        │  API Gateway / BFF (FastAPI) │
                        │  Auth, tenant, quotas, audit │
                        └──────┬───────────────┬───────┘
                               │               │
                  ┌────────────▼───┐     ┌─────▼─────────────┐
                  │  PostgreSQL    │     │  Redis (queue)    │
                  │  donnees + RLS │     │  Celery broker    │
                  └────────────┬───┘     └─────┬─────────────┘
                               │               │
                               ▼               ▼
                        ┌──────────────────────────────┐
                        │  Worker d'execution          │
                        │  LangGraph + etapes durables │
                        └──────┬───────────────┬───────┘
                               │               │
                  ┌────────────▼───┐     ┌─────▼─────────────┐
                  │  MCP Gateway   │     │  LLM Provider     │
                  │  credentials   │     │  Ollama/OpenAI... │
                  └──────┬─────────┘     └───────────────────┘
                         │
        ┌────────────────┼────────────────┬────────────────┐
        ▼                ▼                ▼                ▼
   email-mcp        report-mcp        slack-mcp        crm-mcp
   (SMTP)           (PDF/S3)          (Slack)          (HubSpot)
```

Composants :

- **Frontend Next.js** : UI, proxy authentifie vers l'API.
- **API FastAPI** : REST, auth, tenancy, validation, SSE.
- **Worker** : execute les runs hors requete HTTP.
- **PostgreSQL** : source de verite.
- **Redis** : file Celery, cache, rate limit.
- **MCP Gateway** : injecte les credentials du tenant et proxy les appels MCP.
- **LLM Provider** : abstraction multi-fournisseur.
- **Object storage** : MinIO/S3 pour les artefacts (PDF, CSV, images).
- **Observabilite** : OTel, Prometheus, Grafana, Loki, Sentry.
- **Scheduler** : Celery beat (produit) et Airflow (batch interne optionnel).

---

## 5. Decisions structurantes (ADR)

| ID | Decision | Choix recommande | Pourquoi |
|---|---|---|---|
| ADR-01 | Execution asynchrone | Celery + Redis | Simple, mature, suffisant pour des runs de quelques minutes |
| ADR-02 | Durabilite forte | Option Temporal | Si le client exige des workflows longs et reprenables |
| ADR-03 | Base de donnees | PostgreSQL | Transactions, RLS, JSONB, ecosysteme |
| ADR-04 | Multi-tenancy | `tenant_id` + RLS Postgres | Isolation forte, une seule base |
| ADR-05 | Auth | Auth.js (front) + JWT/OIDC (API) | SSO entreprise, sessions navigateur |
| ADR-06 | Secrets | Chiffrement applicatif + KMS/Vault | Jamais de secret en clair en base |
| ADR-07 | LLM | Abstraction `LLMProvider` | Ollama par defaut, cloud en option |
| ADR-08 | Connecteurs | MCP + gateway | Contrat standard, isolation des credentials |
| ADR-09 | Artefacts | S3/MinIO + URLs signees | Pas de fichiers dans le conteneur |
| ADR-10 | Scheduling produit | Celery beat | Airflow est trop lourd pour du multi-tenant |
| ADR-11 | Airflow | Batch interne / on-prem optionnel | Garder la valeur "orchestration visible" |
| ADR-12 | Deploiement | Compose on-prem + Helm cloud | Deux modes de vente |

---

## 6. Modele de donnees

### Tables principales

```
tenants
  id UUID PK
  name TEXT
  slug TEXT UNIQUE
  plan TEXT
  created_at TIMESTAMPTZ

users
  id UUID PK
  email TEXT UNIQUE
  password_hash TEXT NULL
  oidc_subject TEXT NULL
  display_name TEXT
  created_at TIMESTAMPTZ

memberships
  id UUID PK
  tenant_id UUID FK -> tenants
  user_id UUID FK -> users
  role TEXT CHECK (owner|admin|operator|viewer)
  UNIQUE (tenant_id, user_id)

api_keys
  id UUID PK
  tenant_id UUID
  name TEXT
  key_hash TEXT
  scopes TEXT[]
  last_used_at TIMESTAMPTZ

connectors
  id UUID PK
  tenant_id UUID
  type TEXT (smtp|slack|teams|s3|hubspot|jira|webhook)
  name TEXT
  config JSONB
  secret_ref TEXT
  status TEXT (active|error|disabled)
  created_at TIMESTAMPTZ

workflows
  id UUID PK
  tenant_id UUID
  name TEXT
  description TEXT
  definition JSONB
  active_version INT
  created_at TIMESTAMPTZ

workflow_versions
  id UUID PK
  workflow_id UUID
  version INT
  definition JSONB
  created_by UUID
  created_at TIMESTAMPTZ
  UNIQUE (workflow_id, version)

tasks
  id UUID PK
  tenant_id UUID
  workflow_id UUID NULL
  input JSONB
  idempotency_key TEXT
  status TEXT (queued|running|awaiting_approval|succeeded|failed|canceled)
  created_by UUID
  created_at TIMESTAMPTZ
  UNIQUE (tenant_id, idempotency_key)

runs
  id UUID PK
  task_id UUID FK -> tasks
  tenant_id UUID
  workflow_version INT
  status TEXT
  started_at TIMESTAMPTZ
  finished_at TIMESTAMPTZ
  error TEXT NULL
  total_tokens INT
  total_cost NUMERIC

steps
  id UUID PK
  run_id UUID FK -> runs
  node TEXT
  attempt INT
  status TEXT (pending|running|succeeded|failed|skipped|awaiting_approval)
  input JSONB
  output JSONB
  error TEXT NULL
  started_at TIMESTAMPTZ
  finished_at TIMESTAMPTZ

approvals
  id UUID PK
  run_id UUID
  step_id UUID
  status TEXT (pending|approved|rejected|expired)
  requested_by UUID
  decided_by UUID NULL
  comment TEXT NULL
  created_at TIMESTAMPTZ
  decided_at TIMESTAMPTZ

artifacts
  id UUID PK
  run_id UUID
  tenant_id UUID
  kind TEXT (pdf|csv|json|png)
  filename TEXT
  storage_key TEXT
  size_bytes BIGINT
  sha256 TEXT
  created_at TIMESTAMPTZ

audit_events
  id UUID PK
  tenant_id UUID
  actor_id UUID NULL
  action TEXT
  resource_type TEXT
  resource_id UUID NULL
  metadata JSONB
  ip INET
  prev_hash TEXT
  hash TEXT
  created_at TIMESTAMPTZ

schedules
  id UUID PK
  tenant_id UUID
  workflow_id UUID
  cron TEXT
  timezone TEXT
  enabled BOOL
  next_run_at TIMESTAMPTZ

llm_usage
  id UUID PK
  tenant_id UUID
  run_id UUID
  provider TEXT
  model TEXT
  prompt_tokens INT
  completion_tokens INT
  cost NUMERIC
  created_at TIMESTAMPTZ

eval_cases
  id UUID PK
  name TEXT
  input TEXT
  expected_action TEXT
  expected_json JSONB

eval_runs
  id UUID PK
  provider TEXT
  model TEXT
  score NUMERIC
  passed INT
  failed INT
  created_at TIMESTAMPTZ
```

### Regles

- Toutes les tables metier portent `tenant_id` (sauf `users`, `eval_*`).
- RLS Postgres : `tenant_id = current_setting('app.tenant_id')::uuid`.
- `audit_events` est append-only (pas d'UPDATE/DELETE).
- Les artefacts ne sont jamais stockes en base, seulement leurs metadonnees.

---

## 7. API cible

### Conventions

- Prefixe `/v1`.
- Reponse d'erreur uniforme :
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`.
- Pagination : `?limit=50&cursor=...`.
- Idempotence : header `Idempotency-Key` sur les POST de creation.

### Auth et tenants

```
POST   /v1/auth/login                 login_password()
POST   /v1/auth/logout                logout()
GET    /v1/auth/me                    get_me()
GET    /v1/auth/oidc/start            oidc_start()
GET    /v1/auth/oidc/callback         oidc_callback()
GET    /v1/tenants                    list_tenants()
POST   /v1/tenants                    create_tenant()
GET    /v1/tenants/{id}/members       list_members()
POST   /v1/tenants/{id}/members       add_member()
PATCH  /v1/tenants/{id}/members/{uid} update_member_role()
DELETE /v1/tenants/{id}/members/{uid} remove_member()
```

### Taches et runs

```
POST   /v1/tasks                      create_task()
GET    /v1/tasks                      list_tasks()
GET    /v1/tasks/{id}                 get_task()
POST   /v1/tasks/{id}/cancel          cancel_task()
GET    /v1/tasks/{id}/events          stream_task_events()   (SSE)
GET    /v1/runs                       list_runs()
GET    /v1/runs/{id}                  get_run()
GET    /v1/runs/{id}/steps            list_steps()
GET    /v1/runs/{id}/artifacts        list_artifacts()
GET    /v1/runs/{id}/artifacts/{aid}  download_artifact()
GET    /v1/runs/{id}/logs             get_run_logs()
POST   /v1/runs/{id}/retry            retry_run()
```

### Approbations

```
GET    /v1/approvals                  list_pending_approvals()
POST   /v1/approvals/{id}/approve     approve_step()
POST   /v1/approvals/{id}/reject      reject_step()
```

### Workflows et templates

```
GET    /v1/workflows                  list_workflows()
POST   /v1/workflows                  create_workflow()
GET    /v1/workflows/{id}             get_workflow()
PATCH  /v1/workflows/{id}             update_workflow()
POST   /v1/workflows/{id}/validate    validate_workflow()
POST   /v1/workflows/{id}/versions    publish_version()
POST   /v1/workflows/{id}/run         run_workflow()
GET    /v1/templates                  list_templates()
POST   /v1/templates/{id}/instantiate instantiate_template()
```

### Connecteurs

```
GET    /v1/connectors                 list_connectors()
POST   /v1/connectors                 create_connector()
GET    /v1/connectors/{id}            get_connector()
PATCH  /v1/connectors/{id}            update_connector()
DELETE /v1/connectors/{id}            delete_connector()
POST   /v1/connectors/{id}/test       test_connector()
POST   /v1/connectors/{id}/rotate     rotate_credentials()
GET    /v1/connectors/catalog         list_connector_catalog()
```

### Planning et admin

```
GET    /v1/schedules                  list_schedules()
POST   /v1/schedules                  create_schedule()
PATCH  /v1/schedules/{id}             update_schedule()
POST   /v1/schedules/{id}/pause       pause_schedule()
POST   /v1/schedules/{id}/resume      resume_schedule()
GET    /v1/admin/audit                query_audit_events()
GET    /v1/admin/usage                get_usage_summary()
GET    /v1/admin/health               get_system_health()
GET    /healthz                       liveness()
GET    /readyz                        readiness()
GET    /metrics                       prometheus_metrics()
```

### Exemple de contrat

```json
POST /v1/tasks
{
  "message": "Envoie un email a Jean et genere un rapport Q3",
  "workflow_id": null,
  "connector_ids": ["smtp-1"],
  "require_approval": true
}

201 Created
{
  "id": "3f6c...",
  "status": "queued",
  "run_id": "9a1b...",
  "events_url": "/v1/tasks/3f6c.../events"
}
```

---

## 8. Conception backend

### 8.1 Arborescence cible

```
api/
├── main.py
├── config/
│   └── settings.py
├── db/
│   ├── session.py
│   ├── base.py
│   ├── models.py
│   └── migrations/
├── auth/
│   ├── security.py
│   ├── oidc.py
│   └── dependencies.py
├── middleware/
│   ├── request_id.py
│   ├── rate_limit.py
│   ├── tenant.py
│   └── audit.py
├── repositories/
│   ├── base.py
│   ├── tenants.py
│   ├── users.py
│   ├── tasks.py
│   ├── runs.py
│   ├── steps.py
│   ├── approvals.py
│   ├── artifacts.py
│   ├── connectors.py
│   ├── workflows.py
│   ├── schedules.py
│   ├── audit.py
│   └── usage.py
├── services/
│   ├── agent_service.py
│   ├── workflow_service.py
│   ├── connector_service.py
│   ├── approval_service.py
│   ├── artifact_service.py
│   ├── audit_service.py
│   ├── usage_service.py
│   ├── scheduler_service.py
│   └── notification_service.py
├── llm/
│   ├── provider.py
│   ├── ollama_provider.py
│   ├── openai_provider.py
│   ├── prompts.py
│   └── structured.py
├── agent/
│   ├── state.py
│   ├── graph.py
│   ├── nodes.py
│   └── tools.py
├── workers/
│   ├── celery_app.py
│   └── tasks.py
├── api/
│   ├── deps.py
│   ├── errors.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── tenants.py
│   │   ├── tasks.py
│   │   ├── runs.py
│   │   ├── approvals.py
│   │   ├── workflows.py
│   │   ├── connectors.py
│   │   ├── schedules.py
│   │   ├── admin.py
│   │   └── health.py
│   └── schemas/
│       ├── auth.py
│       ├── task.py
│       ├── run.py
│       ├── workflow.py
│       ├── connector.py
│       └── common.py
└── tests/
```

### 8.2 Fonctions par module

#### `config/settings.py`

```python
class Settings(BaseSettings): ...
def get_settings() -> Settings
def get_database_url() -> str
def get_redis_url() -> str
def get_llm_settings() -> dict
```

#### `db/session.py`

```python
def get_engine() -> Engine
def get_session_factory() -> sessionmaker
def get_db() -> Generator[Session, None, None]
@contextmanager
def session_scope() -> Iterator[Session]
```

#### `db/models.py`

```python
class Tenant(Base): ...
class User(Base): ...
class Membership(Base): ...
class ApiKey(Base): ...
class Connector(Base): ...
class Workflow(Base): ...
class WorkflowVersion(Base): ...
class Task(Base): ...
class Run(Base): ...
class Step(Base): ...
class Approval(Base): ...
class Artifact(Base): ...
class AuditEvent(Base): ...
class Schedule(Base): ...
class LlmUsage(Base): ...
class EvalCase(Base): ...
class EvalRun(Base): ...
```

#### `auth/security.py`

```python
def hash_password(password: str) -> str
def verify_password(password: str, hashed: str) -> bool
def create_access_token(user_id: UUID, tenant_id: UUID, role: str) -> str
def create_refresh_token(user_id: UUID) -> str
def decode_token(token: str) -> TokenPayload
def require_role(*roles: str) -> Callable
```

#### `auth/oidc.py`

```python
def build_oidc_client() -> OIDCClient
def get_authorization_url(state: str) -> str
def exchange_code(code: str) -> dict
def map_claims_to_user(claims: dict) -> UserClaims
def provision_user(claims: UserClaims, tenant_id: UUID) -> User
```

#### `auth/dependencies.py`

```python
def get_current_user() -> User
def get_current_tenant() -> Tenant
def get_current_membership() -> Membership
def get_api_key_principal() -> ApiKeyPrincipal
```

#### `middleware/*.py`

```python
class RequestIdMiddleware(BaseHTTPMiddleware): ...
class RateLimitMiddleware(BaseHTTPMiddleware): ...
class TenantMiddleware(BaseHTTPMiddleware): ...
class AuditMiddleware(BaseHTTPMiddleware): ...

def extract_tenant_id(request: Request) -> UUID | None
def build_rate_limit_key(request: Request) -> str
```

#### `repositories/base.py`

```python
class BaseRepository:
    def get(self, id: UUID) -> T | None
    def list(self, **filters) -> list[T]
    def create(self, **data) -> T
    def update(self, id: UUID, **data) -> T
    def delete(self, id: UUID) -> None
```

#### `repositories/tasks.py`

```python
class TaskRepository(BaseRepository):
    def create_task(self, tenant_id: UUID, payload: TaskCreate) -> Task
    def get_task(self, tenant_id: UUID, task_id: UUID) -> Task
    def list_tasks(self, tenant_id: UUID, cursor: str | None, limit: int) -> Page[Task]
    def update_status(self, task_id: UUID, status: str) -> Task
    def find_by_idempotency_key(self, tenant_id: UUID, key: str) -> Task | None
```

#### `repositories/runs.py`

```python
class RunRepository(BaseRepository):
    def create_run(self, task: Task) -> Run
    def get_run(self, tenant_id: UUID, run_id: UUID) -> Run
    def list_runs(self, tenant_id: UUID, cursor: str | None, limit: int) -> Page[Run]
    def start_run(self, run_id: UUID) -> Run
    def finish_run(self, run_id: UUID, status: str, error: str | None) -> Run
    def append_step(self, run_id: UUID, node: str, payload: dict) -> Step
    def update_step(self, step_id: UUID, status: str, output: dict | None) -> Step
```

#### `services/agent_service.py`

```python
class AgentService:
    def classify_request(self, message: str) -> Classification
    def validate_action(self, action: str, message: str) -> str
    def detect_intents(self, message: str) -> IntentSet
    def build_plan(self, classification: Classification) -> Plan
    def execute_plan(self, run: Run, plan: Plan) -> RunResult
    def handle_approval(self, approval: Approval) -> RunResult
    def cancel_run(self, run_id: UUID) -> None
```

#### `services/workflow_service.py`

```python
class WorkflowService:
    def create_workflow(self, tenant_id: UUID, payload: WorkflowCreate) -> Workflow
    def publish_version(self, workflow_id: UUID, definition: dict) -> WorkflowVersion
    def validate_definition(self, definition: dict) -> ValidationResult
    def start_run(self, tenant_id: UUID, workflow_id: UUID, input: dict) -> Run
    def resume_run(self, run_id: UUID) -> Run
    def cancel_run(self, run_id: UUID) -> None
```

#### `services/connector_service.py`

```python
class ConnectorService:
    def create_connector(self, tenant_id: UUID, payload: ConnectorCreate) -> Connector
    def test_connection(self, connector_id: UUID) -> ConnectorTestResult
    def get_credentials(self, connector_id: UUID) -> ConnectorCredentials
    def rotate_credentials(self, connector_id: UUID, secret: str) -> Connector
    def list_capabilities(self, connector_id: UUID) -> list[ToolCapability]
```

#### `services/approval_service.py`

```python
class ApprovalService:
    def request_approval(self, run_id: UUID, step_id: UUID, reason: str) -> Approval
    def approve(self, approval_id: UUID, actor: User, comment: str) -> Run
    def reject(self, approval_id: UUID, actor: User, comment: str) -> Run
    def list_pending(self, tenant_id: UUID) -> list[Approval]
    def expire_stale(self, older_than: timedelta) -> int
```

#### `services/artifact_service.py`

```python
class ArtifactService:
    def save_artifact(self, run_id: UUID, kind: str, filename: str, data: bytes) -> Artifact
    def get_artifact(self, artifact_id: UUID) -> Artifact
    def sign_download_url(self, artifact_id: UUID, ttl: int) -> str
    def delete_artifact(self, artifact_id: UUID) -> None
```

#### `services/audit_service.py`

```python
class AuditService:
    def record_event(self, event: AuditEventCreate) -> AuditEvent
    def query_events(self, tenant_id: UUID, filters: AuditFilters) -> Page[AuditEvent]
    def export_events(self, tenant_id: UUID, fmt: str) -> bytes
    def verify_chain(self, tenant_id: UUID) -> ChainVerification
```

#### `services/usage_service.py`

```python
class UsageService:
    def record_llm_usage(self, run_id: UUID, usage: LlmUsageData) -> None
    def compute_cost(self, provider: str, model: str, usage: LlmUsageData) -> Decimal
    def get_usage_summary(self, tenant_id: UUID, period: Period) -> UsageSummary
    def check_quota(self, tenant_id: UUID) -> QuotaStatus
```

#### `services/scheduler_service.py`

```python
class SchedulerService:
    def create_schedule(self, tenant_id: UUID, payload: ScheduleCreate) -> Schedule
    def compute_next_run(self, cron: str, tz: str, now: datetime) -> datetime
    def tick(self) -> int
    def pause(self, schedule_id: UUID) -> Schedule
    def resume(self, schedule_id: UUID) -> Schedule
```

#### `llm/provider.py`

```python
class LLMProvider(ABC):
    def chat(self, messages: list[Message], **options) -> LLMResponse
    def embed(self, texts: list[str]) -> list[list[float]]
    def count_tokens(self, text: str) -> int
    def name(self) -> str

def get_provider(settings: Settings) -> LLMProvider
def register_provider(name: str, factory: Callable[[], LLMProvider]) -> None
```

#### `llm/ollama_provider.py`

```python
class OllamaProvider(LLMProvider):
    def chat(self, messages, **options) -> LLMResponse
    def embed(self, texts) -> list[list[float]]
    def count_tokens(self, text) -> int
```

#### `llm/openai_provider.py`

```python
class OpenAIProvider(LLMProvider): ...
class AzureOpenAIProvider(LLMProvider): ...
class MistralProvider(LLMProvider): ...
```

#### `llm/prompts.py`

```python
def build_router_prompt() -> str
def build_validation_prompt(message: str) -> str
def build_email_prompt(context: dict) -> str
def build_report_prompt(context: dict) -> str
def build_repair_prompt(raw: str, error: str) -> str
def get_prompt_version() -> str
```

#### `llm/structured.py`

```python
def parse_json_response(raw: str) -> dict
def extract_json_with_fallbacks(raw: str) -> dict
def repair_json(raw: str) -> dict
def validate_schema(data: dict, schema: type[BaseModel]) -> BaseModel
```

#### `agent/state.py`

```python
class AgentState(TypedDict):
    message: str
    action: str
    data: dict
    plan: list[PlanStep]
    results: Annotated[list[str], operator.add]
    approval: dict | None
    error: str | None
```

#### `agent/graph.py`

```python
def build_graph() -> CompiledGraph
def route_after_classify(state: AgentState) -> str
def route_after_validation(state: AgentState) -> str
def route_after_approval(state: AgentState) -> str
def route_after_step(state: AgentState) -> str
```

#### `agent/nodes.py`

```python
def classify_node(state: AgentState) -> AgentState
def validate_node(state: AgentState) -> AgentState
def plan_node(state: AgentState) -> AgentState
def approval_node(state: AgentState) -> AgentState
def email_node(state: AgentState) -> AgentState
def report_node(state: AgentState) -> AgentState
def tool_node(state: AgentState) -> AgentState
def error_node(state: AgentState) -> AgentState
def finalize_node(state: AgentState) -> AgentState
```

#### `agent/tools.py`

```python
def list_mcp_tools(url: str) -> list[ToolDefinition]
def call_mcp_tool(url: str, tool: str, arguments: dict) -> ToolResult
def with_retry(fn: Callable, attempts: int, backoff: float) -> Any
def with_timeout(fn: Callable, seconds: float) -> Any
def validate_tool_arguments(tool: str, arguments: dict) -> None
```

#### `workers/celery_app.py`

```python
def create_celery_app(settings: Settings) -> Celery
```

#### `workers/tasks.py`

```python
@celery_app.task(bind=True, max_retries=3)
def run_task(self, run_id: str) -> None
@celery_app.task(bind=True, max_retries=3)
def execute_step(self, run_id: str, step_id: str) -> None
@celery_app.task
def poll_approvals() -> None
@celery_app.task
def tick_schedules() -> None
@celery_app.task
def cleanup_artifacts() -> None
@celery_app.task
def send_notification(event: dict) -> None
```

#### `api/routers/*.py`

```python
# tasks.py
def create_task(payload: TaskCreate, user: User, db: Session) -> TaskRead
def list_tasks(cursor: str | None, limit: int, user: User) -> Page[TaskRead]
def get_task(task_id: UUID, user: User) -> TaskRead
def cancel_task(task_id: UUID, user: User) -> TaskRead
def stream_task_events(task_id: UUID, user: User) -> StreamingResponse

# runs.py
def list_runs(cursor: str | None, limit: int, user: User) -> Page[RunRead]
def get_run(run_id: UUID, user: User) -> RunRead
def list_steps(run_id: UUID, user: User) -> list[StepRead]
def list_artifacts(run_id: UUID, user: User) -> list[ArtifactRead]
def download_artifact(run_id: UUID, artifact_id: UUID, user: User) -> RedirectResponse
def retry_run(run_id: UUID, user: User) -> RunRead

# approvals.py
def list_pending_approvals(user: User) -> list[ApprovalRead]
def approve_step(approval_id: UUID, payload: ApprovalDecision, user: User) -> RunRead
def reject_step(approval_id: UUID, payload: ApprovalDecision, user: User) -> RunRead

# workflows.py
def list_workflows(user: User) -> list[WorkflowRead]
def create_workflow(payload: WorkflowCreate, user: User) -> WorkflowRead
def validate_workflow(workflow_id: UUID) -> ValidationResult
def publish_version(workflow_id: UUID, payload: VersionCreate, user: User) -> WorkflowVersionRead
def run_workflow(workflow_id: UUID, payload: RunCreate, user: User) -> TaskRead

# connectors.py
def list_connectors(user: User) -> list[ConnectorRead]
def create_connector(payload: ConnectorCreate, user: User) -> ConnectorRead
def test_connector(connector_id: UUID, user: User) -> ConnectorTestResult
def rotate_credentials(connector_id: UUID, payload: RotateSecret, user: User) -> ConnectorRead

# admin.py
def query_audit_events(filters: AuditFilters, user: User) -> Page[AuditEventRead]
def get_usage_summary(period: Period, user: User) -> UsageSummary
def get_system_health(user: User) -> SystemHealth

# health.py
def liveness() -> dict
def readiness(db: Session, redis: Redis, llm: LLMProvider) -> dict
def prometheus_metrics() -> Response
```

#### `api/errors.py`

```python
class AppError(Exception):
    code: str
    message: str
    status_code: int

def error_handler(request: Request, exc: AppError) -> JSONResponse
def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse
def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse
```

#### `api/deps.py`

```python
def get_db_session() -> Generator[Session, None, None]
def get_agent_service(db: Session, llm: LLMProvider) -> AgentService
def get_workflow_service(db: Session) -> WorkflowService
def get_connector_service(db: Session) -> ConnectorService
def get_audit_service(db: Session) -> AuditService
```

### 8.3 MCP cible

```
mcp_servers/
├── base.py
├── email_server.py
├── report_server.py
├── slack_server.py
├── teams_server.py
├── files_server.py
├── crm_server.py
├── calendar_server.py
├── http_server.py
└── db_server.py

mcp_gateway/
├── main.py
├── registry.py
├── credentials.py
└── proxy.py
```

Fonctions :

```python
# mcp_servers/base.py
def create_mcp_app(name: str, tools: list[Callable]) -> FastMCP
def health() -> dict
def require_scope(scope: str) -> Callable

# mcp_servers/email_server.py
def send_email(to: str, subject: str, body: str, attachments: list[str] | None) -> dict
def list_templates() -> list[dict]
def get_message_status(message_id: str) -> dict

# mcp_servers/report_server.py
def generate_report(title: str, content: str, format: str = "markdown") -> dict
def render_pdf(markdown: str, template: str | None) -> bytes
def upload_artifact(filename: str, data: bytes) -> str

# mcp_servers/slack_server.py
def post_message(channel: str, text: str, blocks: list[dict] | None) -> dict
def upload_file(channel: str, filename: str, data: bytes) -> dict

# mcp_servers/files_server.py
def read_file(path: str) -> bytes
def write_file(path: str, data: bytes) -> dict
def list_files(prefix: str) -> list[dict]

# mcp_servers/crm_server.py
def find_contact(email: str) -> dict | None
def update_contact(contact_id: str, fields: dict) -> dict
def create_deal(payload: dict) -> dict

# mcp_gateway/main.py
def resolve_connector(tenant_id: UUID, connector_id: UUID) -> Connector
def inject_credentials(connector: Connector) -> dict
def proxy_mcp_request(connector: Connector, request: MCPRequest) -> MCPResponse
def list_allowed_tools(connector: Connector) -> list[str]
```

---

## 9. Conception frontend

### 9.1 Arborescence cible

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── callback/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx
│   │   ├── tasks/page.tsx
│   │   ├── tasks/[id]/page.tsx
│   │   ├── runs/page.tsx
│   │   ├── runs/[id]/page.tsx
│   │   ├── approvals/page.tsx
│   │   ├── workflows/page.tsx
│   │   ├── connectors/page.tsx
│   │   ├── usage/page.tsx
│   │   └── admin/page.tsx
│   └── api/
│       ├── auth/[...nextauth]/route.ts
│       └── proxy/[...path]/route.ts
├── components/
│   ├── TaskComposer.tsx
│   ├── RunTimeline.tsx
│   ├── StepCard.tsx
│   ├── ApprovalDialog.tsx
│   ├── ConnectorCard.tsx
│   ├── WorkflowBuilder.tsx
│   ├── UsageChart.tsx
│   ├── StatusBadge.tsx
│   └── EmptyState.tsx
├── lib/
│   ├── api.ts
│   ├── auth.ts
│   ├── sse.ts
│   ├── format.ts
│   └── types.ts
├── hooks/
│   ├── useTaskSubmission.ts
│   ├── useRunEvents.ts
│   ├── useApprovals.ts
│   └── useConnectors.ts
└── middleware.ts
```

### 9.2 Fonctions frontend

```ts
// lib/api.ts
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T>
export async function createTask(input: TaskCreate): Promise<TaskRead>
export async function getTask(id: string): Promise<TaskRead>
export async function listRuns(cursor?: string): Promise<Page<RunRead>>
export async function getRun(id: string): Promise<RunRead>
export async function listSteps(runId: string): Promise<StepRead[]>
export async function approveStep(id: string, comment?: string): Promise<RunRead>
export async function rejectStep(id: string, comment?: string): Promise<RunRead>
export async function listConnectors(): Promise<ConnectorRead[]>
export async function testConnector(id: string): Promise<ConnectorTestResult>
export async function listWorkflows(): Promise<WorkflowRead[]>

// lib/auth.ts
export async function getSession(): Promise<Session | null>
export async function requireSession(): Promise<Session>
export async function signIn(provider?: string): Promise<void>
export async function signOut(): Promise<void>

// lib/sse.ts
export function subscribeToTask(taskId: string, onEvent: (e: TaskEvent) => void): () => void
export function subscribeToRun(runId: string, onEvent: (e: RunEvent) => void): () => void

// hooks/useTaskSubmission.ts
export function useTaskSubmission(): {
  submit: (input: TaskCreate) => Promise<void>;
  loading: boolean;
  error: string | null;
  task: TaskRead | null;
}

// hooks/useRunEvents.ts
export function useRunEvents(runId: string): {
  steps: StepRead[];
  status: RunStatus;
  connected: boolean;
}

// hooks/useApprovals.ts
export function useApprovals(): {
  approvals: ApprovalRead[];
  approve: (id: string, comment?: string) => Promise<void>;
  reject: (id: string, comment?: string) => Promise<void>;
  loading: boolean;
}

// components/TaskComposer.tsx
export function TaskComposer(props: TaskComposerProps): JSX.Element
export function useComposerState(): ComposerState

// components/RunTimeline.tsx
export function RunTimeline(props: { steps: StepRead[] }): JSX.Element
export function StepCard(props: { step: StepRead }): JSX.Element
export function StepStatusBadge(props: { status: string }): JSX.Element

// components/ApprovalDialog.tsx
export function ApprovalDialog(props: ApprovalDialogProps): JSX.Element

// components/WorkflowBuilder.tsx
export function WorkflowBuilder(props: { initial?: WorkflowDefinition }): JSX.Element
export function useWorkflowDraft(initial?: WorkflowDefinition): WorkflowDraft
export function validateDraft(draft: WorkflowDraft): ValidationResult

// app/api/proxy/[...path]/route.ts
export async function forwardRequest(req: Request, ctx: { params: { path: string[] } }): Promise<Response>

// middleware.ts
export function authMiddleware(req: NextRequest): NextResponse
export function tenantMiddleware(req: NextRequest): NextResponse
```

### 9.3 Ecrans prioritaires

1. **Composer** : champ texte, exemples, choix du workflow, option
   "demander une approbation", bouton lancer.
2. **Timeline de run** : etapes, statut, duree, entree/sortie repliable,
   artefacts telechargeables.
3. **Boite d'approbations** : liste des actions en attente, approuver/rejeter
   avec commentaire.
4. **Historique** : filtres par statut/date/utilisateur, recherche.
5. **Connecteurs** : catalogue, formulaire, bouton "tester", etat.
6. **Workflows** : liste, editeur JSON ou builder visuel, validation, version.
7. **Usage** : tokens, cout, runs par periode, quotas.
8. **Admin** : membres, roles, audit, sante systeme.

---

## 10. Moteur d'execution

### 10.1 Machines a etats

Task :

```
queued -> running -> awaiting_approval -> running -> succeeded
                  \-> failed
                  \-> canceled
```

Run :

```
pending -> running -> awaiting_approval -> running -> succeeded
                   \-> failed
                   \-> canceled
```

Step :

```
pending -> running -> succeeded
                   \-> failed -> retrying -> running
                   \-> awaiting_approval -> running
                   \-> skipped
```

### 10.2 Execution durable

Option recommandee : **Celery + Redis**.

- `run_task` orchestre le run.
- Chaque etape est un `execute_step` avec `step_id`.
- L'etat est en base : un worker peut reprendre apres crash.
- `acks_late=True`, `task_reject_on_worker_lost=True`.
- Idempotence : `step_id` + `attempt` + cle d'idempotence.
- Timeouts : `soft_time_limit`, `time_limit`.
- Retries : backoff exponentiel + jitter.
- DLQ : file `dead_letter` + endpoint admin pour rejouer.

Option entreprise : **Temporal**.

- `TaskWorkflow.run()` avec activities `classify_activity`,
  `execute_tool_activity`, `request_approval_activity`, `finalize_activity`.
- Reprise automatique, signaux pour les approbations, timers pour les SLA.

### 10.3 Approbations humaines

- Une etape peut declencher `request_approval`.
- Le run passe en `awaiting_approval`, le worker s'arrete.
- L'UI notifie (in-app, email, Slack).
- `approve_step` reprend le run via `resume_run`.
- `reject_step` termine le run en `failed` avec motif.
- Expiration automatique apres N heures -> `expired`.

### 10.4 Idempotence et effets de bord

- Header `Idempotency-Key` sur `POST /v1/tasks`.
- Table `outbox` pour les emails/notifications : ecrire l'intention puis
  envoyer, marquer `sent`.
- Ne jamais renvoyer un email deja envoye apres un retry.
- Artefacts : hash SHA-256 pour deduplication.

### 10.5 Annulation

- `cancel_task` ecrit `cancel_requested=true`.
- Le worker verifie ce flag entre chaque etape.
- Les etapes en cours recoivent un timeout court.
- Les etapes suivantes passent en `skipped`.

---

## 11. Connecteurs et MCP Gateway

### 11.1 Principe

- Chaque connecteur est un serveur MCP avec un contrat de tools.
- Les credentials ne sont jamais dans le conteneur du connecteur.
- La gateway recoit `tenant_id + connector_id`, recupere le secret chiffre,
  l'injecte dans l'appel MCP, et journalise l'action.
- Allowlist de tools par connecteur.

### 11.2 Connecteurs prioritaires

| Connecteur | Tools | Valeur client |
|---|---|---|
| SMTP / SendGrid | `send_email`, `send_template` | Emails reels |
| Slack | `post_message`, `upload_file` | Notifications equipe |
| Teams | `post_message` | Notifications entreprise |
| S3 / MinIO | `put_object`, `get_signed_url` | Stockage artefacts |
| PDF | `render_pdf` | Rapports telechargeables |
| HubSpot | `find_contact`, `update_contact`, `create_deal` | CRM |
| Jira | `create_issue`, `comment_issue` | Tickets |
| Google Drive | `upload_file`, `share_file` | Documents |
| Calendar | `create_event` | Planification |
| Webhook | `post_json` | Integration maison |

### 11.3 Securite des connecteurs

- Secrets chiffres avec Fernet + cle KMS/Vault.
- Rotation de cle sans downtime.
- Scope par connecteur (lecture seule / envoi).
- Journal d'audit de chaque appel.
- Test de connexion obligatoire avant activation.
- Pas d'appel HTTP arbitraire : uniquement les tools allowlist.

---

## 12. Securite et conformite

- **Auth** : OIDC/SAML, MFA, sessions courtes + refresh.
- **RBAC** : owner, admin, operator, viewer.
- **Isolation** : `tenant_id` partout + RLS Postgres.
- **Secrets** : chiffres, jamais logges, rotation.
- **Audit** : append-only, hash chain, export CSV/JSON.
- **Chiffrement** : TLS partout, chiffrement au repos (base + bucket).
- **Prompt injection** : allowlist de tools, validation d'arguments,
  separation instructions/donnees, pas de contenu utilisateur dans le system
  prompt.
- **PII** : redaction dans les logs, retention configurable, export/suppression
  RGPD.
- **Rate limiting** : par tenant, par utilisateur, par endpoint.
- **Quotas** : tokens LLM, runs/jour, connecteurs actifs.
- **Supply chain** : dependances epinglees, SBOM, scan Trivy, signatures.
- **Sauvegardes** : PITR Postgres, versioning bucket, test de restauration.
- **Conformite** : journal d'acces, politique de retention, DPA.

---

## 13. Observabilite et SLO

### Logs

- JSON structures : `timestamp`, `level`, `request_id`, `tenant_id`,
  `run_id`, `step_id`, `message`.
- Redaction automatique des secrets et emails.

### Traces

- OpenTelemetry : API -> worker -> MCP gateway -> connecteur -> LLM.
- Attributs : `tenant.id`, `run.id`, `step.node`, `llm.model`, `llm.tokens`.

### Metriques

- `tasks_total{status}`
- `runs_total{status}`
- `run_duration_seconds`
- `step_duration_seconds{node}`
- `approval_wait_seconds`
- `llm_tokens_total{provider,model}`
- `llm_cost_total`
- `queue_depth{queue}`
- `mcp_call_errors_total{connector}`

### SLO proposes

- Disponibilite API : 99.5 %.
- p95 classification : < 2 s.
- p95 run simple (2 etapes) : < 30 s.
- Taux de succes des runs : > 98 % hors erreurs connecteur.
- Delai d'approbation moyen : < 15 min (alerte).

### Alertes

- Taux d'erreur > 5 % sur 10 min.
- File Celery > 100 pendant 10 min.
- LLM indisponible.
- Connecteur en erreur.
- Cout LLM > seuil quotidien.

---

## 14. Tests, evals et qualite

### Tests

- **Unitaires** : `pytest`, fonctions pures (validation, prompts, parseurs).
- **Integration** : Postgres + Redis via Testcontainers, repositories, API.
- **Contrat MCP** : verifier les tools et schemas.
- **E2E** : Playwright (login, creer tache, suivre run, approuver, telecharger).
- **Charge** : k6 sur `POST /v1/tasks` + SSE.
- **Securite** : OWASP ZAP, tests d'autorisation par role.

### Evals LLM

- Dataset `evals/datasets/routing.yaml` :
  - `message`, `expected_action`, `expected_fields`.
- `evals/runner.py` :
  - `run_eval_suite(provider, model, dataset) -> EvalReport`
  - `score_case(case, prediction) -> CaseScore`
  - `compare_models(models, dataset) -> ComparisonReport`
- Seuil de qualite : 95 % de routage correct, 0 action inventee.
- Inclure les cas pieges : meteo, small talk, demande ambigue, injection.

### Qualite code

- `ruff` + `mypy` + `eslint` + `tsc`.
- Couverture backend > 80 %, frontend critique > 70 %.
- Migrations verifiees en CI.
- Revue de code obligatoire.

---

## 15. CI/CD et deploiement

### Pipeline GitHub Actions

```
lint-backend -> typecheck-backend -> test-backend
lint-frontend -> typecheck-frontend -> build-frontend
build-images -> scan-images -> push-registry
migrate-staging -> deploy-staging -> smoke-tests
approve -> deploy-prod
```

Fonctions/scripts :

```python
# scripts/check_migrations.py
def check_pending_migrations() -> bool

# scripts/seed_demo_data.py
def seed_tenant(name: str) -> Tenant
def seed_workflows(tenant_id: UUID) -> list[Workflow]
def seed_connectors(tenant_id: UUID) -> list[Connector]

# scripts/create_tenant.py
def create_tenant(name: str, admin_email: str) -> Tenant

# scripts/rotate_keys.py
def rotate_encryption_key(old: str, new: str) -> int
```

### Modes de deploiement

1. **On-prem Docker Compose** (petit client) :
   - `docker compose -f docker-compose.prod.yml up -d`
   - Postgres, Redis, MinIO, API, worker, frontend, gateway.
2. **Kubernetes / Helm** (client plus grand) :
   - `helm install agent ./charts/agent -f values.prod.yaml`
   - HPA, PDB, ingress TLS, secrets, backups.

### Environnements

- `dev` : local, LLM Ollama.
- `staging` : donnees synthetiques, LLM local ou cloud.
- `prod` : secrets manages, backups, monitoring.

### Sauvegardes et DR

- Postgres : PITR, snapshot quotidien, test mensuel.
- Bucket : versioning + replication.
- Objectifs : RPO 1 h, RTO 4 h.

---

## 16. Roadmap step by step

Estimations pour 1 developpeur full-stack experimente. A ajuster selon l'equipe.

### Sprint 0 - Fondations (1 semaine)

Objectif : rendre le repo propre et testable.

- [ ] `pyproject.toml` (ruff, mypy, pytest), `package.json` scripts.
- [ ] `config/settings.py`, logs JSON, `request_id`.
- [ ] `api/errors.py` (erreur uniforme).
- [ ] CI GitHub Actions (lint + tests).
- [ ] Tests unitaires du classifieur actuel.
- [ ] `.env.example` documente.

Fichiers : `api/config/settings.py`, `api/api/errors.py`,
`api/middleware/request_id.py`, `.github/workflows/ci.yml`.

Acceptation : CI verte, `GET /healthz` et `/readyz` OK.

### Sprint 1 - Persistance (1 semaine)

Objectif : garder l'historique des taches.

- [ ] Postgres + Alembic.
- [ ] Modeles `Task`, `Run`, `Step`.
- [ ] Repositories `TaskRepository`, `RunRepository`.
- [ ] `POST /v1/tasks` cree une tache et un run.
- [ ] `GET /v1/tasks`, `GET /v1/runs/{id}`.
- [ ] Tests d'integration Testcontainers.

Fonctions : `create_task()`, `create_run()`, `append_step()`, `finish_run()`.

Acceptation : une tache survit au redemarrage de l'API.

### Sprint 2 - Execution asynchrone (1 a 2 semaines)

Objectif : ne plus bloquer la requete HTTP.

- [ ] Redis + Celery.
- [ ] `run_task`, `execute_step`.
- [ ] SSE `GET /v1/tasks/{id}/events`.
- [ ] Retries, timeouts, DLQ.
- [ ] Annulation.
- [ ] Idempotency-Key.

Fonctions : `run_task()`, `execute_step()`, `stream_task_events()`,
`cancel_task()`, `find_by_idempotency_key()`.

Acceptation : un run de 30 s ne bloque pas l'API ; reprise apres kill worker.

### Sprint 3 - Auth, tenants, RBAC (1 a 2 semaines)

Objectif : multi-utilisateurs.

- [ ] Tables `tenants`, `users`, `memberships`, `api_keys`.
- [ ] Login mot de passe + OIDC.
- [ ] JWT, refresh, logout.
- [ ] Middleware tenant + RLS.
- [ ] Roles et tests d'autorisation.
- [ ] Audit de base.

Fonctions : `hash_password()`, `create_access_token()`, `get_current_user()`,
`require_role()`, `record_event()`.

Acceptation : un viewer ne peut pas creer de tache ; un tenant ne voit pas
les donnees d'un autre.

### Sprint 4 - Frontend produit (2 semaines)

Objectif : une UI utilisable.

- [ ] Auth.js + login.
- [ ] Layout dashboard.
- [ ] Composer + exemples.
- [ ] Historique + timeline de run.
- [ ] Approbations.
- [ ] Telechargement d'artefacts.
- [ ] Proxy authentifie.

Fonctions : `TaskComposer()`, `RunTimeline()`, `useRunEvents()`,
`ApprovalDialog()`, `forwardRequest()`.

Acceptation : un utilisateur fait tout le parcours sans PowerShell.

### Sprint 5 - Connecteurs reels (2 semaines)

Objectif : actions reelles.

- [ ] Gateway MCP + credentials chiffres.
- [ ] SMTP/SendGrid reel + outbox.
- [ ] PDF + S3/MinIO.
- [ ] Slack.
- [ ] Test de connexion dans l'UI.
- [ ] Audit des appels connecteur.

Fonctions : `send_email()`, `render_pdf()`, `upload_artifact()`,
`proxy_mcp_request()`, `test_connection()`.

Acceptation : email recu, PDF telechargeable, message Slack poste.

### Sprint 6 - Workflows et planning (2 semaines)

Objectif : reutiliser et planifier.

- [ ] `workflows` + versions.
- [ ] Validation de definition.
- [ ] Templates prets a l'emploi.
- [ ] Schedules + Celery beat.
- [ ] Execution planifiee.

Fonctions : `create_workflow()`, `publish_version()`, `validate_definition()`,
`create_schedule()`, `tick()`.

Acceptation : un rapport hebdomadaire part automatiquement.

### Sprint 7 - Observabilite et qualite (1 a 2 semaines)

Objectif : exploiter en production.

- [ ] OTel + Prometheus + Grafana.
- [ ] Sentry.
- [ ] Metriques LLM et couts.
- [ ] Evals routing + regression.
- [ ] k6 + tests de charge.
- [ ] SLO et alertes.

Fonctions : `record_llm_usage()`, `run_eval_suite()`, `prometheus_metrics()`.

Acceptation : dashboard Grafana + alerte sur erreurs ; score eval > 95 %.

### Sprint 8 - Packaging et vente (2 semaines)

Objectif : livrer chez un client.

- [ ] Compose prod + Helm.
- [ ] SSO + MFA.
- [ ] White-label (logo, couleurs).
- [ ] Seed demo + mode sandbox.
- [ ] Documentation admin + utilisateur.
- [ ] Tests de restauration.

Fonctions : `seed_demo_data()`, `create_tenant()`, `rotate_keys()`.

Acceptation : installation on-prem documentee en moins d'une heure.

---

## 17. Quick wins pour une demo client (2 semaines)

Si l'objectif est de convaincre vite, faire dans cet ordre :

1. **Postgres + historique** (Sprint 1) : montrer que rien ne se perd.
2. **Celery + timeline SSE** (Sprint 2) : montrer un run en direct.
3. **Auth simple + 2 roles** (extrait Sprint 3) : montrer l'isolation.
4. **Approbation humaine** : le point qui rassure le plus un client.
5. **Email reel + PDF telechargeable** (extrait Sprint 5) : la valeur tangible.
6. **Dashboard usage** : cout et nombre de runs.
7. **Seed demo** : 5 workflows prets a cliquer.

Demo type (10 minutes) :

1. Login.
2. Lancer "Rapport Q3 + email a Jean".
3. Montrer la timeline et l'attente d'approbation.
4. Approuver.
5. Montrer l'email recu et le PDF.
6. Ouvrir l'audit et l'usage.

---

## 18. Fonctionnalites "wow" qui font vendre

- **Trace viewer** : chaque decision du LLM expliquee, avec l'etape et le tool.
- **Approval inbox** avec notifications Slack/Teams.
- **Workflow builder visuel** : langage naturel -> DAG editable.
- **Marketplace de templates** : "Rapport hebdo", "Triage email", "Onboarding".
- **Mode sandbox** : essayer sans connecter de vrais comptes.
- **Rapport de run partageable** (PDF/HTML) avec branding client.
- **Cout par run** et optimisation automatique du modele.
- **Multilingue FR/EN**.
- **On-premise** : argument fort pour les clients sensibles.
- **Connecteur "maison"** : webhook generique en 5 minutes.

---

## 19. KPIs et modele economique

### KPIs produit

- Nombre de runs / semaine.
- Taux de succes des runs.
- Temps gagne estime par run.
- Taux d'approbation.
- Cout LLM par run.
- Adoption : utilisateurs actifs / sieges.
- Retention a 30/60/90 jours.

### Modele de pricing possible

- **Par siege** : 20-50 EUR/utilisateur/mois.
- **Par run** : 0.05-0.20 EUR/run selon modele.
- **Pack connecteurs** : Slack/Teams/CRM en option.
- **On-prem** : licence annuelle + support.
- **Services** : integration, templates sur mesure.

---

## 20. Risques et questions ouvertes

| Risque | Impact | Mitigation |
|---|---|---|
| LLM local trop lent | UX degradee | Modeles plus petits, cache, GPU, fallback cloud |
| Prompt injection | Action non voulue | Allowlist tools, validation, approbations |
| Cout LLM cloud | Marge negative | Quotas, routage modele, cache |
| Connecteurs instables | Runs en echec | Retries, DLQ, tests de connexion |
| Multi-tenant mal isole | Fuite de donnees | RLS + tests d'autorisation |
| Airflow mono-noeud | Pas de haute disponibilite | Postgres + volume, puis Helm/K8s en prod |
| Complexite K8s | Livraison lente | Commencer par Compose, Helm ensuite |
| Adoption utilisateur | Projet abandonne | Templates prets, onboarding, UI simple |

Questions a trancher avec le client :

1. On-prem ou cloud ? (impacte LLM, secrets, deploiement)
2. Quels 2 connecteurs sont indispensables au lancement ?
3. Faut-il une approbation sur toutes les actions ou seulement sensibles ?
4. Quelle retention des donnees et des artefacts ?
5. Qui administre les utilisateurs (SSO existant ?)
6. Quel budget LLM mensuel ?
7. Quels SLO contractuels ?

---

## 21. Checklist de lancement

### Technique

- [ ] CI verte (lint, types, tests, build).
- [ ] Migrations versionnees et testees.
- [ ] Postgres + Redis + MinIO en prod.
- [ ] Secrets chiffres, rotation testee.
- [ ] RLS active et testee.
- [ ] Backups + restauration testes.
- [ ] OTel + Grafana + alertes.
- [ ] Evals routing > 95 %.
- [ ] Tests de charge passes.
- [ ] Runbook incident.

### Produit

- [ ] Login SSO.
- [ ] 5 templates prets.
- [ ] 2 connecteurs reels.
- [ ] Approbations + notifications.
- [ ] Historique + artefacts.
- [ ] Dashboard usage.
- [ ] Documentation utilisateur.
- [ ] Mode demo.

### Commercial

- [ ] Demo script 10 min.
- [ ] Grille tarifaire.
- [ ] DPA / politique de retention.
- [ ] Support et SLA definis.

---

## 22. Ordre de demarrage recommande

Si tu dois commencer demain, fais exactement ceci :

1. Creer `api/config/settings.py`, `api/api/errors.py`, logs JSON.
2. Ajouter Postgres + Alembic + `Task`/`Run`/`Step`.
3. Implementer `POST /v1/tasks` + `GET /v1/runs/{id}`.
4. Ajouter Celery + Redis + `run_task` + `execute_step`.
5. Ajouter SSE + timeline dans le frontend.
6. Ajouter auth + tenant + RBAC.
7. Ajouter approbation humaine.
8. Brancher un vrai SMTP + PDF/S3.
9. Ajouter audit + usage + dashboard.
10. Packager Compose prod, puis Helm.

Ce plan transforme le POC en produit vendable sans jeter l'existant : le
classifieur, LangGraph, les serveurs MCP et le frontend restent la base, mais
ils sont entoures de persistance, securite, fiabilite et experience utilisateur.
