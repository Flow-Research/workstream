# Workstream

Workstream is software that manages work done by people, AI agents, or both.
It checks submitted work and makes a permanent record of the result.

A project sets the rules for its work. A contributor does a task and submits
the result. Workstream checks the result against the project rules. When the
work is accepted, Workstream makes a record that shows who did what, under
which rules, and with what result. Other systems can then use that record.
For example, a payment system can use it to pay the contributor.

Workstream is two things:

- **A shared protocol.** The protocol is the set of rules for valid work. It
  defines how tasks are assigned, how work is submitted, checked, and reviewed,
  and which records are made.
- **The software that applies those rules.** This repository contains that
  software.

The protocol does not yet have a separate, versioned specification or a
conformance test suite. That work is still to be done. For more information,
see [Protocol And Implementation](docs/protocol-and-implementation.md).

## How Workstream works

Each piece of work goes through these steps:

1. **A project sets its rules.** A project manager uploads a project guide.
   Workstream helps turn the guide into versioned policies. Approved policies
   are locked, so later changes do not affect work that has already started.
2. **A contributor gets a task.** A contributor claims a ready task.
3. **The contributor prepares the work.** The contributor puts the work into
   one ZIP file.
4. **Workstream checks the package before it accepts the submission.** These
   are the *pre-submission checks*. If the package has a problem, the
   contributor gets feedback and no submission is made.
5. **Workstream stores the submission.** After a submission is stored, nobody
   can change it.
6. **Workstream checks the submitted work.** These are the *post-submission
   checks*. They compare the work with the project's requirements.
7. **The work is accepted, sent back, or rejected.** By default, a project
   requires a human reviewer to make this decision. Live human review is not
   complete yet. A project can turn off human review. If it does, work that
   passes all required checks is accepted automatically. Failed checks can
   send the work back. On the last permitted attempt, failed checks reject
   the work.
8. **The contributor revises the work if necessary.** When the work is sent
   back, the contributor can submit a new version. The project sets the
   maximum number of revisions and a deadline.
9. **Workstream makes permanent records.** Every valid human review makes a
   reviewer contribution record. An accepted submission also makes a
   `FinalAcceptance` record and a contribution record for the contributor.

Workstream keeps the full history. It does not overwrite submissions,
findings, reviews, or records.

### Key terms

| Term | Meaning |
|---|---|
| Project guide | The document that describes the work a project wants. |
| Policy | A versioned set of rules made from the project guide, for example the checks to run. |
| Task | One unit of work that a contributor does. |
| Submission | The work a contributor sends for a task. A submission cannot be changed. |
| Pre-submission check | A check on the ZIP package before Workstream accepts it as a submission. |
| Post-submission check | A check on the stored submission against the project requirements. |
| Review | A decision by an authorized reviewer: `accept`, `needs_revision`, or `reject`. |
| `FinalAcceptance` | The record that a submission is accepted, by a reviewer or automatically. Only this record can make a contribution record for accepted work. |
| `ContributionRecord` | A permanent record of accepted work or of a valid human review. Nobody can create or edit it directly. |

The [glossary](docs/glossary.md) defines all Workstream terms.

### What Workstream does not do

- **It does not do the work.** People and agents use their own tools.
  Workstream receives and checks the result.
- **It does not log users in.** An external service verifies who a user is.
  For v0.1, that service is Flow Identity. Workstream itself decides what
  each user is permitted to do.
- **It does not send payments.** Workstream records the contributions that a
  project can pay for. Payment delivery is planned, not available.
- **It does not depend on one application.** Any application, organization,
  or industry can use the same steps.

## Current status

Workstream is in development. Version 0.1 is not released.

These parts work in a local test run:

- Set up a project from a guide, with separate approval of the pre-submission
  and post-submission policies.
- Create tasks, one at a time or in batches.
- Claim a task, submit a ZIP file, and get check results.
- Accept work automatically when a project turns off human review.
- Make contribution records and conditional awards for accepted work.

The local test run used recorded AI model output. It does not prove project
setup with a live AI model.

These parts are not complete:

- Live human review and revision after a human decision.
- Reviewer contribution records, because live human review is not complete.
- Proof of project setup with a live AI model.
- Operation on a hosted server.
- Payment delivery.

The [v0.1 Roadmap And Capability Status](docs/roadmap_status.md) gives the
full, current status. Read it before you rely on a feature.

