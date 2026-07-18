# Product Principles

## 1. Workstream Is The Control Plane

Workstream does not need to own the execution workspace. Humans and agents can work in terminals, editors, notebooks, external platforms, or local repositories.

Workstream owns:

- project guide
- task status
- submission record
- checker output
- review decision
- revision history
- compensation awards and fulfillment state
- reputation projection when separately implemented

Workstream is source-agnostic, but v0.1 stays manual-first. External origin adapters and automated routing stay out until the internal loop works.

## 2. Project Rules Are First-Class

Every project has its own guide, quality bar, submission artifact policy,
checker policy, review policy, revision policy, and independently published
contribution policy.

Workstream combines the approved submission artifact policy with non-bypassable default artifact rules and generates the pre-submit checker policy.

The platform does not rely on memory or chat messages to enforce rules. If a
rule matters, it belongs in the project guide, submission artifact policy,
checker policy, review policy, revision policy, contribution policy, or task
template.

Prior submitted attempts remain tied to their stamped context. Human-review
revision preparation compares the prior Project Guide identity/activation
sequence with the currently active pair: exact match keeps, any different valid
pair rebases forward or backward, and unsafe context blocks. The contributor
sees the frozen result and the reviewer consumes the context stamped on the
leased Submission without rebasing.

## 3. Same Lifecycle, Different Domain Language

Projects may differ by domain, language, task format, or review style. The lifecycle remains stable:

```text
Guide -> Task -> Submission -> Checker -> Review -> Revision/FinalAcceptance
-> Contribution -> Conditional Compensation Award/Fulfillment
-> deferred reputation projection
```

## 4. Automated Checks Protect Human Review

Human reviewers do not spend time on submissions that fail basic gates.

Critical- and high-severity checker failures block review. Medium and low severity issues are visible to reviewers and can influence decisions.

Blocking pre-submit checker failures block submission creation before a submission version exists.

## 5. Human Judgment Remains Critical

Automated checks catch structural, formatting, packaging, and basic quality problems. Human reviewers judge whether the work actually satisfies the task and project guide.

The system improves reviewer judgment. It does not pretend to replace it.

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

## 10. Build Internal First

The first version is internal task evaluation and contribution infrastructure. The marketplace, source adapters, external clients, blockchain settlement, and public reputation network come after the core loop works.
