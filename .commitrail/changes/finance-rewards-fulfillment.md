# Size-based rewards and dedicated Finance fulfillment

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: One current Workstream v0.1 implementation of sized rewards and Finance fulfillment, in one PR with cohesive, revertible commits.

## Intent

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

## Bounded change

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

## Acceptance criteria
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

## Risk and review routing

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

## Evidence

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

## Next required implementation: atomic award fulfillment custody

Concrete gap: the current COMP award participant returns an immutable award but
creates no fulfillment root or durable handoff event. Finance cannot admit an
earned obligation without that exact Workstream source. Extend the existing
FinalAcceptance -> CON -> COMP transaction; do not add a second acceptance path.
This is the next dependency in the full specification, not a substitute goal.

Allowed scope: existing COMP award API/participant/composition, a cohesive COMP
fulfillment API/model/service, CON participation scalar forwarding/composition,
REV's current manifest description/predicate, `core/config.py` source-instance
setting, model discovery, one new0072 migration, supported-head/schema/ownership
metadata, focused and affected current fixtures/tests, current capability docs.
No Finance provider/HTTP handler, separate lifecycle controller, generic job
engine, retained-row deletion, old request reader/default or live effect.

Plan:
- Require current award input to carry Task/Submission/FinalAcceptance/size and
  expected lifecycle generation as exact scalar facts supplied by CON. Propagate
  these from the existing request and immutable contribution; no cross-owner ORM
  join or substitute IDs. Update every current caller/fixture together.
- Inject the same held REV fence and existing session-bound OutboxAppendPort into
  the COMP participant through existing composition. Require the canonical live
  generation before a new root; exact replay reads existing root/event only.
- Use configured `WORKSTREAM_SOURCE_INSTANCE_ID` (canonical UUIDv7), shared with
  later Finance registration. Never generate a deployment identity per request
  or derive a record ID from a hash/token. Missing source configuration refuses
  compensated admission atomically; unpaid outcomes create no root/event. Add
  activation readiness validation so deployment misconfiguration is found before
  new compensated work can be accepted, rather than losing an earned obligation.
- Persist one immutable CompensationFulfillmentRoot per award: owner-generated
  UUIDv7, unique increasing ordinal, exact admission generation, source instance,
  original binding/route, complete canonical envelope and both digests, source
  FinalAcceptance authority reference and exact initial outbox event identity.
  Allocate max ordinal+1 only while holding the canonical global REV fence; a
  unique constraint and native source/closure guards independently enforce it.
  No new counter/controller or clock-derived business ordering is introduced.
- Append a selector/digest-only `compensation.obligation.deliver` event through
  the shared outbox in the same transaction. No amount, payee/provider data,
  broker publish or external I/O. Replay must require exact stored event custody,
  never append/repair/reallocate missing roots on replay.
- Native PostgreSQL guards enforce immutable root/body, exact award/contribution/
  Submission/acceptance/binding lineage and canonical digests, live generation,
  contiguous new ordinal under the fence, and deferred award/root/event closure.
  Missing root or altered/missing event makes the entire earning transaction fail.
-0072 installs only while disabled and refuses existing awards without roots
  atomically, retaining every row; no synthetic historical envelope or ordinal.
  Fresh install, actual0071 upgrade, repeated head and refusal/rollback need proof.
- The current manifest names actual internal award/root/outbox participation.
  Finance admission/payment delivery remain unavailable until their real runtime,
  receipts, AUTH, phase/cutoff handlers and deployment qualification are delivered.
  Source reads, callbacks, cutoff/drain and Finance execution remain required
  following work in this same PR; no root-only readiness claim.

Acceptance/proof: paid public automatic acceptance commits one exact root/event;
unpaid and true-human-review branches create none; replay preserves IDs/ordinal/
body/counts; omitted or wrong root/event rolls back acceptance/contribution/award;
independent sessions cannot allocate duplicates; closed/stale/nested fence and
non-live generations deny before new effects; immutable root alteration and raw
SQL incomplete earning fail; suspension retains the original binding/earned
facts rather than repricing them; actual migration/refusal preserves data.
Use the existing public journey and native transaction/race fixtures plus
focused pure canonical-envelope tests. No claim of Finance HTTP/worker/S3 proof.

Risk remainsL0. Obtain plan review on transaction/custody/configuration and test
reachability before implementation; then replay affected security, architecture,
product/reuse/senior and QA/test-delta/CI/docs reviewers on a clean candidate.
Human focus: source identity setup, same-transaction closure, exact replay,
original-binding preservation and no activation of unimplemented delivery.

### Plan review corrections adopted before implementation

- `FULFILLMENT-PLAN-001`/`PLAN-FULFILL-001/003`: allowed scope explicitly includes
  existing REV controller/service and its composition. Inject a mandatory COMP
  public readiness port; before consuming target-live authority, resolve the
  configured canonical UUIDv7 and reject missing/mismatched committed-root
  identity. New roots compare their source against all existing roots while
  holding the same global fence; no second registry. Tests cover missing/invalid
  configuration, restart with the same UUID, and two differently configured
  processes. The current AUTH observation shape needs no historical reader.
- Forward `source_authorization_decision_id` and `source_routing_manifest_id`
  from FinalAcceptance through CON and the required COMP award request; persist
  both on the root and check their exact native acceptance/manifest chain.
  Define COMP's exact historical binding read returning original project,
  instrument, binding and route regardless of active/suspended status; never
  use the active-only policy-authoring lookup. Current expected generation fences
  the call; replay checks the root's original admission/manifest generation,
  without equating it to a later current generation.
- `FULFILLMENT-PLAN-002`/`PLAN-FULFILL-004`: remove the0038 reconstruction test and
  its sole-use migration/config/operator/fence/runtime-hash helpers in
  `tests/reviews/lifecycle/test_participant_control.py`. Replace the old SQL/hash
  swapping test in `test_transitions.py` with current operation replay and
  unknown/stale-manifest denial and current-manifest acceptance. Lift its distinct forged-Python-fact/native-
  SQL rejection into current stopped-generation fixtures. Retain immutable
  authority, current phase/restart select-only replay and actual migration proof.
