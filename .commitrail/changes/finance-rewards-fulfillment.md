# Size-based rewards and dedicated Finance fulfillment

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Implement the size-based reward and dedicated Finance contract in `workstream_finance_exec.md` through one PR with cohesive, revertible commits.

## Intent

Carry accepted Workstream contributions through authenticated financial fulfillment. The user explicitly requests one PR; implementation stages are commit boundaries within that PR. The specification is the settled product contract, including one eligible Finance human authorizing bank transfers.

## Current behavior

Baseline main is `94334ccf4085c26c7bfaa054465fc05cfbdad1fc`. REV FinalAcceptance composes TASK and CON participants in the caller's transaction; compensation already persists immutable award sets. Policy definitions currently permit multiple instruments. Finance fulfillment is absent. Native human acceptance is explicitly unavailable. Existing policy, award, revision, AUTH and OUTBOX tests protect the boundaries this change extends.

## Bounded change

### Allowed

- The owner and integration paths enumerated in specification section 19.3: backend contribution/compensation/task/artifact/review/AUTH/ACTORS/OUTBOX public APIs and implementations, same-owner adapters, API delivery, workers, shared settings/model registration and forward migrations.
- Dedicated `backend/app/modules/finance/`, its adapters, routes, workers, contracts and focused tests.
- Existing Rust identity issuer, CLI, MCP, deployment wiring and affected tests/contracts/docs.
- This record, the implementation specification and affected current capability/architecture documentation; ignored local roadmap exports if roadmap changes require them.

### Not allowed

- Merge, production payout or deployment without applicable user authorization; no secrets in Git.
- Separate Finance application/database/migration chain, parallel identity/grant store, direct cross-owner financial writes or bypassed authenticated HTTP.
- Native human review expansion, wallets, withdrawal, external routing, automatic historical payouts, rewritten historical economic evidence or weakened tests/CI.

## Design and decisions

Extend existing policy, task selection, revision and acceptance operations. Finance shares host infrastructure but owns financial records. Durable handoffs use actual authenticated HTTP after transaction closure. New v2 writes select one exact size-based award; genuine v1 history remains read-only. Payment uncertainty reconciles the same provider reference.

Rejected alternatives: separate app/database, duplicate workflow engines, direct same-process fulfillment delivery, multiple-person approval, and a second money award for points conversion.

Commit sequence follows specification section 19.2: (1) executable contracts/digests and retained-data preflight; (2) policy/task/revision propagation; (3) atomic award/root/handoff and callback custody; (4) Finance/AUTH/machine identity and runtime partition; (5) configuration/plans/credit/authorized transfer; (6) HTTP/client/recovery integration; (7) operational qualification and documentation. Split stages into smaller cohesive commits as needed. Reverting code is not a data rollback: preserve durable financial evidence and use the specification's coordinated cutover/restore procedure.

### First commit boundary: obligation wire contract

Allowed: `backend/app/modules/compensation/api/fulfillment_contracts.py`, `backend/app/modules/finance/api/`, `backend/app/modules/finance/contracts/`, narrowly scoped core wire-format primitives, and focused COMP/FIN contract tests. Excluded: models, migrations, module registry, routes, workers, AUTH activation, provider calls and financial effects. The next preflight commit requires its own concrete query/report plan before implementation; it is excluded from this contract-only commit.

Both owners independently validate the portable closed JSON Schema and canonical digests through their own public entry paths. Neither owner's decoder calls the other's decoder. Reuse the existing core hash and route-token primitive; avoid duplicated manually maintained field rules. Decode raw bytes before ordinary request parsing: enforce 64 KiB, strict UTF-8, duplicate-member rejection, object-only envelopes and unknown-member rejection. Tests exercise both entry paths against the same fixtures, including changed quantity with old digests and recomputed digests over an invalid source shape. Pure wire validation proves no source authority or database identity.

First-stage repair scope also includes `backend/pyproject.toml` package data,
the module registry and its scanner/count test, and the current architecture
module inventory. These make the contract installable and maintain scanner
parity; they activate no runtime financial effects. Existing registry tests
retain exact membership assertions with Finance added; no private-edge or
dynamic-import exceptions are introduced.

