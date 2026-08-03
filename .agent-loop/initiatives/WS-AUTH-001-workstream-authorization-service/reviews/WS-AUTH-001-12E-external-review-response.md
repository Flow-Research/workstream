# WS-AUTH-001-12E External Review Response

## Comments addressed

- Corrected the trusted-branch versus post-merge activation-count wording and
  the split ownership of Celery admission in 12E versus full call-graph cutover
  in 12B2.
- Applied Alembic naming-convention-safe check names, append-only `TRUNCATE`
  protection, matching downgrade cleanup, and a provenance-only downgrade
  refusal proof.
- Required human execution for Project Manager sufficiency mutations and added
  a schema-level regression for service execution against a report operation.
- Failed before broker dispatch when the committed setup-run row is missing,
  persisted the deterministic task identity before enqueue, and recorded a
  post-acceptance task-identity mismatch separately from broker failure. Added
  an exact persisted-state regression.
- Reused the representative-task source-kind constant, corrected async context
  manager annotations, preserved explicitly empty verified material results,
  cleared cached settings after every project test, and proved a successful
  sufficiency capability is single-use.
- Updated all independent active-action, OpenAPI route, operations-count, and
  ART fixed-service test fixtures for the three activated actions and the
  shared fixed-service principal resolver.
- Updated the canonical schema fingerprint and test reset custody for the new
  append-only replay table.
- Repaired the hosted project-lifecycle failures: verified-material fixtures,
  deterministic Celery identity expectations, service actor provenance,
  bounded agent-runtime wording, unverified legacy-material rejection, and
  ambiguous latest-snapshot translation.

## Comments deferred

- A dedicated prepare-denial resource type is a broader authorization-protocol
  change. The current typed sufficiency resource remains bounded and tested;
  changing that protocol during an activation repair would expand the chunk.
- Extracting the duplicated human/service replay-recovery sequence is a
  maintainability refactor across security-critical transaction paths. The two
  explicit paths remain behaviorally distinct and reviewed, so this is not
  mixed into the correctness repair.
- Retaining the validated sufficiency model inside `prepared.py` is a
  maintainability improvement only; validation is already mandatory before
  any binding is issued. It is deferred to avoid unrelated PREP refactoring.
- The roadmap must not claim PR `#263` merged before human merge. Its merge
  citation belongs in the post-merge memory update.
- CodeRabbit's PR-description and docstring heuristics are advisory. The
  repository's actual docstring gate passed; the PR description will be aligned
  to the repository trust-bundle template without weakening any gate.

## Human decisions needed

None. The user retains merge authority for PR #263.

## Commands rerun

- Ruff across the backend: passed.
- Git diff whitespace validation: passed.
- Focused authorization boundary and documentation selection: passed.
- Focused OpenAPI and audit action-parity selections: passed.
- Four ART fixed-service adapter regressions: passed.
- Canonical migration rebuild and schema fingerprint computation: passed.
- Test-database reset against the append-only replay trigger: passed.
- Local project-lifecycle collection is unstable on this machine due to
  repeatable Python segmentation faults; the corrected complete semantic lanes
  remain assigned to hosted GitHub Actions as requested by the user.

## Remaining risks

- The corrected exact head must pass all five hosted semantic lanes, aggregate
  and per-file coverage, Agent Gates, and a fresh CodeRabbit review.