- `PLAN-FULFILL-002`: extend `test_medium_public_claim_to_selected_automatic_acceptance`
  for real root/event paid, unpaid and human-review observations. Add
  `test_fulfillment_closure_rolls_back_incomplete_earning` using real award
  creation with only root admission omitted; target each deferred constraint
  IMMEDIATE for omitted root, omitted/wrong event, then disable only that named
  guard inside a rolled-back transaction to prove the assertion discriminates.
  Compare all acceptance/contribution/award/root/outbox rows afterward.
  `test_fulfillment_ordinals_serialize_distinct_acceptances` uses two real paid
  sources: sessionA holds REV before allocation, sessionB's advisory wait is
  observed, then commit n/n+1; a rolled-back A consumes no committed ordinal.
  `test_compensation_root_requires_current_root_fence` invokes COMP directly with
  real closed/stale/nested custody, so upstream TASK/CON cannot mask denial.
  Native alteration/incomplete-closure probes and exact replay/no-write probes
  retain their separate boundaries.
- `test_fulfillment_root_migration` proves fresh/actual0071→0072 disabled success,
  repeated head/fingerprint and atomic retained-award refusal. Its0071 award
  fixture is native previous-schema data preparation: use current AUTH/fence
  owners with the installed schema's exact manifest facts and native history
  guards, stage a real earning with only the not-yet-installed root participant
  omitted, and retain every row. No old application/fence reader, SQL function
  swap, schema patch or runtime manifest fallback is introduced. Assert the
  exact retained acceptance/award authority predicates before testing refusal.
- The new outbox key stays absent from handler and replay-safe registrations in
  this slice; a real candidate/claim probe must prove it cannot dispatch.
  Fulfillment admission/payment delivery remain unavailable. Add new tests to
  existing Finance/PostgreSQL semantic lanes and exact ownership catalogue;
  run `test_ci_lane_catalogue.py`, `test_ci_test_lanes.py` and
  `test_behavior_ownership.py` without weakening their scope/inventory checks.
- Update `docs/roadmap_status.md`, `docs/architecture_data_model.md`,
  `docs/spec_review_lifecycle.md` and `docs/spec_contribution_compensation.md`.
  Wording stays root-only: no Finance source-read/HTTP/worker/payment or
  cutoff/drain qualification from this change. Those remain full-goal work.


Root implementation dependency checks found two concrete public dependency
cycles. COMP uses a consumer-owned fence contract with an adapter translating the
same held REV capability; no second lock/controller is created. The existing
exact quantity formatter moves from CON into shared `core/financial_wire.py`,
with every current caller updated and the old definition removed. This closes
COMP→CON and COMP→REV cycles without aliases or duplicated formatting. These
shared formatter and adapter files are explicitly within the affected scope.

The affected configuration scope also includes `backend/.env.example` and current
COMP source-provisioning instructions: a once-provisioned UUIDv7 is retained across
all replicas and restarts; no example or process generates a deployment default.


### Atomic fulfillment custody implementation and development evidence

The earning path now forwards exact source acceptance/AUTH/routing facts through
CON to COMP, using the same caller-held REV fence. COMP creates one immutable
source-root/envelope and selector-only shared-outbox event per selected award.
Native PostgreSQL validates original immutable Submission selection, exact
binding/route, authority generation, canonical digests, singleton source and
serialized ordinal allocation, with deferred award/root/event closure. Replay
requires original custody and does not repair, allocate or append. The existing
lifecycle checks explicit source configuration before target-live authority.
The new event remains unregistered; Finance delivery is still unavailable.

Observed development checks (dirty worktree; not frozen review evidence):
- Pure contract/current participation and CI lane/ownership controls: 266 passed.
  The new schema test is explicitly owned by the schema-contract lane and its
  exact inventory expectation; no test is exempted or removed from discovery.
- Real PostgreSQL guarded public selected acceptance and human/unpaid branches:
  four passed, including complete initial-root/event custody and inability to
  claim the unregistered event. Owned PostgreSQL/MinIO cleanup completed.
- Native incomplete-earning rollback, named-guard discriminating probe,
  immutable roots, exact replay, original suspended binding and source restart,
  and missing-source live activation: three passed; direct ROOT closed/stale/
  nested/raw-savepoint denial: one passed. Owned infrastructure cleanup completed.
- Exact 0071-to-0072/fresh/repeated-head and retained-native-award refusal:
  two passed in 239.49 seconds, with every preflight-retained row unchanged and
  owned PostgreSQL/MinIO cleanup completed. This caught and repaired the missing
  supported-0071 Alembic entry; no compatibility reader was added.
- Distinct-source contention commit diagnostic passed, but the final combined
  commit/rollback/lifecycle/contribution run is still pending. Earlier setup PRE
  timing and POST infrastructure failures remain unexplained; an isolated pass
  is not a disposition of those failures or whole-matrix qualification.
- Ruff and module dependency checks passed before final documentation edits;
  final full collection, stale wording, links and frozen review remain pending.

The full specification, full-suite and durable external Finance/worker journey
remain required in this same draft PR. This slice does not establish Finance
admission, source reads, callbacks, receipts, cutoff/drain or payment readiness.


Specification reconciliation corrected the initial event to the exact
`compensation.obligation.deliver` key required by execution section 14.3,
replacing the temporary name everywhere rather than adding another event path.
The combined dirty-development native run was deliberately interrupted after
its first two passes before changing runtime files; its owned infrastructure
cleanup completed. It is not claimed as suite evidence. The changed event SQL
requires a fresh schema fingerprint, native rerun and subsequent frozen review.
A separate 200-sample database-clock probe found no backwards step during its
6.28-second observation; this does not explain or dismiss the earlier timing
failure. No timing validation or test assertion has been relaxed.

The corrected native event guard's fresh PostgreSQL 16 schema fingerprint is
`2d902e3bd209bf8fcae7f0907b66b108ad839e79b1c0ae38aa5dd9ea312a76e3`.
Full collection discovered 11,882 tests without errors; collection is not suite
execution. Final current Markdown links and stale wording passed. The corrected
builder/current participation contracts passed 18 tests. The first external
schema probe failed because its temporary script lacked the backend import
path; the corrected probe used its actual backend working directory, completed
and cleaned up its owned database/MinIO resources. No schema gate was bypassed.


### Frozen root verification and current-custody probe correction

