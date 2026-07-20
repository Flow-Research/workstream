# Chunk Contract: WS-REV-001-02A3 - Guide Activation Chronology

## Goal

Add immutable per-project Project Guide activation chronology and canonical
human approval provenance on top of the merged Project/setup publication fence.
Preserve the public route and existing `PROJECT_SETUP_ROLES` coarse authorization,
add an explicitly no-write active-repeat success, and keep superseded-guide
reactivation denied.

## Risk Class

L1 schema, migration, authorization-lineage, and activation concurrency.

## Preconditions

- `WS-REV-001-02A1` is merged and its complete writer inventory is still
  current.
- `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` PR #153 and its reusable human-reference
  function remain present on trusted main.
- The user separately starts this child. The start refresh records the sole
  Alembic head and allocates only its then-current next revision.

## Database Contract

`ProjectGuide` adds:

```text
activation_sequence BIGINT NULL
approved_by VARCHAR(36) NULL
```

The migration creates these exact objects:

```text
ck_project_guides_activation_sequence_positive
ck_project_guides_activation_state
uq_project_guides_project_activation_sequence
uq_project_guides_context_triplet
fk_project_guides_approved_by_actor_profiles
project_guides_approved_by_human
guard_project_guide_activation_history()
project_guides_activation_history_guard
```

The two unique constraints cover exact columns:

```text
uq_project_guides_project_activation_sequence
  (project_id, activation_sequence)
uq_project_guides_context_triplet
  (project_id, id, version, activation_sequence)
```

`fk_project_guides_approved_by_actor_profiles` references
`actor_profiles(id)`. `project_guides_approved_by_human` executes the existing
`public.require_human_actor_profile_reference('approved_by')` trigger function
configuration. This chunk does not create, replace, or drop that AUTH function.

Status/provenance is exact:

```text
draft      -> sequence, approved_by, effective_at, superseded_at are all NULL
active     -> positive sequence, approved_by, effective_at are present; superseded_at is NULL
superseded -> positive sequence and all provenance are present;
              superseded_at >= effective_at >= created_at
```

Active also requires `effective_at >= created_at`. The activation update may
allocate only status, activation sequence, approver, effective time, and the
database-maintained update time; all draft content/context/creation fields stay
unchanged. After first activation, the entire ProjectGuide row is immutable
except the exact lifecycle transition fields. `active -> superseded` may change
only status, `superseded_at` from NULL to one database timestamp, and the
database-maintained update time. The guard then rejects every change or clear,
including changes to `id`, `project_id`, `version`, content, change summary,
creator/creation time, activation sequence, approver, effective time, or
superseded time. Status may move only `draft -> active -> superseded`; active
no-write repeat is unchanged-row idempotency, and `superseded -> active` remains
rejected. The later 02A2 chunk owns the reviewed guard amendment that permits
only its exact reactivation transition while continuing to freeze all original
context, content, creation, and approval facts.

## Migration Contract

- Lock `actor_profiles` and `project_guides` in access-exclusive mode before
  preflight and DDL.
- Refuse unknown status, polluted draft provenance, incomplete active/
  superseded provenance, invalid timestamp order, malformed/missing/non-human
  approver, or more than one active guide for a Project.
- Treat two non-draft guides in one Project with identical
  `(effective_at, created_at)` as ambiguous historical chronology and refuse;
  ID is used only for bounded diagnostics and deterministic ordering after the
  ambiguity check.
- Bound diagnostics by table/failure class and row count. Malformed actor
  values are redacted exactly as in migration 0027.
- Backfill each valid Project's active/superseded rows with `row_number()` over
  `effective_at, created_at, id`; drafts remain null.
- Refusal leaves the exact prior head recorded at the 02A3 start refresh, all
  original column shapes, data, constraints, and functions unchanged and creates
  none of this chunk's objects. Migration 0027 remains only the historical owner
  of the shared AUTH function; it is not a reserved future parent revision.
- Downgrade locks the same tables and refuses before DDL when any guide has
  allocated activation provenance or any later dependency references
  `uq_project_guides_context_triplet` or another chronology object. A safe
  draft-only downgrade removes this chunk's triggers, owned guard function,
  constraints, and sequence column in dependency order, restores
  `approved_by VARCHAR(100)`, and never drops the shared AUTH function.

## Activation Command Order

```text
existing PROJECT_SETUP_ROLES coarse check
-> Project FOR UPDATE
-> ActorProfile FOR UPDATE
-> exact ActorIdentityLink FOR UPDATE
-> ProjectGuide rows by ascending id
-> remaining setup rows in the merged 02A1 type/id order
-> revalidate actor/link, guide status, ownership, and complete setup
-> read one database timestamp
-> allocate max(project activation_sequence)+1 for first activation only
-> supersede current active guide and activate candidate
-> commit once
```

ActorProfile and ActorIdentityLink form an activation-only identity fence after
Project. They do not reorder the 02A1 publication-row sequence, which still
begins at ProjectGuide and retains the same type/ID order for every command.

