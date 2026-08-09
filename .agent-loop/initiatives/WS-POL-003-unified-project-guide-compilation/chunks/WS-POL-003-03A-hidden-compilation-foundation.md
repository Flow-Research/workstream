# Chunk Contract: WS-POL-003-03A - Hidden Compilation Foundation

Status: Active after human start on merged AUTH boundary foundation. Risk: L1.

## Goal

Install the hidden durable foundation for one logical unified project-guide
compilation per exact setup generation. Add immutable attempt/result custody,
strict validation, append-only supersession, crash-safe repository transitions,
and deny-only authorization seams. Make no model call and change no live product
behavior.

## Why this chunk exists

POL-02 can perform one strict provider call, but Workstream cannot safely use it
until an attempt is reserved before I/O, uncertain provider outcomes retain the
same key, accepted output survives a crash before projection, and current
compilation selection cannot fork. AUTH also needs the exact hidden resource
manifest before AUTH-12I may activate request or execute authority.

This is the first capability repair under `WS-AUTH-003`: every new POL import of
AUTH uses only `app.modules.authorization.api`; no new private AUTH edge is
permitted. Existing unrelated private-import debt remains frozen.

## Exact modular shape

```text
app/modules/authorization/api/project_guide_compilation.py
  dependency-free request/execute facts and opaque capability Protocol

app/modules/projects/guide_compilation/
  authorization.py   deny-only project-side seam using AUTH public API
  contracts.py       attempt states, commands, and validated durable values
  models.py          attempt and immutable compilation tables only
  repository.py      short-transaction reservation/recovery/CAS operations
  validation.py      canonical result/context/hash revalidation
```

The package is internal to Projects. Cross-module consumers must later use a
Projects public API rather than import these files. This chunk creates no such
consumer and no composition-root wiring.

## Exact attempt identity and states

One attempt is uniquely bound to project, guide, guide version, source snapshot
and hash, setup run/generation, canonical input/material hashes, both catalogue
snapshot identities and hashes, configured agent identity/version, instruction
version, and one server-derived provider idempotency key.

```text
reserved -> provider_uncertain -> accepted -> persisted
reserved -----------------------> accepted
reserved/provider_uncertain ----> invalid_terminal
```

`invalid_terminal` and `persisted` are terminal. Invalid or unsafe output
consumes that generation. Transport uncertainty reconciles only under the
original attempt and provider key. Reservation commits before any future
provider I/O; this chunk performs no provider I/O.

`accepted` means provider-result custody only. It is not Project Manager
approval, the Review decision `accept`, guide activation, effective policy,
setup success, or contribution/reputation/compensation evidence.

Accepted canonical output and complete/component hashes are stored on the
attempt before inserting one immutable compilation. A later compilation names
its predecessor through `supersedes_compilation_id`; old rows are never updated
to express currentness. Database uniqueness plus repository compare-and-swap
allows one root and one child for an expected predecessor.

## Exact hidden authorization surface

`authorization/api/project_guide_compilation.py` defines only these frozen
dataclasses and Protocol; it imports no Projects or AUTH-private type:

- `ProjectGuideCompilationRequestFacts`: `project_id`, `guide_id`,
  `guide_version`, `source_snapshot_id`, `source_snapshot_hash`, `setup_run_id`,
  `setup_generation`, `operation_id`, `request_id`, `idempotency_key`,
  `pre_catalogue_id`, `pre_catalogue_version`, `pre_catalogue_schema_version`,
  `pre_catalogue_manifest_hash`, `post_catalogue_id`,
  `post_catalogue_version`, `post_catalogue_schema_version`,
  `post_catalogue_manifest_hash`, `agent_identity`, `agent_version`,
  `instruction_version`, and optional `expected_predecessor_compilation_id`.
- `ProjectGuideCompilationExecutePreflightFacts`: every request fact plus exact
  `attempt_id` and `provider_idempotency_key`.
- `ProjectGuideCompilationExecutePersistFacts`: every execute-preflight fact
  plus `result_hash`, `sufficiency_component_hash`,
  `artifact_policy_component_hash`, `pre_submit_policy_component_hash`, and
  `post_submit_policy_component_hash`.
- `ProjectGuideCompilationAuthorizationPort[PreparedHandleT]`:
  `prepare_request`, `consume_request`, `authorize_execute_preflight`,
  `prepare_execute_persist`, and `consume_execute_persist`. Every method takes
  exact `ActorIdentityFacts`, one exact fact type, and the action-specific
  opaque handle where applicable. Consume returns the committed authorization
  decision-event UUID.

Public facts use only UUIDs, bounded canonical strings, positive integers, and
the named immutable fields above. They reject `dict[str, Any]`, mutable
collections, raw guide text, raw/provider output, paths, URLs, credentials,
reasoning/traces, and unbounded values.

The future actions are:

- `project.guide_compilation.request`: human Project Manager request/recovery;
- `project.guide_compilation.execute`: fixed `workstream.project.setup`
  preflight and fresh transaction-bound accepted-result persistence.

