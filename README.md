# Workstream

Workstream is governed contribution infrastructure for coordinating, verifying,
and recording work performed by humans, AI agents, or both. It transforms
project-defined tasks, immutable submissions, deterministic checks, and
authorized review into trusted `ContributionRecord` facts that applications,
organizations, and economic systems can consume.

Workstream governs the work lifecycle; it does not need to own the system that
requested the work, the tools used to complete it, the identity provider, or
the consequence applied afterward. A project defines the rules, an authorized
contributor performs the work, Workstream binds the exact submitted artifact to
those rules and its verification evidence, and an authorized reviewer records
the outcome. The resulting immutable contribution lineage establishes who did
what, under which rules, using which artifact, and with what verified result.

## End-To-End Lifecycle

The complete Workstream model is:

```text
Project Guide
-> Versioned Policies
-> Task Assignment Or Claim
-> Immutable Submission Artifact
-> Deterministic Checks
-> Authorized Review
-> Accept / Needs Revision / Reject
-> Revision And Resubmission When Required
-> Immutable ContributionRecords
-> Optional Project-Specific Consequences
```

The current submission contract normally receives one outer ZIP containing the
complete work. Workstream computes canonical content identity, stores the bytes
through its artifact boundary, verifies stored content before trusted use, and
runs configured checks against the submitted package and its bounded recursive
contents. Contributors, checkers, reviewers, and downstream projections are
therefore tied to the same immutable submission lineage.

Every valid Review creates a reviewer `completed_review`
`ContributionRecord`. An `accept` decision also creates `FinalAcceptance` and a
submitter `accepted_submission` `ContributionRecord`. These records cannot be
created or edited directly by a person or downstream adapter. Together they are
the central durable outcome of Workstream.

## How Workstream Establishes Trust

- **Identity is separate from authority.** External identity verification does
  not grant product access. Explicit administrative or project-scoped grants,
  resource ownership, lifecycle guards, and revocation determine authority.
- **Project rules are versioned and locked.** Assignments, submissions,
  Reviews, and contributions retain the guide and policy context that governed
  them instead of silently adopting later rules.
- **Artifacts are immutable and content-addressed.** Workstream derives identity
  from server-computed SHA-256 and byte count, independently verifies stored
  bytes, and binds trusted content facts to that identity.
- **Checks are attributable and reproducible.** Configured pre-submit and
  post-submit checkers record results against the exact submission and policy
  context.
- **Review is authorized and attributable.** A Review records the authorized
  reviewer, exact artifact lineage, locked rules, findings, and one canonical
  decision: `accept`, `needs_revision`, or `reject`.
- **Separation of duties limits self-dealing.** Submitter and reviewer authority
  are independent, self-review is prohibited, and narrower project conflict
  rules may be enforced.
- **History is preserved.** Submissions, findings, responses, resolutions,
  Reviews, contribution records, awards, receipts, and audit evidence remain
  linked rather than being overwritten.

## Source-Agnostic Core, Bounded v0.1 Intake

Workstream does not require tasks to originate from one marketplace,
application, organization, or industry. AI evaluation programs, government
workforce initiatives, research programs, open-source projects, contractor
pipelines, academic review, data-labeling operations, and legal, medical,
engineering, creative, human-to-agent, or agent-to-agent workflows can use the
same governed lifecycle while retaining their own user experience and operating
model.

Source-agnostic does not mean every source adapter is already implemented.
v0.1 remains manual-first with controlled manual, Markdown, and CSV intake.
External origin onboarding, automated routing, and execution workspaces remain
later adapters. Revision and reassignment belong to the governed lifecycle;
adjudication remains a separately approved future capability rather than a
claim about current v0.1 behavior.

## Product Boundary

Workstream determines what governed work occurred and whether the resulting
contribution fact can be trusted. Payments, points, tokens, staking, slashing,
reputation, eligibility, reporting, datasets, and model-training systems may
consume that fact and apply project-specific consequences. They do not create,
revise, or control Workstream identity, authorization, submission, review, or
contribution truth.

That boundary allows one Workstream core to support centralized, sovereign,
federated, and permissionless applications without coupling lifecycle truth to
any one application's business or economic model.

Flow Identity is the current v0.1 external authentication provider. It is an
adapter boundary, not the definition or ownership boundary of Workstream.
Workstream is not an execution workspace and is not blockchain-first.

## Core Invariants

Different projects speak different domain languages, but Workstream preserves
the same governing invariants across them:

- project guides and policies are versioned before they govern work
- tasks, assignments, submissions, checks, and Reviews retain their exact
  project and actor lineage
- invalid submission packets stop before trusted Submission creation
- findings, responses, resolutions, Reviews, and contribution facts append to
  history rather than rewriting it
- `FinalAcceptance` is the sole source of an accepted submitter contribution
- conditional compensation follows contribution truth and never controls it

These invariants turn project-specific operating knowledge into reusable
infrastructure without narrowing the complete v0.1 lifecycle defined above.

## Current v0.1 State

Workstream is under active v0.1 development. Progress is tracked by proven
capabilities, not by calendar weeks or promised dates.

Implemented foundations on `main` include external Flow-token verification,
canonical local actors and authorization, project guides and task records,
submission packets, immutable artifact storage, automated checker execution,
and the pre-review gate. Project-guide ingestion has typed source handling,
bounded extraction, security controls, persisted sufficiency evidence, and
authorized fixed-service guide-source binding and reads.

Active work is connecting those foundations into the remaining production
lifecycle: the remaining artifact custody chain, review and revision,
contribution records, and conditional compensation awards and fulfillment.
Contribution evidence remains the input for a separately implemented future
reputation projection. Frontend product work follows stable and tested backend
contracts for the surface it consumes.

The release bar is a verified end-to-end v0.1 lifecycle, not the completion of
an old timeboxed plan. See the [v0.1 Roadmap And Capability Status](docs/roadmap_status.md)
for the lifecycle scoreboard, current critical path, and complete release gates;
reading internal engineering records is not required to understand product
progress.

## Start Here

