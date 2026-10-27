# Terminal Systems real-project drill and integration repairs

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Repair demonstrated Terminal Systems checker/setup integration defects and report the actual public API and durable-worker journey with exact release evidence and explicit remaining limits.

## Intent

A real restart-safe repair must be tested after reference application. Starting
the interruption control from the deliberately broken starter makes valid
recovery work fail; allowing a failed restart verifier to pass model assessment
conceals that failure.

## Current behavior

`post/model/trial_plan.py` requires a fresh interruption workspace and seeds the
starter, while hiding reference material. `trial_assessment.py` guards resource
failures but omits nonzero restart verification from condition 11 contradictions.
The generic relay and execution engine already support exact retained-parent
state, so they need no change.

## Bounded change

### Trial repair allowed files

- `pilots/terminal_systems/checkers/post/model/{trial_plan,trial_assessment,test_trial_plan,test_trial_assessment,test_runtime_checker}.py`.
- Focused local subprocess recovery proof under the existing model test suite.
- `scripts/test_public_hosted_model_post.py`: repair its qualified-image unit fixture and explicitly prove changed source trees remain rejected; do not relabel historical image qualification.
- `backend/scripts/test_lane_catalogue.py` and its `backend/tests/test_ci_lane_catalogue.py` fingerprints: assign the added setup regression module to its existing semantic lane. Preserve complete selection, counts and rejection of unassigned modules. Format the already-affected CLI regression with the pinned formatter.
- Checker README, qualification fixture README/author notes, affected capability wording in `docs/roadmap_status.md`, and this record.

### Trial repair exclusions

- Generic runtime/relay changes, migrations, new subsystems or fallback paths. The bounded setup declaration repair below is the only additional product-contract change.
- Reference visibility in interruption/restart/verification, or changing incomplete repair from fresh state.
- Changing retained-parent/export custody, existing locked bindings, deployed resources or unrelated worktrees.

## Design and decisions

Require `reference_baseline` in the prompt and strict proposal validator; the
existing plan builder resolves it to `reference_verify_3`. The interruption
projection inherits retained state without seed roles and exposes verification
only. Restart still inherits the exact interruption export and full verification
inherits the exact restart export. Require successful `restart_verification`
for condition 11, while allowing the documented interruption to be signalled.
Any subsequent use needs a new immutable image and projection binding; existing
locked selectors are not mutated.

## Acceptance criteria

- [x] Complete and partial proposals reject fresh interruption state.
- [x] Incomplete repair remains fresh; interruption inherits repaired state with no seed and verification-only visibility.
- [x] Local subprocess proof rejects the unrepaired starter and passes repaired interruption/restart through the generated plan and projection; restored defects fail the regression.
- [x] A nonzero restart verifier cannot receive an all-satisfied model pass; an exact condition 11 finding is accepted and a documented signalled interruption remains valid.
- [x] Focused suites, lint, stale wording and Markdown links pass; evidence distinguishes local semantics from real isolated/runtime qualification.

## Risk and review routing

- Risk class: L1 — bounded untrusted trial evidence and model false-pass boundary.
- Required reviewers: QA, test delta, security, documentation; lead coordinates focused independent review.
- Human review focus: Repaired-state intent, exact retained lineage, protected material visibility, false-pass rejection and new immutable runtime selector qualification.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Repaired recovery and failed-verifier guards | `python3 -m unittest discover -s pilots/terminal_systems/checkers/post/model -p 'test_*.py'` | Pass | Local subprocess proof does not qualify Smol, image registration or live model quality |
| Existing qualification fixture behavior | `python3 -m unittest discover -s pilots/terminal_systems/checkers/post/qualification -p 'test_*.py'` | Pass | Engineering fixture only |
| Regression sensitivity | In temporary copies, restore fresh seeded interruption projection; remove partial-plan state guard; remove restart-verifier contradiction | Guard-specific focused regressions fail at their intended assertions | Restoring the whole original plan instead fails setup validation; that separate probe is not runtime recovery proof or general mutation coverage |
| Project code quality | `ruff check pilots/terminal_systems/checkers/post/model` and `ruff format --check pilots/terminal_systems/checkers/post/model` | Pass | No generic-owner or hosted suite claim |
| Current documentation | `python3 scripts/check_stale_workstream_wording.py`, `python3 scripts/check_markdown_links.py`, `git diff --check` | Pass | Markdown check covers changed local links |

