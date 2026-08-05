# Chunk Contract: WS-ART-001-04B2 - Default Checker Execution

Initiative: `WS-ART-001` | Risk: L1 | Status: Active implementation

Artifact contract phase: `upload_admission`

## Goal

Project the already inspected outer ZIP into one sealed read-only scratch tree
and execute the mandatory artifact-custody and Workstream-default phases of the
04B1 plan against exact server-derived facts. Do not execute project-specific
rules or persist the final evidence set yet.

## Allowed Files

- shared checker-input materialization through `ArtifactScratchManager`;
- execution adapters for catalogue entries backed by 04A2/04A3 capabilities;
- platform/default phase orchestration, bounded result types, cleanup and tests;
- fixed-service materializer resource facts/guards while the action remains
  planned and unavailable;
- focused docs, evidence, and CI gate maintenance.

## Not Allowed

- re-parsing through a second ZIP implementation or changing 04A identities;
- arbitrary execution, network access, direct temp paths, or provider I/O;
- project-specific rule execution or durable evidence/admission/Submission;
- passing scratch paths or prepared handles across processes or Celery;
- AUTH activation/grants, public routes, post-submit/review/contribution work.

## Acceptance Criteria

- one sealed materialization is derived from the 04A manifest and generation;
- the sealed tree is a callback-scoped, non-serializable `SealedSubmissionTree`
  capability: projection and checker dispatch complete inside one
  `ArtifactScratchManager` workspace lifetime, and only bounded result values
  return after mandatory cleanup; no bare path or close-optional tree escapes;
- the hidden execution request carries the exact 04B1 effective plan and hash,
  catalogue manifest hash and ordered phase slice, plus the 04A archive
  commitment, inspection, semantic manifest, change-gate result, and
  process-local prepared-artifact generation that the materializer validates;
  policy row IDs alone are not executable input;
- archive and projected file hashes/sizes/types/executable flags agree before a
  checker can read the tree;
- focused mismatch tests cover missing and extra entries, normalized-path and
  file/directory type drift, per-file SHA-256 and byte-count drift, executable
  drift, and aggregate-count drift; every case denies checker access and proves
  cleanup with no durable/provider effect;
- fixed sealed modes are `0400` for non-executable regular files, `0500` for
  executable regular files, and `0500` for directories; executable intent is
  intentionally projected for semantic parity, but the callback capability
  exposes neither paths nor a subprocess/shell/execution primitive; tests prove
  no execution helper is reachable from the 04B2 phase slice;
- workspace reservations account for projected expanded bytes and entries under
  the aggregate scratch quota. The cleanup bound is a separate startup-fixed
  workspace-entry limit at least as large as the configured accepted archive
  entry limit; worst-case nested cleanup at that limit is tested;
- mandatory catalogue unavailability, authorization denial, integrity drift,
  cancellation, timeout, or scratch exhaustion fails before checker access and
  creates no durable/provider effect;
- platform/default entries execute in deterministic dependency order and emit
  bounded path-redacted results carrying entry ID/version and plan identity;
- the closed entry-result vocabulary is `passed`, `warning`, `failed`,
  `advisory_disabled`, and `dependency_not_run`; terminal execution failures
  separately distinguish contributor-blocking checker failure, retryable
  infrastructure unavailable, authority denied/unavailable, cancellation,
  timeout, scratch exhaustion, and integrity incident;
- no result or failure uses the product review values `accept`,
  `needs_revision`, or `reject`;
- the executable phase slice is closed to `custody`, `identity`,
  `materialization`, and `default_policy`; `project_policy` entries and policy
  primitives are never dispatched by 04B2;
- every `default_policy` adapter consumes only typed server-owned input and the
  immutable Workstream-default semantics committed by its catalogue entry ID,
  version, and catalogue-manifest hash; it never reads the merged project policy
  or a project-rule configuration;
- disabled advisory entries are explicit; disabled mandatory entries fail
  closed and cannot appear as passing or skipped-success;
- executor tests independently reject stale/forged plan identity, unknown
  dispatch capability, duplicate result identity, and disabled mandatory state;
  dependency or blocking default failure stops dependent/later dispatch, while
  an advisory warning remains non-blocking and explicit;
- cleanup is bounded and idempotent on every terminal path;
- projection-specific tests cover cancellation during member projection and
  sealing, timeout before and during checker access, scratch exhaustion before
  workspace exposure, adapter failure after sealed-tree handoff, and repeated
  cleanup/close;
