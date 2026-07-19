# Chunk Contract: WS-AUTH-001-CONTRIBUTOR-FOUNDATION - Contributor Fields And Canonical-Human Lineage

## Status

Internal review passed. PR #152 merged AUTH-09D-B as `93dd392`; signed
schema-v2 memory at `912a6254` stopped and named this same-initiative
successor. The user explicitly started this chunk on 2026-07-19. Its branch
starts from trusted `main` at `93dd392`, whose single Alembic head is
`0026_actor_profile_lifecycle`. Exact contract `2a21166d` passed all required
L1 preimplementation reviewer tracks before runtime edits began.
Initial candidate `e41c33c0` failed diagnostic-privacy, exact proof, docs, and
evidence review. Bounded repair and deterministic evidence are complete; GitHub
Backend must still prove the full-suite 78 percent and actor/task 90 percent
reports before merge. Exact code SHA `4d1fc507` passed all nine required
internal tracks; PR publication and external checks are current.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Clean-cut the two current human attribution fields to `contributor_id`, bind
them to canonical human `ActorProfile` records at the database boundary, and
expose one transaction-local canonical-active-human revalidation capability for
later task and revision mutations.

## Why this chunk exists

The previous plan deferred the assignment rename to AUTH-13 and the submission
rename to AUTH-14. That ordering blocks REV from safely adding canonical task,
guide, and submission lineage until most product authorization cutovers finish.
This bounded schema foundation removes that cycle without activating an action,
changing a grant, or implementing review behavior.

## Risk class

L1

## SLA

P1

## Preconditions

- AUTH-09D-B is merged and signed automated memory names this chunk as its
  same-initiative successor.
- The branch is created from current trusted `main`, records the exact single
  Alembic head, and allocates only the then-current next migration.
- Preimplementation review approves the exact database primitive used to
  enforce human ActorProfile lineage and its downgrade behavior.

## Allowed files

```text
backend/app/modules/actors/{models,repository,service}.py
backend/app/modules/tasks/{models,schemas,repository,router,service}.py
backend/app/db/models.py
backend/alembic/versions/0027_contributor_foundation.py
backend/tests/test_actors.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
backend/tests/test_tasks.py
backend/tests/test_alembic.py
backend/scripts/api_contract_e2e.py
.github/workflows/backend.yml
scripts/test_agent_gates.py
docs/architecture_data_model.md
docs/operations_authorization_service.md
docs/spec_authorization_service.md
docs/spec_chunk_5_submission_packet_foundation.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-CONTRIBUTOR-FOUNDATION.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
permission, ActionId, owner, evaluator, or availability changes
project/admin role grant changes
AUTH-09E service admission or fixed-service authority
task, assignment, submission, checker, review, or revision lifecycle state or
transition changes beyond the exact active-human write guard below
Submission task-assignment lineage, predecessor chains, or guide stamps owned by REV
renaming the separately enumerated AUTH-14 attestation and contributor-facing fields
token-role removal, legacy workflow eligibility removal, or AUTH-13/14 route cutover
compatibility aliases, dual fields, fallback reads/writes, or data duplication
AuthorizationService, authorization runtime/resource contexts, authorization
repositories, permissions, decisions, or authority evidence
skip/xfail additions, assertion weakening, test deletion, coverage exclusion, or
coverage-threshold reduction
```

## Acceptance criteria

- The retired `TaskAssignment` human-owner field is clean-cut to
  `contributor_id` across the live PostgreSQL column and index, SQLAlchemy
  model, Pydantic response, service and repository references, new audit
  payloads, scripts, current docs, and generated OpenAPI. No property, response
  alias, shadow column, or dual write remains.
- The retired `Submission` human-owner field receives the same clean cut.
  Existing task,
  submission, checker, and revision behavior and attribution remain unchanged
  apart from the intentional response-field rename and fail-closed
  transaction-local active-human write revalidation.
- Both `contributor_id` columns are non-null `varchar(36)` foreign keys to the
  canonical `actor_profiles.id` root. The exact foreign keys are
  `fk_task_assignments_contributor_id_actor_profiles` and
  `fk_submissions_contributor_id_actor_profiles`. A single reviewed, reusable
  PostgreSQL lineage primitive rejects a service ActorProfile for either field.