Clean `0848d4bb9` passed 266 controls, both migration tests (282.83 seconds),
and all six new root tests, including distinct-source commit/rollback contention.
The combined native run then failed the newly lifted stopped-phase SQL probe:
application replay had succeeded without writes, but the probe passed original
admission generation 2 to a predicate requiring the current controller generation.
This was a test-input error, not evidence for changing the production guard.
The probe now passes the current transition receipt generation, independently
asserts old-generation denial, and retains new-effect denial. No predicate or
assertion was relaxed. The affected unpaid/money/points participation test also
explicitly asserts zero-or-one root and exact initial handoff-event cardinality,
including zero for unpaid. Both owned jobs completed PostgreSQL/MinIO cleanup.
Further affected native tests were not executed after fail-fast and remain pending.


Hosted checks on the frozen commit found affected consumer gaps: the TASK public
API still imported CON solely for the size literal; the immutable-export
inventory omitted the new frozen selection dataclass; MCP's valid runtime check
needed explicit task-type narrowing for mypy; and five changed CLI fixtures
needed canonical formatting. Repair scope includes those exact existing owners,
`tests/architecture/test_module_boundaries.py`, shared `core/financial_wire.py`,
CON size consumers and the five CLI fixture files. Move the one size literal to
shared core and update every current import, removing the CON re-export without
an alias. Keep TASK's no-business-dependency assertion and exact immutable-export
inventory intact. Explicitly narrow malformed MCP task input before access and
preserve its rejection behavior. Formatting changes do not alter test assertions.
Two current docs also need the precise term Celery worker so the existing stale
actor-vocabulary guard recognizes technical execution; the guard stays unchanged.
Proof: actual architecture tests, MCP mypy/affected gateway contracts, formatting
checks, current docs gates and affected native generation/participation cases.

TASK revision candidates also deliberately reuse CON's canonical immutable
`RewardSelectionFacts`, beyond the primitive size literal. That existing public
edge carries governed selected terms and passes the repository dependency graph;
replacing it with a duplicate TASK selection schema would add a parallel rule.
The architecture test therefore retains exact inventory of that single public
module and rejects every other cross-owner dependency, alongside its existing
private-reexport and mutation denial probes. This explicitly supersedes the
above intended no-business-dependency wording: no private or unregistered public
edge is permitted; canonical CON immutable selection reuse remains intentional.
No validator, ledger or CI gate is weakened or exempted.

The CI repair development checks passed MCP strict mypy (26 source files), all
31 existing task-execution/size gateway cases, all 98 CLI test-file formatting
checks and Ruff. All current Markdown link, authorization, artifact and review
wording gates passed. The broader control run had 302 passes and the one TASK
public-edge inventory failure described above; the three repaired architecture
probes then passed, including actual private-reexport denial and frozen selected
terms. A mistaken initial MCP `-k` selector selected no tests and is not counted
as evidence; the complete two actual task modules were run afterward. Native
stopped-phase generation and affected contribution checks remain running.


### Native substitution proof required by implementation review

The dirty repair run completed all 29 affected lifecycle/contribution cases
(741.46 seconds) with PostgreSQL/MinIO cleanup complete; exact clean b962 control
run passed all 303 cases (177.09 seconds). These are distinct custody boundaries.
Both implementation reviewer sessions then failed with a usage-limit error, so
neither supplied a final verdict. The security/architecture reviewer identified
a valid missing proof before termination: independent direct-SQL root INSERT
substitutions were not exercised by readiness, ORM custody, closure or UPDATE/
DELETE tests. Treat the implementation review as incomplete, not passed.

Repair is limited to the current root test module and this record, using the
existing two-source real paid fixture and actual earning transaction. Commit a
first genuine root as the singleton source anchor; stage the second genuine
award under actual AUTH/REV custody with only its root participant omitted.
Construct the current Python envelope, append its event through real OUTBOX, and
INSERT the root through SQL. Independently substitute source (with recomputed
wire digests), ordinal, generation, project, binding, authority, manifest,
acceptance and envelope/digests. Require named native failures at INSERT and
complete rollback of all staged earning rows. Retain an unmodified successful
control and a rolled-back named-trigger removal probe that discriminates the
source-UUID rejection. No production constraints or validators are relaxed.


Development native substitution proof passed (161.09 seconds), including genuine
foreign-project references, internally rehashed source/body changes, named SQL
rejections, rollback snapshots, a valid committed control and the trigger-removal
discriminator. Owned database/MinIO cleanup completed. The first invocation
failed before tests because the owned services were stopped after the host
restart; restarting only those existing containers restored the actual dependency.
The final test extracts only raw INSERT and real event-append setup into focused
helpers, adds an independent source-digest-column substitution and forces deferred
closure after the trigger-removal control before rolling it back. Final-source
execution and reviewer replay are still required; the prior development pass is
not attributed to that final source.


### Collected implementation findings and bounded repair plan

Both combined implementation reviews closed BLOCKED on clean `3f53c74a8`,
base/merge-base `b22134f5e`; these are engineering findings, not product review
outcomes. `QA-FULFILL-001` / `FULFILLMENT-IMPL-001` expose the previously missed
zero-root source race. `QA-FULFILL-002` / `FULFILLMENT-IMPL-002` expose required
paid reviewer storage/export regression. `TEST-FULFILL-001` requires independent
event-to-root closure proof; `DOC-FULFILL-001` identifies two stale current root/
ordinal claims. CI inventory was structurally sound; no final runtime or whole-PR
passing verdict exists. The earlier plan's first-root-only anchor assumption is
superseded by the concrete A-activation/B-first-root counterexample.

This repair stays L0 and in this same PR. Additional allowed owners are existing
REV lifecycle model/fence/public protocol and native control/history guards,
COMP consumer fence adapter/API/service, affected current lifecycle/AUTH fixtures,
0072 and its actual predecessor-data fixture, current reviewer storage/export
proofs, the existing root tests, schema fingerprint and affected current docs/
roadmap/record. No separate registry/controller, historical decoder, old-hash
fallback, fabricated Review/FinalAcceptance, human-review runtime or new handler
registration. Retain current reviewer-policy, immutable storage/export and its
tests; these are required business branches, not compatibility behavior.

