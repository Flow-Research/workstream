# Product Principles

## 1. Workstream Governs Contribution Truth

Workstream defines a shared protocol for governed work and provides its
software implementation. The protocol specifies valid actions and records;
the implementation enforces them. The distinction and remaining formalization
work are described in [Protocol And Implementation](protocol-and-implementation.md).

Workstream does not need to own the source application or execution workspace.
Humans and agents can work in terminals, editors, notebooks, external
platforms, or local repositories. Workstream governs the rules, artifact
lineage, verification, review, and durable contribution outcome.

Workstream owns:

- project guide
- task status
- submission record
- checker output
- review decision
- revision history
- immutable contribution records
- compensation awards and fulfillment state
- reputation projection when separately implemented

Source applications and downstream consequence systems integrate around this
truth; they do not create or rewrite it. Workstream is source-agnostic, but
v0.1 stays manual-first. External origin adapters and automated routing stay
out until the internal loop works. Flow Identity remains the current external
authentication adapter rather than the product boundary.

## 2. Project Rules Are First-Class

Every project has its own guide, quality bar, submission artifact policy,
checker policy, review policy, revision policy, and independently published
contribution policy.

Workstream applies its non-bypassable PRE default separately from the project's
explicitly approved external PRE and POST image selections. Optional setup
assistance proposes source-cited requirements; it never selects images.

The platform does not rely on memory or chat messages to enforce rules. If a
rule matters, it belongs in the project guide, submission artifact policy,
checker policy, review policy, revision policy, contribution policy, or task
template.

Prior submitted attempts remain tied to their stamped context. Human-review
revision preparation compares the complete prior context with all applicable
current guide and policy selectors: exact components keep, every changed valid
component rebases together, and unsafe context blocks. The contributor sees the
frozen result and the reviewer consumes the context stamped on the leased
Submission without rebasing.

## 3. Same Lifecycle, Different Domain Language

Projects may differ by domain, language, task format, or review style. The lifecycle remains stable:

```text
Guide -> Task -> Pre-Submission Intake -> Submission -> Post-Submission Evaluation
-> Policy-Governed Review/Revision or Automatic FinalAcceptance
-> Contribution -> Conditional Compensation Award/Fulfillment
-> deferred reputation projection
```

## 4. Automated Checks Protect Human Review

Pre-submission intake protects package fitness before Submission creation.
Post-submission evaluation assesses the immutable work against its locked
requirements and protects reviewer time. Neither stage decides final acceptance.
These stages are not synonyms for deterministic execution: a supported model
evaluator is distinct from deterministic policy compilation and intake rules.

Required failures and warnings follow the locked policy. Checker findings are
evidence for routing, not checker-owned acceptance.

Blocking pre-submit checker failures block submission creation before a submission version exists.

## 5. Human Judgment Remains Critical

Automated checks catch structural, formatting, packaging, and basic quality problems. Human reviewers judge whether the work actually satisfies the task and project guide.

Human review is required by default. If the locked ReviewPolicy explicitly
disables it, passing required checks reaches shared authorized FinalAcceptance
and a submitter contribution, with no fabricated Review or reviewer contribution.
Public human-review execution remains governed by the capability ledger.

## 5A. Human Owners Are Accountable For Agent-Assisted Work

Workstream allows humans to use agents and external tools, but the human contributor or owner is accountable for the submitted packet.

The first version enforces accountability through assignment ownership,
contributor attestation, immutable Submission versions, Reviews, findings,
responses, resolutions, and evidence. Reputation events and a built-in
owner-agent execution workspace are later work.

## 6. Revision Is A State, Not A Failure

Needs revision is a normal lifecycle state. The system preserves immutable
feedback, requires one response per unresolved blocking finding and one later
resolution, and makes resubmission auditable.

Revision must also preserve context. Contributors and reviewers need to know which guide and policy versions governed the prior attempt and which versions govern the next attempt.

## 7. Evidence Beats Claims

Every acceptance is backed by evidence. Evidence can include checker logs, test results, screenshots, file hashes, review notes, or before/after diffs.

## 8. Future Reputation Must Be Earned

When separately implemented, reputation comes from outcomes:

- accepted work
- revision rate
- rejection rate
- review quality
- task difficulty
- skill area
- dispute outcomes

Reputation is not a manual label.

## 9. Compensation Must Be Traceable

Even when fulfillment is manual, Workstream must track:

- contribution and beneficiary
- frozen `ContributionPolicyVersion` and `ContributionAwardDefinition`
- instrument, unit, and exact quantity
- delivery and fulfillment status
- immutable fulfillment receipt and external reference

Every valid human Review creates a reviewer contribution. Accept also creates
FinalAcceptance, and only that fact creates a submitter contribution. Frozen contribution award rules create immutable
awards only for payable contributions; explicit unpaid rules create no award.
Fulfillment receipts and status projections track delivery separately.

## 10. Prove The Governed Core First

The first version proves governed contribution infrastructure through one
internal lifecycle. Marketplace experiences, source adapters, external client
surfaces, blockchain settlement, and a public reputation network come after the
core loop works. They remain consumers or adapters, not alternate sources of
Workstream lifecycle truth.

## 11. Intelligence Proposes; Governed Authority Decides

Future orchestration intelligence may propose outcome decomposition, candidate
matches, exception classifications, evidence gaps, and recovery plans. It does
not create task authority, contribution truth, adverse reputation, nonpayment,
misconduct findings, or appeal decisions.

Hard constraints remain deterministic and versioned. Material decisions remain
attributable to an explicitly authorized actor under the applicable future
policy. Every recommendation must preserve its
inputs, evidence, uncertainty, alternatives, model or rule version, and
accountable approver.

## 12. Dependencies Stay Bounded

Complex outcomes may produce versioned task dependencies and, only when pilot
evidence requires it, a directed acyclic graph. Every child task inherits parent
legal, privacy, safety, budget, tool, data, and acceptance constraints. Every
task has an authorized owner; every multi-task outcome has an integration owner
in the external execution host.

Unrestricted recursive delegation, invisible subagent spawning, and dependency
growth that creates unauthorized work or exceeds an applicable approved budget
are prohibited. Released dependency changes are prospective and never rewrite
frozen assignments or evidence.

## 13. Matching Uses Plural Evidence, Not A Global Score

Future matching first applies eligibility and conflict rules, then produces an
explainable shortlist from task-specific capability evidence, recency,
uncertainty, availability, cost, collaboration needs, and concentration.
Capability, authority, reputation, availability, price, and conflicts remain
separate.

Participants may decline work without reputation penalty. Qualified newcomers
must have bounded opportunities to earn evidence. Workstream does not turn
historical reputation into a permanent labour caste.

## 14. Automation Earns And Can Lose Authority

New planning and routing behavior begins in shadow mode against a human-curated
baseline. It expands only after repeated healthy outcomes and contracts when
quality, fairness, safety, privacy, concentration, appeals, or economics cross
declared limits.

Canonical records remain available during an automation stop. Operations fall
back to manual queueing and authorized review instead of failing closed around
an unavailable or unsafe model.

## 15. Protect Private Source Material

Project guides and examples must not copy confidential client materials or
private platform data without authorization. Use owned or authorized source
material; evidence retention does not grant new permission to disclose it.