## Run Workstream on your computer

This quick start uses Docker. For other setups, read the full
[Developer Setup](docs/engineering/developer-setup.md) guide.

You need Git, Docker Engine, and Docker Compose v2.

1. Copy the example configuration file:

   ```bash
   cp .env.example .env
   ```

2. Make the file private:

   ```bash
   chmod 600 .env
   ```

   This command works on Linux, macOS, and Git Bash. On PowerShell, make the
   file readable only by your Windows user before you add secrets.

3. In `.env`, give `COMPOSE_PROJECT_NAME` a unique value.

4. In `.env`, replace every `change-me` value with your own secret. The
   [local pilot runbook](docs/engineering/local-pilot.md) tells you how to
   make the secrets.

5. In `.env`, select host ports that no other program uses.

6. Build and start Workstream:

   ```bash
   docker compose --profile backend up --build --wait
   ```

   This command starts the API, the background worker, the scheduler,
   PostgreSQL, Redis, and MinIO (local file storage).

7. Make sure the API is running. Replace `<WORKSTREAM_API_HOST_PORT>` with the
   port that you selected in `.env`. On macOS, Linux, or Git Bash:

   ```bash
   curl --fail http://127.0.0.1:<WORKSTREAM_API_HOST_PORT>/api/v1/health
   ```

   On PowerShell:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:<WORKSTREAM_API_HOST_PORT>/api/v1/health
   ```

   The correct response is `{"status":"ok"}`.

8. To stop Workstream:

   ```bash
   docker compose --profile backend down
   ```

## Use the command-line client

The [Workstream CLI](cli/README.md) is a terminal client for the public API.
You can use it to set up projects, find and claim tasks, submit work, and
export contribution records. It sends your Flow token, from
`WORKSTREAM_TOKEN`, with each request.

## Repository layout

| Folder | Contents |
|---|---|
| `backend/` | The Workstream API and background workers (Python and FastAPI). |
| `cli/` | The command-line client (Go). |
| `mcp_server/` | An MCP (Model Context Protocol) adapter. AI agents can use it to read profile and permission data. |
| `external_checkers/` | The service and SDK that run external checker images (Rust). |
| `contracts/` | Shared data contracts. |
| `docs/` | Product, architecture, and operations documents. |
| `docker/` | Container files for local development. |
| `scripts/` | Scripts that check the repository and its documents. |
| `examples/` and `experiments/` | A sample benchmark project, and experiments that test features before they are built. |
| `.commitrail/` | Engineering records about changes to this repository. |

## Learn more

| If you want to | Read |
|---|---|
| Understand the product | [Product Brief](docs/product_brief.md) and [Product Principles](docs/product_principles.md) |
| Read the detailed lifecycle and implementation notes | [Workstream Technical Reference](docs/workstream_reference.md) |
| Understand the architecture | [System Architecture](docs/architecture_system_architecture.md) and [Architecture Lockdown](docs/architecture_lockdown.md) |
| See what works now | [v0.1 Roadmap And Capability Status](docs/roadmap_status.md) |
| Find a term | [Glossary](docs/glossary.md) |
| See all documents | [Documentation index](docs/README.md) |

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md) before you change this repository.
Each change follows this sequence:

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> Pull Request -> Human Merge
```

Dependency changes require a rebuild:

```bash
docker compose build backend
```

### Native Linux Workflow

Use this path only with CPython 3.11 or 3.12 on Linux glibc 2.27 or newer and
an x86_64 or aarch64 machine. Docker is still used for backing services.
Confirm that `python3 --version` reports Python 3.11 or 3.12 before creating
the environment. Install uv 0.12.3 and use the
committed lockfile; an unconstrained pip install is not a supported setup path.
Create and secure the root Compose configuration before its first command, as
described in the [local pilot runbook](docs/engineering/local-pilot.md). Give it
a unique project name, replace every required secret and choose unused backing
service host ports. The separate `backend/.env` configures the native process.

```bash
cp .env.example .env
chmod 600 .env
# Edit root .env before continuing.
docker compose up -d --wait postgres redis
cd backend
cp .env.example .env
chmod 600 .env
# Edit backend/.env before continuing.
python3 --version
uv --version
uv sync --locked --extra dev --python python3
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload
```

