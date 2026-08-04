# Discovery: WS-QUAL-001 Behavior And Mutation Assurance

## Current hosted truth

Main Backend run `30926337804` on merge `5f2baf90` completed 3,162 tests with
21,620 / 23,938 statements covered (90.316651 percent), 620.264 seconds total
hosted wall time, and a 464.471-second slowest lane. The complete suite is above
90 percent, but `.github/workflows/backend.yml` intentionally blocks globally
at 78 percent and applies more than ten named 90-percent subsystem/per-file
checks.

This means raising the global floor is neither necessary nor sufficient for the
new human goal. The remaining gap is whether assertions detect behavioral
changes.

## Existing test-integrity controls

| Control | Current implementation | What it proves | What it does not prove |
|---|---|---|---|
| Complete semantic lanes | `.github/workflows/backend.yml`, `backend/scripts/run_test_lanes.py` | Five canonical lanes collect and execute under isolated custody | Assertions are sensitive to faults |
| Evidence validation | `backend/scripts/validate_test_lane_evidence.py`, `merge_test_lane_evidence.py` | No missing lane, skipped node, missing coverage, or invalid bundle | Tests kill plausible defects |
| Global coverage | `coverage report --fail-under=78` | Complete app execution stays above the permitted baseline | Behavioral correctness |
| Protected coverage | Named `--fail-under=90` checks | New/material subsystems retain deeper execution | Assertions reject wrong outcomes |
| Weakening scan | `scripts/workstream_agent_gate.py` | Flags common skip/bypass/threshold suppression tokens | Semantic weakening expressed without those tokens |
| Internal review | QA, test-delta, CI integrity and other routed reviewers | Human/agent reasoning examines behavior and scope | Deterministic executable fault sensitivity |

`backend/tests/test_project_policy_mutations.py` tests project-policy mutation
behavior; it is not a mutation-testing engine. No `mutmut`, Cosmic Ray, or
equivalent package/configuration currently exists in backend dependencies or
GitHub workflows.

## Candidate engine evidence

The current `mutmut` documentation says the tool supports pytest-aware test
selection, function/module wildcards, incremental results, parallel execution,
source-path restriction, and optional covered-line filtering. Its current
project metadata supports Python 3.10 through 3.14, which includes Workstream's
Python 3.11/3.12 range. It requires fork support, compatible with hosted Linux
runners. Sources:

- <https://mutmut.readthedocs.io/en/latest/>
- <https://github.com/boxed/mutmut/blob/main/pyproject.toml>

Cosmic Ray is also viable and stores resumable mutation sessions, but its
configuration centers on explicit module paths and test commands, and its
official documentation notes that plugin options are not fully documented.
That creates more wrapper/configuration ownership for the first pilot:

- <https://cosmic-ray.readthedocs.io/en/stable/>
- <https://cosmic-ray.readthedocs.io/en/stable/tutorials/intro/index.html>

Planning therefore selects `mutmut` only as the leading candidate. The pilot
must prove an exact pinned release, async pytest compatibility, deterministic
results, safe worktree isolation, and bounded hosted runtime before adoption.

## Selection boundary

Production changes can be derived from `origin/main...HEAD`. Test-only behavior
changes have no changed production file, so a deterministic behavior-claim
manifest is required to name the bounded production targets and owning tests.
Without this second path, a coverage-only test PR could avoid mutation
assurance entirely.

The planned canonical boundary is
`.ci/behavior-claims/<chunk-id>.json` under a repository-owned schema. It is
immutable PR content, not PR prose or a workflow input. Behavior claims name
repository-relative targets, qualified callables, owning pytest nodes, and
typed outcomes. Narrow non-behavioral test maintenance is classified through
the same schema so “no production diff” cannot become an implicit bypass.

Eligible pilot targets should begin with pure functions or direct service
methods that have fast owning tests. Initial discovery candidates live in the
project/checker policy, compiler, and runner layers already exercised by 02R
and 03R. The implementation chunk must choose a much smaller representative
set from current main and record why each target is eligible.

Ineligible-by-default categories for the pilot:

- migrations and generated/declarative files;
- Pydantic/SQLAlchemy schemas whose mutations are primarily framework noise;
- composition-only modules and adapter wiring;
- external-effect adapters requiring network or real object storage per mutant;
- modules whose only truthful proof requires the full PostgreSQL/HTTP suite;
- unchanged modules not named by an explicit test-only behavior claim.

## Evidence model

A useful result must bind:

- exact git tree/source digest;
- mutation engine version and configuration digest;
- target module/callable and owning test nodes;
- generated, killed, survived, timeout, suspicious, excluded, and error counts;
- stable mutant identifiers and classifications;
- command timeout and elapsed time;
- whether the result is pilot-only or blocking.

A percentage without these facts is insufficient. Cache reuse is allowed only
when the wrapper proves the cached inputs match the exact current inputs.

## Unknowns the pilot must answer

- Whether current mutmut works cleanly with Workstream's async pytest fixtures.
- How precisely relevant tests are selected without broad incidental execution.
- Which mutation operators create equivalent/noisy results in Workstream code.
- Hosted runtime and p95 variability for representative changed targets.
- Whether fresh execution is cheap enough or authenticated cache reuse is
  needed.
- Which narrow classification categories can be machine checked without
  becoming an exclusion escape hatch.

## Historical reconciliation

PRs #103, #105, #108, #265, and #269 remain completed QUAL evidence. The old
01B2/milestone ladder remains superseded. `WS-QUAL-001-04R`, which proposed
raising the global floor to 90 percent, is superseded before implementation by
the human decision to keep 78 percent and move to behavior/mutation assurance.
Historical ENG-008 mutation planning is discovery input only; its retired
signed-loop and machine-scope requirements are not current authority.
