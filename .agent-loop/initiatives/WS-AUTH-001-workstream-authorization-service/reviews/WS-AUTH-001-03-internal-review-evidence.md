# Internal Review Evidence: WS-AUTH-001-03

## Chunk

`WS-AUTH-001-03` - Legacy Actor Classification Preflight

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 8c5334c1635694689ef4a7fb11c572bd6a871e09

Original implementation SHA: `8e2ae489834a3934d6ef507834139a1009dac2e6`

External repair implementation SHA: `4923b677f0a928d77792084c3edc4569b8c28e7b`

Reviewed at: 2026-07-13T08:55:20Z

Reviewer run IDs: plan-review=WS-AUTH-001-03-PLAN-20260713;
senior-engineering=WS-AUTH-001-03-IMPLEMENTATION-ENG-SEC-20260713;
architecture=WS-AUTH-001-03-IMPLEMENTATION-ENG-SEC-20260713;
security-auth=WS-AUTH-001-03-IMPLEMENTATION-ENG-SEC-20260713;
product-ops=WS-AUTH-001-03-IMPLEMENTATION-ENG-SEC-20260713;
docs=WS-AUTH-001-03-IMPLEMENTATION-ENG-SEC-20260713;
reuse-dedup=WS-AUTH-001-03-IMPLEMENTATION-ENG-SEC-20260713;
qa-test=WS-AUTH-001-03-IMPLEMENTATION-QA-CI-20260713;
test-delta=WS-AUTH-001-03-IMPLEMENTATION-QA-CI-20260713;
ci-integrity=WS-AUTH-001-03-IMPLEMENTATION-QA-CI-20260713

Merge-resolution review run IDs:
engineering-security=WS-AUTH-001-03-MERGE-ENG-SEC-20260713T082234Z;
qa-test-ci=WS-AUTH-001-03-MERGE-QA-CI-20260713T082357Z

Evidence-binding re-review run IDs:
engineering-security=WS-AUTH-001-03-EVIDENCE-ENG-SEC-20260713;
qa-test-ci=WS-AUTH-001-03-EVIDENCE-QA-CI-20260713

External-repair re-review run IDs:
engineering-security=WS-AUTH-001-03-EXTERNAL-ENG-SEC-20260713T085520Z;
qa-test-ci=WS-AUTH-001-03-EXTERNAL-QA-CI-20260713T085307Z

Original implementation `8e2ae48` remains the classifier foundation. Merge
integration `0ae502b` incorporates PR #108 without changing its implementation
or test blobs; lifecycle head `a70b89c` resolves the merge conflicts. External
repair `4923b67` preserves primary CLI failures across cleanup failure, and
reviewed code head `8c5334c` reconciles its exact proof and durable evidence.

## Reviewed Change

- Added a strict, versioned legacy-actor manifest and confidential immutable
  envelope contract with canonical UUIDv5 identity binding.
- Added complete sorted live-row, manifest, database, and full-envelope
  SHA-256 evidence without identity-bearing stdout or stderr.
- Added a dry-run-first operator CLI and crash-safe, no-overwrite `0600`
  publication outside the main, active, and every linked Git worktree.
- Added a migration-stable textual projection and strict
  `WORKSTREAM_LEGACY_ACTOR_CLASSIFICATION_FILE` handoff without a live actor ORM
  dependency or database mutation.
- Added explicit empty-registry proof and fail-closed missing, stale, duplicate,
  mismatch, checksum, TOCTOU, database-binding, custody, and canonical-byte
  behavior.
- Updated the authorization runbook and durable AUTH loop state after PR #107
  merged and the user explicitly started AUTH-03.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Deterministic artifact boundary and bounded CLI are maintainable; same-cluster binding limitation is explicit. |
| QA/test | PASS | None | All prior adversarial gaps are repaired and behavior-tested. |
| security/auth | PASS WITH LOW RISKS | None | Identity inference, raw-output leakage, linked-worktree publication, permissive custody, and cleanup traceback paths fail closed. |
| product/ops | PASS | None | Dry-run/export/custody/recovery/deletion workflow matches the operator contract. |
| architecture | PASS | None | Migration verification is independent from mutable actor ORM state and changes no schema or grant authority. |
| docs | PASS | None | Runbook commands, confidential custody, DB-binding limitation, future migration gate, rollback, and deletion are explicit. |
| CI integrity | PASS WITH LOW RISKS | None | No workflow, package, threshold, exclusion, or bypass changed; repository-wide `>=78` proof remains GitHub CI-owned. |
| reuse/dedup | PASS WITH LOW RISKS | None | Local UUID derivation is deliberately retained to keep migration evidence independent from mutable application modules. |
| test delta | PASS | None | No test was removed, skipped, xfailed, or weakened; repairs add real file, CLI, and PostgreSQL concurrency proof. |

