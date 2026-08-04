# WS-ART-001-04A1 External Review Response

## CodeRabbit

CodeRabbit completed its review on PR #264 without actionable comments.

CodeRabbit's earlier detailed review still contained one major finding and two
nitpicks, so the absence of a new summary comment was not treated as closure:

- **Major — resolved:** recovery tests no longer attach or read the unmapped
  `recovery_submission_id` attribute on `ArtifactVerificationJob`. The fixture
  now derives the real immutable `Submission.id` from the persisted
  `CheckerRun` lineage and passes it explicitly in every task-scoped recovery
  request, including retries.
- **Receipt nullability — resolved:** migration 0051 now makes
  `artifact_operation_receipts.put_attempt_id` non-null after its locked
  populated-legacy preflight. The ORM matches that v2-only invariant, the
  downgrade restores legacy nullability before recreating the v1 shape, and a
  model contract assertion protects the mapping.
- **Test-helper import — documented, no code move:** moving the shared
  checker-output helper would also move its large project/guide/task/submission
  relationship fixture across domain test modules. That broad fixture
  refactor is outside this removal chunk and would increase this PR's coupling
  and review surface. The import remains test-only and has no runtime effect.
- **Docstring heuristic — no change:** the repository's hosted docstring gate
  passed. No repository standard was weakened and no unrelated docstrings were
  added solely for a standalone reviewer heuristic.

Local correction evidence:

- Ruff on all changed Python files: passed;
- `git diff --check`: passed;
- no `recovery_submission_id` references remain under `backend/tests`;
- focused PostgreSQL rerun was interrupted by the known local Python exit 139
  before pytest produced a result; hosted sharded Backend and Agent Gates are
  the authoritative execution evidence for this correction.

The first hosted correction run then exposed the expected schema-custody delta:
making `put_attempt_id` non-null changed the canonical public-schema
fingerprint. The database migrations completed successfully, but fixture reset
failed closed because `EXPECTED_PUBLIC_SCHEMA_SHA256` still named the prior
nullable schema. The constant now records the hosted schema digest
`8acef1c1d96ced0a4d4723ce71aa2e675ab841ec4305d9421ed0584313b98b55`;
no reset guard was removed or weakened.

## Hosted CI correction

The first Backend sharded run failed one `shared_foundations` test. Replacing
the deleted contributor fixture with a current checker-output fixture made the
recovery resource submission-scoped, but the operator HTTP test requests still
omitted the canonical `submission_id`. Production correctly failed closed with
`409 artifact recovery resource facts changed`.

The test now carries the exact submission lineage for denied, stale, successful,
replayed, altered, ineligible, and cross-project recovery requests. No production
authorization or recovery guard was weakened.

Focused correction evidence:

- the formerly failing operator HTTP test: `1 passed`;
- complete operator API and recovery files: `15 passed`;
- Ruff on the corrected test file: passed.

The correction is pushed for a fresh hosted Backend and Agent Gates run.

The fresh run proved `shared_foundations`, `project_lifecycle`,
`task_lifecycle`, and `schema_contracts_a`, then exposed one stale assertion in
`schema_contracts_b`: the broad current-schema contract still required the two
tables this chunk intentionally removes. The assertion now classifies
`artifact_upload_sessions.id` and `artifact_upload_items.id` as discarded
columns. The exact formerly failing schema test passes locally.

All five shards then passed, while the aggregate ART subsystem coverage gate
reported `89.52%`. The deleted contributor tests had also carried ambiguous-put
terminal coverage. That proof is now restored on the current task-scoped
checker-output producer for mismatch, provider conflict, and collision with an
already verified replica. All three cases pass. Combining those exact tests
with the authenticated hosted shard coverage reaches `90.01%`; the hosted gate
must confirm the final commit.
