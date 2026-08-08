# Chunk Contract: WS-POL-003-01 - Unified Contract and Catalogue Projection

Status: Active after explicit human start on 2026-08-08. Risk: L1.

## Goal

Add strict bounded unified input/result/evidence contracts and two read-only
capability projections from existing phase-owner truth. No model call,
persistence, registry, compiler behavior, composition-root, or lifecycle
change is permitted.

## Why this chunk exists

The later unified adapter needs one closed model-facing contract without
copying ART's 26-entry catalogue or treating CHECKER's runtime registry as a
second POL-owned registry.

## Allowed files

```text
backend/app/interfaces/project_agents.py
backend/app/modules/checkers/catalogue.py
backend/app/modules/projects/post_submit_policy.py
backend/scripts/run_test_lanes.py
backend/tests/test_ci_test_lanes.py
backend/tests/test_project_guide_compilation_contracts.py
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/**
```

`catalogue.py` and `post_submit_policy.py` may add pure read-only projection
functions only. Their existing registry, definitions, defaults, compiler,
validation, hashing, and execution semantics are frozen.

The CI lane files may change only to assign the new test module exactly once
to the existing task-lifecycle lane and update its exact-inventory assertion.

## Not allowed

```text
new or changed ART/CHECKER catalogue definitions/defaults/registrations
new registry, service locator, composition-root state, or startup wiring
database/model/migration/repository/Celery/API/authorization changes
agent adapter, prompt, provider/model call, checker dispatch, or execution
post-submit compiler behavior changes, including default-checker handling
effective-plan reconstruction or independent canonical/hash algorithms
open Any/dict model-visible configuration or executable suggestion fields
```

Default-checker repetition is rejected only by the new unified proposal
validator. This chunk does not change the historical post-submit compiler.

## Frozen contracts and bounds

- New Pydantic contracts use `extra="forbid"` and strict scalar validation.
- At most: 100 findings, 200 atomic requirements, 100 pre bindings, 100 post
  bindings, 50 capability suggestions, 20 setup notes, and 20 evidence refs
  per item. Safe operator text is at most 1,000 characters per field and
  rejects control characters, URL/scheme/path/credential/command/import/
  dependency-shaped content where the field is model-produced.
- `GuideEvidenceRef` contains only server-minted immutable lineage:
  `source_item_id`, `extraction_usage_id`, canonical output SHA-256, and bounded
  numeric start/end ordinals. It contains no raw excerpt, URL, path,
  credential, signed reference, caller text, or provider/scratch handle.
- Representative task context is optional and contains only bounded
  server-redacted policy-shape identifiers. It contains no actor/user ID,
  email, raw task body, submission/review/payment data, secret, URL, or path.
- The ART guide material must be marked verified, contain no legacy raw
  representative-task items, and expose only the canonical `content_markdown`
  guide field plus ART-verified source items. The unified context receives a
  deeply immutable canonical payload snapshot, payload hash, and immutable
  source lineage so post-validation mutation cannot change evidence truth.
  Extracted guide content remains explicitly untrusted model input; it is not
  accepted as output evidence.
- Capability configuration is a tuple of closed key/value parameters. Keys
  must be present in the selected canonical definition's policy fields; values
  are bounded JSON scalars or bounded scalar tuples, never nested objects,
  source code, commands, imports, dependencies, URLs, or paths.

## Canonical pre-submit projection

- The projection consumes one exact startup-composed
  `PreSubmissionCheckerCatalogue`; it never calls a second builder in product
  execution.
- It preserves the complete immutable envelope, `manifest_sha256`, and all 26
  exact definition projections in canonical order, including disabled advisory
  rows and all 19 existing definition fields.
- The first 14 `platform_capability` definitions are non-selectable platform
  coverage. Only enabled `project_policy`/`policy_primitive` definitions are
  selectable project capabilities.
- Disabled mandatory catalogue state makes the projection unavailable;
  disabled advisory rows remain visible but non-selectable.
- The projection does not invent timeout, safety, implementation-version, or
  other metadata absent from ART-04B1.

