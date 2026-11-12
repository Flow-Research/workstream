# Size-based rewards and dedicated Finance fulfillment

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: One current Workstream v0.1 implementation of sized rewards and Finance fulfillment, in one PR with cohesive, revertible commits.

## Goal and human direction

Implement `workstream_finance_exec.md` under the user's explicit correction:
Workstream has not shipped. Completely replace superseded development behavior.
Do not introduce reward-model versions, parallel old/new implementations,
compatibility aliases, historical response decoders, old-hash fallbacks, or tests
and fixtures whose only purpose is preserving obsolete behavior. Update affected
callers, storage, contracts, schemas, clients and documentation together.

The prior implementation incorrectly treated development fixtures as a shipped
compatibility obligation. That approach is rejected. Earlier commits and review
receipts remain Git history, not current requirements or authorization.
The existing external protocol identifiers and real policy/submission revisions
retain their actual meanings; they do not select competing implementations.

Deliver sized task selection through immutable submissions, governed revisions,
shared final acceptance and selected awards, followed by authenticated Finance
fulfillment. Preserve current authority, locked lineage, atomicity and immutable
business evidence. One eligible Finance human authorizes bank transfers. Do not
merge, deploy or initiate live payments without the required authorization.

## Current behavior and concrete gap

The branch contains current reward policy authoring, wire validation and
create-time size work. The replacement removes reward-model markers, old
graph/response readers, archived replay fixtures and the predecessor-specific
preflight. The selected-acceptance implementation now records exact Task,
Assignment, admission and immutable Submission selection, uses it for awards and
reads, and extends existing revision/replay owners. Full migration, concurrency,
revision/replay and suite qualification remains required.
No complete Finance runtime or end-to-end fulfillment journey is delivered.

## Immediate bounded replacement

Allowed files: this specification/change record; the affected CON policy/API,
COMP award/API, TASK create/import/replay/schema owners; FIN wire schemas and
fixtures; shared financial wire validation; unreleased reward/task migrations;
their CLI/MCP consumers and frozen contracts; focused and affected existing
fixtures/tests; affected current docs and roadmap claims. Remove predecessor-only
preflight/capture/archive utilities and compatibility-only fixtures/tests after
tracing their consumers. Replace affected callers; do not add aliases.

Prohibited: unrelated cleanup, new workflow/controller/auth stores, changing
human review defaults, price inference, silent financial rewrites, deleting
retained database rows or artifact data, weakened CI/assertions, live payments,
deployment, merging or a second PR.

Plan:
1. Reconcile the specification with the user's correction and remove competing
   reward-model versions and historical enrollment/compatibility requirements.
2. Replace policy graph, DTO, SQL and client validation with the one sized/fixed/
   unpaid model. Remove the reward-model marker rather than hardcoding it.
3. Remove old Task response/hash/manifest branches. Current receipts always
   record size and use the one canonical request/response format. Normalize
   omitted creation size to Small before hashing; explicit Small has the same
   current meaning. Import membership uses the current canonical row shape.
4. Remove compatibility-only tests/fixtures/utilities. Retain or replace proof
   of authorization, exact source/quantity selection, immutable evidence,
   concurrency, rollback and retries through current public owners.
5. Verify affected public API, PostgreSQL, CLI and MCP behavior, then freeze a
   clean candidate for focused review and keep the single PR draft.

Migration boundary: replace this PR's unmerged migration implementations within
its existing single Alembic chain. Do not maintain a transition from intermediate
commits in this PR. Fresh installation and supported baseline upgrade must reach
one current schema. If retained economic facts or immutable command bodies cannot
be converted without inventing amounts, changing evidence or deleting data, fail
atomically with a concrete incompatibility report. Do not preserve an old runtime
or fabricate values to make migration pass. This refusal is a data protection
boundary, not another implementation. Actual retained-data deletion needs
explicit authorization; removing obsolete code/tests does not authorize it.

Acceptance criteria:
- No reward-model marker, old/new policy branch, archived response decoder or
  old-hash fallback remains in the affected runtime or current contracts.
- Compensated accepted submissions require exactly Small/Medium/Large quantities;
  reviewer compensation is one fixed quantity; unpaid rules have no awards.
- Manual/JSON/CSV creation records exact size; omission means Small; null and
  unknown values fail. New Task size is immutable and receipts record it.
