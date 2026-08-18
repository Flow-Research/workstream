# PR Trust Bundle: WS-CI-005-PLAN

## Chunk

`WS-CI-005-PLAN`

## Goal

Plan a discriminating semantic-proof layer for the existing reviewer system.

## Human-approved intent

Improve reviewer skills and custom agents so a `PASS` is supported by proof
capable of observing the claimed defect, without adding repository authority.

## What changed

Added the initiative intent, discovery, plan, risks, decisions, status, chunk
map, and three bounded future implementation contracts.

## Why it changed

Prior reviews were correctly bound to exact Git targets but still accepted
tests or inspection too weak to prove the claimed behavior.

## Design chosen

Extend the existing WS-CI-004 reviewer protocol with a closed claimed-boundary
and proof-strength model, test-of-the-test probes, reusable escaped-failure
patterns, and blind forward evaluation before behavioral adoption.

## Alternatives rejected

- More reviewers: duplicates specialties without improving proof quality.
- Filename inference: cannot establish semantic compatibility.
- Hosted evidence authority: would create a second authority system.
- Universal heavyweight execution: disproportionate for low-risk changes.

## Scope control

Planning and repository engineering memory only. No product code, migration,
workflow, permission, merge gate, coverage threshold, or reviewer specialty is
changed.

## Product behavior

None.

## Acceptance criteria proof

- Proof boundaries and compatibility are explicit in `PLAN.md`.
- Ten historical escaped-defect classes and malicious evidence are recorded.
- Each future acceptance atom maps to an exact named proof.
- State projections and merge outcomes are machine-valid and remain planned.

## Tests/checks run

- Active-state, chunk-state, Markdown-link, and stale-wording checks passed.
- Reviewer contract validation passed.
- Reviewer-contract and review-target unit tests passed: 35 tests.
- `git diff --check origin/main...HEAD` passed.

## Test delta

No runtime tests changed. Future test selectors are contractual obligations,
not claims that implementation already exists.

## CI integrity

No workflow, runner, lane, coverage command, threshold, or package script
changed. Required Agent Gates commands pass locally.

## Reviewer results

Initial reviewed code SHA: `c848ccfeccb96001cc7689060311b6acccd435d6`

Reviewed at: 2026-08-17

Reviewer run IDs: `ci005_plan_arch`, `ci005_plan_ci`, `ci005_plan_qa`,
`ci005_plan_security`, `ci005_plan_docs_product`, `ci005_plan_senior`

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS WITH LOW RISKS | None | Adoption remains conditional on blind evaluation. |
| QA/test | PASS | None | Exact proof selectors and all ten escaped classes verified. |
| security/auth | PASS | None | Untrusted evidence and custody boundaries verified. |
| product/ops | PASS | None | Same focused docs/product session; no product lifecycle change. |
| architecture | PASS | None | Canonical WS-CI-004 ownership and three-chunk boundary verified. |
| CI integrity | PASS WITH LOW RISKS | None | No CI surface changed; required local gates passed. |
| docs | PASS | None | Durable state, terminology, and links verified. |
| reuse/dedup | N/A - with approved reason | None | Planning-only Markdown adds no implementation helper or abstraction. Architecture still verified canonical validator and registry reuse. |
| test delta | N/A - with approved reason | None | No test file, assertion, selection, or coverage command changed. QA still verified future proof obligations. |

The external-review repair makes these committed results historical. Final
exact-head receipts are create-once local session evidence and must replay the
applicable tracks after every push; the GitHub PR body mirrors their current
status without making this committed bundle self-referential.

## External review

CodeRabbit provided a fresh substantive review on PR #350. Its two findings
are addressed in the adjacent external-review response; final-head refresh is
required.

## Remaining risks

The planned implementation may still become ceremonial or non-discriminating.
Each future chunk therefore requires its named controls and final blind
evaluation before behavioral adoption.

## Follow-up work

After human approval, start only `WS-CI-005-01`. Do not start successors
automatically.

## Human review focus

Confirm source inspection cannot replace executed database/session custody,
the taxonomy remains minimal, and no new authority is introduced.

## Human merge ownership

GitHub permissions, protected-branch checks, and explicit human approval remain
authoritative. Internal receipts and this bundle are advisory evidence only.