First-commit verification: `cd backend && .venv/bin/python -m pytest -q tests/finance/test_obligation_contracts.py`; `.venv/bin/ruff check app/core/financial_wire.py app/modules/compensation/api/fulfillment_contracts.py app/modules/finance/api tests/finance/test_obligation_contracts.py`. These are planned new tests/files, not executed proof. Schema fixtures include the exact specification vector, money and historical controls, plus negative canonicalization/shape/digest cases. Source-authority and runtime HTTP assertions remain later integration proof.

### Next commit boundary: retained-reward preflight

Allowed: `backend/scripts/finance_reward_preflight.py`, focused
`backend/tests/finance/test_reward_preflight.py` and its fixture imports, plus
this record and a short operational usage note. This is an offline migration
inspection command, not a product service or second migration runner. It uses
the shared configured engine and fixed SQL over the existing owner tables;
no private owner imports, mutations, repairs, HTTP routes, runtime handlers or
new schema are introduced.

Use one `REPEATABLE READ READ ONLY` transaction with a 30-second local statement
timeout. Each closed category returns `total_count`, sorted `sample_ids`
(default 100; caller may lower to 1–100), `truncated`, and `blocks_cutover`.
No economic bodies, request responses, actors' PII or credentials are emitted.
Exactly one supported Alembic revision must exist. Missing required tables or
columns fail closed. A missing `reward_model_version` column at the pinned
pre-v2 revision means v1; after the v2 migration the exact column determines
version and markers on definitions/awards are checked against their policy.
The post-v2 supported revision is added with its forward migration, not guessed
from arbitrary future schemas. Optional roots/receipts are reported only under
their exact owner table names when introduced, with explicit absent inventory
until then. This report is diagnostic, never cutover authority: the migration
must rerun blocker predicates while holding the real owner cutover fence.

Closed report categories and fixed predicates:

- `v1_policy_drafts/published/retired`: policy-version rows by exact status and
  v1 marker; inventory only. `unscreened_draft_tasks`: null locked contribution
  policy and draft status; inventory only, no economic terms inferred.
- `live_v1_tasks`: task has an exact v1 locked policy and status != accepted;
  conservative blocker because even a currently unassigned ready task can
  still originate v1 acceptance. `live_v1_assignments`: v1 submitter policy and
  active status; blocker. `live_v1_submissions`: v1 immutable submission policy
  and attempt_status in evaluation_pending/review_pending/needs_revision;
  blocker. `live_v1_revision_preparations`: joins its exact task in the live-v1
  task set; blocker, regardless of preparation outcome.
- `retained_contributions`, `retained_awards`: all existing source rows;
  inventory. `dual_award_contributions`: group awards by contribution ID with
  count > 1; inventory preserving both facts.
- `saved_task_commands`, `saved_import_batches`, `saved_import_commands`,
  `saved_policy_operations`, `saved_revision_preparations`: existing receipt/
  event/preparation rows, IDs only; inventory, never rewrite stored JSON.
- Exact saved selectors are respectively `task_command_receipts.id`,
  `task_import_batches.id`, `task_import_batch_command_receipts.id`,
  `contribution_policy_lifecycle_events.id`, and `task_revision_preparations.id`.
  Also inventory `saved_import_members` from `task_import_batch_members.id`,
  and `saved_policy_transition_custody` separately from
  `contribution_policy_transition_custody.operation_id`; these are distinct
  retained facts and are not silently deduplicated against lifecycle events.
- `acceptance_source_anomalies`: FinalAcceptance missing exact matching
  Submission/project/task/contributor or missing referenced authorization
  AUDIT row; task-route sources must additionally match their routing manifest's
  project/task/submission/contributor/content/policy/router/decision and exact
  final-acceptance ID, with its retained authority receipt valid. Use the
  existing SQL `task_routing_receipt_valid` as retained authorization proof;
  do not require a currently active grant or current lifecycle generation.
  Human sources must match actual accepting Review, lease, reviewer, locked
  review policy, source project/task/submission/assignment/content and existing
  source authority AUDIT. No new human acceptance is enabled. Block on a missing
  or crossed source. `acceptance_contribution_gaps`: FinalAcceptance without
  exact submitter ContributionRecord; blocker.
