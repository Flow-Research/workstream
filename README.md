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

## Core Thesis

Different projects speak different domain languages, but governed work and
contribution systems share the same lifecycle:

- every project has a guide
- every project has an approved submission artifact policy
- every task belongs to a project
- every project has an active published contribution policy version with
  explicit `accepted_submission` and `completed_review` rules, including
  explicit unpaid rules where intended
- every task has acceptance criteria
- every submission has required artifacts, evidence references, hashes, and contributor attestation
- every invalid submission packet is blocked before submission creation
- every submission passes automated checks before human review
- every valid human decision appends an immutable Review; submitted findings
  and later resolutions are immutable
- every revision responds to unresolved blocking feedback without rewriting it
- every valid human review creates a reviewer contribution
- every accepted Review creates one immutable FinalAcceptance
- every submitter accepted_submission contribution consumes FinalAcceptance
- every payable contribution updates compensation fulfillment; all contributions
  may feed a separately implemented reputation projection

Workstream turns that operating knowledge into reusable infrastructure.

## Current v0.1 State

Workstream is under active v0.1 development. Progress is tracked by proven
capabilities, not by calendar weeks or promised dates.

Implemented foundations on `main` include external Flow-token verification,
canonical local actors and authorization, project guides and task records,
submission packets, immutable artifact storage, automated checker execution,
and the pre-review gate. Project-guide ingestion now has typed source handling,
bounded extraction, security controls, persisted sufficiency evidence, and
authorized fixed-service guide-source binding and reads.

Active work is connecting those foundations into the remaining production
lifecycle: the remaining artifact custody chain, review and revision,
contribution records, and conditional compensation awards and fulfillment.
Contribution evidence remains the input for a separately implemented future
reputation projection. Frontend product work follows stable and tested backend
contracts for the surface it consumes.

The release bar is a verified end-to-end v0.1 lifecycle, not the completion of
an old timeboxed plan. See [Current v0.1 Status](docs/roadmap_status.md) for the
capability ledger and explicit remaining work.

## Start Here

- [Contribution Guide](CONTRIBUTING.md)
- [Current v0.1 Status](docs/roadmap_status.md)
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
- [ADR 0010: Revision Context Rebase Uses The Active Project Guide](docs/decision_0010_revision_context_rebase.md)
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
agents live in `.codex/agents/`. Durable engineering plans, decisions, and
optional review notes live in `.agent-loop/`.

This engineering loop is separate from Workstream product state. It governs how
the repository is changed; it does not define runtime task or review records.
Independent initiatives and branches may proceed concurrently. Start with
[CONTRIBUTING.md](CONTRIBUTING.md) before proposing repository work.

## Local Backend Database

Workstream uses Postgres locally and in CI. It uses Celery with Redis for
durable local project setup jobs and automatic pre-review checker gates. MinIO
provides the S3-compatible artifact protocol in local development and CI. Start
the local services with:

```bash
docker compose up -d postgres redis minio
```

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
.venv/bin/celery -A app.workers.celery_app.celery_app worker --loglevel=INFO
```

## v0.1 Success Standard

Workstream v0.1 must run a real internal task cycle with real people:

```text
Create project guide
Create task
Assign task
Submit packet
Run checks
Review packet
Record review decision: accept, needs_revision, or reject
Create reviewer contribution for every valid human review
For accept, create FinalAcceptance
Use FinalAcceptance as the sole source of the submitter contribution
Record compensation status only for payable contribution awards
Project reputation only after its separate implementation
Review lessons learned
```

The system is successful only if it prevents weak work from reaching review,
preserves evidence, and gives operators a clear path from task intake through
review, contribution, conditional compensation, and fulfillment.

## Operating Standard

Workstream is built as durable operational infrastructure:

Governance:

- project rules live in guides and policies, not chat memory
- guide and policy versions are locked per task so rules do not drift silently
- out-of-band guidance is not enforceable until it becomes a guide, policy, template, or checker contract update

Lifecycle and revision:

- status is a ledger, not a loose label
- revisions append one response and later resolution per required prior finding
- revision context is prepared from the active Project Guide before
  resubmission; exact stamped identity/activation-sequence match keeps context,
  and any different valid active pair rebases forward or backward

Artifacts, evidence, and auditing:

- reviews cite evidence and required changes
- submitted artifacts are immutable and hash-bound to checker runs
- every checker result is stored and auditable

Contribution and compensation:

- every valid human review creates a reviewer contribution from locked evidence
- for an accept decision, FinalAcceptance alone sources the submitter contribution
- only payable contributions create immutable awards and fulfillment tracking;
  explicit unpaid rules create none
- compensation fulfillment is recorded separately from task acceptance

Checkers, lessons, and gates:

- lessons learned become guide updates or new checkers
- quality gates remain separate: project activation, task screening, and submission quality
