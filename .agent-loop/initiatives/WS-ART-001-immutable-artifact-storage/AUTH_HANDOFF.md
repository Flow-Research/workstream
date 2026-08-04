# WS-ART-001 Authorization Handoff

> The complete v0.1 dependency inventory and replacement sequencing are owned
> by `../WS-XINT-002-art-auth-end-to-end/`. This handoff remains the historical
> ART-03 through ART-06 baseline and must not be used to invent a missing AUTH
> action or capability during implementation.

ART owns hidden artifact behavior, canonical product resource facts, lifecycle
guards, surface manifests, and feature tests. AUTH owns ActionId/PermissionId
catalogues, service identities, fixed matrices, evaluator integration, grants,
activation custody, and availability.

## 2026-08-02 Reconciliation

XINT-002-01 already registered the one contributor action and removed the six
obsolete upload-session actions. AUTH-04B implementation merged in PR #245;
fixed-service guide binding/read are active, and ART-03C completed the verified
guide-pipeline cutover. Submission actions remain governed by the later split
activation order below.

The remaining AUTH order requires one correction before submission work can go
live: split XINT-06 into `06A` (pre-submit materializer only, after hidden
ART-04B and before XINT-05A) and `06B` (post-submit materializer plus checker
output write/binding, after ART-06A/06B). This prevents contributor preparation
from activating while its mandatory fixed materializer still denies.

## Guide Source Sequence

1. Guide-source ingest and fixed-service binding/read are active through their
   merged AUTH chunks; contributor submission actions remain unavailable.
2. ART-03A implements hidden `artifact.guide_source.ingest` behavior and its
   exact resource/guard/surface manifest.
3. AUTH activates only that exact action through a separately reviewed AUTH
   contract after consuming ART evidence.
4. ART-03B1, 03B2, 03B3A, 03B3B1, 03B3B2, 03B3B3A, 03B3B3B,
   03B3B3C, 03B3B3D, 03B3B4, and 03B4 implement hidden authoritative binding, exact setup
   generation, verified materialization, bounded extraction, and Celery
   sufficiency continuation. `artifact.guide_source.binding.create` maps to
   fixed permission `artifact.binding.create`; `artifact.guide_source.read`
   remains separate.
5. AUTH-04B activates only those exact fixed-service actions after consuming
   the complete split-03B evidence. Extraction does not imply a provider-write
   permission or inherit Project Manager authority.
6. ART-03C performs the legacy clean cut. No ART chunk writes availability.

### Exact AUTH-04B Activation Manifest

AUTH-04B may activate only these two existing planned actions after every
split-03B merge is present:

- `artifact.guide_source.binding.create`, mapped only to existing permission
  `artifact.binding.create` and fixed service identity
  `workstream.artifact.binding`. Its transaction-bound facts are exactly:
  `project_id`, `guide_id`, `guide_source_snapshot_id`,
  `guide_source_item_id`, `project_setup_run_id`, `setup_generation`,
  `content_id`, `verified_replica_id`, `sha256`, `byte_count`, and the fixed
  `logical_role=guide_source_original`.
- `artifact.guide_source.read`, mapped only to its existing read permission and
  fixed service identity `workstream.artifact.guide_reader`. Its fresh
  transaction-bound facts are exactly: `project_id`, `guide_id`,
  `guide_source_snapshot_id`, `guide_source_item_id`, `project_setup_run_id`,
  `setup_generation`, `binding_id`, `content_id`, `verified_replica_id`,
  `storage_namespace_id`, `namespace_fingerprint`, `verification_receipt_id`,
  `verification_generation`, `sha256`, `byte_count`, and `media_type`.

Both consumers lock and revalidate the draft guide, latest snapshot, exact
source item, current setup run/generation, verified content, replica, and
receipt lineage before consuming the opaque prepared handle and before any
protected mutation or provider read. Prepared handles are process-local,
single-use, action/session/transaction/resource bound, and never enter Celery.
Wrong service, action, session, transaction, generation, project, guide,
snapshot, item, binding, content, replica, receipt, digest, size, media type,
replay, copied handle, replacement, or stale lineage denies before provider I/O
or mutation.