## Review findings

Independent pre-implementation inspection identified both owner defects and
confirmed that generic state custody must remain unchanged. Lead-managed
independent review follows the frozen candidate.
The qualification fixture's author notes now agree with repaired-baseline
interruption; its README explicitly limits the literal-output restart control
to plumbing proof. The existing synthetic test remains intact, alongside the
new recovery-code regression.

## Reconciliation

- Current-source reconciliation: Based on main `ac637495f`; no generic-owner changes required.
- Roadmap reconciliation: Updated the detailed project-checker boundary. Executive summary, scoreboard, dependency diagram and remaining gates still correctly require exact image/binding/runtime qualification; this repair adds no generic capability or lifecycle branch. No local sheet exports exist in this worktree.
- Next usable boundary: Build/register an exact new image and projection, then qualify the real task through the public journey.
- Remaining risks: Real nested runtime and live-provider qualification remain separate from local tests.


## Single-PR coordination

The user explicitly requested that all repairs found in this drill and its report
remain in PR #697. Parallel worktrees are temporary implementation areas; they
do not create separate repair PRs. The sections below bound the additional
demonstrated setup defect and live qualification. Component test passes do not
constitute a completed hosted journey.

## Setup evaluation-context declaration repair

### Intent

A real Terminal Systems setup drill needs predecessor findings and the predecessor
archive. Runtime already provides those explicitly selected roles. Setup currently
can express only broad `task_context/runtime_gap`, which correctly prevents a
supported binding. Extend the existing declaration and policy validation; no new
runtime authority or materialization path is needed.

### Bounded change

Allowed: `backend/app/interfaces/project_agents.py`,
`backend/app/modules/checkers/api/external_policy.py`,
`backend/app/core/project_guide_instructions.py`, strict proposal decoding in
`cli/internal/api/guide_proposal.go`, focused setup/external-policy/CLI tests and the strict provider fixture in
`backend/tests/test_agent_runtime.py` and the affected approved-binding fixture in
`backend/tests/checkers/external/test_revision_materialization.py`,
`mcp_server/contracts/guide_proposal_get.json`,
`mcp_server/contracts/guide_post_policy_get.json`, `docs/spec_chunk_3_project_guide_foundation.md` and
`docs/roadmap_status.md`, and this record.

Prohibited: runtime transport/authority changes, broad task/guide-context access,
schema migration, dependencies, CI weakening, unrelated cleanup, retained data changes, or a separate repair PR. Authorized drill deployment is bounded separately below.

1. Add exact `evaluation_context` input and dependency; require a typed, canonical
   role tuple on that input only, using the existing supported role vocabulary.
   Exclude the absent field so retained compilation hashes remain stable.
2. Require paired input/dependency, `current_runner`, `material_unavailable` and
   POST background scope. Keep broad task/guide context unavailable.
3. Use one public external-policy helper for symmetric exact declared roles versus
   selected v1 configuration, with canonical registry validation in both proposal
   projection and approval-time actual resolution.
4. Update setup instructions and strict CLI decoding, then prove positive model
   and trial declarations, denial boundaries and retained serialization.

### Acceptance criteria

- Model-only and trial POST revision specifications admit exact selected roles.
- PRE, missing/unknown/duplicate/noncanonical roles, misplaced role fields,
  missing/extra declaration or selection, and role mismatch fail closed.
- Unsupported actual registry schemas fail approval before policy persistence.
- Broad task/guide context remains a gap and retained input serialization/hashes
  remain unchanged when the new field is absent.
- Run focused Python tests, strict CLI integration/unit checks, applicable lint,
  boundary, Commitrail, stale wording and Markdown-link checks. Assess generated
  OpenAPI exposure and roadmap claims; update only affected capability wording.

### Risk and review routing