- `contribution_source_anomalies`: exact Submission/project/task/artifact
  mismatch, where the canonical artifact hash is
  `submissions.artifact_content_id -> artifact_contents.sha256` (there is no
  Submission hash column); accepted_submission must match FinalAcceptance and assignment,
  submitter and policy; completed_review must match actual Review/lease,
  reviewer and reviewer policy. Do not require a current grant for historical
  evidence. Missing/crossed source or policy facts block cutover.
- `award_source_anomalies`: award/contribution/definition project, contributor,
  policy, contribution kind, original instrument/unit/quantity/binding mismatch,
  or absent source/definition/binding; blocker. `award_completeness_anomalies`:
  retained contribution's award-definition set differs from its exact frozen
  rule (including valid unpaid zero and v1 dual sets); blocker.

Planned verification uses a real isolated PostgreSQL database: empty supported
schema inventory; real existing authorized routing fixture before and after
acceptance (live blockers disappear, dual awards retained); sample-limit
truncation; direct DML rejected in the same read-only snapshot; repeated report
and before/after economic row snapshots unchanged. Every blocker also gets a
reachable negative PostgreSQL control. For diagnostic corruption cases, a
schema-owning isolated test may temporarily disable USER triggers on one named
table, change one valid source field to a crossed but physically valid FK/value,
re-enable triggers and run the read-only diagnostic. This deliberately models
retained datastore corruption; it proves the diagnostic, never that current
runtime guards permit that corruption. Keep physical FKs/check constraints,
restore schema through the existing schema-owning test fixture, and prohibit
this setup in application code. Required controls cover mismatched acceptance
source/authority, missing contribution, crossed contribution content, crossed
award quantity/source, and missing required award; normal owner fixtures cover
each live-task/assignment/submission/revision blocker. Later migration rehearsal
adds genuine archived evidence and independent-session cutover races.
Commands (new test not yet executed): `cd backend && .venv/bin/python
scripts/run_isolated_tests.py -- .venv/bin/python -m pytest -q
tests/finance/test_reward_preflight.py`; `.venv/bin/ruff check
scripts/finance_reward_preflight.py tests/finance/test_reward_preflight.py`.

### Independent contract continuation: reports and exceptions

While preflight is reviewed, extend only the existing COMP/FIN public contract
entry points, shared canonical-format primitives, portable schemas/fixtures and
focused tests. Reports must match an explicitly supplied immutable obligation's
source/root/award/project/binding/route/instrument/unit/correlation and full
quantity. Validate closed fulfilled/failed shapes and receiver-time bounds;
late delivery remains valid. Exceptions must identify the exact prior fulfilled
event under the same obligation and use the prescribed time bounds. These pure
validators supply no source authority and perform no persistence or effects.
Both owners validate each fixture independently, including wrong-binding and
partial-quantity negatives. No routes, receipt store, new policy writer or
provider implementation is introduced by this continuation. Verification is
the focused contract suite plus canonicalization and shape adversarial controls.

### Next implementation boundary: v2 policy and exact task reward selection

This closes specification sections 4–6 and the policy/selection portion of
section 17, before fulfillment activation. Allowed: existing CON policy public
inputs/views, draft/publication/eligibility/graph/units owners; COMP award and
participation contracts; TASK create/import/screen/release/claim, contributor
reads, submission and revision owners; ART admission context; AUTH policy
permissions; their adapter roots, REST/CLI/MCP callers, focused fixtures/tests,
new forward Alembic revisions, preflight support for those exact revisions and
affected canonical policy/task/revision documentation. Finance execution,
provider calls, new human-review runtime and fulfillment handlers stay excluded.

Implementation decisions to review before runtime edits:

- Replace the current per-definition authoring shape with the specified common
  header and three-size/fixed-reviewer/unpaid rule shapes. Reject superseded
  input; do not maintain two authoring paths. Preserve per-definition facts in
  historical views. PM and FM share all six existing project policy actions;
  units/bindings remain Finance-only. Extend the existing unit command for money.
- Add v1 markers to retained policy versions/definitions/awards mechanically,
  preserving IDs, quantities and every stored digest/response. New policy and
  award inserts require v2; only a complete authorized replacement can upgrade
  an unpublished v1 draft. V1 publication/new acceptance is forbidden. Historical
  replay stays select-only, including dual awards and originally absent fields.
