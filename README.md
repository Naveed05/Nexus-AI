# NEXUS AI

> **An agentic multimodal AI work platform that turns natural-language goals into verified work.**

NEXUS is a production-minded AI system designed to combine frontier models, specialized intelligence, tools, retrieval, workspace context, secure execution, verification, and reproducible artifacts into one task-oriented platform.

## Why NEXUS exists

Most AI applications stop at generating an answer. NEXUS is designed around a stronger contract:

> **Understand the goal → plan the work → choose the right model/tools → execute safely → observe results → verify evidence/output → revise when needed → deliver artifacts → remember useful context.**

The objective is not simply to build another chatbot. It is to build an extensible AI execution layer for real workflows across research, data science, software engineering, document intelligence, learning, and business tasks.

## Core execution loop

```text
UNDERSTAND
    ↓
PLAN
    ↓
ROUTE
    ↓
EXECUTE
    ↓
OBSERVE
    ↓
VERIFY
    ↓
REVISE
    ↓
DELIVER
    ↓
REMEMBER
```

## Architecture

```text
                         USER
                          │
                 text / files / images
                          │
                          ▼
                 ┌─────────────────┐
                 │ NEXUS CONTEXT   │
                 │ task + workspace│
                 │ memory + files  │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ ROUTER /        │
                 │ PLANNER         │
                 └────────┬────────┘
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
      Frontier LLMs   Specialized AI    Deterministic
      / reasoning     / ML tooling      kernel logic
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                    TOOL SYSTEM
                          │
       ┌─────────┬────────┼────────┬──────────┐
       ▼         ▼        ▼        ▼          ▼
    Research   Python   Data     Files      GitHub
    / RAG      sandbox  / ML     / docs     / code
       │         │        │        │          │
       └─────────┴────────┼────────┴──────────┘
                          ▼
                    VERIFICATION
                          │
                          ▼
                     ARTIFACTS
                          │
                          ▼
                       MEMORY
```

## Current capabilities

### 🧠 Agentic kernel

- task-aware planning
- deterministic model routing
- dependency-aware execution
- bounded retries and recovery
- step-level execution state
- structured execution events
- explicit tool selection
- observable verification

### 🔑 Multi-provider / BYOK model layer

NEXUS supports a Bring Your Own Key foundation so each user can connect their own model-provider credentials instead of sharing a platform-wide API key. The provider layer currently supports OpenAI, Anthropic Claude, and Groq, with per-user credential isolation, masked credentials, provider validation, provider-specific request adapters, and an extensible provider abstraction.

Raw user API keys are never returned by the credential-management interface. Production persistence is expected to use an encrypted secret store rather than plaintext application storage.

### 🤖 Model intelligence

NEXUS is designed to route work according to task complexity, capability requirements, risk, latency, context size, and cost rather than blindly using one model for every request.

The architecture supports frontier reasoning models alongside lower-cost models and specialized ML systems.

### 🔎 Knowledge & research

- workspace-scoped document ingestion
- PDF, DOCX, TXT and Markdown foundations
- chunking and metadata
- hybrid retrieval
- vector + lexical scoring
- durable local vector index
- evidence-preserving research workflows
- source/citation provenance
- bounded evidence packs
- grounding-aware verification
- structured research reports

### 📊 Data intelligence

NEXUS includes a foundation for:

- dataset registration and workspace isolation
- CSV / Parquet / JSON ingestion
- schema discovery
- data profiling
- cleaning plans
- transformations
- EDA
- correlations and statistics
- baseline ML
- reproducible artifacts

### 🛠️ Tool intelligence

Tools are treated as first-class capabilities with explicit contracts:

```text
Tool
├── name
├── description
├── input_schema
├── output_schema
├── permission
├── risk_level
├── timeout
├── cost
├── sandbox_required
└── audit_policy
```

Current tool families include calculation, dataset profiling/analysis, baseline ML, knowledge retrieval, and evidence-first research.

### 🧩 Tool & capability evolution

NEXUS now treats tools as discoverable, versioned capabilities rather than only callable functions:

- immutable tool contracts with semantic versions and capability tags
- deterministic capability inventory and filtered tool discovery
- capability-aware step selection with permission-policy enforcement
- explicit required/matched capability telemetry in execution events
- thread-safe tool health tracking with repeated-failure isolation
- cooldown-based circuit breaking for unstable tools
- API endpoints for tool contracts, capability discovery, and health inspection
- backward-compatible support for legacy custom tools without capability metadata

### 🔐 Secure execution foundations

NEXUS separates task intent from tool authorization and execution. The architecture includes:

```text
USER
 ↓
PERMISSION POLICY
 ↓
TOOL AUTHORIZATION
 ↓
SANDBOX / CONTROLLED EXECUTION
 ↓
AUDITABLE EVENTS
 ↓
VERIFICATION
```

High-risk capabilities are designed to require stronger controls rather than silently executing privileged actions.

### 👨‍💻 Developer intelligence

NEXUS now includes an evidence-first developer workflow with deterministic patch planning, impact analysis, verification planning, patch audit fingerprints, approval provenance, execution boundaries, approval freshness, and high-confidence secret-content blocking.

Developer changes are represented as immutable, reviewable artifacts before execution. High-risk patches require an exact, approved, fresh audit fingerprint.

### 🚀 Public Beta hardening

Phase 28 is the final Version 1 hardening pass before public beta:

- production beta access-key boundary
- bounded request body size and sliding-window rate limiting
- backup snapshot utility and recovery drill guidance
- incident-response and operational runbook
- final public-beta regression coverage
- explicit migration boundary for identity, distributed state, and distributed rate limiting

The beta deployment remains intentionally single-instance until shared identity, transactional state, object storage, distributed queueing, and centralized secrets are introduced.

## 🤖 Advanced agent autonomy

Phase 30 adds a bounded autonomy layer around NEXUS execution:

- verification-driven completion using explicit confidence and evidence
- bounded self-revision with hard revision limits
- escalation when confidence is insufficient or revision budgets are exhausted
- resumable agent state with objective-bound checkpoints
- explainable self-correction plans derived from verification issues
- an explicit autonomy policy matrix separating reversible actions from approval-gated side effects
- regression and end-to-end autonomy contract coverage

NEXUS autonomy remains policy- and budget-bound: the agent cannot self-authorize policy changes or external side effects.

## 🌐 Scale & distributed infrastructure

Phase 29 establishes the migration boundary from the single-instance beta runtime toward distributed production infrastructure:

- versioned durable state with compare-and-swap conflict protection
- leased execution jobs with worker ownership, retry limits, expired-lease recovery, and dead-letter handling
- bounded TTL caching behind a cache contract
- content-addressed object storage behind an object-store contract
- explicit backend configuration for state, queue, cache, and object storage
- scale-topology inspection at `/api/v1/scale/topology`
- readiness visibility that keeps the current SQLite/in-process/filesystem boundary explicit

The current default remains intentionally single-instance. Horizontal scale is reported as ready only when shared transactional state, distributed queueing, shared cache, and shared object storage are configured.

## 🚀 Deployment & observability

Phase 27 adds the operational boundary needed to move NEXUS toward a public beta:

- containerized FastAPI deployment with a non-root runtime user
- Docker Compose persistence for the local runtime/workspace state
- liveness and readiness endpoints
- structured JSON HTTP request telemetry with propagated request IDs
- dependency-free Prometheus-compatible service metrics
- operational observability summary and deployment runbook
- container-image build validation in GitHub Actions
- explicit single-instance scaling boundary and migration guidance for shared production state

The current deployment is intentionally conservative: local SQLite and in-process registries remain the safe single-instance boundary. Horizontal scale should follow a migration to shared transactional state, object storage, distributed queueing, and shared cache.

## 🧠 Persistent memory

The persistent-memory foundation provides workspace-scoped durable records, SQLite persistence, deterministic ranked recall, confidence-aware context rendering, reinforcement, deduplication, explicit forgetting controls, bounded record sizes, timezone-aware timestamps, and minimum-confidence recall filtering.

Memory is treated as prior context rather than a source of truth, so current evidence can override stale remembered context.

### 🖼️ Multimodal intelligence

The multimodal foundation provides a safe contract for text, image, audio, and video inputs:

- immutable content-addressed asset descriptors
- SHA-256 identity for exact input provenance
- bounded media ingestion
- workspace isolation checks
- deterministic modality-to-capability routing
- explicit vision, OCR, speech, temporal, and grounding capabilities
- evidence envelopes bound to the exact source asset
- validated metadata and timezone-aware provenance

This foundation is designed so model-backed multimodal analysis can be added without weakening NEXUS's verification and provenance guarantees.

### ⚙️ Advanced agentic execution

NEXUS has bounded adaptive-execution contracts for autonomous workflows:

- hard limits for plan steps, execution attempts, and replans
- deterministic replan decisions
- explicit verification-failure recovery
- execution-failure recovery paths
- dependency-failure prioritization
- auditable reasons for every replan decision
- no replanning after successful verification

These controls provide a safe foundation for multi-step autonomous execution without allowing unbounded agent loops.

### ⚙️ Agent runtime

NEXUS now exposes a bounded agent runtime with durable SQLite-backed run state, explicit task/run lifecycle states, cancellation, step/tool/retry budgets, structured execution telemetry, runtime status APIs, and deterministic run inspection. The runtime is designed as the control boundary for future asynchronous workers and distributed execution. Runtime persistence is configurable through `RUN_STORAGE_PATH` and defaults to `.nexus/runs.sqlite3`.

### 🧭 Productization

Phase 26 turns the completed runtime and frontend foundations into a clearer product contract:

- product plans with bounded run/file quotas and visible usage
- stable product profile and onboarding APIs
- reusable workflow templates for research, data, documents, and code
- quick-start template selection directly from the frontend
- workspace-aware product context and usage dashboard
- explicit file-size and quota enforcement at the API boundary
- product onboarding/readiness signals
- automated regression coverage for product contracts and limits

### 🌐 Production frontend

Phase 25 adds a production-oriented task-first web interface served by the NEXUS API with:

- responsive task execution and verified-result surfaces
- live runtime health, capacity, model, and tool capability visibility
- workspace creation, file upload, and workspace-scoped memory controls
- dependency-free browser runtime with no client-side credential persistence
- same-origin API integration and production security headers
- web app metadata for standalone installation
- automated frontend serving, contract, and security regression coverage

### ⚙️ Production runtime integration

Phase 24 establishes the production execution boundary on top of the completed runtime/model/tool foundations with:

- durable production run coordination and idempotency protection
- bounded runtime concurrency and capacity reporting
- SQLite-backed execution jobs with deterministic claiming and completion state
- explainable production model/tool planning before execution
- production execution and health APIs
- bounded runtime execution metrics suitable for operational export
- cross-process refresh of durable run state
- regression coverage for persistence, queue lifecycle, planning, health, and metrics

### 🧠 Memory evolution

Phase 23 evolves persistent memory into a lifecycle-aware context system with:

- typed memories for facts, preferences, procedures, episodes, and verified task outcomes
- provenance metadata linking memories to their source and source identifiers
- expiry and archival controls so stale context does not silently re-enter reasoning
- explicit supersession for correcting outdated memories while preserving history
- bounded importance decay for aging memories
- workspace-scoped lifecycle statistics and inspection APIs
- safe memory APIs that expose lifecycle metadata without crossing workspace boundaries

### 🧠 Model intelligence

Phase 22 adds provider-neutral model intelligence with:

- explicit model requirement contracts for capabilities, reasoning, context, tools, cost, and latency
- deterministic multi-factor routing with explainable score components
- provider-neutral execution adapters and normalized tool-call responses
- bounded primary/fallback execution using prevalidated frontier workflow plans
- BYOK execution integration without exposing user credentials
- model/provider health telemetry with failure counts and latency snapshots
- safe model catalog and health APIs for operational observability

### 🌐 Advanced frontier-model workflows

NEXUS now has a frontier workflow foundation with:

- explicit capability requirements
- reasoning-level requirements
- minimum context-window requirements
- tool-capability requirements
- cost and latency budgets
- deterministic primary/fallback model planning
- bounded fallback cascades
- capability-safe fallback decisions
- auditable provider, timeout, and transient-failure reasons

### 📏 Evaluation & benchmark platform foundation

