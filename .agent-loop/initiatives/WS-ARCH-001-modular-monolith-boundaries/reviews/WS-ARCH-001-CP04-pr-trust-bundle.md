# WS-ARCH-001-CP04 Planning PR Trust Bundle

## Chunk

`WS-ARCH-001-CP04` planning split into executable future contracts CP04A and
CP04B.

## Goal

Produce bounded executable contracts for ContributionPolicy behavior before any
implementation starts.

## Human-approved intent

Establish only the minimum ContributionPolicy foundation needed before returning
to task readiness and canonical `allow_review`; do not implement the wider CON
lifecycle in this initiative.

## Scope

- Keep CP04 as a planned non-executable coordination parent.
- Add CP04A for the CONTRIBUTIONS public API, hidden read/create/update-draft
  behavior, owner ports, and shared durable operation recovery.
- Add CP04B for hidden publish/retire behavior against locked server-owned graph
  facts and immutable lifecycle evidence.
- Keep all five ContributionPolicy actions unavailable until CP05.
- Reconcile current ARCH, AUTH, CON, handoff, status, and roadmap records.

## What changed

CP04A now owns hidden policy read/create/update-draft behavior and shared
operation recovery. CP04B owns irreversible publish/retire behavior. Both
contracts name exact owner boundaries, transaction ordering, acceptance tests,
and hosted-only PostgreSQL/concurrency proof.

## Why it changed

The former single CP04 skeleton mixed editable draft behavior with irreversible
publication. The split bounds review and implementation risk while retaining one
linear path to CP05 activation.

## Design chosen

`CP04A -> CP04B -> CP05`, with PROJECTS retaining project eligibility,
CONTRIBUTIONS retaining policy/unit truth, COMPENSATION retaining binding truth,
and opaque AUTH PREP consumed before product mutation.

## Alternatives rejected

- One combined implementation PR: too broad across editable and irreversible behavior.
- Caller-supplied publication truth: unsafe against stale or forged economic facts.
- Private cross-module imports or a second AUTH protocol: violates the modular boundary.

## Non-goals

No runtime implementation, migration, route, Celery job, AUTH activation,
ProjectGuide mutation, task/assignment/submission behavior, review behavior,
ContributionRecord, CompensationAward, fulfillment, callback, delivery, or
reputation behavior is added.

## Product behavior

None becomes live in this planning PR. All five policy actions remain
unavailable and no route or worker is added.

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

## Acceptance criteria proof

The CP04A and CP04B contracts include criterion-to-test matrices for PREP
atomicity, concealed recovery, route absence, concurrency, immutable events,
cross-project publish/retire denial without lifecycle or AUTH side effects,
replacement publication, and terminal retirement. PostgreSQL-only proof is
explicitly assigned to hosted semantic lanes while named focused denial tests
remain runnable locally.

## Tests/checks run

Deterministic state, wording, Markdown-link, and diff checks are required on the
final head. Hosted CI owns the repository-wide exact-head gates.

## Test delta

Planning only; no runtime tests are added yet. The future test inventory is
explicit in both executable contracts, with one primary behavior per test and
no new file reaching 500 lines.

## CI integrity

No CI workflow or threshold is weakened. Full hosted lanes and aggregate
coverage remain mandatory.

## Reviewer results

The earlier nine-reviewer result at `445944a29107d844c4f4cf6020525c026334375d`
is historical because main was merged afterward. Fresh exact-head results must
be mirrored in the PR body after all upgraded reviewers complete; this committed
bundle does not claim current reviewer approval.

## External review

Fresh substantive review of PR head `769e15e0c6d947d471e626a2362c8adfdf9df53f`
found stale review evidence and missing acceptance-to-test mappings. A later
review found the missing CP04B cross-project proof mapping, and CodeRabbit found
the publication-order summary drift. All four findings were replayed as valid
and addressed in the contract, discovery record, and external-review response.
CodeRabbit substantive final-head review remains unavailable unless it reviews
the resulting final head.

## Remaining risks

Future implementation must prove the named PostgreSQL races and direct-SQL
guards; planning text alone is not runtime evidence.

## Follow-up work

After human merge, implement CP04A only. CP04B follows after CP04A merges; CP05
alone activates the five actions.

## Human review focus

Confirm the CP04A/CP04B split, owner boundaries, operation/PREP ordering,
replacement-publication audit semantics, absence of routes and activation, and
the linear `CP04A -> CP04B -> CP05` dependency.

## Human merge ownership

Only an authorized human may merge this planning PR. CP04A implementation must
not begin until this plan merges.
