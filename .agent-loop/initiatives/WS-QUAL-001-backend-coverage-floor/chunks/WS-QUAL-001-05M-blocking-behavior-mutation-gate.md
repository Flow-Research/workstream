# Chunk Contract: WS-QUAL-001-05M — Blocking Behavior-Mutation Gate

## Parent initiative

`WS-QUAL-001` — Behavior And Mutation Assurance

## Goal

Convert the accepted 04M changed-scope pilot into a required, fail-closed
behavior-mutation check for eligible Backend production changes and explicit
test-only behavior claims.

## Accepted calibration input

PR #285 merged as `7f395d47`. Its final exact-head hosted pilot on
`0c25acec8fb3326e68169512e829711a0790b190` completed mutation execution in
34.886 seconds and the hosted job in 53 seconds. It reconciled 2,493 generated
mutants: 149 killed, 89 survived, 2,255 excluded, and zero timeout, suspicious,
or error outcomes. Strong calibration killed two representative mutants and
the deliberately weak control left two representative mutants alive. The
human accepted this calibration and explicitly started 05M.

## Risk class

L1 — blocking CI/test policy.

## SLA

P2.

## Allowed files

```text
backend/pyproject.toml
backend/scripts/mutation_policy.py
backend/tests/test_mutation_policy.py
scripts/behavior-claim.schema.json
scripts/mutation-requirements.in
scripts/mutation-requirements.txt
scripts/test_lightweight_agent_gates.py
.ci/behavior-claims/README.md
.ci/behavior-claims/WS-QUAL-001-05M.json
.ci/behavior-claims/example.behavior-claim.json
.github/workflows/mutation-pilot.yml
CONTRIBUTING.md
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**
```

## Not allowed

```text
backend/app/** or backend/alembic/** product changes
global mutation score or percentage threshold
change to the global 78-percent or protected 90-percent coverage floors
free-form exemptions, source mutation pragmas, or survivor allowlists
silent success for survivor, timeout, suspicious, error, stale, or unknown status
full-repository mutation on ordinary PRs
production dependency changes unrelated to the protected mutation runner
Backend semantic-lane, fan-in, coverage, or test-inventory weakening
pull_request_target, privileged PR execution, writable token, checkout credentials,
secrets in mutation execution, or unpinned Actions
```

## Policy design

- Eligible changed Python targets under the merged policy remain mandatory.
- One canonical schema-v1 claim file supplies bounded callable and owning-test
  scope. The workflow discovers it from the exact base/head delta; workflow
  inputs, labels, environment variables, and PR prose cannot choose it.
- For eligible production changes, the protected evaluator maps every added or
  modified executable hunk to its current qualified function, async function,
  or method and requires the claim to own every derived callable. Unmapped
  module/class executable changes, deleted-only executable hunks, omitted
  callables, and unrelated-callable claims fail closed rather than silently
  narrowing mutation scope.
- Disposable mutmut configuration is derived from the validated exact-head
  selection. Contributors do not edit a second target/test list in
  `backend/pyproject.toml`.
- `killed` passes. `survived`, `timeout`, `suspicious`, and `error` block.
  `excluded` passes only as an engine result outside the reviewed callable
  filters and remains fully enumerated in evidence. Unknown or missing statuses
  block.
- The only allowed surviving classification is the repository-owned
  `calibration_control` for mutants belonging to the exact
  `_weak_calibration` callable. It is derived and verified by policy, never
  supplied as contributor prose or an allowlist.
- Changes with no eligible target and no behavior claim are deterministically
  `not_applicable`; they do not install or run the mutation engine. An explicit
  test-only behavior claim remains additive and cannot remove changed targets.
- Ordinary pull requests execute selection, config generation, evidence
  validation, outcome classification, and final verdict with the evaluator
  and every imported policy helper archived from the protected base revision.
  Protected evaluation must not import PR-head policy helpers. Candidate policy
  and workflow changes therefore cannot become their own authority. The 05M bootstrap PR is
  reviewed under merged 04M plus all internal/external checks; its first
  protected-main run must prove the new evaluator before it becomes authority
  for later PRs. GitHub permissions, required checks, and explicit human merge
  remain the authority for changes to the evaluator/workflow themselves.

## Acceptance criteria

- [ ] The pull-request workflow always emits one stable required check; it does
      not use workflow-level path filters that leave skipped required checks
      pending. Internal preflight returns typed `not_applicable` before mutation
      dependency installation/execution for unrelated changes.