- Current replay/import checks preserve fresh AUTH, source/receipt custody,
  canonical hashes and atomicity using the single current format.
- Clients reject substituted size, null/partial/mixed representations and unknown
  obsolete marker fields; no partial or unsafe success output is published.
- Database guards independently enforce graph/header/tier invariants. Upgrade
  incompatibilities roll back without data loss or invented financial terms.
- Current docs describe only this v0.1 behavior and explicitly qualify unfinished
  selection/revision/award/Finance execution.

## Risk, review and human focus

Risk: L0 for the complete financial initiative; the immediate replacement changes
architecture, authorization/replay and migration boundaries. Before code, obtain
focused plan review. After deterministic evidence, use security, architecture,
QA/test-delta, reuse and documentation tracks; CI integrity checks that fixtures,
checks and test selection remain honest. Product review applies to lifecycle and
financial behavior. Group related specialties proportionately; do not claim
multiple independent reviews from one combined assignment.

Human review focus: one current model, correct selection and economic facts,
retained-data refusal without deletion, current AUTH/replay boundaries, exact
public-API and durable-worker evidence. Prior compatibility review passes do not
qualify the replacement.

## Replacement evidence and remaining dependency

Plan feasibility was reviewed at `dc6a621a90bbcd7ea41ec078b095e7420e9fc496`
under the corrected user direction. No compatibility requirement survives that
review. Current-model implementation proof during work: 222 pure financial,
policy/size/selection cases; 95 focused CON/participation cases; 52 MCP client
cases; 36 rebuilt CLI cases; Go package tests; MCP strict typing; scoped Ruff,
stale wording and Markdown links. These are working-tree supporting results,
not a full-PR or final-target qualification.

Fresh isolated PostgreSQL installs the replacement schema without model-marker
columns. Four current admission/creation cases passed, including canonical
omission/explicit-Small equivalence and unchanged financial data after refusal.
A broader current public run passed 24 cases, then loaded inconsistent fixture
revisions because a helper changed during execution. Both helper and caller now
use the single header contract; replay the failed claim case on the frozen
candidate. Do not add an old parameter alias to satisfy an already running
process. The final compound award FK was added after those database runs;
its actual schema fingerprint was separately probed and installed in the rigid
schema test gate. Exact candidate proof remains required.

Review identified remaining dual-instrument positive fixtures and stale enrollment
wording. The repair replaces those arrangements with one current instrument,
retains independent money and points cases, and removes the obsolete operation.
Baseline migration tests retain immutable-data preservation proof; they do not
provide a current runtime compatibility path. Current
complete-set contracts and readers accept only zero/one award. The missing-award
mutation now omits the required single award rather than omitting a fictional
second award. No count/coverage gate or skip is weakened.

The remaining paid-path dependency is explicit immutable Submission selection:
policy-wide tier enumeration cannot select an earned award. Finish the existing
TASK/ART copy chain, selected CON source/read/cache lookup and SQL completeness
closure, including governed revisions, before qualifying paid acceptance or its
integration tests. Do not preserve the old all-definitions operation, choose the
first tier, or describe isolated passing module checks as a paid journey.

## Completion and remaining work

After this cleanup, finish the same PR's selection-copy chain, governed revision,
selected-award/root/outbox atomicity, Finance/AUTH/issuer and worker partition,
configuration/plans/credit/transfers, authenticated HTTP/callback/recovery paths
and realistic failure/retry drills from specification sections 19–20. No next
stage is delivered merely because contract/module tests pass.

Assess and update affected roadmap summaries, scoreboard, diagram, gates and
references in this PR. Run stale-wording and Markdown-link checks. Local sheet
exports, when present, follow repository rules. Keep PR #709 draft until the full
scope and applicable reviews are complete; merge remains a specific human action.

Review repairs remove the remaining enrollment CLI command, historical-credit
authorization branch and orphan admission discriminator from the current
specification/ADR. Current points credit follows its exact active arrangement;
bank transfers retain their separate human authorization and prior-fulfillment
checks. Duplicate-award storage proof names the actual single-award constraint.

## Selected reward copy chain within this PR

Concrete gap: current policy-wide definition enumeration fails closed for a
three-tier submitter rule. It must be replaced with the one exact immutable
Submission selection; no parallel reader or compatibility implementation remains.