- tests prove pre-submit and post-submit projection parity for Unix executable,
  non-Unix/invalid mode, symlink/special rejection, and permission-only revision
  cases; neither projection preserves arbitrary archive modes;
- parity is proved through one shared projection contract and future
  post-submit-compatible adapter fixtures; this chunk does not implement the
  post-submit workflow;
- the behavior remains hidden and process-local for later 04B3/04C composition;
- archive projection is implemented inside the canonical
  `SubmissionArchiveInspector` traversal boundary (or a private iterator shared
  by its inspection and projection methods), with no second ZIP validation or
  extraction implementation outside `submission_archive.py`;
- tests prove 04B2 does not call the legacy checker registry, standalone
  precheck service, or `pre_submit_static_feedback`; those paths remain frozen
  legacy behavior until 05B removes them;
- pure packet/attestation/quality predicates are shared where their semantics
  match, but the platform sensitive-path adapter uses the narrow
  high-confidence default set and never inherits the legacy runner's broad
  token/secret/dependency-directory heuristics;
- the production planned/unavailable materializer authority denies before
  workspace or checker access, while a bounded fixed-service test authority can
  exercise the hidden process-local path without creating an ART-local protocol;
- `workstream.artifact.materializer` authority for
  `artifact.pre_submit.checker_input.materialize` is required before
  `PreparedArtifact.inspect()`, ZIP open, workspace reservation/creation, or any
  projected/checker fact. The catalogue custodian is `AUTH_ART_04B`; the planned
  cross-initiative activation remains XINT-06A after 04B3.
- projection uses component-by-component descriptor-relative directory/file
  creation under the pinned workspace descriptor, `O_NOFOLLOW | O_EXCL` for
  files, no `ZipFile.extract*` or path-string writes, exact manifest collision
  checks, descriptor-owned chmod, post-write hash/size/type verification, and
  directory fsync before the tree capability is exposed;
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

## Verification

```bash
(cd backend && .venv/bin/pytest tests/test_checker_materialization.py tests/test_default_pre_submit_execution.py tests/test_checker_catalogue.py tests/test_artifact_preparation.py tests/test_submission_archive.py tests/test_submission_manifest.py tests/test_submission_change_gate.py tests/test_config.py -q)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/coverage report --include='app/modules/artifacts/*' --precision=2 --fail-under=90)
(cd backend && .venv/bin/coverage report --include='app/modules/checkers/*' --precision=2 --fail-under=90)
(cd backend && .venv/bin/coverage report --include='app/core/cancellation.py,app/core/config.py,app/core/file_locks.py' --precision=2 --fail-under=90)
(cd backend && .venv/bin/coverage report --include='app/interfaces/artifact_operations.py,app/interfaces/artifacts.py' --precision=2 --fail-under=90)
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
```

## Exact CI Coverage Gates

The hosted Backend Gates retain every existing ART/checker coverage report.
This chunk must additionally prove or preserve exactly:

```bash
coverage report --include='app/modules/artifacts/*' --precision=2 --fail-under=90
coverage report --include='app/modules/checkers/*' --precision=2 --fail-under=90
coverage report --include='app/core/cancellation.py,app/core/file_locks.py' --precision=2 --fail-under=90
coverage report --include='app/interfaces/artifact_operations.py,app/interfaces/artifacts.py' --precision=2 --fail-under=90
```

If implementation does not change one of those surfaces, its existing hosted
gate remains unchanged; it may not be removed or weakened.

## Required Documentation

Implementation must reconcile the hidden capability, scratch quota, result
taxonomy, default/project phase ownership, executable projection, and planned
AUTH wording in:

- `docs/spec_artifact_storage_service.md`;
- `docs/architecture_checker_framework.md`;
- `docs/architecture_data_model.md`;
- `docs/template_submission_artifact_policy.md`;
- `docs/template_submission_packet.md`;
- `docs/template_checker_policy.md`;
- `docs/architecture_lockdown.md` and `docs/glossary.md` where their canonical
  terms require it;
- `docs/spec_authorization_service.md` and
  `docs/operations_authorization_service.md` only if the exact resource/guard or
  planned-denial wording changes;
- `docs/roadmap_status.md`, initiative `STATUS.md`, `CHUNK_MAP.md`, and final
  review evidence after implementation.

These updates describe hidden 04B2 execution only. They must not change the
legacy public standalone precheck contract before 05B or imply contributor
preparation, durable evidence, admission, or Submission is active.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is the checked tree exactly the 04A manifest tree?
- Can any disabled/failed mandatory default be bypassed?
- Are all scratch and authorization capabilities process-local and bounded?
