# Status: WS-REV-001 Review And Revision Lifecycle

## Current status

`WS-REV-001-01` merged through PR #145 at trusted main
`b2b9016d5fee33ddca40882c97620a178d8e52f0`. The user explicitly started
parent `WS-REV-001-02` on 2026-07-18. Required L1 plan review failed the
combined implementation boundary and required a 02A/02B/02C split before any
runtime or migration edit.

REV may continue planning and test design only. AUTH currently owns migration
`0026` for AUTH-09D-A profile lifecycle. After AUTH-09D-A merges, AUTH owns the
next-priority, separately reviewed contributor-field foundation from the
then-current migration head. That foundation must clean-cut both retired
task-subsystem contributor-identity fields to `contributor_id`, preserve
existing behavior, establish
database-backed canonical-human ActorProfile lineage, and provide an exact
merged PR/SHA. REV runtime remains blocked until that merge.

The parent 02 contract is now non-executable. Planning defines 02A guide
activation chronology/publication locking, 02B immutable policy and dormant
task/assignment lifecycle compatibility, and 02C Submission
attribution/context/lineage. No backend model, service, migration, or persistence
test has changed.

Planning candidate `0292825a52f884f42d82e1522637f2ff2bf4bb7a` passed the
repaired circuit breaker, all required internal reviewer tracks, mandatory
contract scanners, Markdown links, 87 agent gates, and schema-v2 merge-intent
validation. It is planning-publication ready, not runtime-ready.

## Chunk 01 merge history

While Chunk 01 was under review, CON planning PR #142 merged to main at
`a947b8693a97bdb94c9dc63202a51e197834d613`. The branch pulled that merge and
reconciled its shared active documents. PR #142 changes planning/contracts only;
no CON runtime behavior became active.

AUTH-09B PR #143 then merged to main at
`053242b90d927ace3fab92eeca72da27a61cecec`. The branch pulled it cleanly;
only the shared agent-gate test file overlapped. AUTH-09B activates controlled
`actor.service.provision`, not service admission or any REV action.

CON-01 PR #144 then merged to main at
`e118e33afcd89b8ee78ecfc8f0e0d585ae0ee4b9`. The branch reconciled its
`architecture_data_model.md` overlap by retaining the exact shared
FinalAcceptance fields and ActorProfile/ReviewPolicy lineage. CON-01 publishes
the active CON contract and ADR 0016 but changes no runtime.

ART-02A3 PR #141 then merged to main at
`a10d9018007d2e847b4870e9b26cbd24e24c7bb4`. It atomically removes
ArtifactStore v1 and activates the byte-only ART v2 LocalStorage clean cut plus
typed product capability composition. It does not implement S3/MinIO,
submission/checker artifact cutovers, lease-scoped review packet reads, or
review-evidence candidate/finalize behavior.

AUTH-09C PR #146 then merged to main at
`0ffdabf3dbb77e4e066683fde1a095d744ff1f43`. The sole REV conflict was in the
shared agent-gate lifecycle assertions. The resolution retains REV's
branch-sensitive ART proof while adopting main's merged ART-02A3 and AUTH-09C
state. AUTH-09C activates only two bounded actor-registry reads and no REV
action.

Chunk 01 adopts `docs/spec_review_lifecycle.md` as the active normative
contract, preserves the supplied WS-REV and WS-IMP archival Markdown/PDF bytes,
reconciles active documentation, and adds a fail-closed stale review-contract
gate. It changes no backend, migration, AUTH, ART, or CON runtime code.

## Dependency state

- AUTH-08 remains the historical 74-PermissionId, 57-ActionId snapshot: 9
  active and 48 planned. Current trusted main after AUTH-09C has 74
  PermissionIds and 65 ActionIds: 12 active and 53 planned.
- All 24 REV lifecycle action dependencies remain unavailable: planned
  `submission.create`, 19 planned review actions, and four approved but
  unregistered REV additions. The separately proposed ART evidence-binding
  service action is not included in those 24.
- AUTH owns registration, service identity admission, evaluator integration,
  activation, and prepared-mutation authority. REV publishes immutable feature
  manifests and hidden behavior evidence; it does not activate actions.
