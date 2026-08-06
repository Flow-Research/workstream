# Chunk Contract: WS-QUAL-002-01 — Behavior Ownership Catalogue Foundation

## Parent initiative

`WS-QUAL-002` — Behavior Ownership Catalogue

## Goal

Add the versioned catalogue contract, exact eligible-module inventory, and a
deterministic read-only generator/validator without changing mutation CI.

## Why this chunk exists

All population chunks need one reviewed format and toolchain. This foundation
prevents four subsystem branches from inventing incompatible ownership data.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/CHUNK_MAP.md`

## Risk class

L1.

## SLA

P2.

## Allowed files

```text
.ci/behavior-ownership/README.md
.ci/behavior-ownership/partition.v1.json
.ci/behavior-ownership/examples/**
scripts/behavior-ownership.schema.json
backend/scripts/behavior_ownership.py
backend/tests/test_behavior_ownership.py
CONTRIBUTING.md
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/STATUS.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/chunks/WS-QUAL-002-01-catalogue-foundation.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/reviews/WS-QUAL-002-01-*
```

## Not allowed

```text
.github/workflows/**
backend/app/**
backend/alembic/**
backend/scripts/mutation_policy.py
scripts/behavior-claim.schema.json
coverage thresholds, lane membership, skips, deselection, survivor exemptions
authoritative inferred ownership without reviewed catalogue state
```

## Acceptance criteria

- [ ] Schema distinguishes reviewed ownership, candidates, and strict structural-only records.
- [ ] The schema defines `structural_only` as a machine-readable status with a required non-empty reason and forbids callable and test fields for that status; executable records require callable and test fields.
- [ ] Validation and `--run-owned-tests` exclude valid `structural_only` records, reject mixed structural/executable fields, and test the no-executable-callable completeness case from `DISCOVERY.md`.
- [ ] Inventory deterministically enumerates every eligible non-`__init__` module.
- [ ] Eligibility, safe-path checks, callable spans, changed-callable derivation, observable outcomes, and real-boundary vocabulary delegate directly to the existing `mutation_policy.py` definitions; parity tests fail on drift rather than maintaining a second implementation.
- [ ] The sole partition artifact is `.ci/behavior-ownership/partition.v1.json` with schema identity `workstream.behavior-ownership-partition.v1`; it assigns every eligible target to exactly one of `auth`, `artifacts`, `lifecycle`, or `shared`.
- [ ] Partition custody binds its protected-base commit and digest; validation rejects missing, relocated, duplicated, branch-local, or modified copies.
- [ ] Callable groups enumerate exact AST callable members; changed-callable selection remains exact, and wildcards or implicit membership fail closed.
- [ ] Validator rejects unsafe paths, duplicates, missing targets/callables/tests, stale nodes, narrowing, and malformed records.
- [ ] Remap records require immutable `behavior_id` and `supersedes_behavior_id`, exact-Git-delta proof that the protected location is absent or renamed, and an existing PR-head location.
- [ ] Remap validation carries forward all protected tests, outcomes, and real boundaries unless stronger reviewed evidence is added; deletion, narrowing, replacement, invalid ancestry, and zero or multiple effective owners fail closed.
- [ ] Every referenced pytest node collects, and the validator can run the exact nodes referenced by a record or population group.
- [ ] `structural_only` is allowed only for imports, constants, type-only declarations, protocols/interfaces, and declarative metadata with no executable functions, validators, I/O, SQL, external calls, branching, mutation, or runtime side effects; every record includes a reviewed rationale and executable counterexamples fail validation.
- [ ] Generator emits deterministic candidates and a precise unresolved report; it never promotes candidates to reviewed.
- [ ] Empty initial catalogue is allowed only with an explicit completeness report because mutation reactivation is not active.
- [ ] New tooling has at least 90-percent focused coverage.
- [ ] Retired mutation enforcement remains inactive; the Backend workflow and coverage floors are unchanged.
- [ ] Negative tests cover missing/duplicate/wrong-group targets, stale nodes, overbroad groups, executable behavior mislabeled `structural_only`, invalid remap ancestry/location, missing carry-forward evidence, protected-owner replacement, and zero/multiple effective owners.

## Verification commands

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_behavior_ownership.py --cov=scripts.behavior_ownership --cov-fail-under=90)
(cd backend && .venv/bin/ruff check scripts/behavior_ownership.py tests/test_behavior_ownership.py)
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] architecture
- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Confirm that candidate inference cannot become blocking authority, the format
can represent all subsystems, and this PR does not alter current CI behavior.

## Stop conditions

Stop if workflow/mutation reactivation becomes necessary, ownership must be guessed
as reviewed, active Backend, coverage, lint, or review gates must weaken, or the schema cannot represent a
subsystem without free-form exemptions.