Facts bind actor/identity link, exact project/guide/source/setup lineage,
operation/request/idempotency identity, catalogue and agent/instruction
identity, and—on final execute consumption—the accepted result/component
hashes. The project-side default always raises a stable AUTH boundary denial.
No handle is serializable or durable. No action, permission, evaluator,
service-matrix row, or availability changes in 03A.

The generic handle parameter never defines or exposes a concrete handle.
Production handles in AUTH-12I must be process-local, non-dataclass,
non-Pydantic, non-JSON, have no public serializable fields, and bind the exact
action, actor/link or service identity, request/idempotency identity, attempt,
resource facts, database session, and final transaction. They are never copied,
reconstructed, stored, logged, or placed in Celery. In 03A the deny-only seam
rejects every handle/value and wrong request/execute combination before an
instrumented repository/session is touched. AUTH-12I must additionally prove
copied, stale, cross-project, cross-generation, wrong-service, wrong-action,
wrong-session, and wrong-transaction real-handle denials before activation.

Project Manager request/recovery can only create the first reservation or
observe/resume the same exact attempt and provider key. Once an attempt is
`provider_uncertain`, `accepted`, `persisted`, or `invalid_terminal`, it cannot
allocate another key or bypass fixed-service execute custody.

## AUTH ledger delta

Private import ledger: **0 removals, 0 additions**. This is a new hidden
consumer and imports only `app.modules.authorization.api`. No existing Projects
AUTH consumer is touched. The public API leak/reachability test must include the
new module and prove it reaches no Projects or private AUTH module.

## Exact durable schema

Migration file `0062_project_guide_compilation_foundation.py` has
`revision = "0062_project_guide_compilation_foundation"` and
`down_revision = "0061_submission_admission"`; `HEAD_REVISION` changes to the
same new revision. This is valid only while that remains the sole main head.

`project_guide_compilation_attempts` requires:

- unique `uq_compilation_attempt_setup_generation(setup_run_id,
  setup_generation)` and `uq_compilation_attempt_provider_key`;
- positive generation, canonical `sha256:<64 lowercase hex>` checks for every
  identity/result/component hash, bounded identity/version fields, and bounded
  canonical JSON size;
- a state-shape check: reserved/uncertain exclude accepted output;
  `accepted` requires canonical result plus all hashes and no persisted
  compilation; `persisted` requires the same accepted values plus
  `persisted_compilation_id`; `invalid_terminal` excludes accepted/persisted
  values and requires one bounded allowlisted failure code;
- a transition trigger permitting only the closed state graph and rejecting
  identity, provider-key, accepted result/hash, timestamp, and terminal-state
  mutation outside its one legal transition;
- delete/truncate guards so a consumed generation cannot disappear.

`project_guide_compilations` requires:

- unique one compilation per `attempt_id`, partial unique one root per
  `(project_id, guide_id)` where predecessor is null, and unique one child per
  `supersedes_compilation_id`;
- a scoped predecessor FK that cannot cross project/guide, exact attempt and
  persisted-compilation linkage, positive strictly increasing setup generation,
  canonical hash checks, and fixed service/action custody values;
- update/delete/truncate guards: compilation rows are insert-only.

The database intentionally does not make `result_hash` globally unique: two
later exact generations may compile to the same canonical result. Identity is
the unique attempt; content integrity is enforced by hashes and revalidation.

## Allowed files

```text
backend/app/modules/authorization/api/__init__.py
backend/app/modules/authorization/api/project_guide_compilation.py
backend/app/modules/projects/guide_compilation/__init__.py
backend/app/modules/projects/guide_compilation/authorization.py
backend/app/modules/projects/guide_compilation/contracts.py
backend/app/modules/projects/guide_compilation/models.py
backend/app/modules/projects/guide_compilation/repository.py
backend/app/modules/projects/guide_compilation/validation.py
backend/app/db/models.py                         # metadata discovery only
backend/alembic/versions/0062_project_guide_compilation_foundation.py
backend/tests/architecture/test_authorization_boundary.py
backend/tests/projects/guide_compilation/**
backend/tests/test_alembic.py
backend/tests/conftest.py
.ci/behavior-ownership/partition.v1.json
.ci/behavior-ownership/auth/**
.ci/behavior-ownership/projects/**
backend/scripts/behavior_ownership.py        # exact POL-03A additions only
backend/tests/test_behavior_ownership.py     # exact transition proof only
backend/scripts/test_structure_boundary.py   # add exact POL-03A scope only
backend/tests/architecture/test_test_structure_boundary.py
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/assertion-maps/**
.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/STATUS.md
.agent-loop/initiatives/WS-POL-003-unified-project-guide-compilation/**
```

Changes to `tests/conftest.py` are limited to generic database plumbing; changes
to `test_alembic.py` are limited to exact migration registration/topology.
All compilation fixtures and behavior assertions live under the new focused
test package. The behavior-ownership transition accepts only the exact new
eligible files named by this contract and rejects removal, reassignment, extra,
or reordered custody. The structure validator adds the exact new package/tests
to its scope with zero permitted new debt.

## Not allowed

