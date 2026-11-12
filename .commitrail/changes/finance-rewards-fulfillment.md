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
preflight. Exact Submission selection remains the next acceptance dependency.
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