- Forward migration reruns the preflight blockers under the shared lifecycle
  and table cutover fence; live v1 tasks/assignments/submissions/preparations or
  source anomalies abort the transaction. Retained terminal facts remain. Add
  composite version/definition lineage and partial uniqueness, replacing the
  superseded global definition uniqueness and graph validator in place. Do not
  edit old migrations. Extend exact preflight support with the new revision.
- New task insertion stores a size (omission resolves to small; explicit null
  fails). CON resolves a size only under the screened active guide's exact
  policy; TASK copies its selected definition into assignment and immutable
  Submission. PostgreSQL enforces the same copy chain and immutable size.
  Retained unscreened drafts may receive small; immutable v1 submissions keep
  null. Public projections must never choose the newest policy or another tier.
- Revision retains size and records prior/target reward facts beside activation
  lineage, hashes both selections, and atomically rebases continuing TASK and
  assignment context through the existing operation. Preserve deadline/round
  guards and exact acknowledgement; permit both higher and lower terms.
- Shared acceptance obtains the selected definition from locked immutable
  submission facts and creates exactly one v2 award or zero for unpaid. Replace
  the old all-definitions new-write path. Historical v1 read/replay result types
  still represent two instruments; no global one-award validator may erase them.
- Historical TASK create and import replay selects its digest, manifest and
  response decoder from the exact immutable stored receipt/response format,
  before applying new defaults or new model fields. Recognize only the closed
  genuine v1 stored shape; do not try old hashes as a fallback after new hash
  failure. A missing current receipt always uses the new v2 writer. Keep raw
  input field presence so an explicitly changed task size cannot masquerade as
  the old omitted-size request. Preserve old import manifest/member/command
  bodies and their original canonical field set during membership reads;
  never rebuild an old digest from current `TaskImportRow.model_fields`.
  Archived pre-v2 create and import receipts must replay unchanged after the
  upgrade; changed payload under the same key must conflict and no historical
  branch may originate a new v1 task, submission, acceptance or award.

Required proof: focused policy shape/graph/AUTH tests, direct-SQL version/tier
and copy-chain rejection, complete public sized-task flow, exact first-submission
terms after later publication, higher/lower governed revision and acknowledgement,
atomic acceptance rollback/concurrency/replay, retained dual history, and migration
refusal with a live v1 source. Existing owner fixtures must originate new v2
graphs through the replacement writer; retain explicit archived v1 fixtures for
history/migration instead of adding old-writer compatibility. Shared checks and
real public API/durable-worker drill remain final PR requirements.

## Acceptance criteria

- [ ] Positive/negative contract fixtures reproduce canonical digest vectors and reject altered evidence.
- [ ] Sized public task/submission/revision paths preserve exact locked economic selection.
- [ ] Acceptance commits the selected award, root and handoff atomically; callbacks cannot create eligibility.
- [ ] Finance authority and worker profiles enforce source/project/grant currentness and disjoint delivery custody.
- [ ] All three fulfillment modes, uncertain outcomes, failure/retry, revocation, reversal and race boundaries are proven.
- [ ] Real PostgreSQL and public HTTP/durable-worker drills meet specification section 20; client/export contracts agree.
- [ ] Forward migration rehearsal preserves v1 evidence and refuses unsafe cutover.
- [ ] Current documentation, roadmap and operational claims match delivered proof; required reviews and repository checks pass.

## Risk and review routing

