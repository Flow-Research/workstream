# Decisions: WS-QUAL-001 Backend Coverage Floor

## D1: Ninety percent is authoritative

Status: accepted by the user on 2026-07-11.

The complete backend application must maintain at least 90 percent statement
coverage. The user corrected the initial 80 percent instruction to "90% not
80". The floor applies to all modules under `backend/app`, not only changed
files.

## D2: No exclusion-based compliance

Status: accepted through planning PR #99 on 2026-07-12.

Coverage may not be raised by omitting application modules, adding coverage
suppression pragmas, or measuring only a favorable package subset.

## D3: Ratchet from a reproducible baseline

Status: accepted through planning PR #99 on 2026-07-12.

Because current coverage is materially below 90 percent, implementation uses a
non-decreasing enforced ratchet across bounded PRs and reaches 90 in the final
chunk. Machine evidence preserves exact covered/total statements and a
six-decimal configured floor; base-ref comparison prevents regression. This is
an execution strategy, not a reduction of the final requirement.

## D4: Coverage work pauses AUTH-02 publication

Status: accepted through planning PR #99 on 2026-07-12.

AUTH-02 remains implemented on its own worktree but is not published while the
new 90 percent repository requirement lacks an approved enforcement path. The
pause avoids mixing roughly 849 statements of legacy coverage debt into an auth
PR. Resumption requires WS-QUAL to complete through its permanent 90 percent CI
floor and final post-merge memory, followed by an explicit user signal. This
decision does not discard or redesign the off-main auth implementation.

## D5: Behavior proof outranks percentage gains

Status: accepted by the user on 2026-07-12.

Coverage is a safety signal, not the purpose of a test. Every new test must
protect a real behavior or safety invariant and assert an observable result such
as state, lifecycle, authorization, audit, queue/retry, HTTP, redaction, cleanup,
or fail-closed behavior. Execution-only tests added to hit lines or percentages
are prohibited even if they increase coverage. Test-delta and product/ops
reviewers must reject them.

## D6: Chunk 01A uses a bounded 700-line exception for genuine proof

Status: accepted from the user's D5 direction on 2026-07-12 after internal L1
circuit-breaker review.

The original 500-line forecast proved incompatible with the required owned-DB
lifecycle, redaction, cleanup, ratchet, and negative behavior matrix: the two
control scripts alone require 387 readable lines before tests, guards, workflow,
and runbook. After the D7 split, `WS-QUAL-001-01A` may use at most 700
implementation lines; the cap applies to 01A, not the former combined Chunk 01
or 01B. The added budget is reserved for behavior tests and safety/error
handling. Allowed files and all production exclusions remain unchanged.
Crossing 700 requires another split and a new human decision.

## D7: Split database isolation from coverage policy

Status: accepted on 2026-07-12 after all required L1 reviewer groups rejected A2.

The executable harness reached 923 implementation lines before completing the
required ratchet and negative behavior matrix. Real concurrency/interruption
catalog proof, strict policy failure tests, and the operator runbook were
underestimated by A1. The rejected A2 proposal would have raised the cap to
1,100. Reviewers required `01A` for the least-privilege database lifecycle and
`01B` for coverage policy/CI/evidence. The split preserves genuine proof without
compressing safety code. Production scope and later chunks remain unchanged.

## D8: Split 01B policy core from baseline and CI publication

Status: accepted after internal split review and explicit user approval on
2026-07-12. Only 01B1 is started; 01B2 retains its later separate checkpoint.

The reviewed combined 01B contract proved larger than its 500-line boundary:
policy plus 19 behavior tests reached 480 lines before configured coverage,
workflow integration, the runbook, and several required negative cases. Further
compression would weaken proof or readability. The proposed repair is 01B1 for
pure policy parsing/arithmetic/schema/delta behavior, followed after merge and
memory by 01B2 for Git provenance, configured baseline evidence, CI ratchet,
and operations. Each retains a separate 500-line cap, L1 review, PR, merge,
memory, and explicit start checkpoint. No production or coverage-raising test
scope is added.