## Valid Findings Addressed

- Rejected envelope destinations in the main worktree and every registered
  linked worktree, not only the active worktree and Git common directory.
- Removed the live `ActorIdentity` ORM import and queried the fixed legacy
  table projection needed by migration.
- Required effective-user ownership and no group/world bits for manifest and
  envelope inputs, plus an effective-user-owned non-shared output directory.
- Rejected edited or reserialized envelope bytes unless they exactly match the
  canonical representation and terminating newline.
- Replaced the unsupported human `worker` test value with neutral `unknown`.
- Bound oversized integer conversion, float overflow, NaN, and Infinity to the
  stable `invalid_json` failure.
- Rejected whitespace-bearing hosts and malformed HTTPS ports.
- Rolled back a newly linked destination when directory `fsync` fails.
- Prevented engine-cleanup exceptions from overriding bounded CLI output or
  exposing database details.
- Preserved interruption, domain, and unexpected primary errors and their exit
  codes when engine cleanup also fails.
- Proved actual PostgreSQL `repeatable read`, `transaction_read_only=on`, and
  invisibility of a concurrent committed actor in the established snapshot.

## Commands Run

```bash
(cd backend && isolated-runner pytest -q tests/test_actor_legacy_classification.py tests/test_actors.py::test_legacy_classification_snapshot_is_complete_and_read_only --cov=app.modules.actors.legacy_classification --cov=scripts.legacy_actor_classification --cov-report=term-missing)
(cd backend && pytest -q tests/test_actor_legacy_classification.py)
(cd backend && pytest -q tests/test_isolated_database_runner.py)
(cd backend && ruff check app tests scripts)
(cd backend && docstr-coverage --config .docstr.yaml)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
(PYTHONPATH="$PWD/backend" pytest -q scripts/test_agent_gates.py)
git diff --check
```

Results:

- repaired focused Postgres and file/CLI behavior matrix: 60 passed;
- focused classifier plus CLI statement coverage: 92 percent combined;
- pure classifier/CLI behavior matrix: 59 passed at 90.12 percent combined
  statement coverage;
- full actor/classification surface before final bounded repair: 61 passed;
- Ruff, stale wording, stale authorization docs, Markdown links, docstring
  coverage, and diff checks: passed;
- isolated-runner lifecycle test rerun: 16 passed;
- Agent Gates self-tests: 36 passed;
- repository-wide coverage and complete-suite proof: intentionally delegated to
  GitHub Backend CI under the user's explicit direction; the unchanged
  `--cov-fail-under=78` gate remains mandatory.

## Evidence Gate

Evidence gate: PASS WITH EXTERNAL FULL-SUITE PROOF PENDING

All implementation and durable-memory files are inside the approved chunk
contract. No dependency, workflow, package script, coverage threshold,
exclusion, skip, schema,
migration, grant, role, actor-state, product lifecycle, or later AUTH change is
included. Focused behavior, real PostgreSQL isolation, privacy, file custody,
canonicalization, TOCTOU, and failure paths pass. GitHub Backend CI must still
supply the unchanged repository-wide `>=78` coverage and complete-suite proof
before merge.

## Remaining Risks

- The database binding intentionally detects wrong databases only within the
  same PostgreSQL cluster; clone, restore, or recreation requires fresh
  evidence as documented.
- Non-test classification values must come from authoritative operator/issuer
  evidence. This chunk never infers them and cannot perform the later schema
  migration.
- GitHub Backend CI remains required for repository-wide coverage and complete
  regression proof before human merge review.

## Stop Condition

Ready PR #109 is published at
`https://github.com/Flow-Research/workstream/pull/109`. Stop for external checks
and explicit human review. Do not merge or start `WS-AUTH-001-04`
automatically.
