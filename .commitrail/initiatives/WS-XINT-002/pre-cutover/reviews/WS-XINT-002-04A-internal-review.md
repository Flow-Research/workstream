# WS-XINT-002-04A Internal Review

## Scope reviewed

Guide-source ingest activation based on planning correction `35b9bffb`:
Project Manager policy/custody, human PREP preparation and consumption, ART-owned
project/draft-guide/snapshot/item locks, final byte-fact evidence, and denial
atomicity. Guide read and binding remain planned.

## Pre-implementation review

Architecture, security, product/ops, QA, senior engineering, and CI review found
that the original contract omitted the canonical Project Manager policy file and
ART-owned project/guide lineage locks. Implementation did not bypass those
findings. The correction was split into its own planning commit and expanded the
allowed surface narrowly. Review also clarified that a covered Project Manager
grant follows the canonical scope rule: system-scoped grants cover every project;
project-scoped grants cover only their exact project.

## Implementation review

- Architecture: pass with low transaction-ownership reuse risk; no AUTH/ART
  boundary violation.
- Security: pass after canonical Project Manager scope clarification; no
  blocking authorization finding.
- Product/ops: pass with low wording risk, corrected in the custody table.
- QA: pass with low risk; hosted database proof remains required.
- Senior engineering: pass with low risk after separating the planning commit.
- CI integrity: pass with low risk; no gate, threshold, or runner change.
- Docs: findings on PREP narrative and catalogue counts were corrected.
- Reuse/dedup: pass with a low-risk note about the existing duplicated PREP
  request-digest domain literal; no new abstraction required in 04A.
- Test delta: pass after correcting the real-database grant fixture and adding
  adapter-specific final-fact and denial proofs.

The first hosted exact-head run then exposed two stale closed-registry
assertions after guide ingest moved from planned ART-03 custody to active 04A
custody. The contract was corrected to own those exactness surfaces; the audit
active-action set, custody owner counts, canonical custody ledger, and catalogue
totals were updated without weakening an assertion. CI integrity, QA, senior,
docs, reuse, and test-delta tracks were rerun on the corrective delta. Their
valid stale-document findings were also corrected before the final hosted run.
The next hosted run passed semantic-lane custody but reported artifact foundation
coverage at 89.94 percent. Focused safety tests were added for nested-transaction
denial, caller-owned root commit/rollback, and PREP consume-error translation.
They execute eleven previously uncovered production statements, restoring margin
without changing the 90 percent gate.

## Local evidence

- Ruff passed for backend application and affected tests.
- Focused authorization catalogue/policy/PREP tests passed.
- The two exact assertions that failed in the first hosted run pass after the
  corrective change.
- `tests/test_guide_artifacts.py` passes with the new transaction/error safety
  paths and raises focused coverage of ART authorization from 32 to 37 percent.
- `tests/test_guide_artifacts.py` passed, including activated adapter binding,
  forged/unissued handle, mismatch, and reuse proofs.
- Stale authorization docs, stale artifact contracts, Markdown links, agent
  static gate, and `git diff --check` passed.
- The full database-backed coverage command was intentionally not run locally
  because `WORKSTREAM_TEST_DATABASE_URL` is unavailable and the user's machine
  is not the full-suite execution environment.

## Hosted evidence required

The exact implementation head must pass `Backend / test` and
`Agent Gates / agent-gates`. Hosted CI owns the database-backed focused tests,
repository-wide 78 percent baseline, and authorization/artifact 90 percent
coverage gates.
