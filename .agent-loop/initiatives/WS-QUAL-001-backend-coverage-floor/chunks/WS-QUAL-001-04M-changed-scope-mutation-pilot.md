# Chunk Contract: WS-QUAL-001-04M — Changed-Scope Mutation Pilot

## Parent initiative

`WS-QUAL-001` — Behavior And Mutation Assurance

## Goal

Pilot one exactly pinned mutation engine on eligible changed or explicitly
claimed production targets and publish complete exact-head result evidence
without imposing an uncalibrated mutation-score gate.

## Why this chunk exists

Coverage proves execution, not assertion sensitivity. Workstream needs measured
compatibility, mutant quality, selection integrity, and hosted runtime before a
mutation outcome can block contributions.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/CHUNK_MAP.md`

## Risk class

L1 — CI executable/dependency/evidence policy.

## SLA

P2.

## Allowed files

```text
backend/pyproject.toml
backend/scripts/mutation_policy.py
backend/tests/test_mutation_policy.py
scripts/git_delta.py
scripts/test_git_delta.py
scripts/workstream_agent_gate.py
scripts/behavior-claim.schema.json
scripts/mutation-requirements.txt
scripts/test_lightweight_agent_gates.py
.ci/behavior-claims/WS-QUAL-001-04M.json
.ci/behavior-claims/README.md
.github/workflows/mutation-pilot.yml
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**
```

## Not allowed

```text
backend/app/** or backend/alembic/** changes
global or blocking mutation percentage
change to the global 78-percent or protected 90-percent coverage floors
replacement, reduction, or bypass of Backend semantic lanes, API E2E, or fan-in
full-backend mutation on ordinary PRs
mutation pragmas or free-form exclusion lists
production dependency changes
pull_request_target, privileged PR-code execution, writable workflow token,
checkout credentials, secrets in mutation execution, or unpinned Actions
```

## Acceptance criteria

- [ ] One engine and transitive closure are exactly pinned and hash locked as
      development/CI-only dependencies, installed exclusively from
      `scripts/mutation-requirements.txt` with `--require-hashes`.
- [ ] `backend/pyproject.toml` contains configuration only; the mutation engine
      is absent from production dependencies and ordinary dev extras.
      `scripts/mutation-requirements.txt` is the sole mutation-tool dependency
      authority; `backend/uv.lock` remains unchanged and is not a second install
      path.
- [ ] Deterministic policy selects eligible changed targets or validates a
      bounded test-only behavior claim with explicit owning test nodes.
- [ ] Git-delta discovery extracts one shared `scripts/git_delta.py` primitive
      reused by `scripts/workstream_agent_gate.py` and mutation policy, and
      mutation evidence mirrors the
      existing semantic-lane exact-tree/digest/fail-closed conventions rather
      than creating a parallel custody dialect.
- [ ] Schema-v1 `.ci/behavior-claims/<chunk-id>.json` is the only test-only
      claim input; PR prose, labels, workflow inputs, and environment variables
      cannot widen production targets or owning test nodes.
- [ ] `.ci/behavior-claims/README.md` and the backend testing operations guide
      document the pilot format without presenting it as a blocking contributor
      requirement before 05M.
- [ ] Disposable execution cannot leave mutants in the checked-out source tree.
- [ ] Evidence binds exact tree, tool/config, target/test identities, elapsed
      time, and generated/killed/survived/timeout/suspicious/excluded/error
      outcomes.
- [ ] Known strong behavior tests kill representative mutants and a deliberately
      weak fixture leaves a representative mutant alive.
- [ ] Score is observational; infrastructure errors, malformed/stale evidence,
      target escape, or baseline test failure remain blocking.
- [ ] Mutation command is bounded to 12 minutes inside a 15-minute independent
      job and records critical-path impact.
- [ ] Workflow runs untrusted PR code only through `pull_request`/`push`, uses
      explicit read-only permissions, pinned Actions, `persist-credentials:
      false`, no secrets or writable token in mutation execution, and bounded
      non-restorable artifacts/caches; invariant tests enforce each property.
- [ ] Full Backend and existing coverage gates remain unchanged and green.

## Verification commands

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_mutation_policy.py
.venv/bin/ruff check scripts/mutation_policy.py tests/test_mutation_policy.py
cd ..
python3 scripts/check_markdown_links.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

- Is target/test selection deterministic and non-gamable?
- Is result evidence complete enough to calibrate a later blocking policy?
- Is hosted runtime practical without weakening Backend?

## Stop conditions

Stop if the engine cannot be pinned, mutates the contributor worktree, requires
full-suite-per-mutant execution, produces unclassifiable noise, exceeds runtime
bounds, or requires weakening any existing gate.