The evaluation layer now supports:

- deterministic observable-behavior scoring
- explicit CI quality gates
- category-level benchmark aggregation
- baseline/current regression comparison
- pass-rate, check-score, and grounding-score deltas
- machine-readable evaluation reports

The platform is designed to expand into model-routing benchmarks, larger regression suites, quality gates, and production evaluation dashboards.

## ✅ Verification-first design

NEXUS does not treat model output as automatically trustworthy.

The verifier checks observable properties such as:

- non-empty output
- objective presence
- tool-call integrity
- research grounding
- citation validity
- evidence/claim overlap

Research outputs must be backed by retrieved evidence before they can pass the grounding checks.

### 🎛️ Production Intelligence & Control Center

Phase 36 adds a unified operational control surface across the existing production runtime:

- `/api/v1/control-center/summary` aggregates deployment identity, runtime health, agents, models, tools, audit integrity, and recent execution state
- frontend control-center cards expose live operational status without browser-side credentials
- execution timeline surfaces recent runs, step progress, and tool usage
- audit integrity is surfaced as a verified operational signal
- deployment readiness and scale-contract blockers are visible from the same surface
- bounded polling keeps the dashboard current without introducing a new client-side dependency
- focused API and frontend regression coverage protects the control-center contract

### ✨ Phase 37 — Premium Frontend & Experience

Phase 37 transforms the existing frontend into a production-grade NEXUS operator experience without introducing a heavyweight client dependency:

- responsive application shell with persistent navigation and mobile navigation
- goal-first command surface for starting verified work
- dedicated Overview, Workspace, Agents, Executions, Knowledge, and Control Center surfaces
- live runtime telemetry, execution history, agent roster, model catalog, and capability visibility
- workspace files and persistent memory workflows integrated with the existing APIs
- verified-result presentation with grounding and tool-call metadata
- command palette with keyboard navigation and direct surface routing
- dark/light appearance preference persisted locally
- polished loading, empty, error, degraded, and success states
- responsive layouts for desktop, tablet, and mobile
- no external frontend framework or client-side credentials required
- frontend contract tests covering the major navigation and interaction surfaces

The design goal is a focused AI work console rather than a generic chat interface: intent, orchestration, execution, evidence, verification, and operational control remain visible throughout the experience.

## Engineering principles

NEXUS is being built around several principles:

1. **Task-centric, not chat-centric** — the unit of work is a goal and its execution state.
2. **Model-agnostic** — models are interchangeable components behind routing decisions.
3. **Tool-aware** — specialized tools should outperform forcing every problem through an LLM.
4. **Verification-first** — generated output should be checked against observable requirements and evidence.
5. **Evidence-preserving** — research evidence travels with downstream synthesis and verification.
6. **Human-controlled** — privileged actions should have explicit permission boundaries.
7. **Artifact-first** — useful work should produce reusable outputs, not only text.
8. **Observable** — execution should produce structured telemetry suitable for debugging and evaluation.
9. **Incremental and testable** — every capability is added with focused tests and CI validation.

## Project maturity

NEXUS has progressed beyond the original kernel prototype into a multi-layer AI execution platform foundation, with completed work across:

- core orchestration
- model routing
- planning
- secure tool execution
- data and artifact foundations
- dataset workspace execution
- workspace/file management
- document intelligence
- hybrid knowledge retrieval
- evidence-first research
- research-agent orchestration
- deterministic evaluation foundations
- developer intelligence and safe patch execution
- persistent workspace-scoped memory foundations
- multimodal asset, routing, and evidence foundations
- bounded adaptive agentic execution foundations
- frontier-model capability and fallback planning foundations
- evaluation quality gates, category aggregation, and regression detection foundations

The next major engineering focus is deployment, observability, scale hardening, and public-beta readiness.

## Roadmap

