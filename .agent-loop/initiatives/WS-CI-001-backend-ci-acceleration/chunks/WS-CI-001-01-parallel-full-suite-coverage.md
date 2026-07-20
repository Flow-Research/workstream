# Chunk Contract: WS-CI-001-01 — Parallel Full-Suite Coverage

## Parent initiative

`WS-CI-001` — Backend CI Acceleration

## Goal

Run every collected backend test across isolated parallel jobs and combine their
coverage in one fail-closed required Backend check, reducing wall-clock latency
without weakening evidence.

## Why this chunk exists

PR #161 proved the sequential full-suite step consumes 25 minutes 31 seconds of
an approximately 27-minute Backend job. This chunk addresses that bottleneck
before more product chunks incur the same delay.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
.github/workflows/backend.yml
backend/scripts/ci_test_shards.py
backend/tests/test_ci_test_shards.py
scripts/test_agent_gates.py
.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/**
.agent-loop/merge-intents/WS-CI-001-01.json
docs/operations_backend_testing.md
```

## Not allowed

```text
backend/app/**
backend/alembic/**
backend/pyproject.toml or dependency changes
existing backend test behavior or assertions outside the new planner tests
coverage threshold reductions
test skips, deselection, sampling, or path-based workflow suppression
shared-database parallel test processes
unpinned GitHub actions or container images
repository write permissions
changes to Agent Gates, human approval, or merge authority
WS-ENG-001-04B implementation or activation
```

## Acceptance criteria

- [ ] Canonical module inventory comes from symlink-safe filesystem discovery
      and includes every `backend/tests/test_*.py` module except an explicit
      declaration for the separately executed isolated-runner self-test; it
      rejects missing, extra, duplicate, noncanonical, symlinked, escaping, or
      zero-test modules and all collection errors.
- [ ] Canonical executable inventory includes every collected pytest node ID,
      including parameterized nodes, maps each node to exactly one module, and
      uses collected counts as initial shard weights.
- [ ] A schema-versioned deterministic manifest assigns every module exactly
      once across four file-level shards using stable weights and tie-breaking;
      canonical serialization binds schema, actual checked-out tree SHA, ordered
      modules, exclusion, stable test-base cardinalities, shard count, weights,
      and assignments.
- [ ] Every shard validates and runs at the manifest's actual checked-out tree
      SHA with its own digest-pinned PostgreSQL service,
      isolated migrated database/role, coverage filename, and result metadata.
- [ ] Real MinIO remains available to every shard unless executable discovery
      proves and reviewers approve a narrower fail-closed mapping.
- [ ] The API contract E2E proof runs concurrently with shards using its own
      isolated database.
- [ ] Test invocation uses validated whole-module paths through Python
      argv/subprocess arguments, never a shell-expanded list; repository-owned
      pytest hooks prove exact same-process collection/completion equality and
      bind stable test-base cardinalities back to preflight.
- [ ] Exactly four fixed-name artifacts bind checked-out tree SHA, canonical
      manifest digest, schema, shard ID, collected/completed nodes, and SHA-256
      of coverage.
- [ ] Fan-in accepts only allowlisted regular files and rejects symlinks,
      traversal, unexpected files, wildcard surplus, coverage-name collisions,
      credentials, database URLs, environment dumps, and unnecessary DB metadata.
- [ ] The final required Backend `test` job explicitly fails on any failed,
      cancelled, skipped, missing, extra, duplicate, malformed, or foreign
      prerequisite/artifact.
- [ ] Fan-in recomputes manifest and coverage digests, proves each shard's exact
      runtime collection equals its completions, and proves runtime stable
      signatures equal the canonical preflight signatures, rejecting missing,
      duplicate, foreign nodes and count disagreement.
- [ ] Coverage is combined only after complete fan-in and the exact existing 78
      percent global plus twelve 90 percent subsystem reports all pass.
- [ ] Workflow `Backend` and final job ID `test` preserve `Backend / test`; the
      final job uses `if: always()` and validates every `needs.<job>.result`.
- [ ] All actions, PostgreSQL, and MinIO references are immutable SHA/digest pins;
      explicit permissions are `contents: read` plus minimum artifact access, no
      repository write exists, and `pull_request_target` is absent.
- [ ] Hosted exact-checked-out-tree proof runs all shards and reports timing
      against PR #161 without claiming success from local estimates.
- [ ] The backend testing runbook documents diagnosis, artifact retention/schema,
      reruns/stale rejection, cost, check identity, progress, and atomic rollback.

## Verification commands

```bash
ruff check backend/scripts/ci_test_shards.py backend/tests/test_ci_test_shards.py scripts/test_agent_gates.py
python3 -m py_compile backend/scripts/ci_test_shards.py backend/tests/test_ci_test_shards.py scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q backend/tests/test_ci_test_shards.py scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q backend/tests/test_isolated_database_runner.py backend/tests/test_coverage_contract.py
python3 backend/scripts/ci_test_shards.py dry-run --repository-root . --shards 4
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format markdown
git diff --check
```

The dry run must perform real collection, plan four selections, synthesize the
expected shard-observation metadata without executing tests, and validate exact
inventory/provenance fan-in. Hosted PR evidence must additionally show all
Backend matrix jobs, API E2E, full
combined coverage, every protected subsystem report, Agent Gates, and external
review passing on the exact reviewed head.

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Inventory exactness, database/service isolation, failure propagation, artifact
provenance, coverage combination, unchanged thresholds, stable required-check
identity, and measured latency-versus-runner-cost tradeoff.

## Stop conditions

Stop and escalate if:

- complete coverage requires shared mutable database state across shards
- a test must be skipped or weakened to make sharding pass
- the final required check cannot fail closed on upstream cancellation/skipping
- coverage artifacts cannot be bound to exact commit and inventory
- a dependency or backend product change becomes necessary
- hosted wall time does not improve enough to justify added runner cost
- scope expands into path routing or `WS-ENG-001-04B`
