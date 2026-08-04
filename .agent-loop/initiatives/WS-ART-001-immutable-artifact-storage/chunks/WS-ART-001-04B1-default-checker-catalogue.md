# Chunk Contract: WS-ART-001-04B1 - Default Checker Catalogue

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after PLAN4 approval

Artifact contract phase: `upload_admission`

## Goal

Create the single typed, versioned pre-submission checker catalogue and compile
one effective execution plan from Workstream platform defaults plus the exact
task-locked Project Guide policy. This chunk defines composition and validation;
it does not read ZIP bytes, execute checkers, persist evidence, or expose a route.

## Allowed Files

- checker catalogue, typed entry/plan/result contracts, and composition code;
- reuse/migration of existing compiler primitive definitions and runner adapters
  into the catalogue, deleting parallel maps/constants without aliases;
- adapters that register already-merged ART safety/manifest capabilities by
  stable identity without reimplementing them;
- project checker compiler integration needed to emit the one effective plan;
- startup configuration/validation for catalogue availability;
- focused tests, docs, and chunk evidence;
- CI only when needed to preserve or add the exact scoped 90 percent gate.

## Not Allowed

- ZIP parsing, scratch materialization, checker execution, or durable evidence;
- a second registry, project-only execution API, dynamic plugin discovery, or
  string-dispatch conditionals outside the catalogue;
- per-user, per-project, per-task, or runtime mutation of catalogue availability;
- AUTH availability/grant changes, provider I/O, Submission/admission creation,
  post-submit/review/contribution work, or larger configured limits.

## Catalogue Contract

Each entry declares: stable ID, version, owner, phase/order, dependencies,
classification (`mandatory_security`, `mandatory_integrity`,
`mandatory_accountability`, or `advisory`), typed inputs, result schema, stable
failure code, resource budget, default state, disabled behavior, and policy
trace source.

The initial platform catalogue names the already-owned capabilities for outer
ZIP format, archive/path/entry/resource safety, archive digest/size, canonical
semantic manifest, executable normalization, unchanged-work rejection, sealed
scratch integrity, high-confidence sensitive-file exclusion, required packet
fields, required accountability attestations, and warning-only generic quality
signals. Project-specific required files, evidence, layouts, languages, tests,
and quality rules enter only through the locked project policy.

Initial stable v0.1 entries:

| Stable ID | Classification | Phase | Source |
|---|---|---|---|
| `artifact.outer_zip.valid` | `mandatory_security` | custody | 04A2 result |
| `artifact.archive.paths_safe` | `mandatory_security` | custody | 04A2 result |
| `artifact.archive.entries_safe` | `mandatory_security` | custody | 04A2 result |
| `artifact.archive.resources_bounded` | `mandatory_security` | custody | 04A2 result |
| `artifact.archive.integrity_verified` | `mandatory_integrity` | custody | 04A2 result |
| `artifact.archive.identity_computed` | `mandatory_integrity` | identity | 04A2 result |
| `artifact.manifest.semantic_identity_computed` | `mandatory_integrity` | identity | 04A3 result |
| `artifact.manifest.executable_normalized` | `mandatory_integrity` | identity | 04A3 result |
| `artifact.revision.content_changed` | `mandatory_integrity` | identity | 04A3 result |
| `artifact.scratch.sealed_tree_verified` | `mandatory_integrity` | materialization | 04B2 execution |
| `submission.packet.required_fields` | `mandatory_accountability` | default policy | 04B2 execution |
| `submission.attestation.required_topics` | `mandatory_accountability` | default policy | 04B2 execution |
| `artifact.sensitive_paths.high_confidence` | `mandatory_security` | default policy | 04B2 execution |
| `artifact.quality.placeholder_signal` | advisory | default policy | 04B2 execution |

04A2/04A3 entries import the exact typed, process-local result from those
capabilities into the plan; 04B never reruns or independently reinterprets the
ZIP. Their configuration state is still visible in the catalogue. Because they
are mandatory, configuring one disabled makes intake unavailable before its
owning capability is invoked.

The same catalogue registers the existing constrained project primitives under
their current canonical names: `validate_submission_packet`,
`enforce_storage_scheme`, `require_manifest_field`, `verify_hash`,
`require_file`, `require_minimum_evidence`, `forbid_artifact`,
`require_attestation`, `limit_file_size`, `limit_package_size`,
`require_packaging`, and `warn_low_quality_generated_artifact`. A compiled
project rule receives a deterministic rule instance ID derived from the locked
policy lineage and configuration; it does not register a new checker type.

`disabled` is observable configuration state, not success. Mandatory disabled
entries make preparation unavailable; advisory disabled entries are retained in
the plan manifest as disabled. Locked project-required rules cannot be disabled
at runtime. Startup fails for duplicate identities, missing dependencies,
cycles, invalid phase ordering, unknown primitives, invalid severity, or a
mandatory entry configured to skip/pass.

## Acceptance Criteria

- one catalogue and one effective-plan compiler are the only dispatch authority;
- every platform default is named, versioned, classified, ordered, and bounded;
- platform defaults cannot be omitted, reordered unsafely, weakened, or
  downgraded by project policy or task parameters;
- broad `token*`, `secret*`, `credential*`, and dependency-directory heuristics
  are not silently inherited as generic blocking rules; tests prove the exact
  high-confidence/advisory/project-specific classification;
- plan identity commits to catalogue version/state, locked checker bundle hash,
  effective project submission artifact policy hash, and deterministic ordered
  entry/config hashes;
- the legacy precheck path cannot construct an alternate plan;
- no duplicate primitive map, runner registry membership, or compatibility alias
  remains for pre-submit dispatch;
- the hidden contributor surface and fixed materializer action remain unchanged
  and unavailable; no runtime bytes or durable effects occur;
- focused subsystem coverage is at least 90 percent and repository coverage
  remains at least 78 percent.

## Verification

```bash
(cd backend && .venv/bin/pytest tests/test_checker_catalogue.py tests/test_checker_compiler.py tests/test_project_policy.py -q)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
(cd backend && .venv/bin/coverage report --include='app/modules/checkers/*,app/modules/projects/*' --precision=2 --fail-under=90)
(cd backend && .venv/bin/ruff check app tests)
python3 scripts/check_stale_artifact_contracts.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
```

## Exact CI Coverage Gates

The hosted Backend Gates retain every existing ART/checker coverage report.
This chunk must additionally prove or preserve exactly:

```bash
coverage report --include='app/modules/checkers/*' --precision=2 --fail-under=90
coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90
coverage report --include='app/core/config.py' --precision=2 --fail-under=90
coverage report --include='app/main.py' --precision=2 --fail-under=90
```

If implementation does not change one of those surfaces, its existing hosted
gate remains unchanged; it may not be removed or weakened.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is every Workstream default discoverable in one catalogue?
- Can disabling any mandatory entry ever make a bundle eligible?
- Is project-specific policy composed without another API or registry?
