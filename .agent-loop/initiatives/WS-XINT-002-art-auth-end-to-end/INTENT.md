# Intent: WS-XINT-002 ART-AUTH End-to-End Contract

## Outcome

Freeze and deliver the complete v0.1 authorization surface required by the
artifact lifecycle so ART implementation does not discover new AUTH catalogue,
principal, matrix, prepared-capability, or evidence dependencies mid-chunk.

## Why now

The existing ART plan defines guide ingestion, contributor ZIP admission,
submission binding, checker materialization, recovery, and later review use in
separate chunks. AUTH currently owns 25 planned ART actions, but the plan still
contains six obsolete upload-session actions, omits three required end-to-end
actions, and its prepared protocol cannot consume ART product resource types.
That makes ART repeatedly stop for newly discovered AUTH work.

## Boundaries

- AUTH owns ActionId/PermissionId registration, mappings, availability,
  fixed-service identities and matrices, authority locking/evaluation, prepared
  handles, and decision evidence.
- ART owns bytes, commitments, manifests, storage/admission facts, lifecycle
  guards, resource-context composition ports, and hidden feature behavior.
- Project, task, submission, checker, and review modules own their domain rows,
  lock order after AUTH authority locking, and lifecycle invariants.
- Registration and reusable runtime support may merge before feature behavior,
  but every new action remains unavailable until its exact hidden behavior and
  crossed-state evidence exist.

## Non-goals

- No ART, REV, task, submission, or checker implementation in this planning
  amendment.
- No action activation, grant broadening, compatibility alias, generic artifact
  download permission, dynamic service grants, or provider access from AUTH.
- No client delivery, marketplace, external adapter, or post-v0.1 surface.

## Proof strategy

Each implementation chunk must prove closed catalogue/database parity, typed
resource composition, least-privilege actor/service admission, transaction-local
single-use consumption, atomic decision evidence, crossed revocation/staleness,
and at least 90 percent coverage for materially changed backend subsystems.
Full-suite coverage remains hosted in GitHub Actions.