- Preflight classifies each source row independently and in this order:
  `malformed` when the value does not match
  `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`; `missing`
  only for a well-formed value without an ActorProfile; and `service` only for a
  well-formed existing service ActorProfile. There is no assignment/submission
  cross-table inference in this chunk; REV-02C owns exact assignment lineage.
  One deterministic diagnostic contains total count plus at most 20 sorted
  `(row_id, actor_profile_id)` pairs per table/class. Malformed source values
  are replaced with `<redacted-malformed>`; well-formed missing/service UUIDs
  remain actionable. No issuer, subject, email, display name, or token data is
  emitted. Any class aborts atomically.
- Preflight refusal from exact head `0026` leaves the Alembic revision, both old
  column names/types/values, old index names/definitions, and the absence of
  new foreign keys, functions, and triggers unchanged. It never guesses an
  actor, maps by email, selects a current/latest assignment or profile, or
  fabricates remediation data.
- Existing valid values are preserved byte-for-byte while each column is
  renamed and narrowed from `varchar(100)` to `varchar(36)`. The indexes
  `ix_task_assignments_worker_id` and `ix_submissions_worker_id` are renamed to
  `ix_task_assignments_contributor_id` and
  `ix_submissions_contributor_id` with the same ordering and uniqueness.
- The exact invoker-rights function
  `require_human_actor_profile_reference()` accepts exactly one trigger argument
  naming a field present in `to_jsonb(NEW)`, uses that safe field extraction
  without dynamic SQL, and reads `public.actor_profiles`. A missing/extra
  argument or absent field fails with SQLSTATE `55000`; null returns `NEW` so
  the owning column decides nullability; no matching profile returns `NEW` so
  the foreign key emits `23503`; a found service profile fails with `23514`.
  Actor kind is immutable, and status is deliberately not checked by this
  historical-lineage trigger.
- Exact triggers `task_assignments_contributor_human` and
  `submissions_contributor_human` run before INSERT or UPDATE OF
  `contributor_id`. Direct SQL proves INSERT and contributor-ID UPDATE reject
  missing/service profiles, unrelated UPDATE does not invoke the guard, and
  active/suspended/deactivated human profiles remain valid without historical
  rewrite.
- Downgrade locks all three tables, checks for every non-owned trigger/dependency
  on `require_human_actor_profile_reference()`, and reports at most 20 sorted
  dependent object names. Any dependency refuses before DDL and leaves the
  upgraded schema intact. Otherwise it drops the two owned triggers and
  foreign keys, uses `DROP FUNCTION ... RESTRICT`, restores exact old index and
  column names/types, and preserves every ID, value, and row count.
- The actors module exposes exactly one transaction participant,
  `ActorService.require_active_human_write_actor(actor: ActorContext) -> None`.
  It reuses `ActorRepository.get_actor_profile(..., for_update=True)` with
  `populate_existing`, requires human/active, then locks the exact canonical
  identity link selected by verified issuer/subject, checks it belongs to that
  profile and is active, and returns no profile, link, grant, role, permission,
  action, claim, or decision data. This is identity revalidation, not a second
  authorization path.
- Claim and submission keep current coarse-role checks first, then use lock
  order `ActorProfile -> exact ActorIdentityLink -> WorkstreamTask -> active
  TaskAssignment`. `TaskRepository.get_task(..., for_update=True)` and
  `get_active_assignment(..., for_update=True)` refresh the locked rows;
  submission version allocation occurs while the task lock is held. Existing
  task-state, assignment, checker, and caller-owned commit behavior remains.
- Non-human, suspended, deactivated, or revoked-link callers receive stable
  non-disclosing 403 code `active_contributor_required` and message `Active
  contributor identity required`. A missing/mismatched canonical profile/link
  or SQL/lock failure rolls back and returns retryable 503 code
  `contributor_identity_unavailable` and message `Contributor identity
  verification unavailable`. Invalid legacy roles still fail before identity
  revalidation; active callers reach existing resource concealment rules.
- Named independent PostgreSQL sessions and observed
  `pg_stat_activity.wait_event_type='Lock'`, never timing sleeps, prove claim and
  submission against profile suspension and terminal deactivation in both lock
  orders (eight cases), plus identity-link revocation in both lock orders (four
  cases). Lifecycle-first makes the task write lose with no assignment,
  submission, evidence, checker result/call/enqueue, audit mutation,
  idempotency row, or partial state. Task-write-first proves the valid write
  commits before the later lifecycle transition and preserves its history.
