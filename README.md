# Workstream

Workstream is Flow's task evaluation and contribution infrastructure.

Workstream manages project guides, task queues, submission packets, automated checks, reviewer routing, evaluation sprints, revision loops, contribution records, payment status, and reputation signals.

Workstream is how Flow measures, certifies, and coordinates useful human-agent work.

It is not a workspace and it is not blockchain-first. Operators can work with any local tools, human-agent workflow, or external execution environment. Workstream owns the project guide, task queue, submission packet, automated checks, human review, revision loop, acceptance state, payment ledger, and reputation record.

Workstream is source-agnostic, but v0.1 is manual-first. External origin onboarding, source adapters, automated routing, owner-agent execution workspaces, and on-chain settlement remain later adapters until the internal evaluation loop is proven.

The first 30 days are focused on building serious internal infrastructure that can run real projects end to end:

```text
Project Guide
-> Submission Artifact Policy
-> Pre-Submit Checker Policy
-> Task Queue
-> Task Record
-> Submission Packet
-> Platform Checkers
-> Human Review
-> Needs Revision / Accepted / Rejected
-> Contribution Record
-> Payment Record
-> Reputation Update
-> Lessons Learned
```

## Core Thesis

Different projects speak different domain languages, but serious task evaluation and contribution systems share the same lifecycle:

- every project has a guide
- every project has an approved submission artifact policy
- every task belongs to a project
- every project has a base amount or payment policy
- every task has acceptance criteria
- every submission has required artifacts, evidence references, hashes, and worker attestation
- every invalid submission packet is blocked before submission creation
- every submission passes automated checks before human review
- every review creates a decision
- every revision must close prior feedback
- every accepted task updates payment and reputation

Workstream turns that operating knowledge into reusable infrastructure.

## Planning Package

- [Codex Agent Loop](.agent-loop/README.md)
- [Repository Engineering Policy](.agent-loop/policies/repository-engineering-policy.md)
- [30-Day Master Plan](docs/roadmap_30_day_master_plan.md)
- [Roadmap Status](docs/roadmap_status.md)
- [Week 1 Backend Plan](docs/roadmap_week1_backend_plan.md)
- [Week 2 Checker Framework Specification](docs/spec_week2_checker_framework.md)
- [Chunk 6 Checker Contract And Records](docs/spec_chunk_6_checker_contract_records.md)
- [Chunk 7 Checker Runner And Registry](docs/spec_chunk_7_checker_runner_registry.md)
- [Chunk 8 Submission Artifact And Policy Checkers](docs/spec_chunk_8_submission_artifact_policy_checkers.md)
- [Chunk 9 Pre-Review Gate](docs/spec_chunk_9_pre_review_gate.md)
- [Chunk 10 Checker Trial](docs/spec_chunk_10_checker_trial.md)
- [Day-by-Day Execution Plan](docs/roadmap_day_by_day_execution_plan.md)
- [Implementation Backlog](docs/roadmap_implementation_backlog.md)
- [Product Principles](docs/product_principles.md)
- [Product Brief](docs/product_brief.md)
- [First User Flows](docs/product_first_user_flows.md)
- [Architecture Brief PDF](docs/architecture_brief/workstream_architecture_brief.pdf)
- [Architecture Diagrams](docs/diagrams/README.md)
- [System Architecture](docs/architecture_system_architecture.md)
- [Data Model](docs/architecture_data_model.md)
- [Lifecycle State Machine](docs/architecture_lifecycle_state_machine.md)
- [Checker Framework](docs/architecture_checker_framework.md)
- [Operator Workflow](docs/operations_operator_workflow.md)
- [Project Operating Manual](docs/operations_project_operating_manual.md)
- [Queue Policy](docs/operations_queue_policy.md)
- [Workspace And Packet Convention](docs/operations_workspace_packet_convention.md)
- [Reviewer Workflow](docs/operations_reviewer_workflow.md)
- [Revision Replay](docs/operations_revision_replay.md)
- [Roles And Permissions](docs/operations_roles_permissions.md)
- [Payment And Reputation](docs/operations_payment_reputation.md)
- [Risk Register](docs/risk_register.md)
- [Process Pattern Baseline](docs/process_pattern_baseline.md)
- [Architecture Lockdown](docs/architecture_lockdown.md)
- [Glossary](docs/glossary.md)

