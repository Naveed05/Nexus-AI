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

### 🧠 Persistent memory

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

The next major engineering focus is **Security & Human Control Hardening**, followed by a real product frontend/deployment stack.

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
[→] Evaluation & Benchmark Platform
[ ] Security & Human Control Hardening
[ ] Production Frontend
[ ] Productization
[ ] Deployment & Observability
[ ] Public Beta
```

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
