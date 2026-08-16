# WS-ARCH-001-CP04 Planning PR Trust Bundle

## Intent

Produce bounded executable contracts for ContributionPolicy behavior before any
implementation starts.

## Scope

- Keep CP04 as a planned non-executable coordination parent.
- Add CP04A for the CONTRIBUTIONS public API, hidden read/create/update-draft
  behavior, owner ports, and shared durable operation recovery.
- Add CP04B for hidden publish/retire behavior against locked server-owned graph
  facts and immutable lifecycle evidence.
- Keep all five ContributionPolicy actions unavailable until CP05.
- Reconcile current ARCH, AUTH, CON, handoff, status, and roadmap records.

## Non-goals

No runtime implementation, migration, route, Celery job, AUTH activation,
ProjectGuide mutation, task/assignment/submission behavior, review behavior,
ContributionRecord, CompensationAward, fulfillment, callback, delivery, or
reputation behavior is added.

## Key safety decisions

- Every mutation fences `operation_id` before owner locks or AUTH consumption.
- PROJECTS retains project eligibility; CONTRIBUTIONS retains policy and unit
  truth; COMPENSATION retains adapter-binding truth.
- PREP is opaque, transaction-bound, closed before product mutation, and never
  serialized.
- Publication facts are recomputed from locked server-owned rows.
- Replacement publication preserves old content and frozen downstream lineage,
  with exact prior-version retirement attribution in one immutable event.
- Retirement is terminal; no compatibility resurrection path exists.

## Verification

Deterministic state, wording, Markdown-link, and diff checks pass. All nine
required internal reviewer specialties passed on exact clean planning head
`445944a29107d844c4f4cf6020525c026334375d`. Hosted CI will provide the final
repository-wide exact-head gates for this planning PR.

## Human review focus

Confirm the CP04A/CP04B split, owner boundaries, operation/PREP ordering,
replacement-publication audit semantics, absence of routes and activation, and
the linear `CP04A -> CP04B -> CP05` dependency.

Only an authorized human may merge this planning PR. CP04A implementation must
not begin until this plan merges.