- Changes to broad `projects/models.py`, `projects/repository.py`,
  `interfaces/project_agents.py`, or existing project services/routes.
- Model/provider calls, Celery/setup cutover, live composition, or endpoint
  changes.
- AUTH runtime/evaluator/catalogue/permission/action/service-matrix changes.
- Policy projection, approval, checker execution, guide activation, or ART,
  task, submission, review, revision, contribution, or compensation behavior.
- Compatibility aliases, fallbacks, dual persistence paths, mutable-current
  flags, or prepared handles in rows/messages.
- Raw guide duplication, provider credentials/reasoning, or unbounded failure
  details in durable rows.
- New or increased private AUTH import debt or structural test debt.
- Wholesale cherry-pick/replay of WIP `1a7242f2`; only reviewed DDL, logic, and
  assertions may be selectively adapted into the new modular/test shape.

## Acceptance criteria

- Database and ORM enforce one attempt per exact setup run/generation, one
  provider key, complete identity/hash presence, and legal state/result shapes.
- Concurrent identical reservation returns one attempt; mismatched identity for
  the generation denies without inventing another provider key.
- Uncertainty reconciles only under the original provider key; unsafe output is
  bounded, terminal, and non-retryable for that generation.
- Accepted canonical JSON revalidates through the merged strict compilation
  result/context contracts and matches full/component hashes before insertion.
- Crash recovery from accepted-but-not-persisted inserts or returns exactly one
  immutable compilation without provider dispatch or policy projection.
- Append-only CAS permits one root and one child for an expected predecessor;
  stale/concurrent forks fail closed. Update/delete/truncate and identity/key
  mutation are rejected by Postgres.
- Request and execute seams deny before repository mutation. Only AUTH public
  API imports are introduced; the private-import ledger count does not grow.
- No transaction/lock spans provider I/O because 03A performs none and exposes
  only caller-owned short repository operations.
- Migration upgrade/downgrade, one-head topology, ORM parity, concurrency,
  rollback, immutability, and crash states are proven.
- New/changed subsystem coverage is at least 90%; hosted repository coverage
  remains at least 78%.
- Each new test owns one primary observable behavior; no new test or production
  function exceeds the structural policy limits. The extended structure gate
  inventories the exact new package/tests and permits zero new debt; test-delta
  review maps every new test to one named primary invariant.
- Recovery returns exactly one closed classification—`reserved`,
  `provider_uncertain`, `accepted_not_persisted`, `persisted`, or
  `invalid_terminal`—with bounded operator-safe reason codes. It never infers
  setup success, effective policy, guide activation, contribution,
  compensation, or reputation effects.
- Deny/attack proof uses an instrumented repository/session and covers PM
  execute, fixed-service request, wrong actor/link/service, stale generation,
  cross-project/guide/source replay, request-vs-execute misuse, copied handle
  values, result/component swaps, predecessor mismatch, unsafe text, and
  attempted raw provider text/secrets/paths/URLs/unbounded failure persistence.
- Concurrent identical reservation returns the same attempt/key; mismatched
  identity creates no key; uncertainty accepts only the original key;
  accepted-not-persisted recovery creates/returns one compilation; and terminal
  invalid state blocks retry for that generation.

## Verification commands

```bash
cd backend
uv run ruff check app/modules/authorization/api app/modules/projects/guide_compilation \
  app/db/models.py scripts/behavior_ownership.py scripts/test_structure_boundary.py \
  tests/projects/guide_compilation tests/test_alembic.py tests/conftest.py \
  tests/test_behavior_ownership.py tests/architecture/test_test_structure_boundary.py
uv run pytest -q tests/projects/guide_compilation \
  tests/architecture/test_authorization_boundary.py
uv run pytest -q tests/test_behavior_ownership.py \
  tests/architecture/test_test_structure_boundary.py
uv run pytest -q tests/projects/guide_compilation \
  --cov=app.modules.projects.guide_compilation --cov-fail-under=90
uv run pytest -q tests/test_alembic.py
uv run python -m scripts.authorization_boundary validate \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md
uv run python -m scripts.test_structure_boundary validate \
  --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md \
  --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json
uv run python -m scripts.behavior_ownership validate
cd ..
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check origin/main
```

Full backend tests and repository coverage run only in GitHub Actions.

## Required reviewers

- Architecture: public AUTH purity, Projects modularity, append-only graph, and
  absence of a competing protocol/path.
- Security/authorization: exact facts, opaque capability custody, deny ordering,
  safe durable fields, replay/uncertainty, and no private AUTH edge.
- QA: Postgres concurrency, crash transitions, stale CAS, rollback,
  immutability, and no-live-behavior proof.
- Product/operations: setup-generation consumption and terminal recovery without
  changing Workstream lifecycle truth.
- Senior engineering, test-delta, CI-integrity, docs, and reuse/dedup.

## Human review focus

- Can one setup generation ever cause a second logical provider attempt/key?
- Can accepted output survive a crash without becoming effective policy?
- Can append-only supersession fork under concurrency?
- Is the new exact AUTH surface dependency-free, opaque, and inactive?
- Did 03A remain hidden with zero live product behavior?
