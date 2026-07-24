# External Review Response: WS-AUTH-001-10C

Reviewed at: 2026-07-24T17:37:35Z
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

## Comments Deferred

- CodeRabbit's refreshed review is temporarily rate-limited. A fresh review
  will be requested when the service makes it available; no finding is being
  treated as resolved merely because the bot could not run.
- CodeRabbit's generic docstring percentage warning is not used as proof. The
  repository's own Agent Gates docstring check remains authoritative.

## Human Decisions Needed

- None for the addressed findings. The user retains explicit merge approval.

## Commands Rerun

```text
ruff check app/modules/authorization/schemas.py tests/test_authorization.py
pytest -q tests/test_authorization.py -k
  'qualification_evidence_rejects_coerced_values or
   public_reason_and_qualification_contract_is_strict or
   project_role_mutation_routes'
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Remaining Risks

- GitHub Backend full shards, hosted API E2E, and coverage are pending the
  corrected evidence push.
- CodeRabbit's refreshed review is pending its rate-limit window.