- [Developer Quickstart](#developer-quickstart)
- [Contribution Guide](CONTRIBUTING.md)
- [v0.1 Roadmap And Capability Status](docs/roadmap_status.md)
- [Product Principles](docs/product_principles.md)
- [Product Brief](docs/product_brief.md)
- [Architecture Lockdown](docs/architecture_lockdown.md)
- [System Architecture](docs/architecture_system_architecture.md)
- [Glossary](docs/glossary.md)
- [Historical Planning Index](docs/historical_planning.md)

## Product And Operations Documentation

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
- [Review And Revision Lifecycle](docs/spec_review_lifecycle.md)
- [Roles And Permissions](docs/operations_roles_permissions.md)
- [Authorization Service](docs/spec_authorization_service.md)
- [Immutable Artifact Storage](docs/spec_artifact_storage_service.md)
- [Contribution And Compensation](docs/spec_contribution_compensation.md)
- [Authorization Operations](docs/operations_authorization_service.md)
- [Compensation And Reputation](docs/operations_payment_reputation.md)
- [Risk Register](docs/risk_register.md)
- [Process Pattern Baseline](docs/process_pattern_baseline.md)
- [Glossary](docs/glossary.md)

## Historical Review Records

These records preserve earlier product, architecture, process, and adversarial
reviews. They are evidence and design history, not current implementation
status. Current changes receive review through [CONTRIBUTING.md](CONTRIBUTING.md).

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
- [ADR 0010: Human Revision Rebase Uses The Complete Active Project Context](docs/decision_0010_revision_context_rebase.md)
- [ADR 0011: Submission Artifact Policy Drives Pre-Submit Intake](docs/decision_0011_submission_artifact_policy_drives_pre_submit.md)
- [ADR 0012: Workstream Owns Product Authorization](docs/decision_0012_workstream_authorization_service.md)
- [ADR 0013: Immutable Artifact Storage Boundary](docs/decision_0013_immutable_artifact_storage_boundary.md)
- [ADR 0014: External Services Use One Adapter Convention](docs/decision_0014_external_service_adapter_convention.md)
- [ADR 0015: Project Contributor Roles Are Independent](docs/decision_0015_project_contributor_roles_are_independent.md)
- [ADR 0016: Contribution Recognition Precedes External Fulfillment](docs/decision_0016_contribution_compensation_boundary.md)

## Authorization Baseline

Workstream verifies externally issued Flow authentication tokens and owns its
product authorization. Token role claims, email, display name, skills,
reputation, and typed workflow profiles are not product authority. Canonical
authority comes from local actor identity links, administrative grants,
exact-project contributor grants, registered permissions, resource/lifecycle
guards, revocation, and append-only evidence.

All public API documentation uses `/api/v1`. Imported reference specifications
are immutable archival inputs. ADR 0012 and the canonical authorization service
specification control authorization; ADR 0016 and the canonical contribution
and compensation specification control contribution recognition, award
eligibility, and fulfillment boundaries. Older chunk specifications remain
implementation history until their owning migrations replace the runtime.

## Repository-Native Human-Agent SDLC

Workstream uses a Repository-Native Human-Agent SDLC. Plans, tests, review, and
durable decisions live with the code so humans and agents can collaborate
without depending on chat history. GitHub permissions and branch protection
remain the repository authority; process notes never create a second permission
system.

```text
Intent
-> Plan
-> Bounded Change
-> Evidence
-> Review
-> PR
-> Human Merge
```

Codex-discoverable skills live in `.agents/skills/`. Codex custom reviewer
agents live in `.codex/agents/`. The smallest useful durable engineering
records live in `.commitrail/`; start with its `README.md` and `INDEX.md`.

This engineering loop is separate from Workstream product state. It governs how
the repository is changed; it does not define runtime task or review records.
Independent initiatives and branches may proceed concurrently. Start with
[CONTRIBUTING.md](CONTRIBUTING.md) before proposing repository work.

## Developer Quickstart

Workstream's image-extraction boundary is intentionally Linux-only. The
supported runtime is CPython 3.11 or 3.12 on Linux glibc 2.27 or newer, using
either x86_64 or aarch64. macOS and Windows contributors should run the backend
through Docker; do not install a different Pillow build to bypass the approved
artifact boundary.

### Docker Workflow (Recommended)

Prerequisites are Git, Docker Engine, and Docker Compose v2. From the repository
root, build the native-architecture Linux image and start the API with healthy
Postgres and Redis dependencies:

```bash
docker compose up --build --wait backend
```

Then verify the API with the command for your shell:

```bash
# macOS, Linux, or Git Bash
curl --fail http://127.0.0.1:8000/api/v1/health
```

```powershell
# PowerShell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

The expected response is `{"status":"ok"}`. The backend service applies
Alembic migrations before serving, binds the API only to host loopback, and
uses explicit local-only development auth and key material. Artifact storage is
disabled in this first-run profile; integration tests configure MinIO when they
exercise the S3-compatible path.

The image uses Linux glibc on the Docker host's native x86_64 or aarch64
architecture. On Docker Desktop, this is the Docker VM's native architecture.
Do not force `--platform linux/amd64` on an ARM host: CPU emulation does not
provide equivalent evidence for Workstream's inner seccomp isolation filter. If
your shell sets `DOCKER_DEFAULT_PLATFORM`, clear it before building; the
Dockerfile rejects a foreign target architecture.

Run focused checks in the same containerized environment:

```bash
docker compose run --rm --no-deps backend python scripts/check_guide_extractor_dependencies.py
docker compose run --rm --no-deps backend python -m pytest -q tests/test_app.py tests/test_guide_extractor_dependencies.py
docker compose run --rm --no-deps backend ruff check app tests scripts
```

Dependency changes require a rebuild:

```bash
docker compose build backend
```

### Native Linux Workflow

Use this path only with CPython 3.11 or 3.12 on Linux glibc 2.27 or newer and
an x86_64 or aarch64 machine. Docker is still used for backing services.
Confirm that `python3 --version` reports Python 3.11 or 3.12 before creating
the environment. Native extraction also requires `libseccomp.so.2` and a normal
Linux `/proc`; install `libseccomp2` on Debian/Ubuntu or the equivalent
`libseccomp` package for your distribution. Install uv 0.12.3 and use the
committed lockfile; an unconstrained pip install is not a supported setup path.

```bash
docker compose up -d --wait postgres redis
cd backend
cp .env.example .env
python3 --version
uv --version
uv sync --locked --extra dev --python python3
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload
```

The v0.1 schema starts at the single `0001_v01_baseline` Alembic revision.
Development databases stamped with any earlier revision are intentionally not
upgradeable: delete and recreate the local database, then run `alembic upgrade
head`. Workstream never rewrites or compatibility-stamps an old database.

Verify the API from another terminal with:

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
```

`backend/.env` is ignored. Its checked-in example contains only public,
local-development values; replace those values when specifically testing key
rotation, and never reuse them in a shared or hosted environment.

### Logs, Shutdown, And Reset

```bash
docker compose logs -f backend
docker compose down
```

For the native workflow, stop Uvicorn with `Ctrl+C` before running
`docker compose down` for the backing services.

To deliberately delete the local Postgres and MinIO volumes as well, run the
following destructive reset command:

```bash
docker compose down --volumes
```

### Backing Services And Artifact Storage

Workstream uses Postgres locally and in CI. It uses Celery with Redis for
durable local project setup jobs and automatic pre-review checker gates. MinIO
provides the S3-compatible artifact protocol in local development and CI. Start
the local services with:

```bash
docker compose up -d --wait postgres redis minio
```

If either default host port is already in use, set
`WORKSTREAM_POSTGRES_HOST_PORT` or `WORKSTREAM_REDIS_HOST_PORT` before running
Compose. Native-backend users must put the same selected ports in
`backend/.env`; the containerized backend uses the internal service ports.

MinIO uses the compose-only static credentials and the private
`workstream-artifacts` bucket. The integration tests create that bucket
automatically. For local runtime use, create the private bucket with an S3
client against `http://localhost:9000` after MinIO is healthy, using access key
`workstream-minio` and secret key `workstream-minio-secret-key`, before starting
Workstream. Configure the runtime with the exact
[artifact storage settings](docs/spec_artifact_storage_service.md#s3-compatible-adapter).
The repository-managed MinIO port is bound to host loopback. A Workstream
process running on a separate non-production container network may instead use
an operator-controlled private MinIO endpoint; that remains development/test
protocol proof and never qualifies as hosted-provider activation evidence.
Native AWS S3 accepts workload-identity configuration but remains
runtime-ineligible until live deployment proof is approved; startup fails with
`artifact_provider_live_proof_required` before credential probing or provider
I/O.

The default local development URL is:

```text
postgresql+asyncpg://workstream:workstream@localhost:5433/workstream
```

Destructive real API drills use the separate local test database:

```text
postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test
```

Project guide sufficiency, submission artifact policy derivation, and
post-submit checker policy derivation run through the OpenAI Agents SDK adapter.
Install the backend agent extra and set the model explicitly before running
automatic project setup:

```bash
cd backend
.venv/bin/pip install -e ".[agents]"
```

```text
WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=<approved-model>
WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS=1800
WORKSTREAM_PROJECT_AGENT_MAX_PROMPT_BYTES=2000000
OPENAI_API_KEY=<runtime-secret>
WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART=true
WORKSTREAM_CELERY_BROKER_URL=redis://localhost:6379/0
```

The Celery project setup pipeline uses the OpenAI Agents SDK runtime. The Celery worker
environment must include `OPENAI_API_KEY` and the approved model settings.
Persisted sufficiency and derivation agent identity is Workstream-owned; runtime
or provider-returned identity fields are not trusted as audit provenance.

Run the Celery worker before creating guide-source snapshots that should automatically
prepare pre-submit policy, continue into post-submit policy derivation after setup
submission artifact policy approval, and advance locked submissions through the
automatic pre-review checker gate:

```bash
cd backend
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream \
WORKSTREAM_AUTH_PROVIDER=flow \
WORKSTREAM_ENVIRONMENT=local \
WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=<approved-model> \
OPENAI_API_KEY=<runtime-secret> \
WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART=true \
WORKSTREAM_CELERY_BROKER_URL=redis://localhost:6379/0 \
.venv/bin/celery -A app.workers.celery_app.celery_app worker --beat --loglevel=INFO
```

The Beat scheduler must run alongside the Celery execution processes so
artifact pending-work and verified guide-continuation scans can recover
publication failures automatically.

## v0.1 Success Standard

Workstream v0.1 succeeds only when the complete lifecycle defined at the top of
this README runs as a real internal task cycle with real people. The cycle must
prevent invalid work from reaching review, preserve exact evidence and
authority, support revision without rewriting history, produce trusted
contribution facts, and carry payable contributions through conditional award
and fulfillment. Runtime reputation projection is not part of this release
bar.

## Operating Standard

Workstream is built as durable operational infrastructure. Project rules live
in versioned guides and policies rather than chat memory. Each active attempt
keeps its locked governing context; `needs_revision` preparation rebases a
complete valid context for the next attempt rather than silently mixing old and
new rules.

Lifecycle state is a ledger, not a loose label. Submitted artifacts remain
immutable and hash-bound to their checks; findings, responses, resolutions,
Reviews, and contribution facts remain attributable and auditable. Lessons
become governed guide, policy, template, or checker changes before they affect
future work. Project activation, task screening, submission quality, review,
contribution recognition, and conditional fulfillment remain distinct gates
even though they form one end-to-end v0.1 lifecycle.