Allowed files: TASK models, existing screening/claim/context/admission/replay,
revision preparation/recovery/routing and read owners; CON reward-selection and
published-terms APIs/repository, contribution source/repository/participant;
ART admission/binding public contracts, TASK routing-manifest/accepted-effects
contracts, REV shared FinalAcceptance participant/API, CON participation/source
reads and COMP award completion; existing AUTH task-replay guards/contracts;
existing composition roots and their affected callers; one forward migration in
the current chain replacing affected guards; affected public schemas, CLI/MCP
contracts, fixtures/tests and current documentation. No new workflow owner,
policy lineage type, storage engine or authorization path is introduced.
All earlier prohibited changes remain prohibited.

Implementation sequence:
1. Persist Task locked definition, Assignment size/definition and immutable
   Submission size/definition. Resolve through the existing transaction-bound
   CON RewardSelectionPort at screening; validate at release and copy at claim
   and submission admission. Update every direct constructor explicitly; no
   optional dependency fallback or inferred first-tier selection.
2. Extend existing revision candidates/packets with distinct prior/target reward
   facts alongside activation snapshots, canonical packet hash and contributor
   projection without internal bindings. Keep TaskPolicyLineage unchanged.
   Select the same immutable size under the chosen target policy; missing or
   invalid target follows existing blocked/repair handling. Existing revision
   operation alone rebases continuing Task/Assignment; old Submission is immutable.
3. Replace policy-only terms requests/caches with exact recorded selection keys.
   Replace submitter contribution all-definition enumeration with immutable
   Submission-selected definition. Preserve fixed reviewer and unpaid branches.
   Replace SQL completeness with selected zero/one definition equality.
4. Extend existing SQL guards for exact project/policy/rule/size/definition
   equality, immutable copied evidence, and governed revision authorization.
   Upgrade refuses incompatible retained facts atomically without rewriting them.
   Committed replay retains fresh AUTH and returns the original exact result
   after a later continuing-context rebase, without new claim authority.
5. Update current callers/contracts/fixtures together; remove superseded query,
   receipt and fixture assumptions. Run pure guard/selection tests followed by
   real PostgreSQL public API/worker acceptance and failure/retry drills.

Acceptance/proof: small/medium/large select distinct configured quantities;
unpaid selects no definition/award; fixed reviewer remains one independent
award. Reject cross-project/policy/size/definition substitutions in owner code
and direct SQL. Preserve assignment/submission equality, old-submission evidence
after upward/downward/unpaid/instrument-changing revision, blocked-target repair,
acknowledgement hash, concurrent claim, rollback and exact replay. The default human-required branch stops at review handoff with no
FinalAcceptance/contribution/award, preserving its existing unavailable human
acceptance guard. The automatic branch uses shared FinalAcceptance and commits
the selected award atomically; live human acceptance is not qualified here. Cache/batch reads must distinguish two sizes under one
policy and never expose bindings to contributors. Live-drill defects require
focused regressions. Existing pure proof and baseline migration-data proof
remain unless replaced by meaningful current proof. Full-suite and real
integration checks remain required before PR readiness.

Risk remains L0. Plan review must trace owner order and one feasible positive and
negative fixture before implementation. Security, architecture, product/ops,
QA/test delta, reuse and docs/CI reviewers inspect their affected boundaries;
shared checks run once per frozen candidate. Human focus is exact selection,
AUTH, immutable lineage, revision/replay and transaction atomicity. This boundary
qualifies selected acceptance only; it does not claim Finance runtime delivery.

Plan-review corrections (SELECTED-PLAN-001/002 and PLAN-SELECT-001–004):
- Immutable selection flows TASK public acceptance-source/accepted-effects facts
  through REV FinalAcceptance into CON participation; CON does not join TASK's
  private ORM. ART binding/context digests and admission validation carry the
  same copied facts. Existing revision packet/projection and SQL guards own the
  rebase; no separate state machine.
- Claim replay means fresh-authorized same-original-actor/same-assignment read
  of its exact committed result after rebase. Existing AUTH and TASK guards must
  distinguish this from new-claim eligibility; changed request, foreign actor or
  reassigned assignment remains denied. Submission replay means its exact
  existing admission/creation receipt returning original immutable evidence
  after continuing-context rebase, with fresh authority and no new Submission,
  claim or economic fact. Routing/acceptance replay independently retains exact
  source and original selected award; it never reselects from the current Task.