Risk: L1, policy-admission/public contract. Required internal reviewer tracks:
architecture, security, QA/test_delta, documentation/reuse as scoped by the lead.
Independent pre-implementation plan review: `/root/real_trial_plan_review`.
Human review focus: declaration is descriptive only; exact selectors cannot gain
undeclared material; approval rechecks the actual registry; retained hashes stay
stable. Lead owns final clean-target reviewer routing and complete-suite evidence.


### Evidence

Focused owner tests pass, including real model/trial configuration validators,
projection/actual-registry symmetry and an approval compiler probe that supplies
a valid projection with an unsupported actual publication and rejects before any
session write. Strict CLI HTTP integration accepts the exact public field and
rejects malformed roles or missing paired declarations. Existing retained-result
hash tests and the new absent-field serialization probe pass. Runtime custody and
materialization are unchanged; this repair does not approve a project, qualify a
native trial or establish a live revision journey.

Roadmap assessment: update the compilation scoreboard and detailed Terminal
Systems setup boundary to name the exact declaration contract. Executive,
dependency and remaining-gate claims retain their existing supported branches and
requirements: this repair adds no lifecycle dependency or delivered journey.
No local spreadsheet exports are present in this worktree.

The expanded instruction initially exceeded the existing 16,000-character bound;
condensing the same specification/dependency guidance fixed it without raising the
limit. The actual SDK parser also required the new nullable input member in its
strict provider fixtures; those fixtures now include null, while canonical stored
and public inputs omit absent roles. Existing prompt-rule assertions are retained.
The exact pinned OpenAI runtime/contract regression suite passes. An isolated
in-memory removal of both agreement guards makes the named mismatch regression
fail its expected-exception assertion.


Review repairs: QA-EC-001 updates the real PostgreSQL/ART revision fixture to
pair its selected roles with an exact input/dependency while keeping the copied
current-only binding's specification unchanged. QA-EC-002 retains a valid model
specification and profile in the undeclared-context negative, so removing the
approval guard cannot be masked by unrelated model-profile rejection. Duplicate
roles now use two identical entries within the field's cardinality limit.
These repairs consolidate into PR #697; this temporary branch is a work area,
with no separate push or pull request.


## Authorized hosted drill and reporting

### Intent

