# WS-ARCH-001-CP04A Implementation Review Evidence

## Scope inspected

The hidden policy public API, CONTRIBUTIONS service/repository/validation,
COMPENSATION and PROJECTS owner ports, adapter-root composition, migration
`0006`, event/model metadata, focused tests, boundary debt, canonical docs, and
state projections.

## Deterministic evidence

- Ruff passed on all touched CP04A application and test surfaces.
- 155 contract-listed focused/schema tests passed through an isolated
  PostgreSQL database; zero were skipped or deselected.
- 10 dedicated real PostgreSQL integration/concurrency/event tests passed.
- 186 combined CP04A coverage tests passed.
- Every changed application surface independently exceeds 90% coverage; the
  broad CONTRIBUTIONS package is 94.56% in the focused collection.
- Fresh-head Alembic install and committed schema-manifest parity passed.
- Module-boundary protected-base validation removed one touched private edge
  and added none.
- Test-structure, active-state, atomic chunk-state, Markdown-link, stale
  wording/authorization/review/artifact, and `git diff --check` gates passed.

## Integrity disposition

No CI file, package dependency, test threshold, test selection, assertion,
skip, xfail, or deselection mechanism changed. PostgreSQL-required tests retain
isolated-database custody; the contract was corrected rather than weakening
their fixture.

## Exact-head reviewer custody

Required architecture, security, product/operations, QA, test-delta,
CI-integrity, senior-engineering, reuse/dedup, and documentation reviewers run
only after this evidence is committed to a clean exact head. Their private
receipts and PR-body mirrors—not this file—own the final advisory verdicts.

## First implementation-review corrections

The first exact-head reviewer wave found and this implementation corrects:

- closed-domain validation for compensation mode and canonical instrument type
  before authorization preparation;
- discriminating successful-view, cross-project policy/version/request, public
  dataclass immutability, and operation-order tests;
- semantic-lane ownership for every new CP04A test module;
- hosted 90-percent gates for every changed CP04A owner/composition surface;
- public lifecycle event vocabulary parity for the shared CP04A/CP04B event
  foundation.

All affected reviewers must replay against the corrective exact head before a
passing verdict is claimed.

## Second implementation-review correction

The exact-head test-delta replay found that the retired-policy test configured
the repository to return no reusable policy, so it could not detect accidental
reuse of a retired aggregate. The service now rejects a retired aggregate even
if repository filtering regresses, and the focused test supplies an actual
retired policy and proves that a distinct version-one aggregate is created.
The six create-draft behavior tests and Ruff pass after this correction. All
required reviewers must bind their final verdict to the resulting clean head.
