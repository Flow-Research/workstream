# Chunk Contract: WS-QUAL-001-01B1B-R8 Syntactic Integrity Policy

Parent: `WS-QUAL-001` Backend Coverage Floor

## Goal And Rationale

Replace R7's attempted Python execution model with a bounded syntactic policy.
The gate protects changed tests from known pytest/unittest weakening constructs
and deleted assertion constructs; it does not predict runtime reachability,
iterator consumption, or arbitrary Python values.

Risk: L1. SLA: normal. The user's 2026-07-13 instruction to fix the blocking
coverage gate is the implementation start signal only after this contract passes
all required internal plan-review tracks.

## Scope

Allowed files:

- `backend/scripts/coverage_policy.py`
- `backend/tests/test_coverage_contract.py`
- WS-QUAL and global `.agent-loop/` memory

Not allowed: `backend/app/**`, coverage-raising tests, skips/xfails/exclusions,
configuration, workflows, evidence baselines, B2, chunk 02, AUTH-03, product
runtime, dependencies, public docs, or spreadsheet exports.

The implementation base is merged-main SHA
`060b780190435bc79464ae92fd9235a652f70e00`. Its raw added-plus-deleted delta is
capped at 700 lines across the policy and contract-test files, with the same
metric used for the 600-line checkpoint. Tests must keep one case per physical
line for every new or replacement R8 matrix entry, stay reviewable without
generated/encoded fixtures, and must not be compacted to satisfy the cap.
Merged-main formatting remains unchanged. The first implementation step restores
the branch-only R2-R7 policy/test delta to base `060b780`, preserving every base
test, before adding R8. Apply the checkpoint and cap to that resulting candidate
delta. Stop above 700.

## Acceptance Criteria

- Same-scope absolute `pytest` and `unittest` imports, aliases, and direct imports
  establish monotone framework ownership regardless of statement order,
  reassignment, branch, or reachability. Relative imports and imports whose
  absolute root is not exactly `pytest` or `unittest` remain local.
- Python lexical scopes use stdlib `symtable`. Parameters and declarations in a
  nested scope shadow inherited ownership; explicit global/nonlocal names retain
  their resolved owner. A finite, cycle-safe alias closure covers only simple
  `Name = framework-owned Name` and `Name = framework-owned Attribute` aliases.
  Containers, unpacking, comprehensions, iteration, calls/returns, wrapper
  values, and arbitrary attributes never create ownership.
- Once a construct's root is framework-owned, dead branches, empty
  comprehensions, lazy/async generators, wrappers, qualified/arbitrary
  consumers, and argument position cannot suppress detection. Those contexts do
  not themselves create ownership; no statement-order, reachability, class
  transfer, consumer, or runtime-value inference is permitted.
- Reject `pytest.skip`, `pytest.xfail`, `pytest.importorskip`,
  `pytest.mark.skip/skipif/xfail`, pytestmark assignments resolving to those
  marks, `unittest.skip/skipIf/skipUnless/expectedFailure`, `SkipTest`, and
  framework-owned `unittest.TestCase.skipTest`. Reject `self.skipTest` and
  `super().skipTest` only inside a class whose syntactic base resolves through
  the lexical alias closure to framework-owned `unittest.TestCase`. Keep the
  same syntax in unrelated classes clean. `case = TestCase(); case.skipTest()`
  is outside R8 because call-return provenance is intentionally retired.
- Native `assert`, framework-owned `pytest.raises`/imported `raises`, and
  syntactic `self.assert*` calls are recognized in the base file for
  deleted-assertion protection, independent of runtime reachability. The
  receiver must be exactly the name `self`; unrelated receivers remain clean.
- Strings, comments, annotations under postponed evaluation, relative imports,
  local lookalikes, shadowed names, and unrelated methods remain clean.
- Preserve every test present on base SHA `060b780` unchanged and passing,
  including repository root/cwd, committed rename, scope/size, metadata,
  canonical grammar, invalid-syntax fail-closed, native assertion, and lexical
  local-lookalike behavior.
- Retire R2-R7 branch-only reachability, iterator-consumption, sequential-value,
  and control-flow expectations. Map every discovered weakening construct into
  the R8 conservative syntax matrix, including skip and deleted-assertion
  variants; this intentional contract replacement is not test weakening. Do not
  remove, skip, xfail, weaken, or compress merged-main tests or assertions.
- The positive matrix covers dead/empty/lazy/async/wrapper/qualified/arbitrary
  contexts after ownership, owned-name reassignment invariance,
  framework-rooted alias chains/cycles, and resolved global/nonlocal uses.
  Negatives cover strings, comments, postponed annotations, relative imports,
  local lookalikes, unowned cycles, nested parameter/local shadowing, and
  unrelated attributes. Mirror it for native assert, owned/imported raises, and
  exact-receiver `self.assert*` deletion.

## Verification And Review

Run:

```text
cd backend && .venv/bin/python -m pytest -q tests/test_coverage_contract.py
cd backend && .venv/bin/ruff check scripts/coverage_policy.py tests/test_coverage_contract.py
cd backend && .venv/bin/pip check
backend/.venv/bin/python scripts/check_stale_workstream_wording.py
backend/.venv/bin/python scripts/check_stale_authorization_docs.py
backend/.venv/bin/python scripts/check_loop_memory_state.py
backend/.venv/bin/python scripts/check_markdown_links.py
git diff --check
git merge-base --is-ancestor 060b780190435bc79464ae92fd9235a652f70e00 HEAD
test -z "$(git diff --name-only 060b780190435bc79464ae92fd9235a652f70e00...HEAD | grep -Ev '^(backend/scripts/coverage_policy.py|backend/tests/test_coverage_contract.py|\.agent-loop/(LOOP_STATE.md|REVIEW_LOG.md|WORK_QUEUE.md|initiatives/WS-QUAL-001-backend-coverage-floor/.*))$')"
test "$(git diff --numstat 060b780190435bc79464ae92fd9235a652f70e00...HEAD -- backend/scripts/coverage_policy.py backend/tests/test_coverage_contract.py | awk '{total += $1 + $2} END {print total + 0}')" -le 700
cd backend && BASE_SHA=060b780190435bc79464ae92fd9235a652f70e00 .venv/bin/python -c 'import os, sys; sys.path.insert(0, "scripts"); import coverage_policy as policy; policy.validate_delta(os.environ["BASE_SHA"], 700, {"backend/scripts/coverage_policy.py", "backend/tests/test_coverage_contract.py"})'
```

Required reviewers: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, test delta, and circuit breaker.
Human review focus: the intentionally conservative syntax contract, local
lookalike precision, readable tests, no CI weakening, and bounded scope.

## Stop Conditions

Stop if the syntactic contract requires runtime reachability/consumption,
arbitrary call semantics, another abstract interpreter, unreadable tests, more
than two repair cycles, or more than 700 implementation lines. Do not start B2,
chunk 02, AUTH-03, or any other chunk after R8.