1. Add a nullable `fulfillment_source_instance_id` scalar to the existing REV
   control and transition rows. Null represents the real pre-activation state;
   do not fabricate source IDs for retained rows. First authorized LIVE anchors
   the configured UUIDv7 atomically. Thereafter transitions retain that same
   value across disabled/shadow/draining/restart; changing/clearing it fails.
   Bind the transition's scalar into its existing observations digest and exact
   AUTH/native transition/control closure. Keep LifecycleTransitionFacts' JSON
   shape unchanged: its digest can commit this new server observation without
   adding a historical parser/default. Native history carries the scalar needed
   to reconstruct and independently check the observation, including first LIVE
   before the control update. Existing retained JSON/AUTH evidence is not rewritten.
2. Extend the same REV-owned held-fence capability with explicit source matching,
   exposed to COMP through its consumer-owned fence port/adapter. COMP checks
   configured identity against that held canonical source before root/outbox
   insertion. Its earlier generic custody check remains phase/generation-only;
   no new source registry or private cross-owner read is introduced. The native
   root INSERT guard also compares the control's anchored UUID, including when
   roots are empty. Existing canonical lock order and transaction ownership stay.
   Keep generic fence scalar selection unchanged so real predecessor-schema data
   preparation need not reconstruct an old application runtime.
3. Scope the current award-to-root closure to `accepted_submission`. Retain
   `completed_review` fixed award copying, lineage, immutability and public exports
   under their existing storage rules. Current root construction still requires
   actual automatic FinalAcceptance; never synthesize reviewer root authority.
   Reconcile migration refusal with this exact supported boundary: refuse retained
   accepted-submission awards lacking original roots, while preserving genuine
   reviewer award rows unchanged. Use actual 0071 native-data preparation, explicit
   installed-schema columns and actual AUTH/fence custody in that migration fixture;
   do not invoke a current ORM field that does not exist in the predecessor schema.
4. Add named event-to-root closure proof: real OUTBOX selector with no root must
   fail `compensation_event_fulfillment_closure` and roll back; removing only that
   trigger inside a rolled-back transaction must defeat the assertion. Retain
   all award/root/event independent guards and existing raw substitution cases.
5. Correct current data-model/lifecycle root/ordinal claims and describe durable
   source activation and accepted-submission root scope consistently across their
   related current spec/roadmap claims. Finance admission/callback/status/cutoff
   and live human review remain unavailable until implemented and qualified.

Acceptance/proof: LIVE under A with zero roots durably records A in actual
control/history/AUTH observation; B's first paid earning fully rolls back;
A succeeds and later restarts retain A. Direct SQL cannot substitute B even with
no root anchor, rewrite/clear control source, or reuse authority observed for A.
Accepted-submission omission and stray-event closure retain discriminating native
proof. Current active/retired money/points reviewer awards and paid JSON/CSV
pagination commit/read without fabricated roots. Fresh/actual0071/repeated-head,
retained accepted-award refusal and retained reviewer-row preservation are native
migration proofs. Run affected lifecycle authority/storage, root/public journey,
reviewer storage/export and catalogue/architecture controls; regenerate schema
fingerprint from actual PostgreSQL. Then freeze and replay the same reviewer
tracks, including formerly passing structure/docs tracks. Human focus: immutable
source anchor, AUTH/observation/control coupling, supported business scope and
independent closure guards. Full Finance objective remains active and unfinished.


Repair-plan review at clean `366b22588` passed security/architecture/product/reuse/
senior feasibility and passed QA/test-delta/CI/docs feasibility with low risks.
Adopted details: source observations omit the member while unanchored, then include
exact UUID; both scalar columns have nullable UUIDv7 constraints; first-LIVE
caller rollback proves no source/control/history/AUTH residue. The reviewer
exception is limited to the award-trigger branch; root/event guards stay strict.
The stray-event probe must use a committed valid award and a fresh unlinked selector
so award closure cannot mask event closure. Actual0071 facts/AUTH remain unchanged
and old operation replay must remain select-only; no JSON parser/default is added.
The 3f native run was deliberately interrupted before editing runtime guards,
with owned cleanup complete. It produced progress but no complete terminal test
summary and is not claimed as a passing suite. Valid review findings, not a test
observation timeout, motivated the source change and subsequent rerun.


Repair development evidence: all 303 architecture/ownership/lane/pure controls
passed (466.69 seconds). The native regression run passed zero-root A/B source
and raw-SQL enforcement, independent stray-event closure/removal discriminator,
shadow/first-LIVE rollback and all four active/retired money/points reviewer award
storage cases. It then caught the paid export fixture's obsolete two-award CSV
count/stride. Current policy gives each contribution one instrument/award, so
that fixture now requires one CSV row and exact zero-or-one JSON award while
retaining page cursors, IDs/order and cross-format exact award values. This is
an affected fixture replacement, not removal of paid reviewer export behavior.
Owned infrastructure cleanup completed for the 8-pass/1-fail run.

The actual migration run completed upgrade/retained-row comparison, then failed
its repeated-head snapshot read with asyncpg UnicodeDecodeError while decoding
PostgreSQL constraint metadata. No migration assertion or schema guard has been
relaxed. A separate owned three-identical-snapshot probe is running to distinguish
persistent schema metadata corruption from an intermittent transport/decoder
failure before a qualified rerun. The migration run cleaned up its owned services.

The independent diagnostic now completed three identical metadata-manifest reads
successfully against a fresh owned PostgreSQL schema, with unchanged reader code
and normal child exit. This contradicts persistent malformed current constraint
metadata; it does not explain or erase the earlier decode failure. One diagnostic
attempt first failed due to importing a pytest-only fixture path, corrected by
calling the actual metadata reader directly. Another bootstrap failed before the
probe without a terminal traceback, so the final diagnostic also recorded child
exit codes without exposing connection data. No runner/schema gate was modified.
A fresh actual three-case migration run follows this discriminating control;
retained reviewer storage, original AUTH/facts and exact replay remain required.


The next parallel runs exposed an actual owned PostgreSQL backend crash: PID 430
segfaulted during the unchanged 0001 baseline DO/EXECUTE batch, restarting the
cluster and closing both jobs' connections. The authority/storage run had 21
passes before an unpaid export fixture lost its connection; the migration job
lost its connection during setup. Neither is qualified as a passing run. Both
MinIO namespaces were removed; after recovery the lead used the canonical
ownership-checking `_drop` to remove only the two recorded database/role pairs
and verified cleanup. PostgreSQL is 16.14 and its image matches the exact CI
pinned digest. No database/schema gate or engine version was changed.

