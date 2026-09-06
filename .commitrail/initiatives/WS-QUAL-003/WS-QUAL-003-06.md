# WS-QUAL-003-06 — Make PROJECT policy-read composition proof discriminating

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: Isolate policy-read composition tests, split mixed
  rejection cases and replace digest-shape checks with exact binding proof.

## Intent

Continue the behavior-first audit after PR #370. At main `3c9dbd44`, four
`test_projects.py` functions cover policy reads, active-guide reads and malformed
activation input. Two combine unrelated success/rejection transitions. Digest
assertions check only the `sha256:` prefix; wrong but well-formed bindings pass.
The shared `_PolicyReadRepository.__init__` is 124 lines of frozen helper debt.

These are composition/service tests using controlled repository rows, not proof
of stored tenant isolation, AUTH grant evaluation or PostgreSQL lock behavior.
Existing real database/transaction/race tests remain unchanged and hosted.

## Bounded change

### Allowed

- This record and `OVERVIEW.md`: dispositions, proof map and remaining audit.
- `backend/tests/test_projects.py`: remove the four selected test definitions
  and `_PolicyReadRepository`, plus newly unused imports only.
- `backend/tests/projects/policy_read_fixtures.py`: isolate the existing fake
  rows and methods; split initialization into cohesive source/intake/review
  construction phases, retaining values, order and independent instance state.
- `backend/tests/projects/test_policy_read_composition.py`: effective/pre-submit
  read composition, independent rejected lineage cases and propagated authorizer
  exceptions. Retain the real activation validator's malformed-body test here.
- `backend/tests/projects/test_active_guide_read_composition.py`: exact active
  guide fact/digest binding, separate validator delegation, independent rejection
  cases and propagated authorizer exceptions.
- `backend/scripts/test_lane_catalogue.py` and
  `backend/tests/test_ci_lane_catalogue.py`: explicitly select the two new test
  files in the existing PROJECT owner pair, retaining exact catalogue parity;
  prove the dedicated coverage command selects the relocated read tests.
- `.github/workflows/backend.yml`: update only the dedicated PROJECT read
  coverage command's test locations; retain its source, branch mode and 90% floor.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: regenerate current inventory;
  remove the retired oversized helper entry and shrink monolith debt, no new debt.

### Not allowed

Production, migrations, other workflow changes, dependencies, grants/actions, public API
activation, selection weakening, skips, coverage floors, global conftest or test
modules imported as support. Do not replace real database tests with these fakes.
The remaining diagnostic-read fake/consumer tests stay untouched.

## Design and decisions

Keep one owner-scoped fake repository, no second policy engine. Existing row
values and repository methods remain equivalent; splitting initialization must
not change the order of UUID generation, hash input or cross-row references.
Recording/exception behavior uses standard AsyncMock, not another mock framework.

Each rejection starts from a new valid fixture and changes one existing fact.
Keep the prior fallback RuntimeError proof when a deliberately permissive
authorizer unexpectedly allows a missing target. This proves the composer guard,
not AUTH denial. Separately raise a sentinel authorizer exception on a valid
target, assert the same exception propagates, and verify exactly one call.

Exact digest expectations use explicit fixture-owned payloads and the shared
canonical hash primitive; do not call the production composition helper to
compute its own expected result. Keep fact-projection and validator-delegation
proof separate. Validator call capture must assert the actual rows, source items,
exception type and `require_payment_policy=False`, not just booleans.

## Acceptance criteria

| Existing or missing atom | Named proof in the new modules | Boundary |
| --- | --- | --- |
| Two policy actions return the exact row and resource facts | `test_policy_read_binds_exact_target_facts` (effective/pre-submit) | Service composition |
| Policy digest covers the canonical locked chain | `test_policy_read_binds_exact_digest` (effective/pre-submit) | Service composition |
| Draft guide, wrong effective guide, stale checker snapshot | `test_policy_read_rejects_changed_lineage` (three isolated cases) | Composer fallback, not AUTH denial |
| Valid policy target does not swallow authorizer exception | `test_policy_read_propagates_authorizer_exception` (two actions) | Service exception propagation |
| Active bundle returns the exact rows and context fields | `test_active_guide_read_binds_exact_bundle_facts` | Service composition |
| Active digest covers all explicit row identities and available stamps | `test_active_guide_read_binds_exact_digest` | Service composition |
| Exact source and readiness validation delegates | Separate `test_active_guide_read_validates_source` and `test_active_guide_read_validates_readiness` | Delegation only |
| Stale post-submit checker binding | `test_active_guide_read_rejects_stale_post_submit_binding` | Composer fallback |
| Readiness validator raises PolicySetupBlocked | `test_active_guide_read_conceals_validator_failure` | Composer fallback |
| Valid active bundle does not swallow authorizer exception | `test_active_guide_read_propagates_authorizer_exception` | Service exception propagation |
| Hash-valid malformed body reaches real activation guard | Retain `test_activation_readiness_normalizes_hash_valid_malformed_policy_body` | Real service validator |