## D9: Stop 01B1 after repeated semantic-integrity findings

Status: circuit breaker triggered on 2026-07-12; replacement split direction
approved by the user and pending internal split review.

The 01B1 candidate reached 496/500 lines after two repair cycles. Eight review
tracks passed, but final test-delta review still found executable unittest skip
forms, aliased `pytest.raises` deletion, and missing successful arithmetic
boundaries. These are valid acceptance-criterion gaps in the same repeated
semantic-integrity class. The chunk must split again rather than compress tests
or exceed its cap. No replacement chunk may start without internal plan review
and explicit user approval.

## D10: Split parsing from semantic repository-delta enforcement

Status: direction explicitly approved by the user on 2026-07-12; internal split
review pending.

`01B1A` owns complete-app coverage arithmetic, intended configuration parsing,
canonical evidence parsing, strict runner metadata parsing, application pragma
validation, the compute-only CLI, and their behavior tests. `01B1B` separately
owns Git-helper integration, bounded memory/scope accounting, executable
skip/xfail detection, aliased assertion-deletion detection, and real repository
regressions. `01B2` remains unchanged. This boundary keeps parser arithmetic
independent from repository-diff semantics without weakening either proof set.

## D11: Stop 01B1A after two parser-normalization repair cycles

Status: circuit breaker triggered on 2026-07-12.

The 01B1A candidate reached 394/400 lines and 56 focused tests. Final QA and
security review still found accepted `pragma:nocover` comments and leading-space
normalized duplicate pytest-cov requirements. These are valid bypasses in the
same parser-normalization class after two repairs. The task-chunk loop requires
a stop and replan instead of a third repair cycle, even though the individual
edits are small. No PR may open while required reviewers fail.

## D12: Continue coverage and AUTH in isolated worktrees

Status: explicitly directed by the user on 2026-07-12.

Coverage remains isolated in `workstream-qual-001`; AUTH-02 resumes off-main in
`workstream-auth-001-02`. Each track owns its branch, tests, reviewers, and
evidence. Neither track edits the other's worktree. AUTH may prepare its PR in
parallel but must satisfy the repository's current coverage gates before merge.
The 01B1A-R1 replacement is limited to closing the two recorded parser bypasses
without reopening semantic-delta or 01B2 scope.

## D13: Reuse the installed coverage runtime's exclusion grammar

Status: proposed corrective replacement under the user's direction to finish
the coverage blockers; internal contract review pending.

R1 correctly rejected the two named bypasses but used a broader approximate
regex that rejected explanatory comments coverage.py would include. R2 replaces
that approximation with `coverage.config.DEFAULT_EXCLUDE[0]` from the installed
coverage runtime selected by the pinned pytest-cov toolchain and adds
positive/negative same-runtime equivalence proof. Coverage.py itself is not
exactly pinned; R2 records the resolved version, while later 01B2 owns committed
tool-version evidence. This is a reuse correction, not new policy scope.

## D14: Replace file-global semantic aliases with lexical binding

Status: proposed after B1B's two-cycle circuit stop; internal contract review
pending under the user's direction to keep coverage and AUTH running in
parallel.

The B1B candidate correctly handled committed renames and base-AST assertion
spans, but file-global alias sets misclassified locally shadowed pytest names,
and broad `.skipTest` detection caused a test expectation to be weakened. R1
must resolve actual bindings by lexical scope, preserve arbitrary local
lookalikes, and retain every passing Git/scope/size invariant. This is a
corrective replacement, not B2 or application scope.

## D15: Use measured lexical-binding allocation

Status: proposed after R1's first implementation checkpoint; internal contract
review pending.

R1's shared resolver draft measured 282 total implementation lines before its
required adversarial matrix, so the reviewed 300-line cap could not preserve
proof. The draft was discarded. R2 retains the identical behavior and file
scope with a 350-line cap allocated from measured code: 290 lines through the
lint-clean resolver, 50 lines for the matrix, and 10 reserve. This changes only
the evidence-backed size boundary; it does not admit B2, AUTH, application,
configuration, workflow, evidence, documentation, or coverage-raising scope.

