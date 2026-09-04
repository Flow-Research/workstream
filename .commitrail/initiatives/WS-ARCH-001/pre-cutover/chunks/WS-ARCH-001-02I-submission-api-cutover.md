# Chunk Contract: WS-ARCH-001-02I — Admission-Only Submission API Cutover

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Make verified ready-admission consumption the only live contributor Submission
path and remove the complete legacy standalone precheck/caller-owned artifact
contract in one clean cut.

## Why this chunk exists

The live route must never allow unchecked legacy creation or two competing
artifact identities. Public reachability changes only after hidden ownership,
atomicity, and authority are proven.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02A through 02H are merged, all exact owner/resource manifests match
current `main`, and all required production AUTH actions are available only to
their specified human or fixed-service authority. In addition, reviewed
WS-ARCH-001-03/04/05 replacement contracts have merged the checker-remediation
and reviewer-requested revision preparation/consumption contexts, post-submit
checker materialization/output plus failure-repair visibility, and exact REV
admission handoff. Initial, checker-remediation, and human-review revision all
use the same verified admission contract before this cutover begins.

## Allowed files

```text
backend/app/modules/tasks/router.py
backend/app/modules/tasks/schemas.py
backend/app/modules/tasks/service.py
backend/app/modules/tasks/api/**
backend/app/adapters/**/submission*.py
backend/app/main.py
backend/app/interfaces/artifact_operations.py
backend/alembic/versions/<next-current-main-revision>.py
backend/tests/test_tasks.py
backend/tests/test_submission_api.py
backend/tests/test_submission_concurrency.py
backend/tests/test_submission_history.py
backend/tests/test_auth.py
backend/tests/test_alembic.py
backend/tests/test_checkers.py
backend/tests/test_checker_materialization.py
backend/tests/test_review_queue_persistence.py
backend/tests/architecture/**
.ci/module-boundaries/private-edge-debt.v1.json
.ci/behavior-ownership/**
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/AUTH_HANDOFF.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02I-submission-api-cutover.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02I-cutover.md
docs/template_submission_packet.md
docs/spec_artifact_storage_service.md
docs/architecture_data_model.md
docs/roadmap_status.md
```

## Not allowed

ZIP/precheck semantic changes; implementing missing revision/checker/review/
contribution behavior inside this cutover; generic download; alias, redirect, fallback, dual route, caller package hash/
URI/manifest compatibility, or second checker registry.

## Acceptance criteria

- [ ] `POST /tasks/{task_id}/submissions` accepts summary, contributor
      attestation, and one ready-admission ID—not provider URI/hash/manifest.
- [ ] The standalone submission-precheck route/schema/service entry point and
      the internal legacy guard are absent; canonical not-found/openAPI/import
      tests prove no compatibility path remains.
- [ ] Non-ready, stale, consumed, pending, failed, cross-task/project/actor,
      wrong-predecessor and mixed legacy requests fail closed.
- [ ] Exact replay is stable; concurrent consumption creates one Submission,
      binding, transition, evidence set and downstream identifier-only dispatch.
- [ ] Initial, checker-remediation, and reviewer-requested revision requests
      preserve exact predecessor, CheckerRun or Review obligation, and locked
      context lineage; `needs_revision` always accepts a new complete ZIP and
      creates a new immutable Submission.
- [ ] Post-commit pre-review dispatch is exactly-once/idempotent, and dispatch
      failure is visible and repairable without changing the accepted artifact
      identity or duplicating checker work.
- [ ] Final checker outcome and verified artifact identity can reach the exact
      REV admission contract; no Submission becomes reviewable without them.
- [ ] Responses expose immutable Workstream identities only, never provider
      URLs or credentials.
- [ ] Touched legacy private edges are removed and hosted coverage/gates pass.
- [ ] No submission preparation/binding type remains in the legacy shared
      `app.interfaces` namespace after the canonical `artifacts.api` cutover.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/tasks app/adapters app/main.py tests/test_submission_api.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_tasks.py tests/test_submission_api.py tests/test_submission_concurrency.py tests/test_submission_history.py tests/test_auth.py tests/test_alembic.py tests/test_checkers.py tests/test_checker_materialization.py tests/test_review_queue_persistence.py --cov=app.modules.tasks --cov-fail-under=90)
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Complete clean cut, absence of dual authority, public request/response shape,
exactly-once effect, and downstream identifier-only dispatch.

## Stop conditions

Stop if any 02A-02H or named WS-ARCH-001-03/04/05 dependency is unmerged, any
submission context is still legacy-only, checker failure/repair or REV
admission proof is absent, the legacy route cannot be removed atomically, a
compatibility path is requested, or checker/revision semantics must change.
