# Chunk Contract: WS-XINT-002-02 Prepared Operation Boundaries

## Goal

Close the reusable PREP-to-ART operation interface without activating an ART
action or pretending that unmerged feature rows can already be composed.

This chunk preserves the existing opaque transaction-local PREP mechanism,
removes the obsolete upload-session interface, and makes every declared
durable ART mutation request carry opaque prepared authority instead of a raw
request authentication context. Exact feature-owned row composers and final
resource contexts remain owned by their evidence-backed activation chunks.

## Base

Reviewed against `main` merge commit `89956cff`.

## Risk class

L1.

## Allowed files

```text
backend/app/modules/authorization/prepared.py
backend/app/interfaces/artifact_operations.py
backend/tests/test_authorization.py
backend/tests/test_artifact_architecture.py
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/PLAN.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/DECISIONS.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/STATUS.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-02-prepared-feature-boundaries.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/reviews/WS-XINT-002-02-*.md
```

## Not allowed

- action activation, catalogue, migration, evaluator, kernel, repository,
  route, command, provider, durable-write, or product-lifecycle changes;
- feature repository imports in AUTH, caller callbacks, open dictionaries,
  generic service locators, caller-asserted feature facts, or a second
  capability implementation;
- production handle issuance for a planned ART action;
- defining task, assignment, CheckerRun, review lease, finding/response,
  predecessor, revision-obligation, or advancement-fence truth before its
  owning feature chunk merges.

## Closed interface changes

- Remove `ContributorArtifactUploadPort` and every upload-session request from
  the live interface; there is no compatibility alias.
- Add `SubmissionBundlePreparationPort.prepare` with one closed
  `SubmissionBundlePreparationRequest` for the outer ZIP.
- Replace `ReadyUploadSetRequest` with process-local
  `PreparedBundleMaterializationRequest`.
- Guide ingest, submission preparation, verified binding, prepared-bundle and
  binding materialization, and checker-output write requests carry an exact
  `PreparedAuthorizationHandle`; they do not accept `AuthorizationContext` as
  mutation authority.
- Each typed mutation method maps to one closed expected `ActionId`; guide,
  submission, and checker-output binding use separate request types with their
  exact owning selectors. Requests carry no caller-selected action, generic
  resource selector, or facts map.
- Operator read/recovery requests remain unchanged; their existing bounded
  authorization path is outside this durable mutation interface cut.
- Review-packet materialization and review-evidence binding are intentionally
  deferred to WS-XINT-002-07. They require merged REV lease/evidence-slot facts
  and will extend the same typed prepared-operation convention without adding a
  second capability protocol or a generic materialization/binding escape hatch.

## Acceptance criteria

- Existing PREP remains bound to the exact service instance, session, root
  transaction, action, actor, scope, idempotency key, and canonical request
  digest; handles remain opaque, non-copyable, non-serializable, and single-use.
- Production `prepare()` issues no handle or evidence for every planned ART
  action in this chunk. Matrix membership is checked first: a wrong fixed
  service receives `permission_not_granted`; the owning fixed service reaches
  planned availability and receives `action_unavailable`.
- Denial, evidence failure, participant failure, caller rollback, commit
  failure, timeout, or cancellation burns an issued handle outside database
  rollback semantics. Existing failure tests must retry the identical handle
  and prove rejection before a second kernel evaluation or evidence attempt.
- The declared durable ART mutation ports contain no `AuthorizationContext`,
  upload-session method, upload-session identifier, or caller-selected generic
  resource/facts mapping.
- Static tests prove the exact exported interface names and reject reintroduced
  raw-context or upload-session authority paths.
- `PreparedAuthorizationHandle` appears only on process-local, non-Pydantic ART
  mutation request objects. Static tests reject it in route schemas, outbox or
  Celery payloads, provider interfaces, and any serializable public contract.
- Exact final contexts and non-forgeable feature proofs are deliberately not
  invented here. Chunks 03-07 and 05A-D must define them in the owning feature
  modules, bind them to the same session/root transaction, lock their exact
  rows, and test stale/cross-session/cross-root/direct-construction bypasses
  before the corresponding action is activated.
- No planned ART action becomes executable.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=<postgres-test-db> .venv/bin/pytest tests/test_authorization.py tests/test_artifact_architecture.py -q --cov=app.modules.authorization.prepared --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

The focused coverage command measures the materially changed PREP subsystem;
it must remain at or above 90 percent. The exact PR head must also pass GitHub
checks `Backend / test` and `Agent Gates / agent-gates`, preserving the 78
percent repository-wide floor. Full backend coverage runs in GitHub Actions.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

No raw authentication context as durable mutation authority, no obsolete
upload-session interface, no planned-action handle, and no premature feature
truth in AUTH.