## D16: Delegate lexical facts to Python's symbol table

Status: proposed after R2's cycle-zero proof-fit stop; internal contract review
pending.

R2 proved that a partial AST symbol engine misses lambda, vararg, comprehension,
exception-target, nested-class, and control-flow semantics. R3 uses stdlib
`symtable` as the authority for lexical namespaces and layers only bounded AST
framework-value flow and joins on top. The normal 500-line L1 cap provides room
for the reproduced regression matrix without compression. This remains semantic
test-integrity scope only; B2, AUTH, application, configuration, workflow,
evidence, documentation, and coverage-raising tests remain forbidden.

## D17: Fund complete control-flow proof instead of compressing cycle one

Status: proposed after R3's proof-fit stop; internal contract review pending.

R3's 468/500 candidate left 32 lines, while measured review requires roughly
47 policy lines and 20 regression lines after replacement savings. R4 uses a
550-line cap: existing 468, policy through 515, tests through 535, and 15
reserve. The added budget closes already-reproduced semantic behavior only; it
does not admit B2, AUTH, app, config, workflow, evidence, docs, or coverage-
raising tests.

## D18: Separate single syntax consumption from abstract state joins

Status: proposed after R4's cycle-zero stop; internal contract review pending.

R4 replayed AST subtrees to simulate paths, which is incompatible with ordinal
symtable child consumption. R5 visits every syntax node once. It joins incoming
abstract states before a handler/case, uses conservative loop-carried binding
summaries instead of replay, and applies mandatory regions afterward. Assignment
target loading/binding and comprehension ownership share one recursive helper.
This is a replacement architecture for existing findings, not new product/B2/
AUTH/config/workflow/evidence scope.

## D19: Close provenance transitively with evaluation-order proof

Status: proposed after R5's cycle-zero stop; internal contract review pending.

R5 repaired semantic replay but its loop summary was a one-step heuristic.
R6 replaces duplicate RHS walks with one shared cursor-neutral provenance
summary evaluated to closure, including outer-executed nested-scope headers.
It also funds exact iterable-to-target propagation, Python evaluation order,
and distinct sequential `except*` handling. The 800-line cap is restricted to
these reproduced integrity gaps and their tests.

## D20: Use one recursive iterable-element abstraction

Status: proposed after R6's hard-cap stop; internal contract review pending.

R6 closed binding fixed points but substituted raw comprehension elements
without their target environment and special-cased generator consumers. R7
uses one recursive element-provenance function for literal containers,
set/dict keys, and nested comprehension/genexpr environments. Control summaries
use the same abstraction to decide structural consumption/reachability. The
950-line cap funds only these reproduced semantic gaps and regressions.

## D21: Enforce syntax integrity instead of predicting execution

Status: proposed after R7's mandatory two-cycle stop; internal contract review
pending.

R1-R7 demonstrated that exact reachability, value provenance, iterator
consumption, builtin behavior, and class control flow constitute an unbounded
Python abstract interpreter. That work did not raise backend coverage and kept
the measured application baseline at 79.25 percent. R8 narrows B1B to its actual
security purpose: framework-qualified weakening syntax is forbidden in changed
tests, and syntactic assertion constructs cannot be deleted. It deliberately
does not decide whether syntax executes. False-positive risk is bounded by exact
absolute-import ownership, stdlib lexical scopes, relative-import exclusion,
and local-lookalike tests. Ownership is monotone within a scope and propagates
only through cycle-safe simple Name-to-framework Name/Attribute aliases; no
container, unpacking, comprehension, iteration, call return, wrapper value,
statement order, reachability, or runtime inference is admitted. Execution
contexts cannot hide an already-owned construct and cannot create ownership.
This smaller gate must finish before B2 and the
coverage-raising service chunks can move the repository toward 90 percent.