The probe's three identical current metadata reads succeeded but do not explain
the server fault. A serial owned run now tests both export branches, held-source
custody and all three migration cases without simultaneous database rebuilds.
This is a discriminating execution condition, not a feature-code workaround or
a claim that the underlying crash is solved. Source authority tests now also
stage genuine new Operator authority for changed/cleared source observations and
require native control rejection, and separately reject reuse of an A observation
for a first-LIVE B scalar. All remain subject to final-source review/qualification.


Serial recovery proof passed both corrected paid/unpaid export branches, held
source-capability custody and fresh/actual0071/repeated-head installation. It
then reached the retained-reviewer fixture and caught its command builder's
whole-current-ORM SELECT against actual0071 (missing the newly added source
column). The shared test command builder now reads only its three needed stable
selectors: id, phase and generation. There is one current helper, with no schema
version branch or fallback. The actual migration proofs are rerunning serially.

Current repair code is locally coherent and ready for a new frozen candidate,
with complete migration/final-head execution still pending. The actual manifest
is `sha256:f529eb5e237142a3b534c583e6bbf9eb844467e3c3984b03f2db89e20f6243aa`;
fresh PostgreSQL16 source-custody schema fingerprint is
`4d6b6690d5700a89ad076860bc588bc9237c1a81357cbae116994eb7efbe5937`.
No local sheet export directory is present. Prior source-binding and reviewer
findings remain open until fresh implementation review; full Finance runtime,
full-suite and actual worker/HTTP/S3 qualification are not delivered by this repair.


The 90de review closed source/behavior findings by inspection but kept execution
qualification provisional; two current doc sentences still required correction.
Hosted CI independently found the record's noncanonical heading names and stale
structural-debt fingerprints on two earlier affected files. Repair scope is this
record, the two current doc sentences, existing AUTH kernel grant-filter assembly,
`test_artifact_admission.py`, its already-used CHECKERS output-custody fixture
module, and the exact structural ledger. Replace redundant dict unpack/merge with
ordered updates preserving overwrite precedence. Move the same unrelated-checker
Task fixture to that existing helper owner; keep its full locked tuple, mandatory
size and ownership-denial assertions. There is no new exception, size limit,
allowlist or test skip. Regenerate only the two changed debt entries after actual
simplification/fixture relocation, and validate against the trusted main ledger.


Hosted-gate repairs validated locally: canonical record headings pass; the exact
structural ledger passes its trusted-main validator with unchanged limits,
exceptions and 34 debt entries. Ordered grant-filter updates preserve checker
precedence and reduce the affected kernel from1265 to1261 lines. Relocating the
same unrelated-checker fixture into its already-used CHECKERS helper owner keeps
all locked facts/size and ownership-denial assertions and reduces the oversized
artifact test module from2453 to2395 lines. Only those two debt fingerprints were
regenerated. All114 actual authorization contract/kernel/PREP cases passed;
Ruff, current Markdown links and stale authorization wording passed. Current doc
residues now identify anchored REV source and unavailable external Finance
execution precisely. A final clean-source native run must additionally exercise
the relocated fixture and source/closure/reviewer/migration boundaries before
reviewers can qualify execution. The full financial specification remains unfinished.


## Native root qualification and next receipt boundary

Clean `cd2982b073fb871ebf73928454a93227957224de` passed 43 native
PostgreSQL cases in 1230.94 seconds with owned database/MinIO cleanup complete.
The proof covers zero-root activation/source substitution, independent native
award/root/event closure and guard-removal controls, held custody, AUTH/storage,
rollback, ordinal contention, four reviewer-storage/two export branches, the
relocated ownership-denial fixture and all three actual migration cases. Both
combined reviewer tracks pass this bounded native repair; the prior source,
reviewer, independent-event and documentation findings are closed. This does not
qualify public Medium acceptance, stopped-phase earning replay, full-suite,
durable-worker/S3 delivery or the full Finance objective. A separate exact-clean
four-case revised-terms run passed in 220.74 seconds with cleanup complete; the
earlier intermittent not_evaluated result remains unexplained, not erased.

Fresh main is 94334ccf4085c26c7bfaa054465fc05cfbdad1fc. The only open non-draft
PR at preparation is dependency-update PR #711; it supplies no new financial owner.
The next same-PR gap is original-bound-service source reads and immutable
receipt/exception recording. No callback owner is currently exposed. Internal
roots alone cannot provide callback-before-ack or late factual recovery.

Allowed: existing COMP fulfillment/API/composition and narrow public REV fence;
AUTH catalogue/domain/PREP/resource/action/service-matrix owners; API routes,
router/dependencies; model registration and one forward migration after 0072;
affected behavior/module ownership, test lanes, current specs/data model/roadmap
and Finance README; focused API/PostgreSQL and affected existing tests. Prohibit
new lifecycle/auth/job owners, provider/credit execution, worker activation,
compatibility paths, private cross-owner reads, prospective reconciliation code,
weakened assertions/checks, live payments, deployment or merge. All prior scope
prohibitions remain in force.

The plan review found and corrected a concrete specification conflict: callbacks
holding adapter AUTH before REV can cycle with lifecycle transitions holding REV
before AUTH control and revocation holding AUTH control before that adapter.
Amend sections 8.5/10.1/12.6 explicitly. Extend existing REV held-fence machinery
with a small public server-current hold, then take exact action-specific AUTH
locks, then COMP binding/root/receipt locks. COMP validates the same held
capability without reacquiring REV after AUTH. This is the concrete gap for the
public extension; do not add a lock framework or a global fixed-service AUTH
lock. New-root LIVE admission remains unchanged. Current custody is distinct
from a root's immutable original generation and permits factual evidence in all
phases, including a suspended original binding with its exact active reporter.

Use the actual verified HTTP service actor/link and exact binding.adapter_actor_id,
never an internally re-resolved fixed principal. Give finance-evidence and
exact-report lookup disjoint typed resources under source.read. Verify path/body
award and Idempotency-Key/event equality, canonical complete-body digests and
existing decoder source facts. First insertion reads one database clock after
waits for both bounds and received_at. Exact replay uses retained immutable
AUTH/resource evidence with existing validate_replay under fresh principal/fence
checks, returning original acknowledgement/time without another allow or row.
Changed same-event requests conflict. Retain 300-second bounds and arbitrarily
late legitimate evidence.