Execute and report the existing [#555 hosted-drill plan](https://github.com/Flow-Research/workstream/issues/555), consuming merged owners rather than designing another lifecycle or deployment system. The user authorized the current first automated journey; this record bounds its execution and reporting, not a new initiative. The result belongs in the [drill report](../../docs/reports/terminal-systems-hosted-drill-2026-10-27.md).

### Current behavior

The [capability ledger](../../docs/roadmap_status.md) describes implemented guide setup, task intake, immutable Submission, automatic POST, governed acceptance, checker remediation, contribution evidence and bounded Operator recovery. Existing [hosted qualification](hosted-smol-project-execution.md) proves a synthetic guide journey and one scoped live model POST with simulated identity. The [real setup handoff](terminal-systems-live-setup.md) predates the narrowed PRE/POST-only proposal contract. Neither establishes an approved, activated Terminal Systems contribution journey.

### Bounded change

### Allowed

- This record and `docs/reports/terminal-systems-hosted-drill-2026-10-27.md`.
- Lead-coordinated execution of the already authorized real-project drill through existing public APIs, durable workers and supported operational procedures; retain exact non-secret provenance and private evidence outside Git.
- Read-only owner observations to establish exact lineage, atomic outcomes, retained history, accounting and cleanup; existing source-specific recovery only.
- Private operator configuration and scripts for the newly owned EC2 root
  `/var/tmp/workstream-terminal-real-20261027`, original task packages under
  `/tmp/workstream-real-terminal-20261027`, and retained private receipts. Reuse
  pinned images/assets only after source and content identity checks. Keep the
  original project deployment and earlier qualification accounts unchanged.

### Not allowed

- Product changes outside the explicitly bounded trial and setup declaration repairs above. A further demonstrated defect needs its owner, allowed files and discriminating regression added to this same record before repair.
- Direct product-row seeding/repair, fabricated setup or checker results, silently omitted required checks, changed locked rules, blind UNKNOWN redrive, or deletion of retained evidence.
- Live human-review runtime, payment delivery, runtime reputation, frontend, claim expiry/skip, external integrations or expanded evaluator/CI work under #496.
- New spending authority, reset accounts or counters, disclosure of secrets/private material, unrelated resource cleanup, issue closure, push or merge based on this record.

### Design and decisions

1. Bind every result to the deployed source, immutable image/configuration identities, current native Smol node, guide, packages and exact policy/activation lineage. Source inspection alone is not deployed proof.
2. Use original Terminal Systems inputs and genuine positive/negative packages. Obtain a fresh supported setup proposal, resolve required gaps, then separate PM approvals, Finance policy publication and activation. Use explicitly approved `human_review_required=false`; preserve true-policy guards and the existing `review_pending` handoff.
3. Use existing intake, retry, reconciliation, shared FinalAcceptance and evidence owners. Report each implemented capability as exercised, failed, blocked or not run; retain prior scoped proof separately. A report template is not a completed drill.
4. On 2026-10-27 the user explicitly authorized an **additional US$10 total cap**
   for this complete project drill, covering setup, POST and retries together.
   Provision one new immutable project account with at most 10,000,000,000 USD
   nanodollars before paid dispatch. Retain every reservation/effect across
   retries; stop on ambiguous effects or exhausted headroom. This does not
   reconcile or reset the original uncertain setup spend or the separate
   model-only qualification account (US$0.016527 settled). Those accounts and
   their evidence remain unchanged.
5. Label the simulated HTTPS/JWKS issuer explicitly. It exercises the unchanged verifier and AUTH, not production Flow Identity integration or introspection/revocation. Keep tokens, subjects, keys, private model bodies, artifact content and service/provider coordinates out of public evidence.

### Acceptance criteria

- [ ] Report records exact deployed source/image/config/runtime/corpus fingerprints, each scenario's actual outcome, evidence reference and limits; no inherited pass from prior scoped proof.
- [ ] Original inputs, current proposal fidelity, genuine reference/negative packages, model/material requirements and PM agreement satisfy #576 before policy activation.
- [ ] Public setup, approval, task release, claim/start, ZIP preparation, immutable Submission and durable POST reach the governed outcome with locked lineage and no hidden fixture shortcut.
- [ ] Positive false-policy outcome has exactly one FinalAcceptance, submitter ContributionRecord and complete applicable frozen award set, without a fabricated Review, reviewer contribution or fulfillment claim.
- [ ] Intake failure, work failure/remediation, revision limits/windows, infrastructure recovery and request/completion/acceptance interruption retain their distinct state, penalty, history and once-only effects.
- [ ] Wrong authority, revocation, stale replay, AWS custody, resource limits, diagnostic privacy/outage, drain/restart and final-data restore have exact current-run evidence or explicit unresolved blockers.
- [ ] Report reconciles #555/#576/#581/#582/#583 without closing them solely for merged foundations; #496 and deferred runtime scope remain excluded.

### Risk and review routing

- Risk class: L1, cross-owner public-runtime and recovery qualification.
- Required reviewers: architecture, security, qa, product_ops, documentation, focused on the actual evidence and changed claims. Add test_delta for harness/regression edits and ci_integrity only if CI changes enter an amended scope.
- Human review focus: authentic project requirements and approvals; genuine package quality; exact artifact/policy lineage; safe paid-effect recovery; single acceptance/contribution/award effects; simulated identity disclosure; retained data and honest proof limits.
- Plan: inventory the retained environment and accounting; prepare packages/current proposal and approvals; execute positive/negative and recovery scenarios; reconcile exact evidence and remaining gates; freeze the report for affected independent review. The lead owns plan review and runtime coordination.

### Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing implementation and parent acceptance located | Current roadmap, owner records and #555/#576/#581/#582/#583 inspection | Discovery only | Deployed release fingerprints and real-project execution remain to be recorded |
| Current rehearsal | Linked report's scenario matrix | In progress: deployed release, public guide/isolation/replay and registry proofs retained; live setup rejected schema-invalid output | No current-run acceptance or release claim |

### Reconciliation

- Baseline discovery inspected source `ac637495f`; the report must bind actual execution to its exact deployed release rather than assume that source is running.
- Historical issue text describes gVisor and earlier branches. Current merged hosted composition selects native Smol. Project onboarding prose also understates implemented POST capabilities; the report distinguishes these implementations from missing real-project approval/activation proof without changing those files here.
- Roadmap assessment: an unexecuted report adds no capability or exposure claim. Actual results may change remaining release gates; the lead must amend allowed documentation scope and reconcile affected roadmap claims in the same PR before readiness.
- Next usable boundary: execute the authorized rehearsal, retain failures, repair demonstrated defects through bounded owners and report current evidence. No complete disposition is asserted.


## Hosted-image guard fixture reconciliation

The combined branch activates the release-image workflow. Its cache unit test
assumed that the current checkout always matched the separately qualified old
image source tree. The trial repair intentionally changes that tree, so the
existing production guard correctly refuses it. The positive unit fixture must
supply the exact qualified tree through the existing command boundary, while a
separate negative proves a different tree is rejected before checkpointing.
Keep image/archive substitution assertions and all production pins/guards.
This is test-fixture reconciliation, not qualification of a new image or a
compatibility path. Run the full affected hosted attachment/model test modules
and a guard-removal probe; QA/test-delta review covers this added file.


## Combined CI inventory reconciliation

Hosted execution found that the added setup regression file lacked an explicit
entry in the existing lane catalogue, correctly stopping every lane before test
execution. Add that module to the existing project lane; do not bypass the
missing-module guard or change completeness requirements. The affected CLI
fixture also needs canonical formatting. Validate complete collection/allocation
and the formatted CLI cases, then obtain focused CI-integrity review before the
next push. Prior component test passes did not establish hosted inventory
completeness; retain the failed run as evidence.


## Real setup request conformance repair

The first actual guide upload/download preserves exact original bytes. Its setup
attempt becomes provider-unresolved before a model effect is prepared: the
OpenAI Agents SDK OpenRouter request omits the mandatory usage-reporting field
that the existing trusted setup handler requires. The OmniCore adapter already
provides it. Retained observations show zero setup effects, reserved charge or
settlement; no blind retry is authorized by that observation alone.

Allowed: `backend/app/adapters/project_agents/openai_agent_sdk.py` and its
existing native runtime/resilience and setup-handler test modules. Add the
required OpenRouter request field to the existing adapter construction. Keep
the closed trusted handler, provider/profile/budget rules and Responses
behavior unchanged; do not add a fallback, new provider path or config option.
Use the pinned native SDK request serializer with a valid typed profile and
the actual trusted request validator. The regression must fail on the original
adapter and pass after repair before any provider call or model effect. Run
affected SDK/handler tests and focused security/architecture/QA/test-delta
review. Preserve the failed attempt; recovery must use an existing authorized
owner after diagnosis, with no direct row edits or duplicate paid effect.

## Setup instruction example conformance repair

After metered request repair, the real run completed seven paid calls and ended
with invalid terminal output. Separately, current-head CI and a focused local
reproduction prove the canonical instruction example is invalid under the
provider's strict schema: two non-evaluation-context inputs omit its required
nullable `evaluation_context_roles` member. The accompanying instruction also
incorrectly tells the model to omit it. The retained live outputs pass structural validation, so this example defect
is not the demonstrated cause of the live failure. Its final output instead
uses `checker_tool/current_runner` and `isolated_execution/trial_proxy`, which
the canonical dependency owner correctly rejects. The prompt omits the exact
legal provisioning for those kinds.

Allowed: `backend/app/core/project_guide_instructions.py` and the existing
`backend/tests/test_setup_checker_scope.py` regression if a distinct assertion
is needed. Supply explicit null for unrelated input roles in provider-facing
examples and correct the contradictory instruction. Add the exact legal
`checker_tool/checker_implementation` and `isolated_execution/current_runner`
guidance, with `implementation_unavailable`, and the required dependency for
isolated evaluation. Prepared trial material must also declare its isolated
trial dependency. Preserve model/trial/context guidance. Keep the original 16,000
character instruction bound, strict parser, evaluation-context guards and
canonical stored-result omission/hash semantics unchanged. No compatibility
path or schema relaxation. Preserve the failed actual attempt, all seven paid
effects and the same project budget. Any further inference uses a supported
fresh request after diagnosis; never reopen invalid terminal evidence.

Proof: the unchanged complete-example regression fails before repair and must
pass afterward; run affected instruction/parser/SDK tests, verify prompt bounds,
and obtain focused QA/test-delta, security/architecture and documentation review
on the frozen combined candidate. The live attempt and hosted CI failure remain
explicitly retained evidence, not passing qualification. A private offline
control may correct only the four provisioning values to identify the exact
failed invariant; never persist that edited model output as a proposal. Retain a
small public synthetic regression proving the new guidance and canonical
validator agree, including missing or substituted guidance probes. The actual
four-value control exposes a second required invariant: two prepared-material
specifications lack `nested_sandbox/trial_proxy`. Adding only those required
dependencies in the private copy passes structural, canonical and actual-context
validation. This is a diagnostic control, never an approved model result.

## Project POST requirement identity repair

The retained generated output selects all ten intended configured checks and
exact published registry selectors. Seven POST requirement names differ from
the configured rubric selector. That is valid under the published input schema
and Workstream's locked binding contract, but the project image incorrectly
requires equality and would return infrastructure failure. PRE already keeps
these identities separate. Do not force the generic setup agent to use this
project's private rubric names or silently rename retained proposals.

Allowed: `pilots/terminal_systems/checkers/post/model/{checker,runtime_checker,author_checker,revision_checker,result}.py`
and their existing focused test modules; a focused alias/finding case in the
existing PRE test module if needed to prove the intentional contract difference.
Related project-checker README/qualification documentation and this report may
be reconciled. No generic execution, AUTH, registry, compiler or schema changes.

Keep the configured supported check as the exact rubric selector. Independently
validate the input's opaque requirement identifier with the published strict
identifier shape. Reuse one small validator in the existing result module where
it avoids four duplicate guards. Preserve request-digest/registry/phase binding,
all model/trial and revision-context controls, and project-local finding check
IDs, which the canonical output contract permits. Unknown or wrong configured
checks and malformed requirement identifiers must still fail before model or
trial effects. No compatibility alias, fallback or alternate result path.

Proof: reproduce a valid alias being rejected on the original image code, then
exercise generic semantic, runtime, author and revision paths with distinct
valid requirement IDs. Assert unchanged rubric/trial selection and meaningful
findings; independently retain malformed-ID and wrong-selector rejection before
effects. Run affected project suites and focused security/architecture/QA/test-
delta review. Qualify a new immutable POST image and registry identities before
use; never rewrite earlier registered entries, retained trial authority or
locked policy facts. PRE production/image identity remains unchanged.


### Additional repair verification

The existing instruction-example regression fails on the prior source and
passes with explicit nullable provider fields; its typed canonical hash remains
unchanged. Dependency guidance is checked against the actual typed invariants. All 204
affected instruction/runtime/specification tests pass, including the unchanged
16,000-character bound; twelve omission/substitution probes detect the intended
failures.
The project POST repair passes 83 tests (plus 99 subtests); unchanged PRE passes
17 tests (plus 12 subtests), and 30 canonical external-contract cases pass.
Replaying the alias regressions against the original five owner files fails all
five execution paths. Removing only the shared ID validation fails malformed-ID
cases. Separate canonical request/result composition accepts a deliberately
different requirement/finding identifier and rejects a substituted request digest.
These are local proofs; they do not qualify the new image or complete journey.

Roadmap reconciliation adds only the affected detailed integration repairs and
links the actual in-progress report. Executive summary, scoreboard, dependency
and remaining release gates still require approved policies and the realistic
public journey; none are marked completed by these repairs. Current main's CLI
work must be preserved when reconciling the branch before final review.