## Review Passes

- [Process Baseline Operations Review](docs/review_process_baseline_operations_review.md)
- [Final Product Strategy Review](docs/review_final_product_strategy_review.md)
- [Final Architecture Review](docs/review_final_architecture_review.md)
- [Final Adversarial Review](docs/review_final_adversarial_review.md)
- [Adversarial Quality Review](docs/review_adversarial_quality_review.md)
- [Process Pattern Baseline Review](docs/review_process_pattern_baseline_review.md)
- [Review Closure](docs/review_closure.md)

## Templates

- [Project Guide Template](docs/template_project_guide.md)
- [Submission Artifact Policy Template](docs/template_submission_artifact_policy.md)
- [Checker Policy Template](docs/template_checker_policy.md)
- [Task Template](docs/template_task.md)
- [Review Readiness Evidence Template](docs/template_preflight_evidence.md)
- [Submission Packet Template](docs/template_submission_packet.md)
- [Review Packet Template](docs/template_review_packet.md)
- [Task Status Template](docs/template_task_status.md)
- [Prior Feedback Checklist Template](docs/template_prior_feedback_checklist.md)

## Decisions

- [ADR 0001: Core Scope](docs/decision_0001_core_scope.md)
- [ADR 0002: Database Ledger Before Blockchain Settlement](docs/decision_0002_db_first_not_blockchain_first.md)
- [ADR 0003: Project Guides Are First-Class](docs/decision_0003_project_guides_are_first_class.md)
- [ADR 0004: v0.1 Implementation Stack Is Locked](docs/decision_0004_v0_1_stack_is_locked.md)
- [ADR 0005: Postgres Is The Record Database](docs/decision_0005_postgres_is_the_record_database.md)
- [ADR 0006: Workstream Verifies External Flow Auth](docs/decision_0006_external_flow_auth_boundary.md)
- [ADR 0007: Execution Is Async-First](docs/decision_0007_async_first_execution.md)
- [ADR 0008: Files Use An Object-Storage Abstraction](docs/decision_0008_object_storage_abstraction.md)
- [ADR 0009: Review Decisions Are Canonical](docs/decision_0009_review_decisions_are_canonical.md)
- [ADR 0010: Revision Context Rebase Is Controlled By Policy](docs/decision_0010_revision_context_rebase.md)
- [ADR 0011: Submission Artifact Policy Drives Pre-Submit Intake](docs/decision_0011_submission_artifact_policy_drives_pre_submit.md)

## Engineering Loop

Workstream is built with a Codex-native zero-trust engineering loop:

```text
Intent
-> Discovery
-> Plan
-> Chunk Map
-> Chunk Contract
-> Implementation
-> Evidence
-> Internal Review
-> PR
-> Human Checkpoint
-> Memory Update
-> Stop
```

Codex-discoverable skills live in `.agents/skills/`. Codex custom reviewer
agents live in `.codex/agents/`. Durable engineering memory, policies, chunk
contracts, reviews, and status live in `.agent-loop/`.

This engineering loop is separate from Workstream product state. It governs how
the repository is changed; it does not define runtime task or review records.

## Local Backend Database

Workstream uses Postgres locally and in CI. Start the local database with:

```bash
docker compose up -d postgres
```

The default local development URL is:

```text
postgresql+asyncpg://workstream:workstream@localhost:5433/workstream
```

Destructive real API drills use the separate local test database:

```text
postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test
```

Project guide sufficiency and submission artifact policy derivation use the
local fixture adapter by default. This adapter is an async, no-network test and
development stand-in; it is not the production intelligence path.

