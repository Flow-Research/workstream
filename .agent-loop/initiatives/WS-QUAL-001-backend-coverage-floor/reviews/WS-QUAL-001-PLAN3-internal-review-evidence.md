# WS-QUAL-001-PLAN3 Internal Review Evidence

## Review scope

Planning-only changes under
`.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**`. Review began
against main merge `5f2baf90036839589cf3db5ad6949d4888da5e9e` and reconciled without conflict
to current main `24f677cb` after CON PLAN5 PR #270 changed only CON/REV/general
documentation. The QUAL delta is unchanged. No application, test, workflow,
dependency, threshold, or mutation implementation changed.

## Risk routing

- Risk class: L1.
- SLA: P2.
- Work type: CI/test policy architecture and documentation.
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, and test delta.
- Human gate: required for PLAN3 merge, required again before 04M, and required
  after pilot evidence before 05M.
- Budget posture: high scrutiny with bounded planning scope; no implementation
  or runtime spend in PLAN3.
- Why: future work executes third-party tooling against untrusted PR code and
  may eventually become a blocking contributor gate.

## Circuit breaker

PASS with a planning-record size exception. The diff is larger than the
preferred L1 implementation guideline because initiative planning must keep
intent, discovery, plan, decisions, risks, status, chunk map, three contracts,
and review evidence mutually consistent in one planning PR. It touches one
major boundary (QUAL CI/test policy), changes no executable file, and has clear
acceptance criteria and nine completed reviewer tracks. Splitting the records
would publish internally contradictory partial policy without reducing the
eventual 04M or 05M implementation boundary.

## Reviewer results

| Reviewer | Result | Final findings |
|---|---:|---|
| senior engineering | PASS | None |
| QA/test | PASS | None |
| security/auth | PASS | Prior CI privilege and dependency-custody findings resolved |
| product/ops | PASS | None |
| architecture | PASS | Shared git-delta boundary and canonical claim input conditions resolved |
| CI integrity | PASS | None |
| docs | PASS WITH LOW RISKS | Dependency authority and contributor onboarding conditions resolved |
| reuse/dedup | PASS WITH LOW RISKS | Existing delta/evidence conventions are now explicit reuse requirements |
| test delta | PASS | None |

Open reviewer sessions: none.

## Findings resolved

- Added one shared `scripts/git_delta.py` boundary for Agent Gates and mutation
  policy rather than parallel diff parsing.
- Declared schema-v1 `.ci/behavior-claims/<chunk-id>.json` as the only test-only
  claim input; mutable PR prose, labels, workflow inputs, and environment
  variables cannot widen scope.
- Required mutation tooling to install only from a hash-locked sidecar
  requirements file; `pyproject.toml` is configuration-only and `uv.lock` is
  not a second install path.
- Required unprivileged `pull_request`/`push`, explicit read-only permissions,
  pinned Actions, disabled checkout credentials, no secrets/writable token in
  the mutation subprocess, and bounded artifacts/caches.
- Required canonical claim documentation during the pilot and explicit
  `CONTRIBUTING.md` onboarding before any blocking rollout.

## Deterministic evidence

- Markdown link scan — passed for all changed Markdown files.
- Stale Workstream wording scan — passed.
- Stale authorization documentation scan — passed.
- Stale artifact-contract scan — passed.
- Lightweight Agent Gates — 10 passed.
- `git diff --check` — passed.
- Allowed scope — QUAL initiative planning tree only.
- Official candidate-tool assumptions were checked against current mutmut and
  Cosmic Ray primary documentation.

## Remaining risks

- `mutmut` is provisional; 04M must prove exact pinned compatibility with
  Workstream's async pytest and isolation setup.
- Equivalent/noisy mutants and hosted runtime remain unknown until 04M.
- No mutation result may block merging until exact hosted pilot evidence is
  accepted through a separate human checkpoint.
