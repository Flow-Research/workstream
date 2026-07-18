# Source Manifest: WS-REV-001 Review And Revision Lifecycle

## Primary revised input under review

| File | SHA-256 | Status |
|---|---|---|
| `docs/reference_specs/WS-REV-001-review-lifecycle-specification.md` | `fffadc271c267801250b044edc570e515a250eff48afdc64f9c1f8753e6ab058` | Canonical revised archival input; includes Markdown-only section 4.6 action mapping; adopted through the reconciled active contract without editing this file |
| `docs/reference_specs/WS-REV-001-review-lifecycle-specification.pdf` | `8c053bc752a7b0c64e04b3eda1873bb5dbc02bbdfef84bd17d07cbbf01bce2fd` | Canonical revised archival companion; does not contain Markdown section 4.6 and is not a generated twin |

## Normative repository constraints

- `AGENTS.md`
- `docs/architecture_lockdown.md`
- `docs/decision_0009_review_decisions_are_canonical.md`
- `docs/decision_0010_revision_context_rebase.md`
- `docs/decision_0012_workstream_authorization_service.md`
- `docs/decision_0013_immutable_artifact_storage_boundary.md`
- `docs/decision_0014_external_service_adapter_convention.md`
- `docs/decision_0015_project_contributor_roles_are_independent.md`
- `.agent-loop/policies/repository-engineering-policy.md`

## Merged cross-initiative authority

WS-XINT-001 PR #139 merged to trusted main
`5d353b6d3f8a36b9b9ffdc1959487a150ac25fd1` from reviewed head
`f315ffacf09db433af54e84f081c5425167d0a9a`. REV adopts:

- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/PLAN.md`
- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/DECISIONS.md`
- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_REV_HANDOFF.md`
- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/AUTH_ROLE_SERVICE_HANDOFF.md`
- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/ART_REV_HANDOFF.md`
- `.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/REV_CON_HANDOFF.md`

## Later human-approved boundary amendment

On 2026-07-17 the human explicitly amended the merged REV/CON handoff for v0.1:

- every valid reviewer decision, submitted finding, and later resolution is
  immutable; later rounds append new history;
- `Review(accept)` additionally creates one immutable REV-owned
  `FinalAcceptance`;
- submitter `accepted_submission` consumes FinalAcceptance rather than inferring
  acceptance directly from `Review.decision`;
- REV owns lifecycle orchestration inside the caller transaction; one CON participant first creates the
  reviewer contribution and evaluates the reviewer policy; REV applies the
  decision branch; the CON submitter operation runs only after FinalAcceptance
  exists for `accept`; REV stages shared audit and outbox rows; and the request
  route or service command owns the caller `AsyncSession` and commits once; and
- adjudication remains disabled and unimplemented in v0.1 while existing
  boundary/interface compatibility is retained for separately approved future
  work.

This explicit amendment supersedes conflicting contribution-trigger and
audit/outbox-staging wording in the original merged handoff. The merged handoff
already records this boundary; this planning PR does not edit it. Corresponding
CON runtime changes must still merge before any REV consumer starts.

## Merged AUTH reconciliation authority

AUTH reconciliation PR #140 merged to trusted main
`d541521790a0441cfd2193f466e00ef81248ec31` from final branch head
`b80e89837d5204bb2ba59bb1ee0cbc3fe59b1ad5`. It makes the XINT boundary concrete
in AUTH planning through:

- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md`;
- `WS-AUTH-001-REV-CUSTODY` for the availability-neutral 19-row custody transfer;
- `WS-AUTH-001-PREP` for the opaque, single-use prepared mutation handle;
- `WS-AUTH-001-REV-REG` for the four approved but unregistered REV actions;
- `WS-AUTH-001-REV-05/06/07/08/09A/11/12` for exact feature-gated activation; and
- `WS-AUTH-001-REV-LIFECYCLE` for the four additive lifecycle actions.

PR #140 changes planning and authorization documentation only. Its runtime
snapshot was 74 PermissionIds and 57 ActionIds, with 9 active and 48 planned;
none of the 24 REV lifecycle dependencies was active.

AUTH-09A PR #132 then merged to its trusted main
`299363af5d9e8a68bcc9b17457188048483caeed` from reviewed code
`fe61df64fbf82a1f6871c380e6fc1986a4f12205` and final branch head
`d4b65400d35c1036f8d6f15bb81fe5e0b81f10be`. It advances the migration head to
`0023`, adds the common fixed-service schema and seven ART identities with
eleven exact memberships, and registers eight planned AUTH-09 route actions.
The AUTH-09A catalogue was therefore 74 PermissionIds and 65 ActionIds: 9 active
and 56 planned. It provisions no actor, admits no service token, and does not
add any of REV's six identities. Later gates derive counts from then-current
trusted main, and the separate ART evidence-binding proposal is not counted
among the 24 REV dependencies.

