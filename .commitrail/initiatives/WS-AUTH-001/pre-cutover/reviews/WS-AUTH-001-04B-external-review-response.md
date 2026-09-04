# External Review Response: WS-AUTH-001-04B

## Pull Request

PR #113 - Add durable PostgreSQL authorization rate controls

## Backend CI Failure

The first Backend run reached 82.12 percent repository coverage but failed in
test setup. The final AUTH-04B Alembic test downgraded the shared isolated
database to `base`; CI discovery then entered the rate-control suite without
table `api_rate_control_counters`. The owning migration test now restores
Alembic `head` after destructive cleanup. The exact failing order passes 22/22.

## CodeRabbit Findings

One valid nitpick is addressed: repeated raw counter inserts in concurrency,
saturation, and pruning tests now use one `_insert_counter_row` helper while
preserving transaction ownership and exact timestamp/count inputs.

The PR-description warning is addressed by adding the missing human intent,
acceptance proof, evidence, reviewer table, and CI/gate-integrity sections to
the trust bundle and published PR body.

The CodeRabbit docstring warning is not a repository failure. The authoritative
`docstr-coverage --config .docstr.yaml` gate passes at 95.8 percent, and the
Backend docstring step passed. Adding narration-only docstrings to private test
and implementation helpers would not improve behavior or ownership clarity.

CodeRabbit's later incremental run was rate-limited and produced no additional
actionable thread.

## Commands Rerun

```bash
(cd backend && isolated-runner pytest -q tests/test_alembic.py::test_api_rate_control_schema_preserves_domain_and_guards_downgrade tests/test_api_rate_controls.py)
(cd backend && ruff check tests/test_alembic.py tests/test_api_rate_controls.py)
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
git diff --unified=0 origin/main -- backend/tests | (! rg '^-(.*assert|.*pytest\.raises|.*pytest\.mark\.(skip|xfail)|.*skipTest)')
git diff --check
```

- Exact CI failure order: 22 passed.
- No assertion, raises, skip, xfail, threshold, workflow, runtime, or migration
  implementation was weakened.

## Remaining Gate

Push the reviewed repair and require Backend, Agent Gates, CodeRabbit status,
and explicit human review on the new PR head. Publication is not merge approval.