The actor/link revalidation reuses
`ActorService.require_active_human_write_actor`; it is transaction-local
identity/lifecycle validation after `get_registered_actor` has already returned
an ActorContext and after the existing role check. It is not a new authorization
path. Pre-service token verification and canonical-actor resolution keep their
current AUTH-owned envelopes, including `service_actor_not_provisioned`,
`identity_link_revoked`, `actor_suspended`, `actor_deactivated`,
`identity_verification_unavailable`, and actor-registry unavailability. 02A3
does not catch, translate, or replace those dependency outcomes.

Only a failure discovered by the post-dependency, post-lock ProjectService
revalidation maps to these Projects-owned structured public errors:

```text
403 active_project_approver_required
    "Active project approver identity required"
    retryable=false
503 project_approver_identity_unavailable
    "Project approver identity verification unavailable"
    retryable=true
```

A profile that becomes suspended or terminally deactivated, or a link that
becomes revoked, after ActorContext resolution maps to the Projects 403 when
detected under the transaction fence. Missing/inconsistent post-resolution
profile or link state and database failure during this revalidation map to the
Projects 503. Direct service misuse with a non-human ActorContext also returns
the Projects 403, but that is not the public service-token response. Both errors
roll back all guide/Project changes. Independent race tests first establish the
valid request ActorContext, then cover profile suspension, terminal
deactivation, and identity-link revocation relative to the ProjectService actor
lock in both commit orders: lifecycle-first returns the Projects 403 without
guide history; activation-first commits immutable approval and the later
lifecycle change does not invalidate it. No AUTH file, action, permission,
evaluator, or availability changes.

## Allowed Files

```text
backend/app/modules/projects/{models,schemas,repository,service,router}.py
backend/app/db/models.py
backend/alembic/versions/<then-current-next>_guide_activation_chronology.py
backend/tests/test_{alembic,projects}.py
.github/workflows/backend.yml only for additive/preserved coverage proof
docs/architecture_data_model.md
docs/architecture_lifecycle_state_machine.md
docs/spec_chunk_3_project_guide_foundation.md
docs/operations_operator_workflow.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02A3.json
```

## Not Allowed

```text
Project/setup writer inventory or lock-order changes beyond consuming 02A1
superseded-guide reactivation, If-Match, prepared AUTH, or 02A2 behavior
Task or Submission schema, stamping, lifecycle, or attribution
ReviewPolicy, RevisionPolicy, compensation-policy, ART, or CON semantics
AUTH schema, actions, permissions, grants, evaluators, or availability
review queue, Review, FinalAcceptance, or adjudication behavior
```

## Acceptance Criteria

- First activation allocates sequence 1; later activation allocates the next
  positive sequence while preserving every prior sequence and provenance.
- Concurrent activations serialize on Project and cannot duplicate or invert
  chronology. Database time after locks controls effective/superseded times.
- Active canonical-human Project Manager/Admin succeeds. Existing pre-service
  AUTH dependency denials retain their exact envelopes. Post-ActorContext
  transaction revalidation uses only the exact Projects 403/503 split, rolls
  back exactly, and never falls back to token/local identity.
- Profile suspension, terminal deactivation, and identity-link revocation races
  each run in both commit orders with independent sessions and observed
  PostgreSQL lock waits. Lifecycle-first returns the exact 403 without chronology
  or supersession; activation-first preserves committed historical approval.
- Repeating activation for the sole already-active candidate is an explicitly
  additive no-write idempotent success returning the same complete active
  response without changing sequence, timestamps, audit, or Project state.
- A superseded candidate remains denied; public route, body, response model,
  and coarse role authorization otherwise remain unchanged.
- Real-PostgreSQL tests prove preflight, upgrade, safe downgrade/re-upgrade,
  dependency/protected-row downgrade refusal, atomic failure, direct-SQL state,
  human-kind and complete activated-row immutability guards, and one Alembic
  head.
- Project subsystem coverage remains at least 90 percent and global coverage
  remains at least 78 percent without weakening another gate.

## Verification

```bash
(cd backend && .venv/bin/alembic heads)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q tests/test_alembic.py tests/test_projects.py)
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78)
(cd backend && .venv/bin/coverage report --include='app/modules/projects/*' --precision=2 --fail-under=90)
(cd backend && .venv/bin/python -m ruff check app/modules/projects app/db/models.py alembic/versions tests/test_alembic.py tests/test_projects.py)
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
backend/.venv/bin/python scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --unified=0 origin/main...HEAD -- backend/tests | (! rg '^-(.*assert|.*pytest\.raises|.*pytest\.mark\.(skip|xfail)|.*skipTest)')
git diff --check
```

## Required Reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human Review Focus

Historical refusal/backfill, shared AUTH function reuse, actor/project lock
order, lifecycle races, DB time, no-write active repeat, superseded denial, and
downgrade dependency safety.

## Stop Condition

Stop if historical chronology is ambiguous or AUTH schema/logic must change.
Merge, record automated memory, and stop. Do not start 02A4 automatically.