- [ ] Exactly one changed canonical claim is discovered when mutation is
      applicable; missing, multiple, unsafe, stale, symlinked, or mismatched
      claims fail closed.
- [ ] Eligibility and schema-v1 behavior ownership remain compatible with 04M;
      any 05M discovery/configuration correction is explicit and tested.
- [ ] Every added/modified executable hunk in an eligible production target is
      mapped to and covered by the exact claimed callable. Omitted or unrelated
      callables, nested methods, async functions, decorators, module/class-level
      executable changes, renames, and deleted-only hunks have explicit
      deterministic pass/block behavior and cannot escape mutation silently.
- [ ] Disposable mutmut configuration is deterministically generated from the
      validated selection and bound into exact-head evidence; mutable static
      target/test duplication is removed.
- [ ] Every engine status is enumerated. Survivor, timeout, suspicious, error,
      unknown, incomplete, and stale evidence block without implicit success.
- [ ] `excluded` passes only when the exact mutant is outside the reviewed
      callable filters; an excluded mutant matching a selected filter blocks.
- [ ] The only allowed survivor is a policy-derived exact weak-calibration
      control; contributor-authored classifications and free-form exemptions
      are rejected.
- [ ] Test-only behavior claims cannot replace or narrow mandatory changed
      targets. No-target/no-claim changes return typed `not_applicable` rather
      than fabricating mutation evidence.
- [ ] Baseline failure, target escape, source-tree mutation, custody failure,
      dependency drift, and malformed evidence remain blocking.
- [ ] `CONTRIBUTING.md`, the canonical claim README/schema/example, and the
      Backend operations guide explain applicability, claim creation, local
      verification, evidence interpretation, and repair of survivors.
- [ ] The mutation toolchain comes only from the trusted-base hash-locked
      manifest. Eligible owning tests run with production/dev dependencies
      resolved only from the trusted-base `backend/uv.lock` and
      `backend/pyproject.toml`; PR-head dependency metadata cannot become gate
      authority.
- [ ] The one-time 04M-to-05M bootstrap may use the reviewed head mutation
      manifest because protected 04M does not contain the locked `uv` runner;
      after merge, ordinary PRs and protected-main runs use only the protected
      base manifest and backend lock metadata.
- [ ] Ordinary PR verdicts use the protected-base evaluator, not PR-head policy
      code or helpers. Workflow invariants prove the evaluator and all imported
      policy helpers come from the protected base. The bootstrap transition is
      explicit and a successful protected `main` run is required before 05M is
      considered operational.
- [ ] Required mutation execution remains independent and within the accepted
      15-minute job cap, retains a hard 720-second shell command limit and
      700-second engine limit, and does not extend required PR critical-path
      latency by more than two minutes. Full Backend fan-in, Agent Gates, global
      78-percent coverage, and protected 90-percent floors remain authoritative
      and green.
- [ ] All required internal reviewers pass and external CI/review is resolved
      before human merge.

## Verification commands

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_mutation_policy.py
.venv/bin/python -m pytest -q tests/test_ci_test_lanes.py tests/test_coverage_contract.py
.venv/bin/ruff check scripts/mutation_policy.py tests/test_mutation_policy.py
cd ..
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
git diff --check
```

Focused policy tests must include docs/no-target `not_applicable`, applicable
changes without a claim, exact/additive claims, multiple/stale/symlinked claims,
omitted/unrelated/nested/async/decorator/module/deleted callable cases, every
engine status, missing/unknown outcomes, weak-calibration-only survival, and
allowed/rejected excluded mutants. Workflow invariant tests must prove
preflight occurs before dependency installation and ordinary verdicts use the
protected-base evaluator. Hosted PR evidence must include the blocking workflow
result and timing plus successful Backend lane/fan-in coverage and Agent Gates.

## Required reviewers

Senior engineering, QA/test, security, product/ops, architecture, CI integrity,
docs, reuse/dedup, and test delta.

## Human review focus

- Does meaningful surviving behavior always block without a contributor escape
  hatch?
- Is the exact weak calibration the only survivor that can pass?
- Can an ordinary contributor determine applicability and create the claim
  without editing workflow internals or duplicating configuration?
- Does unrelated work avoid an irrelevant mutation job?

## Stop conditions

Stop on an unclassifiable required survivor, unacceptable hosted latency/noise,
need for a broad exemption, weakening of Backend/coverage/test inventory, or a
new dependency, product, authorization, payment, migration, or data boundary.