- Risk class: L0 (financial effects, cross-system authority and retained-data migration).
- Required reviewers: architecture, security, qa, test_delta, product_ops, reuse_dedup, documentation; ci_integrity for worker/deployment/check changes.
- Plan review precedes runtime implementation. Final reviews bind to a clean committed candidate after shared checks.
- Human review focus: economic selection and retained history, execution authority and uncertainty, cutover inputs, realistic drill evidence. Specific PR merge remains a human action.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Baseline reconciled | fetch origin main; inspect open PRs | Main matches pinned baseline; no open non-draft PR | Draft #708 touches intake and #698 CLI ZIP preparation; neither is implementation authority |
| Existing acceptance owner inspected | REV acceptance participant and compensation award participant | Existing caller-owned atomic composition confirmed | Full runtime suite not yet executed |
| Target behavior | Specification sections 20–21 and focused existing owner tests | Required proof defined; implementation pending | No payment/deployment qualification yet |
| Obligation wire validation | Focused COMP/FIN contract suite and Ruff | 76 cases passed; lint passed | Pure input proof only; no source authority, runtime activation or payment proof |
| Full-award reports and exceptions | Both owner contract paths, shared positive/negative fixtures | 164 combined contract cases passed; scoped lint and module boundaries passed | No receipt persistence, source authority or provider-finality proof |
| Retained-reward preflight | Isolated PostgreSQL runner: initial 15-test suite plus 4 affected-source repair tests | Passed, including live work, dual awards, read-only DML rejection, seeded corruption, unsupported human evidence and unknown schema; cleanup confirmed | Supports the pinned pre-v2 schema only; no actual migration fence or cutover proof |
| Genuine v1 archive inputs | Two current-owner captures; three real PostgreSQL restore/replay controls | Captures and controls passed; exact 18-decimal money retained, stored create/import responses replay exactly under fresh authority | Pre-v2 proof; rerun across the v2 forward migration before claiming preservation |

## Review findings

First contract-boundary plan review passed after narrowing the commit scope,
requiring raw-byte JSON guards and independent owner validation against one
portable schema. Preflight is excluded until its exact report/query plan is
reviewed. The first-stage implementation is subject to code review; broader
runtime stages remain unreviewed. No readiness claim.

First implementation review was provisional and identified missing wheel
package data (ARCH-001), permissive floating-point version values (SEC-001),
missing module-registry parity (ARCH-002), and an overly general primitive name
(ARCH-003). Repairs explicitly package contract data, require exact integer
versions, register Finance with unchanged exact-membership protection, and
name the obligation-specific canonical validator accordingly. The schema
loader uses a static package-relative path because the existing boundary
scanner rejects importlib surfaces; no scanner exception is added. A built
wheel extracted outside the checkout successfully loads the schema and validates
the known fixture through both owners. Exact-head replay remains required.

The focused contract-fix replay passed at `c64d4f218`, including an independent
wheel extraction and permissive-schema counterexample. Preflight plan review
then closed missing import-member inventory, incomplete acceptance-source
predicates, an imprecise artifact-hash path and unreachable anomaly controls.
The corrected plan passed at `130148fe0`. Its diagnostic passed the initial
15-test PostgreSQL suite and the four affected tests after source-qualification
repair, using runner-owned temporary databases with confirmed cleanup.

Implementation review identified that native human acceptance has no canonical
decision-receipt owner at the supported baseline: Review stores no authorization
decision ID, and the shared participant refuses human effects. The preflight
therefore blocks every retained human FinalAcceptance as unqualified evidence,
preserving its ID for owner reconciliation. It does not invent a human receipt
format or accept a same-actor unrelated AUDIT row. The same rule blocks retained
completed-review contributions without supported decision authority. Dedicated
real-PostgreSQL regressions cover these escaped false negatives. Task-route
acceptance retains its complete existing receipt validation. This refines the
planned human-source checks above rather than enabling human acceptance.

The source-qualification repair passed focused security/QA/test-delta replay at
`70a60846b`. The next v2 policy/selection plan passed at `629149638` after adding
explicit retained TASK create/import digest, response and membership handling;
new defaults must not rewrite historical canonical field sets.

Before replacing the writer, captured genuine dual awards and omitted-size
task/import receipts from the unchanged pre-v2 owners. The first uncommitted
capture exposed JSON-float precision loss; discarded it and preserved scalar
NUMERIC values as exact strings with verified column metadata. The existing
restore helper now validates and compares that representation without changing
old archive behavior. The new archives have fixed checksums, and the controls
prove exact decimal restoration, provider-free original response replay, fresh
authorization and changed-request conflicts. Cross-v2 migration proof remains
required. The one-time capture utility refuses changed writer code and cannot
serve as a new v1 writer after replacement.

The v2 policy checkpoint replaces authoring with a common header, three exact
submitter tiers, fixed reviewer quantity and explicit unpaid rules. All six
policy actions admit covering PM or FM grants; unit and binding role guards
remain Finance-only. Exact-version selection accepts published or retained
retired v2 terms without a current-policy lookup. Migration `0069` mechanically
labels v1 history, fences cutover on disabled/drained lifecycle and frozen source
checks, replaces definition uniqueness and extends existing publication custody.
The real paid publication drill found a second, deferred one-or-two-definition
guard; its cardinality now matches v2 while retaining event/actor/selector checks.