- Behavior tests preserve claim, start, initial submit, checker-caused revision
  resubmission, audit history, idempotency, concealment, and rollback behavior
  while asserting the canonical `contributor_id` response and evidence shape.
- Migration tests cover valid upgrade/downgrade/upgrade, each unsafe preflight
  refusal, direct-SQL kind enforcement, dependency-aware downgrade refusal, and
  one Alembic head.
- Changed actor and task modules remain at or above 90 percent focused
  coverage. CI adds a persistent task-subsystem 90 percent report without
  changing existing actor/authorization gates or the repository-wide 78
  percent command. Whole-app coverage remains at or above 78 percent.
- The clean-cut corpus is live tables/indexes/constraints, `backend/app`, public
  schemas/OpenAPI, `backend/scripts`, and the current docs allowed above.
  Historical migrations `0003`/`0004`, immutable pre-0027 audit rows, archived
  loop/reference evidence, migration tests that exercise the prior schema,
  legacy role/eligibility tokens, `WorkstreamTask.assigned_to`, and the
  separately owned attestation field is an explicit exclusion. Existing
  audit rows are never rewritten; every new assignment/submission audit payload
  uses `contributor_id`.

## Proposed implementation

1. Allocate migration `0027_contributor_foundation` from the confirmed single
   head. Under an access-exclusive lock on `actor_profiles`,
   `task_assignments`, and `submissions`, run the exact three-class independent
   preflight, rename/narrow both columns and rename their indexes, then add the
   two named non-null foreign keys without changing any value.
2. Install the named invoker-rights trigger function and two named triggers.
   Foreign keys alone own existence, the trigger owns only immutable human kind,
   and normal column constraints own nullability.
3. Add the one actor-owned service operation that locks/revalidates the exact
   profile followed by the exact verified identity link. Do not edit
   authorization repositories, runtime contexts, decisions, grants, evidence,
   actions, or permissions.
4. Invoke it after the existing coarse role check and before the newly locked
   task/assignment reads in claim and submission creation. Implement the exact
   403/503 mappings and roll back every failed revalidation before responding.
5. Clean-cut the exact live corpus to `contributor_id`, including new audit
   evidence and OpenAPI. Preserve the enumerated historical/legacy exclusions;
   AUTH-13/14 and REV retain their separately declared work.
6. Prove migration refusal/preservation, direct-SQL behavior, the 12 observed
   lock races, and existing task/revision behavior before reviewer fanout.
   GitHub Backend is the mandatory pre-merge proof for focused 90 percent
   actor/task coverage, unchanged authorization coverage, and whole-app 78
   percent; do not merge unless every report passes.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python \
  scripts/run_isolated_tests.py --metadata-json <actor-metadata> \
  --timeout-seconds 3600 -- .venv/bin/python -m pytest -q tests/test_actors.py \
  tests/test_auth.py tests/test_tasks.py tests/test_alembic.py \
  --cov=app.modules.actors --cov-report=term-missing --cov-fail-under=90)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python \
  scripts/run_isolated_tests.py --metadata-json <task-metadata> \
  --timeout-seconds 3600 -- .venv/bin/python -m pytest -q tests/test_tasks.py \
  tests/test_alembic.py --cov=app.modules.tasks --cov-report=term-missing \
  --cov-fail-under=90)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python \
  scripts/run_isolated_tests.py --metadata-json <full-metadata> \
  --timeout-seconds 12600 -- .venv/bin/python -m pytest -q \
  --ignore=tests/test_isolated_database_runner.py --cov=app \
  --cov-report=term-missing --cov-fail-under=78)
(cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=<admin-db> .venv/bin/python \
  scripts/run_isolated_tests.py --metadata-json <api-metadata> \
  --timeout-seconds 3600 -- .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review the clean absence of retired human-owner identifiers, exact preservation of attribution,
database rejection of service identities, migration remediation/refusal, race
closure, and the absence of AUTH-13/14 or REV behavior.

## Stop conditions

Stop if migration requires guessed identity mapping, a second actor registry,
an API compatibility alias, changed lifecycle behavior, or an authorization
availability change. Stop after merge and signed memory; do not start AUTH-09E,
REV-02A, or another chunk automatically.
