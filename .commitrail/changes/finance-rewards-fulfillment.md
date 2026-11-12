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
these counts are not coverage gates or whole-PR qualification. Remaining planned
migration refusal, independent-session claim/acceptance races, explicit original
claim/Submission replay after rebase and durable-worker failure/retry proof stay
required. Finance roots, handoff and execution remain unfinished.
