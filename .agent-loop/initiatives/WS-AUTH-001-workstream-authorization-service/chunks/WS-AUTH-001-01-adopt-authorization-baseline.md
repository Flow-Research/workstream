# Chunk Contract: WS-AUTH-001-01 - Adopt Authorization Baseline And Repository Contracts

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Make the adopted authorization model, `/api/v1` namespace decision, superseded
bootstrap behavior, and implementation ordering unambiguous in canonical
repository documentation before application code changes.

## Why this chunk exists

The architecture lockdown requires an ADR before changing a locked auth
boundary. Imported reference files currently conflict with existing role docs
and use `/v1` examples.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
README.md
docs/reference_specs/README.md
docs/decision_0012_workstream_authorization_service.md
docs/architecture_lockdown.md
docs/architecture_system_architecture.md
docs/architecture_data_model.md
docs/operations_roles_permissions.md
docs/roles_permissions.md
docs/glossary.md
docs/roadmap_status.md
docs/operations_authorization_service.md
docs/spec_chunk_2_auth_actor_boundary.md
docs/current_system_data_flow.html
docs/roadmap_implementation_backlog.md
docs/architecture_brief/workstream_architecture_brief.md
docs/architecture_brief/workstream_architecture_brief.pdf
docs/architecture_brief/task_lifecycle_sequence.puml
docs/architecture_brief/images/task_lifecycle_sequence.png
docs/architecture_brief/images/workstream_context.png
docs/architecture_brief/images/workstream_v01_container.png
docs/spec_authorization_service.md
docs/architecture_checker_framework.md
docs/architecture_lifecycle_state_machine.md
docs/operations_operator_workflow.md
docs/operations_project_operating_manual.md
docs/operations_queue_policy.md
docs/product_brief.md
docs/product_first_user_flows.md
docs/template_checker_policy.md
docs/template_project_guide.md
docs/template_prior_feedback_checklist.md
docs/template_revision_replay.md
docs/template_submission_artifact_policy.md
docs/decision_0003_project_guides_are_first_class.md
docs/decision_0009_review_decisions_are_canonical.md
docs/decision_0010_revision_context_rebase.md
docs/decision_0011_submission_artifact_policy_drives_pre_submit.md
docs/operations_payment_reputation.md
docs/operations_reviewer_workflow.md
docs/operations_revision_replay.md
docs/operations_subagent_review_protocol.md
docs/principles.md
docs/product_principles.md
docs/template_preflight_evidence.md
docs/template_review_packet.md
docs/template_submission_packet.md
docs/template_task_status.md
docs/diagrams/*.md
docs/diagrams/workstream_context.puml
docs/diagrams/workstream_v01_container.puml
docs/diagrams/rendered/workstream_context.svg
docs/diagrams/rendered/workstream_v01_container.svg
docs/risk_register.md
docs/spec_*.md
scripts/check_stale_authorization_docs.py
scripts/render_authorization_docs.sh
scripts/test_agent_gates.py
backend/app/adapters/project_agents/openai_agent_sdk.py
backend/tests/test_agent_runtime.py
backend/tests/test_projects.py
.github/workflows/agent-gates.yml
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/CHUNK_MAP.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/chunks/WS-POL-002-03-post-submit-policy-approval-visibility.md
```

The eight exact PlantUML/image paths above are approved companion sources and
generated artifacts for the reconciled active diagrams; they are not a scope
exception.

## Not allowed

```text
backend application code or backend tests beyond the three exact terminology-only
files allowed above; migrations and dependencies
review/contribution/compensation implementation
rewriting payment/reputation architecture beyond recording a later conflict
adding permanent /v1 aliases
the eight imported WS-ARCH/WS-AUTH/WS-CON/WS-IMP/WS-REV Markdown/PDF inputs
docs/reference_specs/SHA256SUMS
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/SOURCE_MANIFEST.md
```

## Acceptance criteria

- An ADR adopts `WS-AUTH-001` and records `/api/v1` as the repository override.
- ADR 0006 remains authoritative for external authentication ownership; the new
  ADR supersedes only token-role and local-profile authorization semantics.
- Explicit human approval of proposed L0 decisions D4-D10 is recorded before
  this chunk becomes active; the chunk does not infer approval from plan review.
- Repository engineering policy assigns external token verification to the
  existing auth adapter/dependency boundary and canonical local permission,
  grant, idempotency, and invalidation ownership to
  `backend/app/modules/authorization`; obsolete
  `backend/app/core/permissions.py` ownership is removed.
- Canonical docs no longer describe token roles or typed ActorProfiles as
  Workstream product authority.
- Every active operational, product-flow, checker-framework, template,
  architecture, decision, diagram, and bounded specification document found by
  the deterministic authority scan is either reconciled in this chunk or
  classified by an explicit reviewed historical/archive allowlist. The scanner
  auto-discovers tracked and untracked active documents outside any hardcoded
  corpus, has known-bad fixtures, and fails if an active authority claim is
  omitted. Only exact reviewed archive/history paths may be allowlisted.
- Agent Gates invokes `python3 scripts/check_stale_authorization_docs.py`
  directly with fail-closed semantics. Regression tests prove the workflow
  retains that step and a newly added active document containing `/v1` or an
  obsolete authority claim fails discovery without editing a scanner corpus.
- The five administrative grants and exact-project contributor grants use
  consistent names.
- Imported Markdown/PDF pairs are reconciled or explicitly labeled so they do
  not silently disagree.
- All eight imported files remain byte-immutable archival planning inputs.
  `docs/reference_specs/README.md` records their hashes/status and the
  `/api/v1` override; canonical reconciled text lives separately in
  `docs/spec_authorization_service.md`.
- `WS-POL-002-03` is recorded as implemented separately in PR #90 without this
  chunk claiming ownership or activating `WS-POL-002-04`.
- Roadmap status names WS-AUTH-001 as current priority, records POL-002 chunks
  01/02 merged and chunk 03 handled separately by PR #90, and defers further
  authorization implementation until auth proof.
- Canonical vocabulary uses Contributor as the umbrella human term. A
  contributor may hold independent exact-project `submitter`, `reviewer`, and
  `adjudicator` grants. Celery, checker, setup, and background workers are
  internal services, not human product roles.
- The project policy derivation prompt and its exact prompt-contract tests use
  Contributor for human submitters. This wording-only repair does not change
  schemas, persisted legacy field names, authorization, or runtime routing.
- Every current operational override/repair command is inventoried and assigned
  a precise registered Project Manager or Operator permission for later chunks;
  any additive permission is approved in the ADR rather than invented in code.
- An authorization operations runbook assigns ownership for issuer/JWKS
  configuration and outages, key rotation, introspection policy, bootstrap
  custody, legacy classification, staged rollout/rollback, alerts, and live
  proof; later chunks fill in executable commands.

## Verification commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/test_agent_gates.py
sha256sum -c docs/reference_specs/SHA256SUMS
PLANTUML_JAR=/path/to/plantuml-1.2026.6.jar scripts/render_authorization_docs.sh
git diff --check
```

Diagram regeneration uses PlantUML `1.2026.6`; evidence records the local JAR
SHA-256 and the regenerated artifact checks.

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- CI integrity
- test delta

## Human review focus

Confirm authority precedence, role names, `/api/v1`, and that no unrelated
review/compensation decisions were adopted accidentally.

## Stop conditions

Stop if the source PDF cannot be regenerated or labeled without ambiguity, or
if reconciling auth requires changing review/compensation behavior.