Persist immutable report/exception body, digest, receiver time, exact source/
root/award/project/binding and request-principal/AUTH references. Native guards
independently close that lineage and authority, enforce event-per-binding and
one fulfilled receipt per award, exact successful-report exception linkage and
UPDATE/DELETE denial. Serialize writers on existing root custody. Derive status
from immutable evidence; any cache is rebuildable without another lock owner.
Fulfilled dominates ordinary late failure; exceptions retain fulfilled and set
attention. Contributor JSON/CSV must expose no operational event/reference IDs.
Actual 0072 upgrade must retain pending roots, initial events, source anchor and
AUTH without manufacturing evidence; fresh and repeated-head install agree.

Acceptance/proof files: finance/test_fulfillment_receipts.py for public HTTP,
fresh principal, disjoint read resources, headers/path/body, replay, time/phase,
rollback and native substitutions; test_fulfillment_projection.py for all seven
section 14.1 outputs, failed/success ordering, exception attention and rebuild;
test_fulfillment_receipt_migration.py for fresh/actual0072/repeat/pending roots.
Use existing project_lifecycle_* lanes for receipt/projection PostgreSQL and
schema_contracts for migration; preserve other actor/catalogue/export lanes.
Extend their existing tests only for distinct behavior. Preserve lane catalogue,
module/behavior ownership and exact OpenAPI action markers on all four routes.

Independent-session barrier proof must show callback-first commits exactly one
receipt then revocation, while revocation-first denies callback with zero
receipt/exception/callback-AUTH writes. The three-party case must also complete
within bounded waits without deadlock. A stale-principal mutation must fail its
outcome assertion even when futures finish. Separately prove same-event concurrent
replay, distinct-success conflict, failed/success projection, every phase and
transition race, exact time boundaries, direct-SQL lineage/AUTH/digest denial and
rollback-only guard-removal discrimination. Inspect existing proof before adding
a distinct test; no coverage targets or failure skips.

Risk: L0. Both combined plan-review tracks pass after the above corrections;
implementation still requires shared checks and clean-target focused security,
architecture, product, reuse/senior and QA/test-delta/CI/docs replay. Human focus:
one canonical lock order, fresh request principal, immutable source/evidence,
zero-write replay and native concurrency closure. Reconcile affected current
capability claims in docs/spec_contribution_compensation.md,
docs/spec_review_lifecycle.md, docs/architecture_data_model.md,
docs/roadmap_status.md and backend/app/modules/finance/README.md during
implementation. This planning-only update changes no delivered capability and
requires no no-op roadmap edit. Full Finance remains unfinished in draft PR #709.

## Current-contract CI repair

Hosted complete-suite execution exposed remaining consumers of superseded
policy, Task and source contracts. Repair the affected current fixtures and
catalogues before extending callback runtime. Allowed scope: failed CON policy,
TASK/ART routing/replay, migration and CLI integration fixtures/tests; current
behavior-catalogue references and behavior-contract test mappings; affected CON
model/repository cohesion and their traced consumers if needed to preserve
existing file limits; exact UUID metadata/typed-boundary proof. No compatibility
reader/default, data rewrite, authorization relaxation, raised size limit, skip,
lane removal or assertion deletion that loses a required failure boundary.

First batch replaces per-rule definitions with the current header/three-tier
quantity contract in real AUTH negative guards and identity-map refresh proof;
uses an unprivileged actor for retained-denial evidence where project managers
now have the required permission; updates the stale module-count catalogue
reference; replaces obsolete historical-hash invariance with current canonical
commitment proof; and fixes malformed test UUIDs so authorization/source rejection
is actually reached. Preserve rollback, fresh denial evidence, foreign binding,
all policy branches, and positive controls. Required subsequent repairs include
CLI source configuration and explicit Task size, incomplete current graphs and
metadata, predecessor-only installed-schema setup, and replay/input-source cases.
Trace each failure before changing its expectation. Keep native enforcement strict.

Risk: L1 within the approved policy/selection replacement, with no new product
policy or external effects in the test repair. Verification: focused pure and
real PostgreSQL failed selectors; current catalogue collection/structure checks;
a complete hosted suite after the batched repairs. Required reviews: QA/test
delta and CI integrity, plus security/architecture/reuse for any production
owner refactor. Human focus: obsolete requirements removed explicitly while
required authorization, isolation, immutable evidence, concurrency and replay
proof remains. The capability ledger is unchanged by fixture/catalogue repair.

The first fixture repair passed 19 exact-clean PostgreSQL cases at 2773dd096,
including real authority quantity/foreign-binding guards, stale identity-map
refresh, unprivileged denial audit, exact prepared router principal, successor
source and shared reset. Pure routing contracts passed 101 cases before commit;
behavior-catalogue collection now resolves the actual eleven-module test.

CLI proof must match its actual hosted lane configuration. The native guide
lane has no MinIO endpoint; injecting one selects S3 startup against its scripted
committed-document fixture namespace and correctly fails the namespace guard.
Changing only the disabled baseline did not remove that automatic selection.
The aligned native-lane run reaches the public policy journey and exposed a
fixture assertion assuming every mutation actor was Finance. The added manager
retirement now supplies its exact manager ID to the same event-identity assertion;
no caller identity check is removed. These CLI results do not claim S3 custody.

## Contribution owner cohesion and independent native guards

Both focused plan tracks approve the affected CON cleanup, including a full
tracked-Python caller sweep and the provisioning script. Move currency/unit
classes unchanged into the existing units/models.py; update every actual import
and metadata registration with no re-export. Move the pure selected-reward
transformation into existing policy_eligibility.py; both repository operations
retain their queries, session/lock ownership and exact exception translation.
Preserve all SQL/metadata and class/function-body semantics. Add source and
destination modules to existing structural guards; do not raise the 500-line
limits. Verify before/after table/index DDL and moved AST equivalence.