```text
[✓] NEXUS Core / Kernel
[✓] Model Routing
[✓] Agent Planning
[✓] Tool Intelligence & Secure Execution
[✓] Data & Artifact Engine
[✓] Dataset Execution Layer
[✓] Workspace & File System
[✓] Document Intelligence + Retrieval
[✓] Knowledge Engine / RAG
[✓] Research Agent
[✓] Evaluation Foundation
[✓] Developer Intelligence
[✓] Persistent Memory Foundation
[✓] Multimodal Intelligence Foundation
[✓] Advanced Agentic Execution Foundation
[✓] Advanced Frontier-Model Workflow Foundation
[✓] Evaluation & Benchmark Platform Foundation
[✓] Security & Human Control Hardening
[✓] Multi-Provider / BYOK Model Layer
[✓] Tool & Capability Evolution
[✓] Model Intelligence
[✓] Memory Evolution
[✓] Production Runtime Integration
[✓] Production Frontend
[✓] Productization
[✓] Deployment & Observability
[✓] Public Beta
[✓] Scale & Distributed Infrastructure
[✓] Advanced Agent Autonomy
[✓] Multi-Agent Collaboration
[✓] Collaboration Audit & Replay
[✓] Durable Collaboration Audit
[✓] Collaboration Audit Operations
[✓] Global Production Scale Contract
[✓] Phase 35 Deployment Identity Hardening
[✓] Phase 36 Production Intelligence & Control Center
[✓] Phase 37 Premium Frontend & Experience
[✓] Phase 38 Interactive Agent Workspace
[✓] Phase 39 Production Frontend Polish & Accessibility
```

### ✨ Phase 39 — Production Frontend Polish & Accessibility

Phase 39 hardens the NEXUS web experience from a premium interface into a resilient operator product surface:

- accessible skip navigation, focus-visible treatment, live status announcements, and reduced-motion support
- boot/loading state that resolves after the initial frontend data surfaces settle
- clearer healthy, degraded, offline, and unavailable status semantics
- resilient frontend error and unhandled-rejection recovery messaging
- keyboard navigation for the command palette
- polished interactive run-queue states and responsive Agent Workspace layouts
- improved mobile collaboration-builder ergonomics
- frontend regression contracts covering accessibility, resilience, and visual-state hooks

The phase remains presentation and operator-experience focused: it does not expand agent authority or bypass existing backend approval boundaries.


## Technology direction

**Backend**
- Python
- FastAPI
- Pydantic
- pytest

**AI / ML**
- OpenAI models
- Hugging Face ecosystem
- scikit-learn
- Polars / Pandas
- PyTorch-oriented integrations

**Data / Retrieval**
- DuckDB direction
- PostgreSQL / pgvector direction
- hybrid retrieval
- embeddings
- durable vector indexing

**Infrastructure direction**
- Docker
- GitHub Actions
- Redis
- object storage
- OpenTelemetry
- production cloud deployment

## Repository structure

```text
apps/api/nexus/
├── api/          # HTTP API
├── core/
│   ├── engine.py
│   ├── planner.py
│   ├── router.py
│   ├── executor.py
│   ├── tools.py
│   ├── permissions.py
│   ├── sandbox.py
│   ├── verification.py
│   ├── evaluation.py
│   ├── advanced_execution.py
│   ├── frontier_workflows.py
│   ├── data_engine.py
│   ├── data_pipeline.py
│   ├── datasets.py
│   ├── dataset_workspace.py
│   ├── workspaces.py
│   ├── files.py
│   ├── documents.py
│   ├── retrieval.py
│   ├── knowledge.py
│   ├── research.py
│   ├── memory.py
│   └── multimodal.py
└── tests/        # automated regression coverage
```

## Quality bar

The goal is to make NEXUS more than an impressive demo. Every major subsystem is expected to earn its place through:

- automated tests
- deterministic behavior where possible
- explicit contracts
- failure handling
- permission boundaries
- evidence tracking
- regression evaluation
- CI validation
- observable execution

## Long-term vision

NEXUS is intended to become a general AI work platform where a user can state a goal naturally and receive a verified, reproducible result — whether the work involves research, data, code, documents, analysis, or multimodal information.

> **Don't just ask AI for an answer. Give it a goal, let it do the work, and make it prove the result.**

## License

TBD during the productization phase.


### 🤝 Multi-Agent Collaboration

Phase 31 adds a bounded collaboration layer for specialized agents:

- explicit specialist roles and capability declarations
- deterministic capability-aware delegation
- bounded workstream counts and dependency-aware readiness
- versioned shared context with agent provenance
- explicit handoff envelopes between agents
- deterministic conflict resolution using evidence and confidence
- escalation when competing proposals lack a decisive margin
- supervisor orchestration that preserves human approval boundaries
- collaboration catalog and planning APIs at `/api/v1/agents` and `/api/v1/agents/collaborate`
- focused regression coverage for delegation, context, conflicts, supervision, and API contracts

Agents can coordinate work, but cannot self-authorize policy changes or external side effects.



### 🧾 Collaboration Audit & Replay

Phase 32 hardens the multi-agent layer with an append-only collaboration audit boundary:

- hash-chained collaboration events with deterministic canonicalization
- bounded audit storage with explicit capacity enforcement
- tamper detection through full-chain verification
- collaboration-plan events recorded at the API boundary
- read-only audit inspection and integrity verification endpoints at `/api/v1/agents/audit`
- focused regression coverage for hash chaining, bounds, and validation
- explicit separation between collaboration coordination and privileged external side effects

Phase 32 preserves the human-approval boundary: auditability does not grant agents additional authority.


### 🧾 Durable Collaboration Audit

Phase 33 evolves the Phase 32 collaboration audit into a durable control-plane record:

- SQLite-backed append-only audit persistence
- hash-chain continuity survives API restarts
- tamper detection by deterministic event re-hashing
- configurable audit storage path
- bounded audit capacity with explicit overflow rejection
- regression coverage for restart persistence and tamper detection
- collaboration audit remains observational and does not grant agents additional authority

The collaboration audit database is intentionally separate from task execution state so audit retention and runtime lifecycle can evolve independently.


### 🌍 Global Production Scale Contract

Phase 35 closes the production-scale control-plane boundary for NEXUS:

- explicit single, horizontal, and global deployment modes
- deterministic readiness evaluation for distributed deployments
- fail-closed checks for shared transactional state, queueing, cache, and object storage
- explicit deployment region and instance identity for distributed runtimes
- `/api/v1/scale/deployment` operational inspection endpoint
- readiness now surfaces the scale contract instead of silently reporting local infrastructure as globally ready
- regression coverage for local, horizontal, and global deployment modes

The contract does not pretend that external PostgreSQL, Redis, or object-storage infrastructure exists when it has not been configured. A global deployment becomes ready only after the required shared backends and deployment identity are supplied.


### 🔎 Collaboration Audit Operations

Phase 34 makes the durable collaboration audit operationally queryable without weakening its integrity boundary:

- bounded event filtering by event type and actor
- cursor-style pagination using a sequence boundary
- operational audit statistics for event count, capacity, head sequence, and latest event time
- integrity status exposed through a dedicated audit summary endpoint
- API validation for invalid limits and cursor values
- regression coverage for filtered queries, pagination, statistics, and API contracts

The audit remains append-only and hash-chained. Querying and operational inspection never grant agents additional authority or mutation access.


### 🧭 Phase 35 Deployment Identity Hardening

The global production scale contract now exposes a deterministic deployment identity:

- versioned scale contract (phase-35.v1)
- SHA-256 deployment fingerprint derived from deployment mode, region, instance identity, and backend topology
- stable fingerprints for identical deployment configurations
- distinct fingerprints when distributed instance identity changes
- fingerprint surfaced through the scale deployment and readiness payloads
- regression coverage for identity stability and separation

This identity is observational: it does not grant permissions or bypass readiness blockers.


### 🧑‍🚀 Phase 38 — Interactive Agent Workspace

Phase 38 turns the premium frontend into an operator workspace for active agent work:

- dedicated Agent Workspace surface with live run inspection
- run progress, state, step/tool/retry telemetry, metadata and failure visibility
- safe run cancellation through the existing runtime control boundary
- automatic live polling while an execution is active
- recent-run queue with direct inspection
- bounded multi-agent collaboration builder using the existing collaboration API
- explicit specialist objectives and capability selection
- approval-aware collaboration plan presentation before execution
- responsive workspace layouts for desktop and mobile
- frontend regression contracts for the interactive workspace surface

The workspace remains an operator surface: it exposes execution state and prepares bounded collaboration plans without granting the browser additional agent authority.

