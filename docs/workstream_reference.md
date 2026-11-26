# Workstream Technical Reference

This document holds the detailed product, lifecycle and implementation notes that
were previously in the README. Read the [README](../README.md) first for a short
introduction. The [v0.1 Roadmap And Capability Status](roadmap_status.md) is the
current capability ledger.

## Definition

Workstream defines a shared protocol for governed work and provides the
software that implements it. It coordinates, verifies, and records work
performed by humans, AI agents, or both. It transforms
project-defined tasks, immutable submissions, policy-governed checks, and
policy-governed acceptance into trusted `ContributionRecord` facts that applications,
organizations, and economic systems can consume.

The protocol defines valid lifecycle actions and records; the software
enforces those rules. A standalone versioned protocol specification and
conformance suite remain formalization work, not delivered interoperability
claims. See [Protocol And Implementation](protocol-and-implementation.md).

Workstream governs the work lifecycle; it does not need to own the system that
requested the work, the tools used to complete it, the identity provider, or
the consequence applied afterward. A project defines the rules, an authorized
contributor performs the work, Workstream binds the exact submitted artifact to
those rules and its verification evidence, and records the authorized outcome
under the project's locked acceptance rules. The resulting immutable contribution lineage establishes who did
what, under which rules, using which artifact, and with what verified result.

## End-To-End Lifecycle

The complete Workstream model is:

```text
Project Guide
-> Versioned Policies
-> Task Assignment Or Claim
-> Artifact Preparation And Pre-Submission Intake Checks
-> Immutable Submission
-> Post-Submission Work Evaluation
-> Policy-Governed Acceptance (Human Review When Required)
-> Accept / Needs Revision / Reject
-> Revision And Resubmission When Required
-> Immutable ContributionRecords
-> Optional Project-Specific Consequences
```

The current submission contract normally receives one outer ZIP containing the
complete work. Workstream computes canonical content identity, stores the bytes
through its artifact boundary, verifies stored content before trusted use, and
runs configured checks against the submitted package and its bounded recursive
contents. After Submission creation, the contributor's submitted work,
post-submission checkers, reviewers, and downstream projections are tied to the
same immutable Submission lineage. Before creation, intake evidence refers to
the prepared artifact and locked intake context, not an existing Submission.

Pre-submission and post-submission checking are different stages:

- **Pre-submission intake checks** assess whether the prepared package is fit
  to submit: required outputs, packaging, evidence integrity, and configured
  intake-quality rules. Blocking failures return feedback before a Submission
  is created. Passing intake does not establish that the task was done correctly.
- **Post-submission work evaluation** assesses the immutable submitted work
  against the locked task/project requirements. Durable results determine
  review eligibility, not final acceptance. Task-specific evaluation may use
  deterministic rules or, when supported and registered, model/agent-based
  evaluators such as a quality judge. These are not the setup agent that
  proposes checker policies. Raw checker results are not acceptance authority;
  when human review is required they do not replace that Review.

The v0.1 project setting `human_review_required` defaults to `true` in the
existing locked ReviewPolicy. After required post-submit checks pass, true
requires human review; false uses an authorized automated FinalAcceptance and
submitter ContributionRecord, with no reviewer contribution.
The separate `requires_second_review` policy field is [fixed to `false`](../.commitrail/changes/enforce-requires-second-review-false.md)
at input, immutable lineage, and database boundaries; second-review and
adjudication behavior remain deferred.
The automated-acceptance branch is implemented in the selected backend
composition: supported false-policy guides can activate, and selected completion
routing uses the shared FinalAcceptance/TASK/CON operation. New false/pass effects
require an Operator-authorized live REV generation whose immutable transition
binds the current reviewed manifest. An older live authorization cannot enable
expanded scope; a typed pre-effect refusal rolls back and uses bounded OUTBOX
retry. The bounded local public API and Celery service drill starts from public guide
inputs with recorded inference;
this is not a deployment claim. Adjudication is excluded.

