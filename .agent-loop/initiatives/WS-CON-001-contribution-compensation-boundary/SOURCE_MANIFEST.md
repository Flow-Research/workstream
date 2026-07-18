# Source Manifest: WS-CON-001 Contribution Record And Compensation Boundary

## Reference inputs

| File | SHA-256 | Status |
|---|---|---|
| `docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md` | `cddbe20f4fadf5307f68519347bdd9520ef49b23fb0b92cad24c31fc9b34c640` | Working transcription; not canonical |
| `docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification(2).pdf` | `ce65e208076769f0bafb09779d60ab6f5fc0c596514d4e8f4cc03690c6e6d457` | Revised archival input; not runtime authority |
| `docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.pdf` | `34c4337f27e42a5b0ed5e153fe8ccd492ecede202c2764506a930d109aef66c1` | Original archival input; pre-existing user deletion remains untouched |

## Trusted baseline

- `origin/main` at `053242b90d927ace3fab92eeca72da27a61cecec`, merging
  AUTH-09B PR #143 after reviewed REV PR #128, AUTH-09A, AUTH PR #140, and
  WS-XINT PR #139.
- PR #128 remains planning authority, not Review runtime implementation.
- Runtime AUTH is 74 PermissionIds, 65 ActionIds, ten active, 55 planned.
  AUTH-09B activates only `actor.service.provision`; no CON or task-claim
  ActionId exists, and provisioning grants no service runtime authority.
- PR #140 remains the source for AUTH activation-custody, prepared-protocol,
  revised chunk,
  operations, and verification contracts. It changes no runtime CON behavior,
  registers no CON action, and activates no feature action.
- AUTH-09B provides the controlled human provisioning path for an approved
  closed fixed ServiceIdentity but does not implement AUTH-09E admission or add
  any CON identity/static row.

## Human boundary amendment

- On 2026-07-17 the human fixed the v0.1 shipping path as
  `Review(accept) -> FinalAcceptance -> accepted_submission` and explicitly
  excluded adjudication lifecycle/actions/readiness.
- Merged REV PR #128 now plans FinalAcceptance, exact
  `accepted`/`needs_revision`/`rejected` effects, two ordered CON participant
  operations, and REV-12A lifecycle-control hooks. WS-CON implementation still
  waits for each exact runtime chunk and consumes no sibling-worktree behavior.
- The amendment's `submission_version_id` is normalized to canonical
  `Submission.id` / `submission_id`; current runtime already stores each
  immutable version as a Submission row.
- Merged REV-04 retains `policy_context_ref` as the foreign key to exact locked
  `ReviewPolicy.id` and `recorded_by` as the reviewer ActorProfile field; CON
  consumes those names and REV owns/proves the lineage.
- `docs/review_closure.md`, `docs/review_final_adversarial_review.md`, and
  `docs/review_adversarial_quality_review.md` are historical internal-review
  recommendations, not live lifecycle specifications. Their older “second
  review” or “overturned” proposals cannot delay FinalAcceptance, add a second
  decision, or gate CON readiness. PLAN2 updates active operations/templates
  only and preserves those review records as historical evidence.

## Normative repository sources

- `AGENTS.md`
- `README.md`
- `docs/glossary.md`
- `docs/architecture_lockdown.md`
- `docs/architecture_data_model.md`
- `docs/architecture_lifecycle_state_machine.md`
- `docs/decision_0005_postgres_is_the_record_database.md`
- `docs/decision_0007_async_first_execution.md`
- `docs/decision_0009_review_decisions_are_canonical.md`
- `docs/decision_0010_revision_context_rebase.md`
- `docs/decision_0012_workstream_authorization_service.md`
- `docs/decision_0013_immutable_artifact_storage_boundary.md`
- `docs/decision_0014_external_service_adapter_convention.md`
- `docs/decision_0015_project_contributor_roles_are_independent.md`
- `docs/spec_authorization_service.md`
- `docs/spec_artifact_storage_service.md`
- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md`
- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-PREP-prepared-mutation-protocol.md`
- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-13-task-assignment-cutover.md`
- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-16-evidence-live-proof.md`
- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/CON_INTEGRATION_REVIEW.md`
- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/DECISIONS.md`
- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/PLAN.md`
- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-08-immutable-decision-kernel.md`
- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-10-contribution-integration-hidden-composition.md`
- `.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-12A-joint-lifecycle-release-control.md`
- `.agent-loop/policies/*`

## Normative WS-XINT handoffs

- `WS-XINT-001/REV_CON_HANDOFF.md`: core contribution participant, frozen
  ContributionPolicyVersion, no core ART dependency.
- `WS-XINT-001/AUTH_ROLE_SERVICE_HANDOFF.md`: independent project grants,
  fixed-service static matrix, AUTH-09E admission.
- `WS-XINT-001/AUTH_REV_HANDOFF.md`: complete REV activation-custody and hidden
  behavior choreography.
- `WS-XINT-001/AUTH_ART_HANDOFF.md`: complete 25-action ART custody transfer;
  referenced only, not a core CON dependency.
- `WS-XINT-001/DECISIONS.md`: D1-D13 ownership and transaction rules.

## Runtime observations

- Current code still contains the retired guide-bound economic schema; CON-05A
  and 05B own semantic then physical removal after a human migration decision.
- No ContributionPolicy, ContributionRecord, CompensationAward, fulfillment, or
  WS-CON action runtime exists yet.
- No FinalAcceptance runtime exists yet; merged planning assigns it to REV-04
  and makes that exact schema a prerequisite for CON-03C/07.
- Existing `Submission` is the versioned identity; no new SubmissionVersion is
  required.
- ART preparation from PR #129 is inactive foundation only and does not approve
  optional contribution-evidence projection.
- Sibling worktrees remain discovery evidence only. Merged REV planning is
  authoritative for sequencing but does not satisfy its own runtime gates.

## Adoption note

The reference inputs contain useful invariants but do not override merged
repository decisions. CON-01 writes the active specification after explicit
approval and leaves archival inputs unchanged.