For the remaining native fixture repair, drafts declare the common financial
header. Remove the old per-rule binding helper input; explicit award population
copies that header into three submitter tiers or one fixed reviewer definition.
Invalid quantity/unit/binding rows start with an empty compensated rule and a
valid size and assert the intended named constraint. Keep missing-size and
duplicate-tier guards separate and retain exact maximum positive controls.
Reparent an existing published money/small row into an empty draft rule and
assert the published-child guard plus unchanged rows. The publication race
updates a current-valid existing tier, proving SQLSTATE55P03, rollback and an
unchanged graph; retain the distinct rule-row race.

Replace the current draft behavior contract's obsolete dual-instrument and
unavailable-action assertions with current owner rules. Map all nine stale
references to exact current tests, strengthen the rule matrix for duplicate
review as well as submitter rules, and remove the structural test's old-name
translation/skip path. Keep each required failure boundary and honest exposure
claims. Reviewers approved this plan against an isolated clean2773 snapshot;
no plan verdict is implementation proof. Actual receipt/Finance runtime and
full-suite qualification remain unfinished.

Cohesion development proof: all 133 registered table/index DDL entries are
identical before/after; moved class ASTs and the selection-function body match
exactly. All nine tracked import sites now use the units owner, with no old
import or re-export. Removing a redundant local import and consolidating the
unit imports leaves repository.py at 497 lines and models.py at 481; both source
and destination files remain under the unchanged guards. The focused structural,
module-boundary and policy-contract run passed 63 cases on development source;
this is supporting proof, not an exact-clean final runtime qualification.
The actual CLI socket proof at clean aaa9599ff passed all three cases in 373.84
seconds with owned database cleanup; its native lane deliberately has no S3 claim.

## Current replay, admission and UUID proof

Update affected tests to specification 5.2.8: a screen or batch receipt returns
its original result after a later task advance under fresh authority. Keep the
late second-write rollback, changed-body 409, unchanged business snapshot and
revoked-manager replay denial; do not change runtime authorization or replay.
Unpaid work context now explicitly includes its immutable size. Frozen revision
root recovery must not depend on mutable PROJECT facts; keep no-write/source
custody and exact recovered-event assertions rather than an obsolete call count.

ART admission fakes copy all three current typed selection facts from their
real request: task size, contribution policy version and optional selected
award UUID. This restores final-authority and stale-lineage tests to their
intended boundaries. Metadata proof retains the exact native UUIDv7 bit condition
while ignoring expression whitespace. FK proof compares actual PostgreSQL UUID
types, preserving owner-local string versus Python UUID representations as
required by AGENTS.md, rather than imposing one Python representation across
owners. No database check is relaxed. The focused pure admission/identifier
run passed 22 cases on isolated development source. Native public replay,
concurrent consumption and fresh revocation proof follows on a clean commit.

## Current native policy storage proof repair

The current repair scope includes test_contributions.py, its publication
concurrency consumer, draft-rule/structural proof, and the two policy behavior
contracts. Replace superseded fixture shapes rather than adding a compatibility
helper. Negative rows now have valid unrelated fields and name the exact native
constraint; the publication race has a successful mutation/rollback control,
SQLSTATE55P03 and unchanged graph proof. Existing size-null and duplicate-tier
guards remain in reward_policy_storage.py. No product schema, AUTH authority,
workflow, dependency or CI threshold changes are allowed in this repair.

The contracts now reference exact executable current tests; the structural
mapper no longer translates names or skips old proof. The rule matrix rejects
both duplicate rule types. Obsolete coverage quotas are removed in accordance
with AGENTS.md; required behavior and complete hosted execution remain blocking.
Focused rule/contract/structure proof passed 50 cases on development source;
lint and Markdown links passed. Native execution and QA/test-delta/CI/docs review
remain required before claiming this repair qualified. No capability change is
claimed by these fixture repairs; the existing Finance roadmap scope remains.

The independent exact-clean replay run at 44acad6f passed all four cases in
162.70 seconds, including fresh per-member authority with unchanged business
effects, revoked-manager denial and retained revision-root recovery. Its
PostgreSQL and MinIO resources were cleaned up. That source is an isolated
commit; integrating its delta does not relabel its original evidence.

The first clean 1d221 replay run passed three cases, then the batch snapshot
correctly exposed two fresh AUTH allow events while all five business snapshots
were unchanged. The replay contract requires fresh authority. Its assertion now
keeps exact task/selection/root/member/receipt/lifecycle equality and separately
requires one new exact-actor/project/action/grant allow per member. The already
existing concurrent replay proof independently requires the same per-member
allow behavior. No allow audit is hidden or treated as a business write. The
failed run completed owned cleanup; its teardown also logged a cross-loop pool
close exception, which is distinct from the reproduced snapshot failure.

## Retained predecessor fixture isolation

Repair the0018 completeness migration tests in records/historical_support.py
and test_migration.py only, with this record. The archived predecessor has two
compensated definitions and no Submission selection column. A revision-bound
raw query reads exactly those stored project/policy/type definitions; both tests
assert the complete two-award source before deliberately inserting one or both.
The current runtime selector and its fixture remain strict and unchanged.
No migration/schema/authority/CI changes, runtime fallback or retained-data
deletion is allowed. QA plan review traced the archived values and explicit
INSERT columns and passed. Risk L1 retained-data proof. Required verification:
real PostgreSQL complete and incomplete upgrades, byte-preserving snapshots,
rollback/revision/function guards, lint and QA/test-delta/CI review. Human focus:
exact predecessor fixture custody rather than current readers on absent columns.
No capability-ledger change is claimed by this test-only repair.

Bounded review at clean983e5a8 passed QA, test-delta, CI integrity, security,
architecture and reuse. Documentation found DOC-POLICY-CONTRACT-001: one
acceptance row still said Finance-only composition. Correct that row to both
authorized project-manager and Finance-manager composition; no runtime change.
The exact983 native policy run passed50 cases in247.49 seconds with complete
cleanup. Original44 replay proof remains attributed to44; reviewers verified
affected source identity rather than relabeling the artifact. Full hosted
execution and Finance HTTP/payment qualification remain unfinished.

Exact isolatede26ab6e completeness proof passed both predecessor upgrade cases
in329.66 seconds. Complete two-award rows are preserved, incomplete rows cause
refusal without partial conversion, and owned PostgreSQL/MinIO cleanup completed.
This is migration evidence only, not current dual-instrument runtime behavior.

