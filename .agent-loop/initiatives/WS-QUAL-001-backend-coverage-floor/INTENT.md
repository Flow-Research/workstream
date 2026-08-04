# Intent: WS-QUAL-001 Behavior And Mutation Assurance

## Problem being solved

Statement coverage shows that code executed, but it does not show that a test
would detect a meaningful behavioral defect. Workstream now exceeds 90 percent
global backend coverage while CI still correctly permits a 78-percent global
floor. The unfinished QUAL problem is assertion sensitivity and behavior
ownership, not another global percentage increase.

## Why this work matters

Humans and agents can add tests that execute lines without proving returned
data, persisted state, denial, failure, recovery, audit, queue, or lifecycle
behavior. A trusted repository must reject those weak tests without making
every contributor run the entire backend once per mutant.

## Current behavior

- Main Backend run `30926337804` on merge `5f2baf90` completed 3,162 tests and
  covered 21,620 / 23,938 statements (90.316651 percent).
- The global blocking floor remains 78 percent.
- Named new or materially changed subsystems retain blocking 90-percent floors.
- Semantic lanes reject incomplete collection, skipped nodes, missing coverage,
  and invalid evidence.
- Agent Gates scan common test and CI weakening tokens.
- No real mutation engine or mutation-result policy currently runs in CI.

## Target behavior

- Preserve the 78-percent global floor and every protected 90-percent floor.
- Require behavior claims to identify the production module and observable
  outcome they protect.
- Mutation-test only eligible changed production logic or explicitly claimed
  production targets for test-only behavior PRs.
- Treat surviving meaningful mutants as missing behavior proof, not as a reason
  to increase statement coverage.
- Bound runtime, isolate mutation evidence from ordinary coverage, and keep the
  complete Backend suite authoritative.
- Introduce blocking mutation policy only after a measured non-blocking pilot
  proves deterministic selection, acceptable noise, and acceptable runtime.

## Design chosen

Use a two-stage rollout. First, pilot one pinned mutation engine with
deterministic target/test selection and complete non-blocking score evidence.
Second, after human review of pilot evidence, introduce a separate fail-closed
gate for eligible changed logic and explicit test-only behavior claims. The
blocking policy is survivor-based with reviewed classifications, not a global
mutation-score target.

## Alternatives considered

- Raise global coverage to 90 percent: rejected because coverage is already
  above 90 and percentage alone does not prove assertion sensitivity.
- Mutate the full backend on every PR: rejected because runtime would be
  unbounded and would discourage contribution.
- Require one killed mutant per test: rejected because it is easily gamed and
  does not prove all eligible changed behavior.
- Immediately block on an uncalibrated mutation percentage: rejected because
  equivalent/noisy mutants and infrastructure behavior must be measured first.
- Restore historical signed-loop or machine-scope machinery: rejected; those
  systems were intentionally retired and are not prerequisites for quality.

## Boundaries preserved

- Coverage, real PostgreSQL, migration, trigger, lock, concurrency, MinIO, API,
  and semantic-lane checks remain unchanged.
- QUAL owns test-assurance policy, evidence, and CI integration only.
- Production defects found by mutation testing move to the owning product
  initiative; QUAL does not silently repair product behavior.
- Mutation targets exclude migrations, generated/declarative code, schemas,
  adapters requiring external effects, and modules without an explicitly
  reviewed eligibility rule during the pilot.

## Expected risks

- Mutation runtime can multiply test time.
- Equivalent or invalid mutants can create noisy false blockers.
- Target or test selection can be gamed to omit behavior.
- Test-only PRs need an explicit production target to avoid percentage padding.
- A new pinned tool adds dependency and supply-chain maintenance.

## What must not change

- Global coverage floor stays at 78 percent.
- Protected subsystem floors stay at 90 percent.
- No skips, xfails, coverage exclusions, assertion deletion, or narrower test
  inventory.
- No mutation pragma or exclusion may be introduced casually to make CI pass.
- No full-repository mutation run is added to the normal PR critical path.

## How this will be proven

- Unit tests prove diff-to-target eligibility, explicit test-only claims,
  classification grammar, evidence completeness, and fail-closed behavior.
- A hosted pilot records generated, killed, survived, timeout, suspicious,
  excluded, and error outcomes with exact source/test identity and elapsed time.
- Known behavior tests must kill seeded representative mutants.
- Weak or vacuous fixture tests must leave representative mutants alive in the
  policy regression suite.
- Existing Backend and Agent Gates remain green and unchanged in authority.

## Human decisions required

The 78-percent global floor decision is complete. A separate human checkpoint
is required after pilot evidence and before any mutation result becomes a
blocking merge gate.
