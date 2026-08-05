# WS-QUAL-001-05M Internal Review Evidence

## Deterministic evidence gate

Result: PASS with the approved L1 size exception. The policy, protected
workflow, schema/example, focused tests, dependency custody, and contributor
documentation form one blocking-gate review boundary. No product code,
migration, Backend lane, coverage floor, or product lifecycle changed.

Commands and results:

- Exact discovery against merged `04M`: `applicable`, one `05M` claim, 19
  changed policy callables, and exact ownership.
- Mutation-policy coverage: 58 tests passed; 91.97 percent.
- Mutation policy, CI-lane, and coverage-contract suites: 263 tests passed.
- Lightweight repository gate suite: 11 tests passed.
- Ruff, diff check, Markdown links, and stale Workstream wording: passed.
- Protected dependency replay: hash-locked `mutmut==3.7.0` and `uv==0.11.7`
  installed; protected-lock FastAPI, SQLAlchemy, Pydantic settings, and
  pytest-asyncio imports passed; mutation-policy suite passed in that
  disposable environment.

Hosted GitHub Actions and CodeRabbit remain external merge gates on the exact
published head.

## Reviewer results

| Track | Result | Material outcome |
|---|---|---|
| Plan | PASS | Exact authority, applicability, runtime, and proof requirements were explicit before implementation. |
| Architecture | PASS after fixes | Calibration is policy-owned and exact; changed-callable ownership cannot be narrowed by a claim. |
| Senior engineering | PASS with low risk | Protected locked backend dependencies make eligible app tests executable; stable legacy `pilot` job id is intentionally retained for check continuity. |
| QA | PASS after fixes | Merge-base mapping, AST existence, calibration impostors, and claim-only targets are covered. |
| Security | PASS after fix | Candidate tests receive a minimal environment without GitHub command files or credentials. |
| CI integrity | PASS after fix | Protected-base evaluator/dependencies, stable always-emitted job, bounded execution, and existing Backend gates remain intact. |
| Test delta | PASS with low risk | Full enforced-survivor failure and complete generated TOML configuration are regression-tested; no skips or weakened assertions. |
| Docs | PASS after correction | Local discovery and hosted selection/evidence interpretation are documented. |
| Product/ops | PASS with low risk | Engineering evidence remains separate from Workstream product review, compensation, and reputation. |
| Reuse/dedup | PASS with low risk | Existing Git-delta discovery is reused; line-range parsing can move to the shared helper in later maintenance. |

## Findings resolved

- Replaced contributor-coupled calibration selection and substring identity
  with exact policy-owned strong and weak controls.
- Required exact equality between changed callables and claim ownership.
- Used merge-base hunks and rejected claimed callables absent from the target
  AST.
- Preserved the stable required job id and future protected-main enforcement.
- Removed secrets and GitHub command-file paths from candidate execution.
- Added protected-base locked backend runtime/test dependencies so eligible
  `backend/app/**` tests reach mutation rather than failing imports.
- Added end-to-end enforced-survivor and complete generated-config tests.
- Added copyable local discovery and evidence-repair guidance.
- Made plain class headers fail closed, replaced formatting-sensitive capability
  detection, made deleted eligible targets fail closed, and typed
  generated-TOML parse failure after CodeRabbit review.

## Residual low risks

- The stable job id remains `pilot` for branch-protection continuity although
  the workflow display name is `Behavior Mutation Gate`.
- Workflow structure has string-invariant tests; the critical enforcement path
  is exercised behaviorally in the backend suite.
- Local diff-line parsing may be centralized in `scripts/git_delta.py` later.
