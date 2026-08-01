# Chunk Contract: WS-AUTH-001-12D2 — Review And Revision Policy Mutation Separation

## Status and prerequisite

Proposed and inactive after 12D.

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Add separately authorized routes for review and revision policy records after
12D alone removes the embedded guide create/update fields.

This contract is reconciled with REV-03P by WS-XINT-003-01. REV owns the
immutable/versioned policy semantics; AUTH owns the mutation authorization,
PREP consumption, and decision evidence. WS-XINT-003-02A first installs exact
immutable policy identity and downstream lineage without activation; 02B then
implements the single writer path below. Neither parent contract may build an
alternate writer.

## One writer path

- Surviving API: separate `PUT /projects/{project_id}/review-policy` and
  `PUT /projects/{project_id}/revision-policy` routes in the dedicated
  `backend/app/modules/projects/policy_mutation_router.py`, registered once by
  `backend/app/api/router.py`, each declaring its exact primary ActionId. This
  follows the project-create and guide-mutation router boundary on current main.
- Surviving service: new `ProjectPolicyMutationService` methods
  `replace_review_policy()` and `replace_revision_policy()`.
- Surviving repository: new append-only
  `ProjectRepository.add_review_policy_version()` and
  `ProjectRepository.add_revision_policy_version()` methods over the existing
  `ReviewPolicy` and `RevisionPolicy` tables/models, upgraded as necessary for
  immutable version provenance.
- A separate `PolicyMutationReplayRepository` may own only the idempotency
  ledger. It must not read or write either policy table.
- Retired callable mutators: `ProjectRepository.upsert_review_policy()`,
  `ProjectRepository.upsert_revision_policy()`,
  `ProjectService._review_policy_model()`, and
  `ProjectService._revision_policy_model()`.
- No compatibility route, alias, second model/table, fallback constructor, or
  dual repository path survives.

Policies may be appended or replaced only while the exact guide version is a
draft. Activation freezes the selected policy versions: active-guide policy
rows are immutable, and later edits require a new draft guide/version rather
than an in-place update.

## Why this chunk exists

Guide management must not imply review/revision-policy authority. Retired
guide-bound economic policy remains CON-owned and has no AUTH-12 replacement.

## Risk class

L1

## SLA

P1

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/router.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/service.py
backend/app/modules/projects/authorization_reads.py
backend/app/modules/authorization/kernel.py
backend/app/modules/authorization/prepared.py
backend/app/modules/authorization/runtime.py
backend/app/api/deps/authorization.py
backend/alembic/versions/<then-current-next>_review_revision_policy_authority.py
backend/tests/test_authorization.py
backend/tests/test_projects.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
```

## Not allowed changes

Review execution/decision lifecycle, ContributionPolicy or award semantics,
fulfillment, guide metadata, submission/checker behavior, ART, or issuer-claim
compatibility.

## Acceptance criteria

- `project.review_policy.update` and `project.revision_policy.update` require
  an exact-project Project Manager grant with `project.review_policy.manage`.
- Entry requires merged 12D. 12D2 does not edit the removed guide payload fields
  or restore any compatibility alias.
- Each route locks the exact project, draft guide/version, current policy row,
  actor/link/grant/scope, consumes PREP once, and commits policy plus bounded
  decision evidence and provenance atomically.
- Each new/updated row records local actor profile, identity link, matched grant,
  project scope, action, and decision-event reference. Historical rows remain
  nullable/readable and are not rewritten.
- UUID idempotency, concealed 404 project-resource denials, canonical conflict,
  denial-evidence restaging, replay, revocation, cross-guide/project, stale row,
  and concurrency follow the parent invariants.
- OpenAPI declares exactly one primary action per new route and no compatibility
  endpoint is added.
- Tests prove old mutators are absent, direct update/delete of persisted policy
  versions is refused, stale draft/active guide, stale current policy,
  revocation, wrong grant/project/guide, replay, copied/wrong PREP handles, and
  crossed concurrent replacements deny without a partial policy or allowed
  decision record.

## Verification commands

Before start, freeze exact isolated-runner, Ruff, migration round-trip,
changed-project/authorization 90% coverage, repository-wide 78% coverage
baseline, API drill, stale-doc, link, and diff commands. Final pushed head SHA
must pass `Backend / test` and `Agent Gates`.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Exact review/revision resources, hard API cut, provenance, and strict CON
economic-policy ownership.

## Stop conditions

Stop if retired economic-policy behavior reappears, behavior expands past
review/revision configuration, or historical rows must be rewritten.
