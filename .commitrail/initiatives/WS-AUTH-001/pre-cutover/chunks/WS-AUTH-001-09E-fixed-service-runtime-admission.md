# Chunk Contract: WS-AUTH-001-09E - Fixed Service Runtime Admission

## Goal

Admit verified, explicitly provisioned service subjects into a separate typed
authorization path that selects only the fixed service identity's exact static
ActionId row. This chunk activates no feature action.

## Risk

L1 / P1. Required reviewers: senior engineering, QA/test, security/auth,
product/ops, architecture, CI integrity, docs, reuse/dedup, and test delta.

## Prerequisites

- AUTH-09A's fixed service-identity field and static service-action matrix are
  merged;
- AUTH-09B controlled provisioning can create the exact service ActorProfile
  and one active identity link;
- AUTH-09C administrative reads plus AUTH-09D-A profile lifecycle and 09D-B
  identity-link lifecycle are merged;
- service lifecycle state is canonical and no feature service action is active
  merely because this chunk starts.

## Allowed files

```text
backend/app/api/deps/authorization.py
backend/app/modules/actors/**
backend/app/modules/authorization/**
backend/app/modules/artifacts/service.py
backend/tests/test_actors.py
backend/tests/test_auth.py
backend/tests/test_authorization.py
backend/tests/test_api_controls.py
backend/tests/test_artifact_admission.py
backend/scripts/api_contract_e2e.py
scripts/test_agent_gates.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-09E.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

`scripts/test_agent_gates.py` may change only to maintain exact deterministic
authored-state assertions for contributor foundation PR #153 and active
AUTH-09E branch/queue/map/status wording. Preserve stale-state negative checks,
unrelated initiative assertions, gate discovery and failure behavior, required
tracks, skips/exclusions, and every coverage threshold.

The artifact service and admission test are allowed only for the merge-induced
closed-context compatibility repair after trusted main introduced ART-02C1.
They may replace the stale exact check against the former concrete
`AuthorizationContext` with exact membership in the human/service context
types and update fixtures/proof accordingly. They may not change artifact
lifecycle, persistence, capacity, provider I/O, or action availability.

## Not allowed

```text
human first-access provisioning for service subjects
AdminRoleGrant, ProjectRoleGrant, Contributor, or human self-profile authority
client-supplied service identity, ActionId, PermissionId, role, or matrix membership
dynamic service grants, shared catch-all service identity, or permission union
feature resource composition, lifecycle behavior, adapter I/O, or action activation
application startup failure solely because a provisionable service row is absent
any Alembic migration or migration-number allocation; ART-owned
`0028_artifact_admission` is merged, AUTH-09E adds no revision, and any later
AUTH migration must allocate after `0028` from then-current trusted main
```

## Admission contract

```text
verified service token
-> exact ActorIdentityLink by configured issuer and opaque subject
-> active service ActorProfile
-> immutable fixed service_identity
-> exact static service-action matrix row
-> typed service AuthorizationContext
-> canonical feature ResourceContext and guards recomposed from locked rows
-> authorization decision
```

Human and service contexts are structurally distinct. Service context includes
the closed `service_identity`; human context cannot carry one. The service
candidate evaluator is selected before any human grant lookup and cannot fall
through to administrative or project contributor candidates.

The runtime types are an explicit closed union of
`HumanAuthorizationContext` and `ServiceAuthorizationContext`, discriminated by
literal `actor_kind`. Only the service context carries a required
`ServiceIdentity`. Existing human call sites migrate mechanically to the human
type; no optional service flag or compatibility fallback is permitted.

Service dispatch occurs before actor-self, administrative, project-role, or
contributor candidate lookup. It derives the exact link and profile only from
the verified token's issuer and opaque subject, validates service kind and
lifecycle state, converts the stored immutable identity through the closed
`ServiceIdentity` enum, selects exact `ActionId` membership from
`SERVICE_ACTIONS_BY_IDENTITY`, and then independently checks action
availability. PermissionId equivalence never supplies service authority.

AUTH-09E owns one reusable transaction-local service-authority revalidation
seam. It locks profile then the exact identity link, verifies unchanged row
identity, service kind, lifecycle state, `service_identity`, exact matrix
membership, and current action availability, and returns refreshed typed
service authority without committing. Later feature activation chunks own the
feature-composed locked `ResourceContext`, final feature-row recomposition, and
terminal mutation proof; this chunk neither fabricates those facts nor claims
end-to-end feature mutation coverage.

Successful exact active service resolution may stage monotonic
`last_verified_at` and `last_seen_at` observations in the caller-owned request
transaction. Unknown, mismatched, inactive, malformed, or unprovisioned
subjects stage no observations. Planned-action or other authorization denial,
cancellation, and persistence failure roll back staged observations before
bounded denial evidence is restaged in a clean transaction. Evidence contains
no issuer, subject, bearer material, token claims/scopes, or service secret.

Static code catalogue/matrix mismatch is an import/startup invariant and may
fail application startup. Missing provisioned service ActorProfile or
ActorIdentityLink database rows are request-local denials and must never block
startup or Access Administrator provisioning.

## Acceptance criteria

- Unknown, unprovisioned, mismatched, suspended, deactivated, or link-revoked
  service subjects deny without persistence or first-access creation.
- A service action outside the exact matrix row denies even when it maps to a
  PermissionId used by an allowed row.
- Planned actions remain unavailable. This chunk changes no feature action to
  active and attaches no ART, REV, CON, project, task, or checker call site.
- Sensitive mutation revalidation exposes the reusable AUTH-owned lock/reload
  seam described above and direct tests prove lifecycle, identity, matrix, and
  availability drift denial. Each later feature activation chunk must compose
  its canonical `ResourceContext` from its own locked rows before terminal
  state can commit. Request- or service-supplied resource facts remain
  untrusted hints and never become authority.
- Service callers never enter human self actions, AdminRoleGrant evaluation,
  ProjectRoleGrant evaluation, contributor candidates, or human rate controls.
- Missing provisioned rows deny the request but do not prevent startup or the
  Access Administrator provisioning path.
- Static matrix and admission parity reject missing/extra identities, rows,
  actions, changed mappings, and cross-service substitution.
- Tests prove exact candidate-row selection independently of universal planned
  action denial: every fixed artifact service matches only its own ActionIds,
  rejects every other service's ActionIds as `permission_not_granted`
  (including any same-PermissionId sibling) before availability can mask the
  missing candidate, and receives `action_unavailable` only for its own planned
  rows.
  A human cannot use service candidates and a service cannot use human grants.
- Dependency and kernel tests cover unknown/unprovisioned subjects, token/link/
  profile kind mismatch, revoked links, suspended/deactivated profiles,
  malformed stored service identity, zero first-access/rate-control/grant calls,
  zero persistence on admission denial, rollback of staged observations,
  missing database rows without startup failure, static matrix parity, and
  lock-time lifecycle/identity/matrix/action drift.
- Cancellation and injected decision-evidence persistence failure tests prove
  staged observations roll back, bounded denial evidence is restaged only from
  a clean transaction, and no issuer, subject, bearer material, claims, scopes,
  provider data, or service secret enters decision evidence.
- Focused authorization/actor coverage remains at least 90 percent and the
  repository-wide coverage floor does not regress.

## Verification commands

```bash
test -n "$WORKSTREAM_TEST_ADMIN_DATABASE_URL"
metadata_dir=$(mktemp -d)
trap 'rm -rf "$metadata_dir"' EXIT
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/auth-09e.json" \
  --timeout-seconds 3600 -- .venv/bin/python -m pytest -q \
  tests/test_actors.py tests/test_auth.py tests/test_authorization.py \
  tests/test_api_controls.py)
(cd backend && .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/api.json" \
  --timeout-seconds 3600 -- .venv/bin/python scripts/api_contract_e2e.py)
# After internal review, open the PR and require the GitHub Backend workflow.
# It runs the full suite at the repository-wide 78 percent floor and enforces
# the actor and authorization subsystem 90 percent floors on hosted runners.
gh pr checks --watch
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
git diff --check
```

## Stop condition

Stop after merge and signed memory. Do not start AUTH-10 or activate any feature
action automatically.
