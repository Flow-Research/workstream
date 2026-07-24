# External Review Response: WS-AUTH-001-10C

Reviewed at: 2026-07-24T20:30:41Z
PR: #194

## Comments Addressed

- CodeRabbit's qualification-model coercion finding was valid in substance.
  Global Pydantic strict mode was not restored because FastAPI supplies nested
  JSON as Python mappings and global strictness rejected valid JSON enum
  strings. The repair instead makes opaque references strict strings and
  admits UUID references only from canonical strings or UUID objects, rejecting
  numeric and byte coercion. Forty-eight focused qualification and route tests
  pass after the repair.
- The PR body was stale and incorrectly claimed no migration. It now uses the
  current migration-aware AUTH-10C trust bundle.
- The internal evidence now uses the checker-required provenance labels, a UTC
  timestamp, fresh AUTH-10C reviewer sessions, and a complete nine-track map.
- GitHub Backend passed the repaired evidence gate but resolved the repository's
  open Ruff range to newly released 0.16.0, producing 381 unrelated lint
  findings. The bounded repair caps Ruff below 0.16 without changing the lint
  command, rules, ignores, tests, or coverage. Full repository lint passes with
  Ruff 0.15.22; adoption of 0.16 rules remains a dedicated repository change.
- CodeRabbit's SQL-NULL facts finding was valid. The special five-key
  invalidation envelope now requires non-null facts on both sides and uses
  coalesced key-existence checks; raw SQL-NULL regression coverage proves that
  neither missing side can bypass counterpart validation.
- Trigger-disabling migration fixtures now snapshot exact trigger modes and
  restore them in `finally`. Migration and authorization lock observers use
  monotonic five-second deadlines with nonzero polling intervals.
- The wrong-project completion test now supplies the valid ordered
  qualification/issued pair, so rejection reaches the intended project binding
  rather than failing earlier on event cardinality. Audit fakes are
  instance-isolated.
- The migration drops the privacy constraint with exact literal raw DDL because
  Alembic's naming convention would otherwise double-prefix the name. The test
  normalization remains deliberately independent so it can serve as an oracle
  instead of importing the implementation under test.
- CodeRabbit's evidence-count and review-log provenance findings were valid.
  Evidence now records the exact 11-case aggregate and the log begins with the
  repaired implementation SHA.
- Fresh hosted API E2E reached the new link-lifecycle scenario and exposed a
  stale script key: the administrative response publishes `identity_link_id`,
  not `id`. Both revoke/reactivate references now use the canonical field; Ruff,
  compilation, and all 15 API-contract helper tests pass.
- The next hosted E2E attempt reached replay reauthorization and exposed a
  comparison against the whole per-request error envelope. The proof now
  excludes only `correlation_id` and retains equality for stable code, message,
  details, and retryability. Internal senior/security review rejected the
  weaker code/message-only intermediate repair before publication.

## Comments Deferred

- CodeRabbit's generic docstring percentage warning is not used as proof. The
  repository's own Agent Gates docstring check remains authoritative.

## Human Decisions Needed

- None for the addressed findings. The user retains explicit merge approval.

## Commands Rerun

```text
ruff check app/modules/authorization/schemas.py tests/test_authorization.py
ruff check alembic/versions/0034_project_role_issue_evidence.py
  tests/conftest.py tests/test_alembic.py tests/test_authorization.py
pytest -q tests/test_authorization.py -k
  'qualification_evidence_rejects_coerced_values or
   public_reason_and_qualification_contract_is_strict or
   project_role_mutation_routes'
isolated pytest migration refusal aggregate — 11 passed, 44 deselected
isolated pytest SQL-NULL fact-shape regression — 1 passed
isolated pytest rate-control lock-wait regression — 1 passed
isolated pytest corrected authorization regressions — 2 passed
pytest -q tests/test_api_contract_e2e.py — 15 passed
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Remaining Risks

- GitHub Backend full shards, hosted API E2E, and coverage require a fresh run
  on the canonical identity-link E2E repair.
- A fresh CodeRabbit pass is required on the pushed repair commit.