The stage describes the purpose and lifecycle boundary, not a promise that all
checks are deterministic. Deterministic compilation and policy routing do not
make model-based judgments reproducible. Only supported implementations run;
the [roadmap](roadmap_status.md#pre-submission-and-post-submission-checking)
distinguishes existing foundations from remaining integration and does not
claim a live agent judge.

On the human-review branch, every valid Review creates a reviewer `completed_review`
`ContributionRecord`. An `accept` decision also creates `FinalAcceptance` and a
submitter `accepted_submission` `ContributionRecord`. These records cannot be
created or edited directly by a person or downstream adapter. Together they are
the central durable outcome of Workstream.

## How Workstream Establishes Trust

- **Identity is separate from authority.** External identity verification does
  not grant product access. Explicit administrative or project-scoped grants,
  resource ownership, lifecycle guards, and revocation determine authority.
- **Project rules are versioned and locked.** Assignments, submissions,
  Reviews, and contributions retain the guide and policy context that governed
  them instead of silently adopting later rules.
- **Artifacts are immutable and content-addressed.** Workstream derives identity
  from server-computed SHA-256 and byte count, independently verifies stored
  bytes, and binds trusted content facts to that identity.
- **Checks have distinct, attributable evidence.** Pre-submit results refer to
  the prepared artifact and locked intake context before Submission creation.
  Post-submit results refer to the immutable Submission and locked evaluation
  policy. Intake feedback cannot substitute for post-submit review-gate evidence;
  recording an evaluation does not guarantee an identical judgment on rerun.
- **Review is authorized and attributable.** A Review records the authorized
  reviewer, exact artifact lineage, locked rules, findings, and one canonical
  decision: `accept`, `needs_revision`, or `reject`.
- **Separation of duties limits self-dealing.** Submitter and reviewer authority
  are independent, self-review is prohibited, and narrower project conflict
  rules may be enforced.
- **History is preserved.** Submissions, findings, responses, resolutions,
  Reviews, contribution records, awards, receipts, and audit evidence remain
  linked rather than being overwritten.

## Source-Agnostic Core, Bounded v0.1 Intake

Workstream does not require tasks to originate from one marketplace,
application, organization, or industry. AI evaluation programs, government
workforce initiatives, research programs, open-source projects, contractor
pipelines, academic review, data-labeling operations, and legal, medical,
engineering, creative, human-to-agent, or agent-to-agent workflows can use the
same governed lifecycle while retaining their own user experience and operating
model.

Source-agnostic does not mean every source adapter is already implemented.
v0.1 remains manual-first. PILOT-02A provides Project Manager declaration, upload,
inspection and verified download of canonical JSON task-import sources through the
[public ART contract](spec_artifact_storage_service.md#task-import-source-custody).
Its public routes are covered by PostgreSQL/MinIO custody, authority, replay and
recovery tests. PILOT-02B imports one verified JSON source into immutable native
batch membership and 1..500 DRAFT Tasks atomically, with fresh-authority exact-file
replay and batch status through the public TASK contract. Its actual 200-row and
rollback/custody controls pass on PostgreSQL and MinIO. PILOT-02C adds explicit atomic batch screening
and release and CLI source/import/status commands with local CSV conversion. A client-converted CSV retains
its received JSON rather than claiming original CSV custody.
External origin onboarding, external task-routing systems, and execution workspaces remain
later adapters. Revision and reassignment belong to the governed lifecycle;
adjudication remains a separately approved future capability rather than a
claim about current v0.1 behavior.

## Long-Term Intelligent Orchestration Direction

After the governed v0.1 lifecycle is proven, a future orchestration adapter may
propose task dependencies and contributor matches for work distributed across
humans and AI agents. Existing Workstream services would still authorize and
version tasks and assignments, bind artifacts and checks, record Reviews and
revisions, and create contribution facts under the canonical lifecycle.

This is a research hypothesis, not current or planned runtime behavior.
Execution remains in a source application such as Garden or another external
host. See the [Product Brief](product_brief.md#future-research-hypothesis-accountable-orchestration)
for the canonical hypothesis. Current availability is governed only by
[Current v0.1 Status](roadmap_status.md).

## Product Boundary

Workstream determines what governed work occurred and whether the resulting
contribution fact can be trusted. Payments, points, tokens, staking, slashing,
reputation, eligibility, reporting, datasets, and model-training systems may
consume that fact and apply project-specific consequences. They do not create,
revise, or control Workstream identity, authorization, submission, review, or
contribution truth.

That boundary allows one Workstream core to support centralized, sovereign,
federated, and permissionless applications without coupling lifecycle truth to
any one application's business or economic model.

Flow Identity is the current v0.1 external authentication provider. It is an
adapter boundary, not the definition or ownership boundary of Workstream.
Workstream is not an execution workspace and is not blockchain-first.

## Core Invariants

Different projects speak different domain languages, but Workstream preserves
the same governing invariants across them:

- project guides and policies are versioned before they govern work
- tasks, assignments, submissions, checks, and Reviews retain their exact
  project and actor lineage
- invalid submission packets stop before trusted Submission creation
- findings, responses, resolutions, Reviews, and contribution facts append to
  history rather than rewriting it
- `FinalAcceptance` is the sole source of an accepted submitter contribution
- conditional compensation follows contribution truth and never controls it

These invariants turn project-specific operating knowledge into reusable
infrastructure without narrowing the complete v0.1 lifecycle defined above.

## Current v0.1 State

The [capability ledger](roadmap_status.md) owns delivered, exposed and deployed
status. The first complete backend journey uses an approved guide and locked
policies, task creation and claim, ZIP intake, external POST evaluation and a
governed outcome. Claim starts work immediately. Required PRE failure prevents
Submission creation. Required POST success under `human_review_required=false`
reaches shared authorized FinalAcceptance, the submitter ContributionRecord and
applicable frozen-policy awards atomically. No Review or reviewer contribution
is fabricated. The default-true branch retains `review_pending`; its live human
review/revision workflow remains unfinished.

Contributor-correctable POST failures have a bounded checker-remediation path;
infrastructure failures use distinct recovery. External fulfillment, runtime
reputation and the live human-review writer are separate remaining work.

Guide originals and examples belong to the project. Setup assistance is optional:
it proposes source-cited PRE/POST specifications, while a human selects exact
project image bindings at approval. Runtime registration is not proof of deployed
sandbox readiness, and local tests are not hosted journey evidence. Consult the
ledger's release gates and linked drill records for the actual proof boundary.

## Authorization Baseline

Workstream verifies externally issued Flow authentication tokens and owns its
product authorization. Token role claims, email, display name, skills,
reputation, and typed workflow profiles are not product authority. Canonical
authority comes from local actor identity links, administrative grants,
exact-project contributor grants, registered permissions, resource/lifecycle
guards, revocation, and append-only evidence.

All public API documentation uses `/api/v1`. Imported reference specifications
are immutable archival inputs. ADR 0012 and the canonical authorization service
specification control authorization; ADR 0016 and the canonical contribution
and compensation specification control contribution recognition, award
eligibility, and fulfillment boundaries. Older chunk specifications remain
implementation history until their owning migrations replace the runtime.

## Terminal Client

The independent [Go CLI](../cli/README.md) follows the public REST contracts.
Its user guide owns installation, login, commands, pagination, uploads, outcome
inspection and contribution exports. [CLI release qualification](engineering/cli-release.md)
owns the binary release procedure. The CLI does not bypass product authorization
or turn an earned award into proof of external payment.

## Repository-Native Human-Agent SDLC

Workstream uses a Repository-Native Human-Agent SDLC. Plans, tests, review, and
durable decisions live with the code so humans and agents can collaborate
without depending on chat history. GitHub permissions and branch protection
remain the repository authority; process notes never create a second permission
system.

```text
Intent
-> Plan
-> Bounded Change
-> Evidence
-> Review
-> PR
-> Human Merge
```

Codex-discoverable skills live in `.agents/skills/`. Codex custom reviewer
agents live in `.codex/agents/`. The smallest useful durable engineering
records live in `.commitrail/`; start with its `README.md` and `INDEX.md`.

This engineering loop is separate from Workstream product state. It governs how
the repository is changed; it does not define runtime task or review records.
Independent initiatives and branches may proceed concurrently. Start with
[CONTRIBUTING.md](../CONTRIBUTING.md) before proposing repository work.

## Implementation owners

Use the current owner contracts for implementation details rather than treating
this conceptual reference as a second capability ledger:

- [Project guides and optional setup proposals](spec_project_guides.md)
- [Task intake, claim and locked context](spec_task_assignment.md)
- [External PRE/POST checks and runtime evidence](architecture_checker_framework.md)
- [Acceptance and human-review boundaries](spec_review_lifecycle.md)
- [Contribution records and conditional awards](spec_contribution_compensation.md)
- [Model access and budget operations](operations_checker_models.md)
- [Operator recovery](operations_operator_workflow.md)
- [Delivered capabilities and remaining gates](roadmap_status.md)

## v0.1 Success Standard

Workstream v0.1 succeeds only when the complete lifecycle defined in
[End-To-End Lifecycle](#end-to-end-lifecycle) runs as a real internal task cycle with real people. The cycle must
prevent invalid work from reaching review, preserve exact evidence and
authority, support revision without rewriting history, produce trusted
contribution facts, and carry payable contributions through conditional award
and fulfillment. Runtime reputation projection is not part of this release
bar.

## Operating Standard

Workstream is built as durable operational infrastructure. Project rules live
in versioned guides and policies rather than chat memory. Each active attempt
keeps its locked governing context. The task's locked project RevisionPolicy
requires an explicit nonnegative revision cap: N=2 permits submissions 0, 1 and
2; N=0 permits only the initial Submission. A final-attempt failure immediately
records rejection, closes its assignment and returns the task to ready, without
another preparation or deadline. Timeout also returns the task to ready. Anyone
eligible may claim a new assignment at round 0, including a previous claimant;
there is no contributor-count limit or repeated-failure hold.

When a revision remains, contributor-fixable failure freezes the complete
next-attempt context and change summary. Revision reruns intake and acknowledges
that exact preparation. A setup-blocked rebase publishes durable PM attention
and pauses the PostgreSQL-time allowance; repair resumes only its remaining
time. Repair of a running context preserves its deadline. Only committed
immutable resubmission ends a running opportunity. Task state, terminal evidence,
authorization, audit and outbox intent commit atomically. Original Submissions
and findings remain immutable; scans and retries recover after downtime.
Infrastructure/provider/budget failures never spend a contributor attempt.
Checker remediation creates no Review or reviewer contribution. Live human
Review decision composition remains #554 work under the same intended policy.
Timeout and exhaustion create no contribution, award or fulfillment facts.

Lifecycle state is a ledger, not a loose label. Submitted artifacts remain
immutable and hash-bound to their checks; findings, responses, resolutions,
Reviews, and contribution facts remain attributable and auditable. Lessons
become governed guide, policy, template, or checker changes before they affect
future work. Project activation, task screening, submission quality, review,
contribution recognition, and conditional fulfillment remain distinct gates
even though they form one end-to-end v0.1 lifecycle.
