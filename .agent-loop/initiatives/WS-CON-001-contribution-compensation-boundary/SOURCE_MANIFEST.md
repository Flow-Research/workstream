# Source Manifest: WS-CON-001

## Reconciliation baseline

- Reconciled `main`: `9550b3cdb8ac12dea72931277cf46ac1b8ffda7f`.
- Current migration head on `main`: `0054_guide_sufficiency_authority`;
  this branch advances it to `0055_contribution_policy`.
- Current capability ledger: `docs/roadmap_status.md`.
- Current contribution process: `AGENTS.md`, `CONTRIBUTING.md`, and
  `.agent-loop/README.md`. Historical signed-start and merge-intent records are
  context, not current authorization or runtime state.

## Canonical product sources

- `README.md`
- `docs/glossary.md`
- `docs/architecture_lockdown.md`
- `docs/architecture_data_model.md`
- `docs/architecture_lifecycle_state_machine.md`
- `docs/roadmap_status.md`
- `docs/spec_contribution_compensation.md`
- `docs/spec_authorization_service.md`
- `docs/spec_artifact_storage_service.md`
- `docs/decision_0009_review_decisions_are_canonical.md`
- `docs/decision_0010_revision_context_rebase.md`
- `docs/decision_0012_workstream_authorization_service.md`
- `docs/decision_0013_immutable_artifact_storage_boundary.md`
- `docs/decision_0014_external_service_adapter_convention.md`
- `docs/decision_0016_contribution_compensation_boundary.md`

## Current implementation evidence

- `backend/app/modules/authorization/**`: actor/grant/fixed-service/PREP and
  typed REV readiness contracts.
- `backend/app/modules/artifacts/**`: artifact admission, binding, extraction,
  guide sufficiency, and guide read/binding foundations.
- `backend/app/modules/outbox/**` and migration `0029`: shared outbox
  persistence/append only; no dispatcher exists.
- `backend/app/modules/audit/**`: existing shared audit foundation plus the 02C
  branch's typed, flush-only REV/CON lifecycle participant. This branch state
  remains unpublished until PR review and human merge.
- `backend/app/modules/compensation/**` and merged migration `0053` add only the
  adapter-binding schema; no creation/lifecycle service exists.
- Review queue persistence now exists; ReviewLease, Review, and FinalAcceptance
  lifecycle implementation remain absent.

## Current initiative evidence

- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**`
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/**`
- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**`
- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/**`
- `.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/**`
- `.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/**`
- Merged ART PR #249: guide-source v2 cutover and migration `0050`; current ART
  runtime evidence, not CON implementation.
- Merged REV PR #258: current PLAN4 planning refresh; not runtime and does not
  satisfy a runtime gate by itself.

Open-PR check and merge states are intentionally not persisted as durable plan
truth. Re-read them immediately before implementation or publication.

## Reference inputs

| File | Status |
|---|---|
| `docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md` | transcription; not canonical |
| `docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification(2).pdf` | archival input; not runtime authority |
| `docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.pdf` | pre-existing user-owned deletion; deliberately untouched |

The reference inputs preserve design evidence but cannot override merged
repository decisions. Old SHAs and signed-loop projections in historical
planning records describe their time; they are not current-state evidence.
