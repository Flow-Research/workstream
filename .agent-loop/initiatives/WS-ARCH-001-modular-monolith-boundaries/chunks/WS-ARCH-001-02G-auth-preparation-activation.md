# Chunk Contract: WS-ARCH-001-02G — AUTH Contributor Preparation Activation

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Activate exactly `artifact.submission_bundle.prepare` for the assigned
contributor over the merged 02D public-capability manifest.

## Why this chunk exists

AUTH availability is a separate security mutation from hidden ART behavior and
must be reviewed against exact merged facts rather than implemented alongside
the feature seam.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Entry gate

WS-ARCH-001-02A through 02F are merged. The exact 02D preparation manifest and
02F hidden transaction manifest match current `main`; production authority has
remained unavailable through those chunks.

## Allowed files

```text
backend/app/modules/authorization/api/**
backend/app/modules/authorization/**/submission*.py
backend/app/modules/authorization/catalogue.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/modules/authorization/repository.py
backend/app/adapters/auth/**
backend/app/adapters/artifacts/__init__.py
backend/app/modules/artifacts/submission_authorization.py
backend/app/modules/artifacts/authorization.py
backend/app/modules/artifacts/submission_admission.py
backend/app/modules/artifacts/service.py
backend/tests/test_authorization.py
backend/tests/test_submission_bundle_admission.py
backend/tests/test_default_pre_submit_execution.py
backend/tests/architecture/test_authorization_boundary.py
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02G-auth-preparation-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/STATUS.md
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02G-preparation-activation.md
docs/spec_authorization_service.md
docs/architecture_data_model.md
docs/roadmap_status.md
```

## Not allowed

New action/permission/service identity; TASK `submission.create` command
activation or `artifact.submission.binding.create` activation;
revision/remediation contexts; ART/TASK persistence; generic download; private
AUTH imports by product modules; database migration or schema mutation.
Do not create a submission-local handle registry, evaluator, or second PREP
protocol; extend the existing kernel and `PreparedAuthorizationService` exact
binding path.

## Acceptance criteria

- [ ] Only ActionId `artifact.submission_bundle.prepare`, mapped to existing
      PermissionId `submission.create`, becomes available for an exact active
      assigned contributor. This does not activate the TASK Submission command
      or the later fixed binding action.
- [ ] Preflight and final transaction-bound preparation use the merged opaque
      handle/public fact manifest and the existing kernel/prelocked/PREP path.
- [ ] Preliminary AUTH concealment runs before TASK disclosure; ART then locks
      exact assignment/task/project facts through public owner ports and calls
      the typed AUTH revalidation seam before reading the first request byte.
      AUTH does not import TASK persistence.
- [ ] AUTH owns strict preliminary/final resource contexts. Final binding
      covers actor and identity link; project, task, assignment and predecessor
      id/version; passing evidence and prepared generation; guide, snapshot,
      effective policy, checker policy and effective plan; semantic manifest;
      archive digest/bytes/media type; storage scheme; operation identity;
      idempotency/request digest; session/transaction; and nullable replay
      intent exactly as recorded by the merged ART manifest.
- [ ] Registry custody remains the existing `WS-XINT-002-05A` row while this
      replacement executable chunk flips only its availability; no alias,
      duplicate owner, or second action path is introduced.
- [ ] Live positive proof consumes the prepared handle before capacity, put
      intent, or provider I/O and produces one verified ready admission through
      the hidden route; exact replay produces no second write, charge, evidence
      set, admission, or provider I/O. The proof uses PostgreSQL and real AUTH
      PREP composition rather than forged or monkeypatched handles.
- [ ] Revoked identity/grant/assignment, stale context, wrong action/session/
      transaction/resource, replay and copied handle deny before protected work.
- [ ] Existing fixed pre-submit materialization and internal storage-service
      authorities remain unchanged; no fixed binding authority or TASK
      Submission consumption becomes available.
- [ ] AUTH and general boundary ledgers do not grow.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/authorization app/adapters/auth app/adapters/artifacts app/modules/artifacts/submission_authorization.py app/modules/artifacts/submission_admission.py app/modules/artifacts/authorization.py tests/test_authorization.py tests/test_submission_bundle_admission.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_submission_bundle_admission.py tests/test_default_pre_submit_execution.py tests/architecture/test_authorization_boundary.py --cov=app.modules.authorization --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
(cd backend && .venv/bin/python -m pytest -q tests/architecture/test_module_boundaries.py tests/test_artifact_architecture.py --no-cov)
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

Exact action/permission/actor scope, denial ordering, and proof that no adjacent
authority was activated.

## Stop conditions

Stop if 02A-02F are not merged, either resource manifest changed, or activation
needs a new catalogue value or broader grant.

## Merge state

- Outcome on merge: `complete`
- `WS-ARCH-001-02G` becomes complete only after the exact-head hosted gates,
  required internal reviewers, and human merge succeed.
