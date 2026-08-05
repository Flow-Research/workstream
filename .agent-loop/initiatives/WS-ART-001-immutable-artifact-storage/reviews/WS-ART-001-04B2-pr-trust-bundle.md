# WS-ART-001-04B2 PR Trust Bundle

## Chunk

`WS-ART-001-04B2` — default checker execution.

## Goal

Materialize one prepared contributor ZIP only after fixed-service authority,
project its exact 04A semantic manifest into bounded private scratch, and run
only the ordered Workstream platform/default pre-submission slice.

## Human-approved intent

Workstream owns the generic default pre-submission checks. Project-specific
rules remain a later phase of the same effective plan and do not execute in
this chunk. Production authority remains planned and unavailable.

## What changed

- Added the hidden authorized materialization service and exact AUTH facts.
- Added quota-charged canonical ZIP projection with fixed executable semantics.
- Added a callback-scoped capability containing immutable verified bytes and
  manifest facts, revoked before scratch cleanup completes.
- Added platform/default dispatch with bounded path-redacted results.
- Shared attestation and quality predicates with the existing checker path.
- Added scratch workspace byte/entry accounting and crash-cleanup compatibility.
- Added focused failure/concurrency tests, semantic lane ownership, coverage
  reports, and canonical documentation.

## Why it changed

04B1 locked what must run. 04B2 supplies the hidden execution boundary needed
before project-policy execution and durable evidence can be composed safely.

## Design chosen

AUTH is consumed before any prepared-byte or workspace access. The canonical
archive inspector alone projects the verified tree. Checker code receives no
path, provider handle, scratch handle, directory fd, or serializable authority.
Cancellation and deadlines abort before checker execution while cleanup still
runs to completion.

## Alternatives rejected

- Public `PreparedArtifact` processing: bypassed fixed-service authority.
- Direct ZIP extraction or a second extractor: duplicated the canonical safety
  boundary.
- Filesystem descriptor capability: allowed callback mutation.
- Legacy checker registry execution: would preserve the authority being
  replaced and mix project-policy work into 04B2.

## Scope control

No public route, project-policy execution, durable evidence, admission,
Submission, review decision, provider I/O, AUTH activation, or legacy removal.

## Product behavior

None is publicly active. Results are non-durable internal values:
`passed`, `warning`, `failed`, `advisory_disabled`, and
`dependency_not_run`; they are not review decisions.

## Acceptance criteria proof

Tests prove authority-before-access, exact plan/catalogue/archive/manifest
identity, closed dispatch, disabled mandatory failure, advisory visibility,
project-policy isolation, semantic drift rejection, scratch capacity, fixed
modes, callback revocation, cancellation/deadline abort, cleanup, and no legacy
runner dependency.

## Tests/checks run

- 29 focused materialization/default tests passed.
- Contract-focused ART and checker suites passed.
- Ruff, compilation, semantic-lane collection/validation, stale contract,
  lightweight agent, Markdown-link, stale-wording, and diff checks passed.
- Full coverage and integration execution is delegated to hosted Backend Gates.

## Test delta

Two focused modules were added; existing cleanup/config tests were strengthened.
No test was removed, skipped, xfailed, or weakened.

## CI integrity

The repository 78 percent floor remains. Existing checker 90 percent coverage
remains, and ART module, cancellation/lock, and artifact-interface 90 percent
reports are explicit. Both new tests are assigned to semantic lanes.

## Reviewer results

Architecture, security, QA, senior engineering, reuse, CI integrity, test
delta, and docs passed. Product/ops passed with one non-blocking observation
that the platform/default slice is derived from the locked full plan.

## External review

Pending GitHub Backend Gates and CodeRabbit on the draft PR.

## Remaining risks

The production materializer remains unavailable until AUTH activation. This
chunk intentionally creates no durable checker evidence or admission.

## Follow-up work

04B3 owns project-policy execution and durable checker evidence. Later AUTH
activation and the 05B admission-backed cutover remain separate ordered work.

## Human review focus

- Confirm no byte/workspace access precedes fixed-service AUTH.
- Confirm the callback sees exactly the 04A manifest tree and cannot retain
  scratch authority or content after close.
- Confirm no project-policy or legacy public precheck path executes.

## Human merge ownership

Only the repository owner may approve and merge this PR.
