# Chunk Contract: WS-CON-001-PLAN3 - AUTH And REV Current-Main Reconciliation

## Goal

Reconcile WS-CON planning with trusted `main` after merged AUTH PR #140 and the
later merged AUTH-09A/REV PR #128 boundary without implementing runtime
behavior, changing AUTH/REV-owned files, or weakening the
review/FinalAcceptance/contribution transaction.

## Risk

L0/L1 authorization, transaction, and release specification; P1.

## Allowed files

```text
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/AUTHORIZATION_HANDOFF.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/CHUNK_MAP.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/CONFORMANCE_MATRIX.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/DECISIONS.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/DISCOVERY.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/INTENT.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/JOINT_RELEASE_HANDOFF.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/PLAN.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/RISKS.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/RUNTIME_VERIFICATION.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/SOURCE_MANIFEST.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/STATUS.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-01-canonical-contract-adoption.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-02A-shared-outbox-persistence.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-02B-shared-outbox-dispatcher.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-02C-shared-lifecycle-audit-participant.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-03C-contribution-award-persistence.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-03D-delivery-receipt-status-persistence.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-04A-hidden-adapter-binding-service.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-04B-hidden-contribution-policy-service.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-05A-legacy-economic-terms-cutover-and-task-freeze.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-05B-legacy-economic-schema-removal.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-06-review-lease-contribution-policy-freeze.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-07-atomic-review-contribution-award-participant.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-08A-outbound-compensation-delivery.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-08B-inbound-fulfillment-callback.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-08R-bound-service-rate-control.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-09B-authorized-contribution-evidence-read.md (deletion only; moved to deferred/)
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/deferred/WS-CON-001-09B-authorized-contribution-evidence-read.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-10A-contribution-award-product-reads.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-10B-operations-reconciliation-rebuild.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-10C-operations-executors.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-11-hidden-release-readiness.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/reviews/WS-CON-001-PLAN-internal-review-evidence.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/reviews/WS-CON-001-PLAN2-internal-review-evidence.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/reviews/WS-CON-001-PLAN3-internal-review-evidence.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/reviews/WS-CON-001-PLAN3-external-review-response.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/reviews/WS-CON-001-PLAN3-pr-trust-bundle.md
.agent-loop/REVIEW_LOG.md
.agent-loop/merge-intents/WS-CON-001-PLAN3.json
```

## Not allowed

```text
backend application, migrations, tests, workflows, dependencies, or runtime catalogue edits
AUTH/REV/ART/XINT initiative or implementation edits
active product-document changes without a newly discovered canonical mismatch
new PermissionId, ActionId, ServiceIdentity, grant, or action activation
feature-owned authorization evaluator, grant query, or availability writer
FinalAcceptance API/action or adjudication lifecycle/dependency
reference specification/PDF edits, restoration, rename, or replacement
```

## Acceptance criteria

- [x] Trusted baseline is merged REV PR #128 at `0302bcf`, containing AUTH-09A
  after PR #140. The runtime catalogue has 74 PermissionIds, 65 ActionIds, nine
  active and 56 planned, with no registered CON-specific or task-claim ActionId.
- [x] CON consumes AUTH's exact prepared mutation protocol: AUTH locks current
  authority first and creates an opaque single-use handle bound to session,
  ActionId, actor-reference kind/reference, idempotency key, and canonical
  request digest; feature rows lock afterward; final facts are recomposed; AUTH
  evaluates once and stages evidence; the route/command commits once.
- [x] CON never describes ServiceIdentity, static matrix membership, or action
  availability as database lock targets and never imports AUTH persistence or
  evaluates grants locally.
- [x] Only the stable `task.claim` PermissionId exists today; no task-claim
  ActionId is registered. After AUTH-10/PREP, CON-05A and task-owned freeze
  composition merge first; AUTH-13 then enumerates/registers the exact action,
  integrates its evaluator, and activates only after merged proof. Existing
  `review.claim` and `review.decision` ActionIds remain planned and require the
  exact reviewer grant plus REV guards before activation.
- [x] `review.decision` activation requires the merged mandatory CON flush-only
  participant with two ordered operation-specific inputs and rollback-safe
  REV+CON single transaction. The reviewer operation precedes the branch; the
  accept-only submitter operation follows FinalAcceptance and accepted task
  effects. FinalAcceptance remains an internal REV consequence with no action/API.
- [x] All 19 REV actions are referenced through the complete AUTH custody
  transfer. CON names only its `review.claim` and `review.decision`
  dependencies and never owns or partially transfers ActionOwner metadata.
- [x] The existing 22 CON surface mappings and service-execution identifiers
  remain explicitly non-final proposals. Each requires a later exact
  feature-owned manifest, reviewed AUTH registration, hidden behavior, and
  AUTH-only activation; dispatcher authority is never inherited by handlers.
- [x] No adjudication dependency, retired compensation-policy compatibility
  path, ART call in
  core contribution creation, or independent CON commit is introduced.
- [x] Required internal reviewers pass the exact final snapshot, deterministic
  gates pass, the PR trust bundle is complete, and exactly one PLAN3 merge
  intent is present in the branch delta. Older PLAN/PLAN2 evidence receives a
  provenance-only rebind when the PR-level gate requires every evidence file
  added by the cumulative branch to match the final reviewed revision.
- [x] Merged REV PR #128 release-control dependencies are reflected exactly:
  every fulfillment-obligation writer uses the shared lifecycle fence before
  allocating a monotonic root ordinal; the same-session drain port returns the
  maximum ordinal; and delivery-draining dispatch/callback paths are limited to
  same-generation roots at or below the persisted cutoff.
- [x] Every unresolved CodeRabbit thread is dispositioned: active chunks name
  deterministic runnable verification commands and pass criteria; AUTH-owned
  registration, context, custody, and activation remain prerequisites rather
  than CON-owned acceptance work; optional CON-09B is explicitly a deferred
  proposal pending a fresh contract; and the PR description carries the full
  trust bundle.

## Verification

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
git diff --check
git diff --quiet origin/main -- backend
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta. CI integrity is required if any script, workflow,
test, dependency, threshold, or runner changes.

## Stop

Stop after reviewed planning reconciliation, PR trust bundle, and merge-intent
preparation. Do not implement CON-01 or any runtime chunk, push, open, or merge
a PR without the user's explicit next instruction and merge approval.