- Merged AUTH-09B supplies controlled provisioning only for identities already
  in AUTH's closed registry. None of REV's six identities exists yet; their
  exact extensions, provisioning, AUTH-09E admission, and feature activation
  remain downstream gates.
- Merged AUTH-09C supplies only bounded system-authorized actor-profile and
  identity-link reads. It adds no REV identity or action and changes none of
  REV's lifecycle, lease, artifact, or contribution boundaries.
- Merged ART-02A3 supplies the active byte-only ART v2 store beneath typed
  product capabilities. Review still consumes only later approved packet-read
  and evidence candidate/finalize ports; it never imports the raw byte store,
  ART scratch/source types, a concrete provider, or repository APIs.
- Merged CON-01 publishes the canonical frozen-policy, ContributionRecord,
  FinalAcceptance trigger, award, and ordered two-operation participant
  contracts. It implements none of them.
- Later CON chunks must provide frozen contribution-policy persistence and the
  ordered flush-only participant before a canonical Review can commit. Every
  valid Review creates reviewer contribution; only an accept-created
  FinalAcceptance creates submitter contribution.
- AUTH-09D-A is in progress and owns migration `0026`. No AUTH contributor
  foundation PR/SHA or migration exists on this REV base. REV assigns no
  migration number and performs no runtime preparation against retired
  contributor-identity storage.
- After AUTH-09D-A, AUTH must merge the bounded contributor-field foundation.
  ART submission commitment/packet-read contracts, CON
  persistence/participant contracts, and the remaining per-child gates stay
  external prerequisites exactly as listed in `CHUNK_MAP.md`.
- Two product values remain human-owned before 02B implementation:
  `review_preference_window_seconds` and
  `review_lease_duration_seconds`. Neither is inferred from `sla_hours`.

## Canonical lifecycle boundary

- Every valid reviewer decision appends an immutable Review. Submitted findings
  and later finding resolutions are also immutable history.
- `accept` additionally creates one internal immutable FinalAcceptance. The
  submitter `accepted_submission` contribution consumes that fact rather than
  inferring acceptance from `Review.decision`.
- `needs_revision` prepares a controlled next-attempt context. An exact match
  with the currently active Project Guide identity and activation sequence keeps
  context; any different internally consistent active pair rebases forward or
  backward; missing or inconsistent active context blocks preparation.
- The reviewer always uses the Project Guide context stamped on the exact leased
  Submission and never performs a separate review-guide rebase.
- `reject` blocks the submitter assignment and sets the Task to `rejected`.
  Approved administrative revision-obligation closure uses `cancelled` with a
  bounded reason.
- Adjudication remains disabled and unimplemented in v0.1. Reputation mutation
  is deferred to its owning future initiative. Interfaces retain typed lineage
  so either can be added later without changing the immutable Review contract.

## Chunk 01 evidence state

Candidate `6da45b2765de68dc5a0628024bdfeacb98d1ea85` passed all nine required
tracks against trusted current main
`053242b90d927ace3fab92eeca72da27a61cecec`: senior engineering, QA/test,
security/auth, product/ops, architecture, docs, reuse/dedup, test delta, and CI
integrity. All 80 current-main agent tests and seven REV additions are retained;
87 agent-gate tests and the deterministic contract gates pass.

Chunk 01 was published and merged as PR #145. CodeRabbit's nine actionable findings and one
Markdown lint nit were repaired without runtime or successor-scope expansion.
After ART-02A3 PR #141 advanced main, the branch merged and reconciled its
active byte-only v2 LocalStorage clean cut while retaining every later
review-facing ART gate. Candidate
`e239282e7d2a2b4d46137707f673f76fda55e4b8` passed the plan gate and all nine
internal reviewer tracks against
`0ffdabf3dbb77e4e066683fde1a095d744ff1f43`; 87 agent gates, Ruff, scanners,
links, checksums, renderer checks, merge-intent validation, and the exact
71-entry A/M reviewed-scope comparison passed. Status-change, removal,
rename-as-D+A, and addition probes failed closed. This chunk activated no review
action or endpoint.

## Stop condition

Complete parent-02 planning review only. Do not edit backend runtime, migration,
or persistence tests. After the exact AUTH contributor-foundation merge and
human approval of the planning split, 02A still requires a separate explicit
start. The duration defaults gate 02B. No child starts its successor
automatically.