Focused proof: 153 policy-owner tests; 291 AUTH/adapter/boundary tests; 108
management-read/catalogue tests; 32 real PostgreSQL policy/history tests and 7
SQL/scope controls. The latter include exact tier resolution, retirement reads,
cross-project denial, malformed tier/version rejection, immutable publication,
PM unit denial in both scopes, migration refusal while live, exact retained dual
economics after authorized drain and forward migration, and original public
create/import replay after upgrade with fresh AUTH and no provider/parser access.
Both successful isolated PostgreSQL runs report complete cleanup. These results
are local checkpoint evidence, not full-suite or final review evidence.

Test changes replace obsolete new-authoring dual-instrument assertions with
closed-shape rejection; genuine dual history remains covered by the checksum-bound
archive. Quantity bounds, malformed internal graphs, deny-before-AUTH behavior,
resource isolation and operation replay remain protected through the replacement
input and shared quantity parser. No v1 authoring compatibility path remains.
The Go policy caller now accepts the same input and reads v1/v2 views; built
binary controls retain exact decimal strings and reject altered tier/marker/header
facts. MCP uses the frozen backend request schema instead of its superseded
definition input and separate graph validator.
Client proof: Go API/command packages passed; 10 built-binary policy controls
passed; MCP's focused 92-test run and the final 15-test policy/OpenAPI replay
passed. The 209 financial-wire, policy-shape and selection contract tests passed.
Scoped Ruff, MCP type checking, module boundaries, stale-input scan and changed
Markdown links passed. No full-suite or independent implementation-review verdict
is claimed by this checkpoint.

Still required within this PR: money-unit command exposure; task/import size and
selected-definition copy chain; revision reward packets; selected-award acceptance;
exact post-size historical replay; new-revision preflight support; Finance runtime,
authenticated handoffs, provider execution and durable-worker drills. Existing
v1-shaped native integration fixtures also need replacement through v2 owners.
Do not activate financial execution or infer readiness from this checkpoint.
Git checkpoint reverts aid source rollback only: `0069` deliberately refuses a
database downgrade; operational restoration requires a matched pre-effect backup.

Two combined reviews inspected checkpoint `024714dfb`: security, architecture,
product/operations and reuse found no blocking implementation issue in the
bounded policy phase. An exact-candidate SQL probe falsified the hypothesis that
application validation concealed missing database enforcement: malformed header
and incomplete-tier publications failed at commit, rolled back, and allowed the
same valid retry. Copies of genuine retained v1 economic rows failed on the
specific new-write prohibition. Those controls now remain regular regression
tests; their four-case PostgreSQL run passed with complete cleanup. Final cutover
race and live-v1 refusal qualification still remain.

QA/test-delta and docs found `QA-POLICY-001` and `DOC-POLICY-001`: MCP accepted
incomplete graphs and floating-point markers; CLI accepted a partial draft;
current authority documentation still excluded PM. The repair uses closed CON
view schemas and one MCP semantic validator for read/list parent-child relations
and exact integer representation, with matching CLI empty-or-complete draft
validation. Read/list adversarial controls preserve valid unpaid, reviewer-only,
three-tier and retained v1 graphs. Current entry, glossary, CLI and affected
roadmap summary/scoreboard/dependency/gate/trace claims now distinguish PM/Finance
policy management from Finance-only units/bindings. No local spreadsheet exports
are present. Repair proof includes 219 backend contracts/read controls, the
focused 94-test MCP/OpenAPI run, Go package checks, built-client malformed-output
controls, scoped lint/type checks and Markdown links. Affected reviewer replay is
required before treating either finding as closed; whole-PR qualification remains
separate.

## Reconciliation

- Current-source reconciliation: baseline matches the specification; no newer merged owners found.
- Next usable boundary: v2 policy/task/revision selection and its forward migration; contracts and pinned-baseline preflight are implemented, with financial activation closed.
- Remaining risks: broad single-PR review surface explicitly selected by user; commit boundaries aid inspection but do not establish runtime rollback safety.