## CLI native-lane fixture isolation

Hosted native_proof at5c30 exposed a backend-only source fixture imported by
the generic CLI conftest. A fresh hash-locked CPython3.12 minimal environment
reproduces exit4 before collection. Move that import to the exact25 existing
backend API test consumers of clean_postgres_database; keep its canonical
backend body unchanged. Allowed: generic CLI conftest, those25 API files and
this record. Prohibited: production, schema, workflow, dependencies, conditional
imports, copied fixture, skipped proof or test deselection. Risk L1 test-proof
integrity. QA/CI plan review passes with bootstrap-order and execution controls.
Verify exact inventory, lint, minimal native falsification/PTY proof, and an
actual backend API case; then QA/test-delta/CI/reuse review. Human focus: no
backend dependency enters isolated socket/terminal tests. No capability-ledger
change is claimed by this test-scoping repair.
## Exact retained-claim migration proof

Repair tests/migrations/test_claim_starts_work.py and this record only. Remove
current HTTP, private task-command/AUTH owners and response/ORM readers from
the0064 fixture. Restore the validated archive using existing setup custody,
remove its setup projections, then prepare explicit predecessor SQL rows under
enabled guards. Prove direct ready insertion fails; insert draft/null-stamp
clones and use native screening/ready transitions. Use a distinct archived human
for wrong-assignee refusal. Do not fabricate current AUTH decisions.

Both internal plan tracks pass the amended exact sequence. PLAN-MIGFIX-001 is
closed by the guarded sequence and its named-guard negative. Risk L1 retained
data proof; allowed changes exclude production, migrations, archive bytes, shared
restore helpers, CI and runtime compatibility. Upgrade to exact0065, whose
conversion is under test, retaining all eight refusal cases, byte/xmin snapshots,
no partial conversion, exact revisions and native guard/downgrade checks.
Current reward-cutover refusal remains separately required. Native PostgreSQL,
lint, QA/test-delta/security/architecture reviews remain required. No capability
change is claimed by this test-only repair.

The first exactfd2a389 claim probe reached native setup but exposed an ambiguous
parameter reused for UUID contributor_id and varchar assigned_by. Keep the
predecessor column types and bind those representations separately; no schema
or guard change. That failed run completed owned cleanup. Rerun the same
selectors, preserving the original failure artifact and exact source custody.

## CLI current replay and paused-reward fixtures

Hosted5c30 CLI HTTP/API lanes exposed two remaining affected consumers. Allowed:
cli/tests/integration/test_revision_repair_http.py and test_task_batch_public_api.py,
plus this record. Complete the current-contract replacement already planned: a
paused blocked revision has both target and target_reward_selection null; an
exact screen replay after release returns its original immutable result under
fresh authority, per specification5.2.8. Preserve all malformed response,
request/substitution, uncertainty, real200-row source/import/transition and
revoked-manager denial assertions. Compare business snapshots separately from
the exact200 new allow IDs, then reset that baseline before revocation denial.
No production/Go parser, schema, authorization, workflow, skip or threshold change.
Risk L1 proof integrity. Verify the existing failing socket test and actual
PostgreSQL/MinIO200-row journey, lint/links and QA/test-delta/CI/reuse reviews.
No capability-ledger change is claimed by these fixture repairs.

Exactd68131c CLI isolation proof passed68 real Linux PTY tests against a freshly
built Go binary in the hash-locked minimal CPython3.12 environment. The35 proof
self-tests also passed on the preceding identical CLI source. Exactd68131c
real guide/policy socket API execution passed1 case in321.09 seconds, with
owned database cleanup and no MinIO/S3 claim. The exact25-file AST inventory
confirms canonical backend fixture reuse and no generic-conftest backend import.
Exact isolated9ec6a8c claim migration proof passed all3 cases in307.55 seconds
with complete cleanup; its test source is byte-identical in d68131c. This closes
execution gaps for these bounded repairs, pending focused implementation review;
full hosted execution and Finance runtime remain unqualified.

## Remaining current-selection consumer proof

The complete hosted5c30 candidate ran actual merge source58b71e0e. Artifacts
identify additional affected test consumers; no full-suite success is inferred.
The next repair extends the already approved current-selection replacement in
three files: authorization/test_acceptance_source_contracts.py,
tasks/test_locked_compensation.py and tasks/test_public_queues.py, plus this
record. Use a valid alternate task_size and UUID for nullable selection fields
in source-digest substitution proof; malformed scalar hashes cannot substitute
for those typed fields. Exact locked paid/unpaid projections include stored size.
Ready-queue selected-column proof includes precisely size and selected-definition
columns, preserving the unexpected-description-column mutant and no-lock check.
No production, schema, AUTH authority, test skip, workflow or quota changes.
Risk L1 proof integrity within existing selection scope. Required verification:
pure source commitment tests and real PostgreSQL locked paid/unpaid read branches
and exact queue columns, followed by QA/test-delta/CI/reuse review. Human focus:
new required selection facts are asserted, not ignored or defaulted. No capability
ledger change is claimed by this test-only repair. Remaining hosted failures
include predecessor-only fixtures, native negatives and other affected consumers
and remain blocking.

## Policy-read authority and schema proof consumers

Both plan tracks separate the remaining hosted consumer defects from missing
historical-window evidence. Implement approved groups1/4 only here: project_reads/
test_contribution_policies_list.py, projects/public_activation/test_workflow.py,
finance/test_selected_reward_migration.py, reviews/lifecycle/test_storage.py,
test_alembic.py exact graph assertion, and this record. PM and FM are authorized
policy readers; keep all unrelated/foreign-project denials, exact actor/grant/
resource audit proof, activation retirement replay and revoked activation denial.
Use the canonical reset import. Current empty upgrade expects only the new
nullable source-anchor key on genesis, preserving every old key/value; exact
revision graph includes0068..0071. No migration/schema/runtime/authority/CI or
fixture-default changes. Risk L1 proof integrity. Verify focused PostgreSQL
role/audit/activation and schema cases plus pure graph, lint/structure/links and
assigned reviews. No capability-ledger delta. Group5 historical running-window
proof lacks a captured preparation and remains unimplemented pending a genuine
source-commit capture plan; do not fabricate it or permit old runtime lineage.