Every removed assertion maps to the above equivalent or stronger proof. No
deletion quota: replacing compound tests may increase named/expanded counts.
New files stay below 500 lines and helpers below 100; every test has one primary
behavior. All unrelated tests/decorators/parameter rows remain AST-identical.

## Risk and review routing

- L1: security-sensitive authorization fact proof and lane registration.
- Before code: focused plan review of actual guard reachability and oracle design.
- Final QA/test-delta; security/CI-integrity; architecture/reuse focused reviews.
- Human focus: exact digest oracles, honest fake-versus-database boundary,
  no hidden loss of historical assertions and no new oversized helpers.

## Evidence

Locally run both new modules, relevant catalogue parity checks, Ruff, structural
validation, Commitrail, links/stale scans and diff checks. A valid control must
pass. In-memory substitution of a wrong well-formed digest must fail the exact
digest assertion (the old prefix assertion would pass); bypassing one lineage
guard must fail its rejection assertion; passing the wrong source/readiness
arguments must fail the exact delegation check. Do not commit mutants.

Compare all removed assertions and unaffected ASTs. Hosted full backend owns
PostgreSQL, race/rollback, isolation, exact-node reconciliation and all coverage
floors. Preserve all baseline cases except the explicitly mapped four replaced
functions; normalize only documented run-generated UUID labels when comparing
different hosted runs. No global deadlock-freedom or exhaustive audit claim.

## Review findings

QA06-01 / CI06-SELECTOR-01 identified a missed secondary consumer: the dedicated
coverage command still selected the old monolith names, even though the full
lanes selected the new files. This is a reviewed scope correction, not part of
the original allowed-file set. The command now names the three unchanged
diagnostic functions and both new modules explicitly, with its coverage target,
branch measurement and 90% floor preserved. The exact command passes 25 cases
at 90.17% locally. `test_project_read_coverage_gate_selects_relocated_proof`
rejects the old selector, protecting this focused gate independently of broad
lane inventory. Hosted verification remains required after this correction.

The selected old tests are current and necessary but their grouping and weak
digest assertions need repair. No selected behavior is obsolete or redundant.
PLAN06-DOC-01 corrected the acceptance heading to the canonical record format.
Plan review confirmed the negative fixtures reach the real composer guards,
the hash oracle adds discrimination beyond runtime shape validation, and the
malformed-body test reaches the real service guard. Preserve the originating
autouse settings-cache cleanup explicitly in both new modules.

Implementation comparison preserves every unrelated top-level definition,
decorator and parameter row. The fake's three initialization phases concatenate
to its exact original statements; seeded UUID/clock construction produces equal
rows, identities and hash inputs. Its repository getter bodies are unchanged.
The source fixture is 186 lines; read test modules are 172 and 208 lines.

Focused execution passes 42 combined read-composition and catalogue cases. Valid controls pass;
wrong well-formed binding digests still pass the old prefix-only tests but fail
the new equality assertions. Bypassed effective-guide and post-submit binding
guards fail at missing-denial assertions. Wrong delegated source items and
compensation flag fail the exact call assertions. These temporary mutants are
not committed. Hosted exact-head coverage and case custody remain PR evidence.

## Reconciliation

- Current source: merged guide/bundle fixture isolation at `3c9dbd44`.
- Next usable boundary: remaining PROJECT diagnostic/mutation test audit and
  cohesive decomposition, then AUTH. POL-04A2 stays paused.
- Remaining risk: controlled rows and AsyncMock cannot prove real database
  locks, authorization grants or persisted evidence. Retain their separate tests.