The v0.1 schema starts at the single `0001_uuid7_v01` Alembic revision.
Development databases stamped with any earlier revision are intentionally not
upgradeable: delete and recreate the local database, then run `alembic upgrade
head`. Workstream never rewrites or compatibility-stamps an old database.

Verify the API from another terminal with:

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
```

Both files are ignored. In `backend/.env`, set `WORKSTREAM_DATABASE_URL` to the
root file's PostgreSQL password and selected loopback host port, and set
`WORKSTREAM_CELERY_BROKER_URL` to its Redis loopback host port. When native
artifact storage is enabled, also select the MinIO profile and copy the root
file's bucket and credentials while using the selected MinIO API host port in
the loopback endpoint. These native process URLs use `localhost`; Compose
containers continue to use internal service names and ports. The `chmod`
commands are for POSIX shells; PowerShell users need equivalent private NTFS
ACLs.

### Native Unified Guide Inference

Set `WORKSTREAM_PROJECT_AGENT_MODEL=gpt-5.6-terra` (or your chosen supported model)
and `OPENAI_API_KEY` in ignored `backend/.env`. Runtime, provider/API protocol,
model and instructions are separate settings in `backend/.env.example`.
Prepare the ignored root `.env` as described in the Docker workflow and start
backing services using its port and credential settings. Put native backend and
provider settings in ignored `backend/.env`, then install the agent runtime and
load that file into API and Celery worker:

```bash
docker compose up -d --wait postgres redis minio
cd backend
uv sync --locked --extra dev --extra agents
uv run --env-file .env uvicorn app.main:app --reload
# In another terminal, from backend/:
uv run --env-file .env celery -A app.workers.celery_app worker --pool=prefork -Q celery --beat --loglevel=info
```

The model key must be in the process environment; `--env-file` supplies it without
shell-exporting or printing it. For connected guide testing, start Postgres,
Redis and MinIO, create the private bucket as described below, and enable the
S3-compatible settings in `.env`. The disabled-store first-run profile does not
support guide artifact ingestion. Committed original-document readiness runs one compilation
and stops at findings and draft proposals; manager review/approval remains separate.

### Logs, Shutdown, And Reset

The API and prefork Celery process emit privacy-bounded structured logs and can export
explicit traces and metrics to an optional OTLP HTTP/protobuf collector. See the
[observability operations guide](docs/engineering/observability.md) for the
configuration, safe field contract, failure behavior, outbox trace boundary,
and on-demand profiling procedure. Implemented instrumentation does not imply a
collector or monitoring service is configured or deployed.

```bash
docker compose --profile backend logs -f backend worker beat
docker compose --profile backend down
```

For the native workflow, stop Uvicorn with `Ctrl+C` before running
`docker compose down` for the backing services.

Database recreation is destructive and must be scoped to your disposable local
environment. First stop its API, Celery workers and scheduler. Confirm the Compose
project name, database host/port and attached volume with `docker compose ps` and
`docker volume inspect <exact-volume-name>`. Do not reset a shared environment or
another worktree's services. Remove only the verified disposable PostgreSQL volume
after stopping that Compose project's containers; do not use `down --volumes`,
which also removes artifact storage.

The UUIDv7 schema uses the distinct, Compose-project-scoped
`workstream_postgres_uuid7_data` volume. Starting it does not convert or erase the
old development volume. Once you have verified that the old volume is disposable
and has no remaining consumers, it can be removed separately by its exact name.
Compose also uses a fresh `workstream_redis_uuid7_data` volume so jobs from the
discarded database are not reused. For subsequent database resets, reset only
that environment's owned queue volume before restarting Celery workers; external
Redis configurations require their own verified private queue reset. Use a fresh
private artifact bucket/namespace for the new database;
do not delete retained/shared S3 or MinIO objects as part of a database reset.

### Backing Services And Artifact Storage

Workstream uses Postgres locally and in CI. It uses Celery with Redis for
durable local project setup jobs and automatic pre-review checker gates. MinIO
provides the S3-compatible artifact protocol in local development and CI. Start
the local services with:

```bash
docker compose up -d --wait postgres redis minio
```

MinIO is built from verified, pinned upstream source using the shared
[development/CI image recipe](docker/minio/README.md), rather than an unavailable
vendor image. The first build needs network access and compilation resources;
later builds reuse Docker's cache. CI builds or restores this image once and
shares it across the existing backend jobs. This does not change the hosted
AWS S3 provider or delete existing artifact volumes.

Set every published host port in the ignored root `.env`: API, PostgreSQL,
Redis, MinIO API and MinIO console. Native-backend users must put the same
selected backing-service ports in `backend/.env`; containerized services always
use the internal DNS names and ports.

MinIO uses checkout-local static credentials and the private bucket selected in
root `.env`. API startup creates and verifies that bucket before migrations;
the application and Celery process continue to access objects only through the
canonical `ArtifactStore`. Configure a native runtime with the exact
[artifact storage settings](docs/spec_artifact_storage_service.md#s3-compatible-adapter)
and the same private bucket.
The repository-managed MinIO port is bound to host loopback. A Workstream
process running on a separate non-production container network may instead use
an operator-controlled private MinIO endpoint; that remains development/test
protocol proof and never qualifies as hosted-provider activation evidence.
Native AWS S3 uses exact release, namespace, role/policy, reviewed role-trust
policy digest and bucket-policy bindings. API, Celery task-process and Beat
startup require a matching fresh immutable three-probe activation. The adapter
also reloads that activation before every
AWS SDK call and before committing provider-derived terminal facts. Missing,
stale or mismatched proof fails with `artifact_provider_live_proof_required`
before credential probing or provider I/O. See the
[artifact storage operations runbook](docs/operations_artifact_storage.md);
repository code and MinIO tests alone do not establish live AWS readiness.

The local development URL uses the password and PostgreSQL host port selected
in the ignored environment files:

```text
postgresql+asyncpg://workstream:<password>@localhost:<port>/workstream
```

Destructive real API drills use the separate local test database:

```text
postgresql+asyncpg://workstream:<password>@localhost:<port>/workstream_test
```

One project-guide compilation proposes sufficiency findings and separate
pre-submission and post-submission policies through the OpenAI Agents SDK adapter.
Use the locked installation and environment-loading commands in
[Native Unified Guide Inference](#native-unified-guide-inference).

The Celery worker captures runtime, model provider, model, API, instructions,
timeout, document limits and tool budgets on the attempt before execution. Credentials stay in
the Celery worker environment. `WORKSTREAM_PROJECT_AGENT_INSTRUCTIONS` and
`WORKSTREAM_PROJECT_AGENT_INSTRUCTION_VERSION` configure trusted instructions;
omitting the text selects the repository's canonical compilation instructions.
The current adapter uses OpenAI Responses with a private Code Interpreter
workspace. `WORKSTREAM_PROJECT_AGENT_MODEL=gpt-5.6-terra` selects the model
independently of the runtime and instructions. Changing that setting requires
verifying the chosen model supports the configured tools and structured output.
`WORKSTREAM_PROJECT_AGENT_REQUEST_TIMEOUT_SECONDS` defaults to 300 seconds per
provider request. `WORKSTREAM_PROJECT_AGENT_RUN_TIMEOUT_SECONDS` defaults to 1,800
seconds for the whole run, including retry waits. The Agents SDK retries a model
request at most twice, with exponential backoff and jitter capped at 30 seconds.
Only proven pre-transmission failures, explicit temporary rate limits, or
provider-confirmed safe replay are eligible. Billing, authentication, invalid
output, denied document access, and unknown dispatched outcomes do not retry.
A process-local circuit opens after three exhausted transient model requests,
then admits one recovery probe after 60 seconds. Cleanup remains available.
The corresponding retry and circuit settings are listed in `backend/.env.example`.
The runtime adapter is selected through the shared typed adapter factory.

Verified guide-source readiness automatically delivers one compilation. A ready
result records both policy proposals and stops at a draft; an insufficient guide
stops with findings. Automatic compilation ends without approving the proposals.
POL-05B exposes exact Project Manager proposal review, pre-submission approval,
setup-wide correction and explicit manual dispatch using POL-05A operations and
AUTH-12F4 authorization. The setup response supplies `finalized_compilation_id`
for opening the exact complete proposal, plus `correction_operation_id` and
`predecessor_compilation_id` for recovering a saved correction after manager
handoff or a lost creation response. See the
[manager proposal flow](docs/operations_project_operating_manual.md#review-approve-or-correct-a-guide-proposal).
POL-06B connects deterministic post-submission policy derivation to committed
pre-submission approval. The fixed setup service derives from the saved result;
project managers discover its `post_submit_policy_id` through the proposal read,
inspect its complete body, and separately approve it or request a unified
correction. Both correction origins use the same explicit manual dispatch.
Derivation, reads, approval and correction creation do not invoke inference or
post-submit evaluators. A periodic scan recovers publication failures from
committed approvals; duplicate delivery retains one policy and receipt.
Hidden post-submission execution and completion custody are implemented.
ARCH-04D2 supplies exact service authority and ARCH-04E1A supplies source-only
facts/types. PILOT-04 registers selected production request/completion routing;
ARCH-04E3-B activates supported false-policy guides. The bounded local public
durable-runtime drill starts from public guide inputs with recorded inference.
The local Celery command above includes Beat; start it before creating guide sources.

The Beat scheduler must run alongside the Celery execution processes so
artifact pending-work, verified guide-continuation and post-policy approval scans can recover
publication failures automatically.

The public submission-bundle preparation flow reserves an exact pre-submit
attempt before invoking checks. Completed retries recover the original evidence
without rerunning checks or issuing a new upload capability. An uncertain attempt
cannot execute again under the same key. POL-07B connects the internal
checker phase service and removes the standalone JSON precheck. Both fresh
pre-submit execution and completed replay use that service, with ART retaining
canonical evidence ownership. The obsolete checker worker, manual execution and
submission-finalize repair routes are removed. `evaluate_post_submission` now
uses hidden durable execution with exact ARCH-04D2 service authority. ARCH-04E1A
retains route-neutral source evidence. REV-04C uses its bounded exact-source
verifier and shared FinalAcceptance/TASK/CON participant. The authorized TASK
outcome owner publishes exact routing sources under CHECKERS current-run custody.
B7 implements hidden
request delivery with invocation fencing. B8 adds hidden completion routing with commit-before-ACK. Production
request/completion registration is supplied by the selected PILOT-04 composition;
ARCH-02I-B exposes the existing admission-backed writer through the public
Submission POST for initial work and checker remediation.
Submission and checker history use live exact-project Submitter authority for the
original contributor. Separate `/projects/{project_id}` reads require a covering
Project Manager grant and expose fixed management fields. Token roles confer no
authority and authentication returns only the verified identity contract.
Finance Authority can publicly discover, create, update, publish,
read and retire a project's ContributionPolicy under
`/api/v1/projects/{project_id}/contribution-policies`. The current-policy read
recovers a draft selector, a published selector, or both for another authorized
Finance actor.
Each mutation requires one UUID `Idempotency-Key`. AUTH owns the authorization
decision for the authenticated actor; the CON caller transaction atomically commits
policy effects, AUTH evidence and immutable replay custody. Both contribution
types must explicitly declare compensated or unpaid rules. Unpaid publication
needs no compensation binding; compensated rules retain verified binding checks.
Project Managers do not acquire Finance powers. Public compensation-binding
administration remains pending.

CON provides internal exact selected-policy validation: a
new guide binding must match the active policy’s current published version;
the revision-adoption purpose validates an explicitly supplied historical version
without reselection. Both validate complete rules and current unit/binding
eligibility in the caller transaction. CP07 supplies the canonical activation operation:
exact separate pre/post approvals, review/revision selections and the published
ContributionPolicyVersion become one immutable guide binding. It atomically
supersedes the explicitly selected prior guide and activates a draft Project.
Replay preserves the original binding after supersession or policy retirement;
active-guide reads require that custody. Activation no longer uses the superseded economic readiness guard.
AUTH-12H supplies explicit live authority for an active Project Manager scoped to
that exact project. Shared prepared authorization locks current identity and grant
before product resources, binds the complete activation digest and rechecks live
authority on replay. Composition without an authority adapter still denies.
AUTH-18 exposes `POST /api/v1/projects/{project_id}/guides/{guide_id}/activate`.
The draft post-policy review package supplies `activation_context`: exact guide,
review/revision, predecessor, separately approved post-policy and published CON
selectors. Missing selectors remain explicit; the context does not promise readiness.
Managers obtain those selectors without Finance privileges, then submit the exact
selection with one UUID `Idempotency-Key`. Save the body and key for receipt replay;
the draft context is not an active-guide replay endpoint. Response validation,
authority evidence and activation effects commit together. ARCH-03D connects the
intake handoff to the exact activated guide. ARCH-02I-B exposes public initial
and checker-remediation intake; controlled human-review revision remains separate.

ARCH-03A completes the existing internal PROJECTS context port. New work selects
one active activated guide; existing work resolves its exact frozen guide and
policy selectors, including after a successor or contribution-policy retirement.
The result includes the saved activation receipt, both checker-policy bodies,
artifact/effective policy, review/revision semantics and exact approved external
image bindings. Retained earlier contexts preserve their immutable identities. It never substitutes current policies or reruns inference. CP08 uses
that port in the existing TASK writers: screening stamps the activated contribution
policy, claim copies it to the assignment, and hidden Submission creation copies
the assignment's exact stamp. PostgreSQL rejects mismatched or replaced stamps.
New work requires no superseded economic configuration. ARCH-03B1 removes
TaskService's private PROJECTS reads: the existing port now returns detached
project descriptions and exact historical guide display facts. Draft task creation
requires project existence, not an activated guide. ARCH-03B2 adds hidden,
project-scoped ready queue facts with bounded live pagination; it exposes no
queue endpoint or authority. ARCH-03B3 adds hidden all-state management queues
with planning fields and operational queues with IDs/status/timestamps only.
ARCH-03B4 adds hidden contributor and management task detail with fixed
fields and project/assignment visibility, now exposed through ARCH-03C5 exact
Contributor and Manager authority. ARCH-03B5 replaces the existing contributor/manager work-context
responses with distinct fixed task facts and exact historical policy identities,
without obsolete payment fields or submission flags. ARCH-03B6 supplies distinct
locked-context projections through the same historical resolver: management
includes the bounded checker summary; operational and audit reads expose only
exact policy references. ARCH-03C6 exposes all three through distinct
exact-authorized routes and removes the old task-only management route. ARCH-03B7 supplies immutable contributor and
management requirements through one historical translator. Its hidden contributor
read reuses exact assignment visibility after locking TASK; the retained requirements
route and separate Manager route use ARCH-03C5 live exact authority. ARCH-03B8 supplies bounded task evidence, publicly authorized by ARCH-03C7;
ARCH-03B9 supplies hidden exact-assignment invalidation with committed cause
verification and a same-transaction delivery fence. ARCH-03C1 supplies real
fixed-service authority and exact decision receipts; ARCH-03C2 supplies atomic
AUTH event publication and production handler registration. ARCH-03C3 replaces
the create/screen/release role-only path with exact Project Manager authority,
atomic audit evidence and durable replay. ARCH-03C4 exposes separate contributor-ready,
manager-planning and Operator-status queues with current scoped grants and signed
pagination. ARCH-03C5 exposes separate Contributor/Manager detail and requirements,
removing their old role/creator wrappers. PILOT-14 adds the task-locked
ContributionPolicyVersion compensation block to ready summaries and Contributor
detail for active exact-project Submitters or Reviewers. It exposes only unpaid
or instrument/unit/exact-quantity terms, never Finance binding or route facts;
claim/start authority remains Submitter-only. ARCH-03C6 exposes separate manager, system-Operator and Audit Authority
locked-context reads with exact current grants. ARCH-03C7 exposes bounded task
history only to covered Audit Authority and removes the old payload-bearing
task-only audit route. AUTH-18 delivers public manager guide activation;
ARCH-03D connects hidden intake through final durable intent to canonical TASK/PROJECTS
ports, preserving historical guide selection. ARCH-02I-B exposes public ZIP
preparation and canonical admission-backed Submission creation. ARCH-04B supplies
hidden exact verified Submission
input with scoped async file access and cleanup. ARCH-04B2 adds hidden typed
checker-output storage, byte-free recovery and flush-only verified binding over
the generic ART put/verification path. ARCH-04C supplies hidden durable execution,
exact request/execution-lease custody, immutable member results and atomic completion events.
Selected image execution retains normalized bounded JSON results. Checker file
output write/bind authority remains unavailable; neither executable catalogue
remains in the live flow. ARCH-04D1 validates retained terminal material against canonical
ART lineage. ARCH-04D2 supplies fixed-service input, execute and finalize authority,
with PostgreSQL enforcement of exact execution/finalization receipts. ARCH-04E1A
adds immutable source storage and detached contracts. PILOT-04 composes selected
hidden dispatch and production routing; ARCH-02I-B exposes public intake and
ARCH-04E3-B admits complete false-policy guides with supported approved
requirements. The hidden
[ARCH-04E2-B operation](.commitrail/initiatives/WS-ARCH-001/WS-ARCH-001-04E2B.md)
consumes canonical fixed-router authorization and commits the actual receipt
with its exact source and complete consequence. Locked true moves TASK to
`review_pending` without a REV queue or CON dependency. Locked false invokes
the shared acceptance participant and atomically stages FinalAcceptance,
accepted TASK/completed assignment, submitter ContributionRecord, applicable
awards and shared audit/outbox evidence. It creates no Review or reviewer
contribution. Database closure rejects partial effects; exact replay verifies
the original tuple with fresh authority instead of repairing it.

B6 supplies atomic Submission/dispatch, B7 hidden request delivery and B8 hidden
completion handling with commit-before-ACK. 04F2 supplies the hidden remediation
handoff without Review, acceptance, contribution or award effects. 04F3 supplies
hidden exact-cause replacement intake through the canonical Submission writer;
it neither creates failure economics nor activates human revision. 04F4 adds
hidden Operator retry for known terminal infrastructure failures with immutable
source evidence. PILOT-04 registers selected production request/completion handlers.
ARCH-02I-B exposes public admission-backed entry; ARCH-04E3-B activates
supported false-policy guides, with new acceptance effects still gated on a
LIVE REV generation bound to the current reviewed manifest. A known pre-effect
refusal retries only within
the existing OUTBOX budget; exhausted delivery dead-letters without automatic
reopen. The connected public-guide API and Celery drill passed with recorded inference. A future setup-fault hold must
retain the Submission and locked rules without contributor penalty; changing
submitted-work rules remains deferred.
Real manager activation now supplies the false-policy lineage when the approved
requirements are supported; a `human_review` disposition still blocks that mode.
Conditional awards stay atomic; payment delivery and fulfillment-root machinery
remain deferred until fulfillment is enabled.

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
keeps its locked governing context. The task's locked project RevisionPolicy
requires an explicit nonnegative revision cap: N=2 permits submissions 0, 1 and
2; N=0 permits only the initial Submission. A final-attempt failure immediately
records rejection, closes its assignment and returns the task to ready, without
another preparation or deadline. Timeout also returns the task to ready. Anyone
eligible may claim a new assignment at round 0, including a previous claimant;
there is no contributor-count limit or repeated-failure hold.

A post-submit coverage gap with no error goes to human review when the locked
ReviewPolicy requires it; otherwise it returns to the contributor
(`checker_coverage_incomplete`) without spending a round, so it never exhausts
the assignment and the next attempt keeps its current round. Consecutive
coverage returns keep the first return's window, so a repeated gap still
expires.

When a revision remains, contributor-fixable failure freezes the complete
next-attempt context and change summary. Revision reruns intake and acknowledges
that exact preparation. A setup-blocked rebase publishes durable PM attention
and pauses the PostgreSQL-time allowance; repair resumes only its remaining
time. Repair of a running context preserves its deadline. Only committed
immutable resubmission ends a running opportunity. Task state, terminal evidence,
authorization, audit and outbox intent commit atomically. Original Submissions
and findings remain immutable; scans and retries recover after downtime.
Infrastructure/provider/budget failures never spend a contributor attempt.
Checker remediation creates no Review or reviewer contribution. Live human
Review decision composition remains #554 work under the same intended policy.
Timeout and exhaustion create no contribution, award or fulfillment facts.

Lifecycle state is a ledger, not a loose label. Submitted artifacts remain
immutable and hash-bound to their checks; findings, responses, resolutions,
Reviews, and contribution facts remain attributable and auditable. Lessons
become governed guide, policy, template, or checker changes before they affect
future work. Project activation, task screening, submission quality, review,
contribution recognition, and conditional fulfillment remain distinct gates
even though they form one end-to-end v0.1 lifecycle.

## License

Workstream is licensed under the
[GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`).

You may change Workstream and let users use your changed version over a
network. If you do, AGPLv3 requires you to offer those users the corresponding
source code under the license terms. Third-party packages and included material stay
under their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