AUTH-09B PR #143 later merged to then-current trusted main
`053242b90d927ace3fab92eeca72da27a61cecec` from final branch head
`9ee5646`. It activates only `actor.service.provision`, producing 74
PermissionIds and 65 ActionIds split into 10 active and 55 planned. The
controlled route may provision only identities already present in AUTH's closed
registry. It adds none of REV's six identities, admits no service token, and
activates no review action; all 24 REV dependencies remain unavailable.

AUTH-09C PR #146 later merged as an ancestor of current trusted main
`0ffdabf3dbb77e4e066683fde1a095d744ff1f43` from final branch head
`a3d6babc`. It keeps 74 PermissionIds and 65 ActionIds while activating only
`actor.profile.read` and `actor.identity_link.read`, moving the split to 12
active and 53 planned. It adds no REV identity or action, and all 24 REV
dependencies remain unavailable.

## Dependency specifications and plans

- `docs/reference_specs/WS-AUTH-001-actor-profile-role-and-authorization-service-specification.md`
- `docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.pdf`
- `docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md`
- `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/`
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/`

## Merged CON planning authority

WS-CON-001 planning PR #142 merged as an ancestor of current main
`a947b8693a97bdb94c9dc63202a51e197834d613` from final branch head
`4b13c3ee28ecddd7c92be70ad2059c130604f9d1`. Its PLAN3 reconciliation is now
the repository-owned CON planning authority. It confirms:

- one reviewer `completed_review` operation before the REV decision branch;
- one accept-only `accepted_submission` operation after REV creates
  FinalAcceptance and applies accepted task/assignment effects;
- operation-specific typed inputs rather than one nullable omnibus request;
- one REV-owned caller transaction and no ART call or mandatory evidence
  projection in the core decision path; and
- no adjudication dependency.

PR #142 changes planning and shared active documentation only. Its CON runtime
chunks remain proposed/inactive and continue to gate REV implementation.

## Merged CON canonical contract

CON-01 PR #144 later merged as an ancestor of current trusted main
`e118e33afcd89b8ee78ecfc8f0e0d585ae0ee4b9`. It publishes
`docs/spec_contribution_compensation.md` and ADR 0016 as repository-owned CON
authority. It preserves the ordered reviewer and accept-only submitter
operations, FinalAcceptance-only submitter trigger, frozen-policy rules,
REV-owned sole commit, and no-ART core transaction. CON-01 changes no runtime,
migration, AUTH/ART/REV-owned contract, or archival reference input. Its later
implementation chunks still own policy persistence, ContributionRecord,
CompensationAward, the flush-only participant, and fulfillment behavior.

AUTH-07A/07B discovery was refreshed against merged AUTH-08 PR #131 at
trusted-main `aa0fdcd6912e66609e39a2fbd7b65f67be6c62f3`, whose final branch head is
`0832358a0262805f553d05b50b0d778e6e6ad995`. AUTH-08 retains the minimal
deny-by-default kernel, adds seven active administrative actions, and establishes
exactly 57 ActionIds: 9 active and 48 planned. All 20 existing revised-spec
submission/review actions stay planned. The four additive REV actions require
separate AUTH registration and later activation contracts. The 57 count is a
historical snapshot, not a future fixed total: WS-XINT-001 also proposes the
separate ART service action `artifact.review_evidence.binding.create`. Every
gate derives exact counts from current trusted main and inventories both deltas.
REV chunks never activate actions. AUTH-08 also provides the required transaction teardown,
decision-evidence `503`, and canonical verification-timestamp repairs. Later
AUTH registration, evaluator, service-admission, and activation chunks remain
independent runtime gates before their corresponding REV behavior is released.

ART discovery was refreshed against merged ART-02A2 PR #129 at trusted-main
`9a04434e2f23c5dec8939dadb943bba4d85110c0`, final branch head
`32aab89262a3944f305e9e5dc4c65a2d31e2e144`. That chunk adds only
committed-source/private-scratch preparation. ART discovery was then refreshed
against merged ART-02A3 PR #141 at trusted main
`a10d9018007d2e847b4870e9b26cbd24e24c7bb4`, final branch head
`7606798e751abf40218d23886779c3659b76e974`. ART-02A3 removes v1 and activates
the byte-only v2 LocalStorage store, namespace fence, and typed product
capability composition. REV consumes none of the scratch/source types or raw
store methods. S3/MinIO, submission/checker binding cutovers, packet read,
review-evidence candidate/finalize, projection, and live-proof contracts,
including a separately approved `WS-ART-001-REV-EVIDENCE` owner chunk, remain
dependency gates.

The merged ART plan also leaves the narrow active-lease packet-read port and
server-derived `Submission.artifact_hash` field unassigned to an approved chunk.
REV-07/10 require exact merged ART/task-owner amendments for those capabilities;
existing artifact-set context is not treated as either contract.

## Historical cross-worktree discovery evidence

The following sibling planning paths were read-only discovery inputs on
2026-07-15, pinned for this review to rebased CON planning head `c965f9b`. They are
not runtime dependencies by path and no file in that worktree was edited by
WS-REV:

- `/home/abiorh/flow/workstream-con-001/.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/`
- `/home/abiorh/flow/workstream-con-001/.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/JOINT_RELEASE_HANDOFF.md`
- `/home/abiorh/flow/workstream-con-001/docs/reference_specs/WS-CON-001-contribution-record-and-compensation-boundary-specification.md`

These paths are dated discovery only. Merged WS-XINT `REV_CON_HANDOFF.md` and
merged CON PR #142 supersede their conflicting mandatory evidence-projection,
policy naming, activation, and core ART-dependency assumptions. Owning WS-CON
runtime contracts must still merge before a REV gate consumes them.

## Adoption note

The revised supplied WS-REV pair now occupies the canonical filenames and its
hashes are recorded in `docs/reference_specs/README.md` and
`docs/reference_specs/SHA256SUMS`; no duplicate `(2)` path remains. The Markdown
is newer than the PDF because its section 4.6 closed action table is absent from
PDF text extraction. Chunk 01 preserves and hashes both canonical files
unchanged, records their provenance/status differences, and creates
`docs/spec_review_lifecycle.md` as the reconciled active normative contract.
Neither WS-REV archival file nor either WS-IMP archival file is edited to
express active repository policy.

## Chunk 01 adoption base

Planning merged through PR #128 at trusted main
`0302bcf854a565d429e232ad6b076a1931ea74e4`. The user explicitly started
`WS-REV-001-01` from that exact commit. Chunk 01 makes
`docs/spec_review_lifecycle.md` the active normative contract while the four
archival files remain literal-hash and trusted-base-diff protected inputs.

## Parent 02 merge and planning-refresh base

Parent `WS-REV-001-02` merged through PR #147 at trusted main
`f18b620932bb257dc1dc355bc0504271813dc6b1`. It is a non-executable split
record. `WS-REV-001-PLAN2` refreshes planning/specification only from that
base and was rebased after AUTH-09D-A merged.

AUTH-09D-A merged through PR #148 at trusted main
`99ae4c963e53f317175dcb308b9e47c93ccf19ed` from reviewed branch head
`9c5ef8a1feffd6324acfd947e67042921955320b`. Its exact migration
`0026_actor_profile_lifecycle`, ActorProfile lifecycle fields/constraints,
direct-SQL history guards, service behavior, and tests are merged authority.

The following are explicitly unmerged discovery evidence and not authority:

- the human-directed but unnamed AUTH contributor/canonical-human foundation;
- any unmerged CON outbox work that still claims the now-consumed `0026` number.

Trusted main has the single head `0026_actor_profile_lifecycle`, retains both
retired task contributor storage names, and contains no merged contributor
foundation.
Current Submission storage also has no immutable causal field for the exact
needs-revision CheckerRun that admits a corrected checker-remediation N+1. 02C
owns the planned server-derived `remediation_source_checker_run_id`, exact
backfill, PostgreSQL lineage/uniqueness/immutability, and currentness locking;
09A4 later adds the human preparation binding and final source XOR. AUTH-14 must
own only public request acknowledgement, authorization cutover, and activation
for that path after an exact contract amendment, not these REV lifecycle
columns or constraints.
Every runtime gate must replace worktree prose with exact owner chunk ID,
merged PR/SHA, migration head, typed symbol/manifest, and tests.

The active contract, its four-action registration manifest, and its six-service
identity manifest become immutable inputs for downstream AUTH gates only after
this chunk is reviewed and merged. Until their owning chunks and AUTH activation
gates complete, every review-lifecycle action and endpoint remains unavailable.

After the initial exact-SHA review, the branch pulled merged CON PR #142 at
`a947b8693a97bdb94c9dc63202a51e197834d613`. The original `0302bcf` start and
archive-integrity proofs remain fixed. The branch then pulled merged AUTH-09B
PR #143 at `053242b90d927ace3fab92eeca72da27a61cecec` and merged CON-01 PR
#144 at `e118e33afcd89b8ee78ecfc8f0e0d585ae0ee4b9`; final PR scope and
exact-SHA review use the newest merged-main boundary. The branch then rebased
cleanly onto merged AUTH-09D-A PR #148 at
`99ae4c963e53f317175dcb308b9e47c93ccf19ed`; the post-rebase review base is
that trusted commit.