```text
WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER=local_fixture
```

Persisted sufficiency and derivation agent identity is Workstream-owned; runtime
or provider-returned identity fields are not trusted as audit provenance.

To try the optional OpenAI Agents SDK adapter, install the backend agent extra
and set the model explicitly:

```bash
cd backend
.venv/bin/pip install -e ".[agents]"
```

```text
WORKSTREAM_PROJECT_AGENT_RUNTIME_ADAPTER=openai_agent_sdk
WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=<approved-model>
WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS=1800
WORKSTREAM_PROJECT_AGENT_MAX_PROMPT_BYTES=2000000
OPENAI_API_KEY=<runtime-secret>
```

The OpenAI Agents SDK adapter is only resolved on the explicit project-agent routes.
Normal project setup APIs and the local fixture adapter do not require an
OpenAI API key.

## Week 1 API Demo UI

The Week 1 API demo UI lives in `demos/week1_api_demo_ui/`. It is a temporary walkthrough client for the Week 1 backend APIs, not the canonical Workstream frontend implementation. It calls the real backend over HTTP through the Vite proxy and uses local Flow-style bearer tokens against the backend `flow` verifier.

Start the backend for the demo:

```bash
cd backend
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream \
WORKSTREAM_AUTH_PROVIDER=flow \
WORKSTREAM_ENVIRONMENT=local \
WORKSTREAM_FLOW_AUTH_ISSUER=https://auth.flow.local/demo \
WORKSTREAM_FLOW_AUTH_AUDIENCE=workstream-demo \
WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET=workstream-demo-local-secret \
WORKSTREAM_ENABLE_DEMO_ROUTES=true \
.venv/bin/alembic upgrade head

WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream \
WORKSTREAM_AUTH_PROVIDER=flow \
WORKSTREAM_ENVIRONMENT=local \
WORKSTREAM_FLOW_AUTH_ISSUER=https://auth.flow.local/demo \
WORKSTREAM_FLOW_AUTH_AUDIENCE=workstream-demo \
WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET=workstream-demo-local-secret \
WORKSTREAM_ENABLE_DEMO_ROUTES=true \
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Start the demo UI:

```bash
cd demos/week1_api_demo_ui
npm install
npm run dev -- --port 5173
```

Open:

```text
http://127.0.0.1:5173/
```

The demo runs the Week 1 path from project guide to locked submission using real API calls. The local demo worker-profile route is guarded by `WORKSTREAM_ENABLE_DEMO_ROUTES=true` and local/test environments only.

## Day-30 Success Standard

By day 30, Workstream runs a real internal task cycle with real people:

```text
Create project guide
Create task
Assign task
Submit packet
Run checks
Review packet
Record review decision: accept, needs_revision, or reject
Create contribution record for accepted work
Record payment status separately for accepted work
Update reputation from review outcome
Review lessons learned
```

The system is successful only if it prevents weak work from reaching review, preserves evidence, and gives operators a clear path from task intake to accepted paid output.

## Operating Standard

Workstream is built as durable operational infrastructure:

Governance:

- project rules live in guides and policies, not chat memory
- guide and policy versions are locked per task so rules do not drift silently
- out-of-band guidance is not enforceable until it becomes a guide, policy, template, or checker contract update

Lifecycle and revision:

- status is a ledger, not a loose label
- revisions replay prior findings one by one
- revision context is prepared before resubmission when guide or policy versions change

Artifacts, evidence, and auditing:

- reviews cite evidence and required changes
- submitted artifacts are immutable and hash-bound to checker runs
- every checker result is stored and auditable

Acceptance and payment:

- accepted work cites evidence before payment exposure is created
- accepted work creates an evidence-backed contribution record before payment or reputation updates
- payments are recorded separately from task acceptance

Checkers, lessons, and gates:

- lessons learned become guide updates or new checkers
- quality gates remain separate: project activation, task screening, and submission quality