- Named future tests in tests/finance/test_selected_reward_journey.py:
  test_medium_public_claim_to_selected_automatic_acceptance publishes three
  distinct tier quantities, creates Medium, calls real screen/release/claim,
  admits ZIP and creates Submission, runs actual outbox/completion, and compares
  all copied IDs and sole medium quantity; test_original_submission_replay_after_rebase
  retains that Submission/admission and proves original response after governed
  revision; test_human_required_has_no_acceptance preserves the default handoff.
  Fixture setup may use existing policy approval owners, but cannot seed Task,
  Assignment or Submission instead of these operations. Durable-worker public
  drill remains distinct from focused in-process integration proof.
- Named future tests in tests/finance/test_selected_reward_storage.py:
  test_same_policy_wrong_tier_copy_rejected substitutes valid Large into the
  Medium Assignment/Submission to reach equality guards past valid FKs;
  test_cross_project_selection_rejected checks ownership;
  test_deferred_selected_award_completeness checks missing/extra/wrong selected
  award at commit; test_unpaid_has_zero_awards checks unpaid closure. Each records
  an unchanged transaction snapshot on rejection. Independent-session
  test_concurrent_claim_keeps_one_selection and
  test_acceptance_replay_keeps_one_selected_award protect concurrency/retry.
- Named future tests in tests/finance/test_selected_reward_migration.py:
  test_fresh_install_and_empty_current_upgrade verifies actual Alembic head;
  test_incompatible_facts_refuse_without_rewrite compares all retained rows and
  starting schema revision after atomic refusal. Existing exact schema-fingerprint
  fixture must reflect installed columns/FKs/checks/deferred and immutable guards,
  using an actual isolated PostgreSQL probe. No fake migration or percentage gate.
- Current storage substitution proof uses the real foreign fixture binding and
  definition independently. PostgreSQL exposed the absent second-local-binding
  assumption; the repair removes it rather than extending old fixture behavior.

- tests/finance/test_selected_reward_journey.py::test_original_claim_replay_after_rebase
  explicitly covers fresh original-actor authority returning the exact committed
  result; changed request, foreign actor and reassigned assignment are denied,
  with no new assignment or economic fact. The durable-worker public failure/
  retry drill remains a later same-PR readiness gate, not proof supplied by this
  selected-acceptance slice's in-process integration tests.

## Selected-acceptance implementation evidence

The implementation replaces policy-wide earning/read enumeration with exact
recorded selection. Screening and claim retain the existing TASK operation;
ART carries selection in its immutable PRE reservation/admission; routing and
REV FinalAcceptance carry immutable Submission facts into CON and COMP. Read
keys include policy, size and definition. Contributor evidence obtains source
selection through TASK's existing public port and excludes binding material.
The current SQL chain independently guards selection equality, immutable
Submission evidence, revision packet/rebase closure and deferred selected-award
completeness. No old-format reader or alternate earning operation is retained.

Working-tree public HTTP drills passed automatic and default human-required
branches, with distinct Small/Medium quantities under one policy and exact
Submission-derived contribution evidence. The points automatic branch also
passed with whole-number quantity output. Direct SQL rejected a valid Large
policy definition substituted into a Medium assignment; immutable Submission
mutation was rejected without changing stored evidence. The existing real
revision/acknowledgement drill passed after repairing the deferred closure's
CASE-expression grouping. These are supporting development results; freeze and
replay against the final candidate before a readiness claim.

Additional supporting proof: 71 PRE/export cases, 59 financial/size/receipt cases,
4 revision projection cases, 144 MCP contract/operation cases with live OpenAPI
comparison, 26 built CLI read/revision/export cases, Go packages, scoped Ruff and
module-boundary validation. Retain exact execution custody in the PR evidence;
these counts are not coverage gates or whole-PR qualification. Clean-candidate replay of
migration refusal, independent-session claim/acceptance races, original claim/
Submission replay after rebase and durable-worker failure/retry proof stays
required. Finance roots, handoff and execution remain unfinished.