## Canonical post-submit projection

- The projection remains in `post_submit_policy.py`, adjacent to the existing
  compiler-version default snapshot, and consumes
  `default_checker_registry().names()` plus
  `POST_SUBMIT_DEFAULT_CHECKERS_BY_COMPILER_VERSION`.
- Envelope identity is
  `workstream.post_submission_checkers`, schema
  `post_submission_checker_capability_projection.v1`, and source version
  `POST_SUBMIT_COMPILER_VERSION`; its canonical SHA-256 commits the sorted
  registered names, frozen default names, stage, and selectability.
- Capability identity is the registered checker name; capability version is
  the frozen source/compiler version; stage is exactly `post_submit`.
- The eight frozen v0.1 defaults are non-selectable platform coverage. The
  registered-minus-default set is project-selectable; on current main it is
  exactly `check_acceptance_criteria_present`.
- Default/unknown/wrong-stage/stale-snapshot bindings fail in unified proposal
  validation. No registry or compiler mutation occurs.

## Acceptance criteria

- Strict input/result/evidence schemas reject extra, unsafe, executable,
  over-limit, PII-bearing, raw-source, and nested-open configuration fields.
- One atomic requirement has exactly one canonical disposition. Binding and
  evidence references resolve to existing requirement/source lineage.
- `platform_covered` requires an exact stage/ID/version reference to an
  enabled mandatory pre-submit platform capability or a canonical post-submit
  default. Advisory pre-submit rows remain visible but cannot satisfy required
  coverage. Ready/blocked status must agree with warning, blocking-gap, and
  capability-gap evidence.
- ART projection equality covers the exact 26-entry manifest and hash; no field
  is dropped, retyped, inferred, or reordered.
- Platform/default and disabled definitions cannot be selected. Enabled
  project capabilities can be selected only at their exact stage/version and
  with catalogue-owned policy fields.
- Post-submit projection is derived solely from the canonical registry and
  frozen default snapshot; parity drift fails closed.
- Optional representative task context may be omitted without invalidating the
  compilation context.
- Static proof finds no new registry, model/provider call, persistence, route,
  Celery, authorization, or catalogue mutation.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/interfaces/project_agents.py app/modules/checkers/catalogue.py app/modules/projects/post_submit_policy.py tests/test_project_guide_compilation_contracts.py)
(cd backend && .venv/bin/python -m pytest -q tests/test_project_guide_compilation_contracts.py tests/test_checker_catalogue.py)
# Hosted Backend lane (supplies WORKSTREAM_TEST_DATABASE_URL/Postgres):
(cd backend && .venv/bin/python -m pytest -q tests/test_project_guide_compilation_contracts.py tests/test_checker_catalogue.py tests/test_checkers.py --cov=app.interfaces.project_agents --cov=app.modules.checkers.catalogue --cov=app.modules.projects.post_submit_policy --cov-report=term-missing --cov-fail-under=90)
# Hosted full Backend matrix and repository coverage gate:
(cd backend && .venv/bin/python -m pytest -q)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
! git diff origin/main -- backend/app/interfaces/project_agents.py backend/app/modules/checkers/catalogue.py backend/app/modules/projects/post_submit_policy.py | rg '^\+.*(class .*Registry|\.register\(|responses\.create|Runner\.run|Celery|Mapped\[|APIRouter)'
git diff --check
```

No configured repository type-check command exists on current main; strict
Pydantic construction, Ruff, focused tests, and the full hosted Backend matrix
are the type/runtime gates for this chunk.

## Required reviewers

- architecture
- security/auth and data safety
- QA/test
- product/operations
- senior engineering
- reuse/dedup
- test delta
- CI integrity
- docs

## Human review focus

Confirm exact phase-owner reuse, no second registry, no executable or leaking
model fields, and no change to catalogue/compiler/runtime behavior.

## Stop conditions

Stop if current canonical sources cannot provide a deterministic read-only
projection without inventing authority metadata, if a projection requires
registry/compiler mutation, or if safe strict configuration requires an open
model-visible object.
