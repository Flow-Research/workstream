# Chunk Contract: WS-ARCH-001-02B — PROJECT Locked Policy Public API

Implementation state: in review; on merge, this chunk is complete and
WS-ARCH-001-02C becomes the next eligible implementation boundary.

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Expose dependency-free immutable PROJECT facts and ports for the locked guide,
source snapshot, effective submission-artifact policy, and pre-submit policy
lineage referenced by one TASK context. This chunk installs the PROJECT-owned
capability; live caller composition and cutover remain in the later chunk that
owns those caller paths.

## Why this chunk exists

TASK's private pre-submit loader currently reads PROJECT ORM rows. Preparation
must obtain server-owned locked-policy facts from PROJECTS without transferring
PROJECT persistence or policy ownership to TASKS or ART.

Locked-context resolution is distinct from current-context selection. Exact
immutable rows that were validly locked by a task remain usable after they
become `superseded`; the port must never substitute their current successors.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02A is merged and its exact TASK fact manifest is recorded.

## Allowed files

```text
backend/app/modules/projects/api/**
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/tests/architecture/test_module_boundaries.py
backend/tests/test_ci_test_lanes.py
backend/tests/test_projects.py
backend/tests/projects/test_locked_policy_context.py
backend/scripts/behavior_ownership.py
backend/scripts/run_test_lanes.py
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02B-project-locked-policy-api.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02B-project-manifest.md
docs/architecture_lockdown.md
```

## Not allowed

Policy recompilation or approval changes; AUTH/ART activation; CHECKER plan
ownership; ORM/session/repository or mutable policy bodies in `projects.api`;
new private edges; live TASK/ART/CHECKER caller cutover or composition wiring.

## Acceptance criteria

- [x] PROJECTS validates exact project/guide/snapshot/policy lineage under its
      own locks and returns immutable canonical facts/digests.
- [x] Cross-project, successor-substituted, draft/pending/incomplete,
      non-canonical, missing, and hash-mismatched context fails closed.
- [x] Exact task-locked guide, effective-policy, and compiled pre-submit-policy
      rows remain valid after later `superseded` transitions; active/current
      selection semantics are not used by this port.
- [x] The public port exposes canonical JSON policy bodies only as deeply
      immutable values. PROJECT owns their validation; later CHECKER consumers
      may interpret them, while TASK and ART may only pass them through.
- [x] No live consumer is cut over in this chunk. The exact PROJECT capability
      is composed into callers only in a later contract that permits the
      application/composition paths; no session or concrete PROJECT factory is
      exported to work around that boundary.
- [x] Public API dependency/leak/cycle and protected-ledger checks pass.
- [x] Record the exact PROJECT fact/port manifest in
      `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02B-project-manifest.md`.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/projects tests/architecture/test_module_boundaries.py tests/projects/test_locked_policy_context.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_asyncio.plugin -p pytest_cov.plugin tests/architecture/test_module_boundaries.py tests/projects/test_locked_policy_context.py --cov=app.modules.projects.api --cov-report=term-missing --cov-fail-under=90)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Exact historical locked-policy lineage, deep immutable output, successor
non-substitution, and absence of PROJECT behavior inside TASK or ART.

## Stop conditions

Stop if the seam needs mutable policy payloads, bypasses locked lineage, or
changes guide/policy lifecycle.