The real paid-to-unpaid revision drill also proves original claim and Submission
replay: fresh original-actor authority returns exact prior results, changed input
returns conflict, and another eligible same-project submitter is denied. Work,
receipt and economic row counts remain unchanged; the original immutable
Submission is identical. Its regression exposed comparison of intentionally
masked contributor receipt fields with private source coordinates. The repair
keeps full immutable-context hash validation and compares captured public fields
through the canonical contributor projection instead of weakening lineage or
adding another receipt format.

The actual migration drill exposed a stale Alembic preflight revision list that
stopped at `0068_issuer_profile_email`. It now recognizes the current migration
chain through `0071_selected_task_reward`; unsupported starting states still
refuse. The new migration tests use actual Alembic installation and upgrade,
exact retained row snapshots and the existing full schema manifest collector.
They assert that incompatible screened work refuses before changing data or DDL.

Affected current read/authorization fixtures now supply explicit selection facts.
The task-detail tests retain exact public result/privacy, scope, transaction and
nonlocking proof; assertions tied to the superseded scalar reward query and its
query count are removed. Existing independent-session claim and acceptance race
tests additionally compare the committed selection with the Task or immutable
Submission. No required behavior is replaced with an end-to-end-only assertion.


## Current command replay and authority hashes

TASK authority hashes include immutable size and exact selected definition in
one current field set shared by command, invalidation and revision recovery
owners. PostgreSQL's revision digest matches that format. Non-null policy
requirements stay distinct because unpaid selection has no definition. No
earlier hash reader is retained.

The existing TASK/AUTH owners replay original manager create, screen and release
responses after continuing work advances or rebases, under fresh
same-actor authority and the exact immutable receipt namespace/request. They validate original captured identity, size, operation state and policy
coordinates against the original immutable source, preserving the receipt and
current transition authority. Creation has its exact unscreened null-policy source. Screen/release use
the immutable original Submission when continuing context differs. Missing or
substituted source stays a conflict. Focused hash substitution proof and the public rebase drill now cover recorded
manager commands and reject changed bodies. Existing AUTH guards and database receipt immutability
remain required. Risk and reviewer tracks remain L0 as declared above.


Supporting repair evidence: the new selected-definition hash regression failed
on the preceding implementation because distinct selections had the same hash;
32 focused contract/receipt cases pass after replacement. The real public
paid-to-unpaid drill passed original create, screen, release, claim and Submission
responses, with changed requests rejected and no new work/economic records.
PostgreSQL's existing revision digest now hashes the same selection facts;
its installed schema fingerprint was obtained from an actual isolated migration.
The public helper compares that SQL digest with the actual claim receipt hash.
Final clean-candidate execution remains required; these are development results.

Migration safety passed actual installation/upgrade/idempotency and atomic
retained-data refusal. Seven existing independent-session, rollback, incomplete
award and unpaid rejection cases passed. The read-fixture batch passed 49 cases
before a fixture tried to access an intentionally private definition ID through
public JSON. That fixture now loads the exact stored Task instead; rerun the
remaining focused cases. None of these results qualifies full-suite, durable
worker, S3 or Finance execution completion.


A combined Finance/migration collection exposed two test utilities importing bare
`conftest`, which resolved to the Finance directory's fixture module. They now
name `tests.conftest` explicitly, including reset monkeypatch targets; no runtime
compatibility path is added. The old cap-recovery fixture also executes current
owners against a predecessor schema and attempts to upgrade retained facts to
head. Its remaining dependency on superseded owner shapes must be replaced with
bounded migration-data safety proof or current-owner recovery proof before
full-suite readiness. Do not restore obsolete writers to satisfy that fixture.


## Reviewed removal of unreachable development recovery

Current preparations always receive a PostgreSQL-observed clock; current routing
atomically exhausts at the cap. The old null-clock pause and cap-blocked recovery
have no current producer, and0069/0071 refuse the retained facts they require.
Both internal plan reviewers approved removing these affected obsolete paths.

