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
backend/app/adapters/auth/**
backend/app/adapters/artifacts/__init__.py
backend/alembic/versions/<next-current-main-revision>.py
backend/tests/test_authorization.py
backend/tests/test_submission_bundle_admission.py
backend/tests/architecture/test_authorization_boundary.py
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/chunks/WS-ARCH-001-02G-auth-preparation-activation.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/evidence/WS-ARCH-001-02G-preparation-activation.md
docs/spec_authorization_service.md
```

## Not allowed

New action/permission/service identity; Submission creation or binding action;
revision/remediation contexts; ART/TASK persistence; generic download; private
AUTH imports by product modules; migration number chosen before rebase.

## Acceptance criteria

- [ ] Only `artifact.submission_bundle.prepare -> submission.create` becomes
      available for an exact active assigned contributor.
- [ ] Preflight and final transaction-bound preparation use the merged opaque
      handle/public fact manifest.
- [ ] Live positive proof consumes the prepared handle before capacity, put
      intent, or provider I/O and produces one verified ready admission through
      the hidden route; exact replay produces no second write, charge, evidence
      set, or admission.
- [ ] Revoked identity/grant/assignment, stale context, wrong action/session/
      transaction/resource, replay and copied handle deny before protected work.
- [ ] No fixed binding authority or Submission consumption becomes available.
- [ ] AUTH and general boundary ledgers do not grow.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app/modules/authorization app/adapters/auth tests/test_authorization.py)
(cd backend && export WORKSTREAM_TEST_DATABASE_URL="${WORKSTREAM_TEST_DATABASE_URL:?set WORKSTREAM_TEST_DATABASE_URL}" && .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_submission_bundle_admission.py tests/architecture/test_authorization_boundary.py --cov=app.modules.authorization --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
(cd backend && .venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main)
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