ART-03B4 adds no new AUTH action. The sufficiency continuation receives only
project, guide, snapshot, setup-run, and setup-generation identifiers, reloads canonical
rows, and consumes only complete policy-current extraction usages. Both actions
must remain planned and unavailable until AUTH-04B merges. They are never
granted to a Project Manager, never inherit uploader authority, and do not
create generic artifact-download authority.

## Submission Bundle Sequence

XINT-002-01 has already merged the registration contract that:

- registers planned ActionId `artifact.submission_bundle.prepare`;
- maps it only to existing human PermissionId `submission.create`;
- limits candidates to the assigned contributor for the exact task/project;
- names ART-owned canonical facts for actor, identity link, project, task,
  active assignment, locked policy context, and operation generation;
- keeps the action unavailable and adds no grant or evaluator activation;
- records parity evidence in AUTH's closed catalogue/constraint/owner manifests;
- deletes the unused planned multi-step upload authority from the live closed
  catalogue, constraints, and service matrix without compatibility aliases.

The retired identifiers may remain only in
immutable historical records and the deterministic deletion proof. They are
not an active design, grant, route, compatibility alias, or permission to
implement a second intake path.

ART-04A1 through 04C2 then implement one hidden continuous surface and publish
its exact route/resource/guard manifest. After 04C, a separate reviewed AUTH
activation contract may integrate the evaluator and change only
`artifact.submission_bundle.prepare` to active. ART-05 cannot start until that
activation merges. Before XINT-05A, XINT-06A must separately activate the fixed
pre-submit materializer required by the locked-guide checker boundary.

The preparation surface authorizes before scratch intake, but the initial
decision cannot authorize the later durable mutation. Immediately before
capacity reservation and `ArtifactPutAttempt` creation, 04C must consume an
AUTH-owned transaction-local prepared capability whose canonical facts cover
the current actor, exact identity link, project authority, assignment, task,
predecessor, locked task/guide/policy context, action availability, and
operation generation. AUTH and the owning product services reload/lock their
own facts; ART receives only the typed capability and never imports AUTH-owned
repositories. Authorization evidence, capacity reservation, and durable put
intent commit atomically before provider I/O.

ART-05 requires a new human authorization decision for `submission.create` and
a separately prepared fixed-service capability for
ActionId `artifact.submission.binding.create`, mapped to PermissionId
`artifact.binding.create`. Both are consumed in the one transaction that locks
the ready admission and TASK-owned context, creates Submission and binding,
and marks the admission consumed. Human authority implies no service authority.
Revocation after durable put intent does not cancel verification/recovery, but
the resulting admission remains unbound until a fresh 05 decision succeeds.
Authorization denial precedes admission-detail errors so unrelated actors
cannot distinguish missing, ready, stale, or consumed admissions.

The continuous contributor action never implies the fixed service actions:

- `artifact.pre_submit.checker_input.materialize` and
  `artifact.post_submit.checker_input.materialize`, both mapped to PermissionId
  `artifact.checker_input.materialize`;
- `artifact.verification.execute`;
- `artifact.pending_work.scan`;
- `artifact.put_attempt.resolve`;
- `artifact.submission.binding.create`, mapped to PermissionId
  `artifact.binding.create`.

Each fixed service action retains its canonical provisioned service identity,
matrix row, resource facts, terminal reauthorization, and separate activation
evidence. No human grant supplies fixed service authority.

## Fail-Closed Rule

An ART implementation contract stops if its required AUTH registration or
activation contract is absent, unmerged, inactive, differently mapped, or
targets a different resource fact shape. Planned catalogue presence, a local
action string, or hidden feature code is never executable authority.

Any dependency not enumerated by WS-XINT-002 is contract drift. Stop and amend
the cross-initiative plan; do not add a local action string, permission alias,
service identity, matrix row, or alternate prepared-capability path.
`WS-XINT-002-01` must delete all six obsolete upload-session ActionIds and
PermissionIds, plus scheduler expiry membership, with no unavailable retained
row or compatibility alias; its enumerated deletion list is authoritative.