Allowed additional affected files: TASK recovery/exhaustion/replay contracts and
models, recovery-only audit API/schema/adapter, recovery-only outbox notice and
registration, their current SQL guards in0071, test clock helpers, obsolete runtime
fixtures and corresponding CI catalogue/behavior ownership entries; affected
architecture and roadmap descriptions. Preserve current root/event recovery,
PM blocked-context repair and clocks, canonical cap exhaustion and exact replay,
all AUTH/transaction guards, and bounded migration data/backfill proof. Remove
empty-only persisted recovery machinery only after explicit locked admission
refuses any retained exhaustion evidence. No data deletion or old reader.
Acceptance: no obsolete branch/event/flag/column/handler remains in current
runtime; current exhaustion/recovery/pause/expiry, rollback/races and public
selected chain pass; schema and test inventory match. Risk stays L0; replay the
same focused reviewer tracks after batching repairs. Human focus remains
immutable evidence, current behavior preservation and complete removal.


The CI catalogue now registers each new Finance/reward proof in its existing
semantic lane; obsolete recovery-only modules and residue overrides are removed.
The behavior partition is regenerated for the six actual new financial owner
files, with exact additive authorization and neighbor/removal rejection proof;
no broad deletion permission is added. The complete locked agents environment
collects 11972 pre-cleanup tests without errors. The admission status-transition
probe confirms the0036 whole-row guard rejects all selected-field mutations and
normal public Submission consumption preserves those fields.


The distinct0049 assignment-backfill regression is retained as isolated native
PostgreSQL migration-fragment proof. It reuses0049's exact SQL and0048's exact
single-sourced terminal guard, checks every row, rejects direct terminal changes
before/after, and proves a failure after trigger disable rolls back rows and
restores the guard. It does not reconstruct a predecessor application, claim a
complete0048 upgrade or assert a valid current product state. Current full-schema
cap/rollback/race and0071 installation/refusal tests supply their own boundaries.
The old archive restore failed its exact table-inventory check; no compatibility
schema was added to force it through. Both planning reviewers approved this
bounded replacement. Its PostgreSQL development run passed; clean-candidate
replay remains required. The229 CI catalogue/behavior-authority checks also pass.


The current-model cleanup development suite passed14 PostgreSQL cases covering
normal cap exhaustion, independent-session races, rollback, direct-SQL guards,
current blocked pause, missing-root recovery and PM pause/resume. The selected
award native probe passed missing/wrong-tier deferred closure, immediate wrong-
tier rejection and sole-award uniqueness; its positive control uses real
acceptance participants and exact replay. The expanded public rebase drill
passed stale acknowledgement rejection, immutable original command/Submission
replay, a new acknowledged Submission copying the revised unpaid selection,
automatic acceptance with one submitter contribution and zero awards/Reviews,
and the public contribution evidence read. Original Submission rows remain exact.
These executions used development trees; retain that custody distinction and
freeze/replay required evidence before a passing implementation verdict.

Remaining selected scope includes the complete read-contract audit (particularly
management size exposure), higher/lower/instrument-changing replacement proof,
full-suite and actual durable-worker/S3 qualification. Finance runtime is still
unfinished. This batch closes obsolete recovery and its distinct retained proof;
it does not narrow the full goal or claim PR readiness.


The frozen cleanup review found one remaining obsolete consumer in the shared
`test_audit.py`: the recovery-only adapter test/import and canonical enum-matrix
case still referenced the removed API. Remove those cases, retaining all current
routed-exhaustion, expiry, repair and shared audit contract proof. A full locked-
agents collection and focused canonical audit tests must pass before closing
this finding; do not restore the deleted adapter to satisfy it.


## Complete current read contracts and remaining cleanup consumers

Concrete gaps: management detail lacks immutable Task size, and95 review found
remaining obsolete preparation-only cap tokens, one shared audit test, and stale
behavior-partition entries. Allowed: existing TASK detail/revision DTOs, their
repository projection and expiry/repair readers,0071 constraints, exact ownership
metadata, affected audit/current tests, Go detail/context decoders/renderers and
fixtures, MCP snapshots and current documentation. No new operation/state,
financial authority, compatibility alias/default/decoder or parallel response.
Keep ordinary submission/exhaustion limit errors and all current repair/expiry
and terminal behavior. Required size is current Task data, including unpaid work;
contributor terms must agree with it. Update every affected caller together.
Acceptance: detail/work context expose exact size to both audiences; strict
current clients reject missing/invalid/mismatched size; current preparation
states cannot encode obsolete cap holds; audit collection and exact ownership
validation pass. Verification uses existing DTO/public read/Go/CLI/MCP contract
proof, current native constraints and full collection. Risk staysL0; affected
QA/CI/docs/security/product/architecture/reuse reviewers replay the new candidate.
Human focus is exact read selection, privacy and complete deletion of obsolete
preparation semantics while current cap exhaustion remains intact.


