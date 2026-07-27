# WS-ART-001 Authorization Handoff

> The complete v0.1 dependency inventory and replacement sequencing are owned
> by `../WS-XINT-002-art-auth-end-to-end/`. This handoff remains the historical
> ART-03 through ART-06 baseline and must not be used to invent a missing AUTH
> action or capability during implementation.

ART owns hidden artifact behavior, canonical product resource facts, lifecycle
guards, surface manifests, and feature tests. AUTH owns ActionId/PermissionId
catalogues, service identities, fixed matrices, evaluator integration, grants,
activation custody, and availability.

## Guide Source Sequence

1. Existing guide-source actions remain planned and unavailable.
2. ART-03A implements hidden `artifact.guide_source.ingest` behavior and its
   exact resource/guard/surface manifest.
3. AUTH activates only that exact action through a separately reviewed AUTH
   contract after consuming ART evidence.
4. ART-03B implements hidden `artifact.guide_source.read` and
   `artifact.guide_source.binding.create` behavior; binding maps to fixed
   permission `artifact.binding.create`.
5. AUTH activates only those exact actions after consuming 03B evidence.
6. ART-03C performs the legacy clean cut. No ART chunk writes availability.

## Submission Bundle Sequence

Before ART-04A starts, AUTH must merge a separately reviewed registration
contract, provisionally named
`WS-AUTH-001-ART-SUBMISSION-BUNDLE-REGISTRATION`, that:

- registers planned ActionId `artifact.submission_bundle.prepare`;
- maps it only to existing human PermissionId `submission.create`;
- limits candidates to the assigned contributor for the exact task/project;
- names ART-owned canonical facts for actor, identity link, project, task,
  active assignment, locked policy context, and operation generation;
- keeps the action unavailable and adds no grant or evaluator activation;
- records parity evidence in AUTH's closed catalogue/constraint/owner manifests;
- explicitly retires the unused planned multi-step upload-session ActionIds or
  proves they are unavailable and have no route/command manifest entry.

Until that AUTH contract merges, current agent-gate catalogue assertions retain
those strings only as an exact planned/unavailable discovery baseline. Their
presence in the closed catalogue is not an active design, grant, route, or
permission to implement a second intake path, and PLAN2 does not edit AUTH-owned
catalogue or parity assertions.

ART-04A through 04C then implement one hidden continuous surface and publish
its exact route/resource/guard manifest. After 04C, a separate reviewed AUTH
activation contract may integrate the evaluator and change only
`artifact.submission_bundle.prepare` to active. ART-05 cannot start until that
activation merges.

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
