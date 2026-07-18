# Chunk Contract: WS-QUAL-001-01B1B Semantic Delta Guards

Parent: `WS-QUAL-001` Backend Coverage Floor

Status: blocked at 223/300 after two binding/AST repair cycles; superseded by
proposed B1B-R1. Retain as circuit-breaker history and do not resume.

## Goal And Reason

Add the repository-delta integrity half of the coverage policy after the parser
core is stable. The separate boundary makes executable test weakening and real
Git diff behavior independently reviewable.

Risk: L1 test/CI integrity. SLA: P1.

## Scope

Allowed implementation files:

- `backend/scripts/coverage_policy.py`
- `backend/tests/test_coverage_contract.py`
- WS-QUAL initiative artifacts and global loop memory/reviews

Not allowed: parser contract redesign, docs/config/workflow/evidence mutation,
`backend/app/**`, runner changes, migrations, APIs, product/auth behavior,
coverage-raising tests, skips/xfails, exclusions, or pragmas.

Implementation cap: 300 lines outside `.agent-loop`; stop above 270 before
remaining proof.

## Acceptance Criteria

- Reuse root `changed_files`, `numstat`, and `diff_text` from repository root;
  restore caller cwd and prove committed behavior from `cd backend`.
- Scope permits only caller-approved files, exact global loop memory, and the
  WS-QUAL initiative; AUTH and unrelated initiative files fail closed.
- Size accounting excludes approved memory only from the numerator and enforces
  the supplied implementation cap.
- AST-aware guards detect executable pytest/unittest skip, xfail, importorskip,
  `skipTest`, and `SkipTest` forms including nested and aliased imports while
  accepting inert strings and ordinary `pytest.raises` usage.
- Deleted assertions detect Python/unittest assertions and all direct, imported,
  or module-aliased `pytest.raises` context managers using real committed Git
  regressions.

## Verification And Review

Use the 01B1A lint, focused-test, dependency, stale-wording, link, and diff
checks plus real temporary-Git behavior tests and this exact delta invocation:

```text
(cd backend && BASE_SHA="$(git merge-base HEAD origin/main)" .venv/bin/python -c 'import os, sys; sys.path.insert(0, "scripts"); import coverage_policy as policy; policy.validate_delta(os.environ["BASE_SHA"], 300, {"backend/scripts/coverage_policy.py", "backend/tests/test_coverage_contract.py"})')
```

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, reuse/dedup, and test delta. Human focus: false
negatives, false positives, root-path behavior, bounded memory scope, and no
parser/01B2 redesign.

Stop after this chunk. Do not start 01B2 or chunk 02. AUTH-02 may continue
independently in its already-authorized worktree.