The exact95 actual0070→head test exposed an intermediate-function compilation
error during recovery cleanup. Fresh installation's baseline transaction had
masked it with its local function-body validation setting.0071 now reads each
installed guard once, checks each replacement anchor exactly once, and installs
only the complete edited body. Actual upgrade validation remains enabled; no
old reader or weakened check is introduced. Existing installation/upgrade and
atomic-refusal tests provide the discriminating regression. Frozen95 remains
blocked evidence, not a passing migration claim.


The follow-up development run now passes both actual0070→head installation/
upgrade and atomic incompatible-data refusal tests (423.47s), with owned database
and MinIO cleanup verified. The schema fingerprint is
`5507ad05976f9d8982e241a403a215973b7802314177a8fdd75f3146b6bb1d29`.
The frozen95 lifecycle run passed21 cases (1692.61s); this is exact95 lifecycle
proof and does not override its failed upgrade. Current Go package checks,
16 CLI HTTP contract cases,188 ownership/lane controls,59 catalogue controls,
module boundaries, Markdown links and stale wording passed. Complete backend
collection found11971 tests before the replacement matrix parameter expansion.
The current MCP claim/read/size consumers passed65 tests after replacing the
stale static replay probe with the current async owner. Its cross-size negative
probe also passed independently. Broader OpenAPI snapshot checks and clean-head
replay remain required; development runs are not frozen implementation receipts.

The existing public replacement drill now also covers lower/higher money and a
money-to-points change through real published policy fixtures, exact preparation
acknowledgement, replacement Submission and shared automatic acceptance. It
asserts the exact revised selected award and unchanged original evidence/replay.
This matrix is running; its outcome is not yet claimed. The affected fixture
parameters supply exact authored quantities through the existing policy owner,
without bypassing publication or adding an application behavior.


The first expanded matrix run passed the unpaid case but stopped before target
publication in the lower-money case: setup tried to recreate the existing
money/USD project unit. The fixture now explicitly receives the original
Submission definition's binding for same-money publication; new points policies
still create their exact new binding. No application fallback or upsert was
added. The corrected four-case run is pending. The c655 review also identified
one residual preparation-only type token in contributor reads; it is removed
while ordinary Submission/assignment exhaustion reasons remain valid.


Exact clean c655 verification passed the two migration tests (278.40s),187 MCP
contract/consumer cases (295.47s), and full11974-test collection (159.72s).
Migration producer asserts clean source before/after and confirms owned resource
cleanup. MCP uses the frozen source paths and records actual argv/cwd/environment
with shared clean-start and verified clean-end observations. These are bounded
source results, not full-suite or Finance-runtime completion.

Review follow-up replaces the synthetic lower-target blocked/running test with
current paused allowance behavior. The focused current pure contracts passed438
cases (35.15s). Affected generic audit tests now use the actual ART recovery event
builder instead of obsolete Task-created/verified-token fixtures. Shared raw
append/read remains required by ART recovery and exact lifecycle replay; its
existing persisted domain token is retained. No authority bypass or historical
Task producer is restored. Native append-only, rollback and non-authority-cause
rejection proof remains required and is rerunning with the current ART fixture.


The corrected-binding development run passed unpaid, lower-money and higher-
money replacements through acceptance. The points case reached the replacement
completion delivery but returned no receipt; the run ended3 passed/1 failed
(376.50s). A points-only reproduction now asserts a stored completion and captures
bounded delivery state if unavailable. No retry/fallback or production change is
introduced without diagnosis. The current ART audit consumer/immutability/
non-authority-cause native run passed4 cases (88.16s), with cleanup verified.
Both c655 reviewer sessions are closed: earlier three recovery defects are
closed; remaining type/clock-fixture cleanup is repaired in the working tree;
the full financial replacement matrix remains unqualified.


The points-only diagnostic control passed (97.82s) with native guards intact.
It does not explain or erase the earlier four-case no-receipt failure. Rerun the
complete matrix from a clean candidate with bounded no-receipt state diagnostics;
keep the matrix unqualified until that result is examined. Do not add a delivery
retry or fallback merely to make the assertion pass.
