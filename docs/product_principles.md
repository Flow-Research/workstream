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
- payment ledger
- reputation ledger

Workstream is source-agnostic, but v0.1 stays manual-first. External origin adapters and automated routing stay out until the internal loop works.

## 2. Project Rules Are First-Class

Every project has its own guide, quality bar, submission artifact policy, checker policy, review policy, revision policy, and payment policy.

Workstream combines the approved submission artifact policy with non-bypassable default artifact rules and generates the pre-submit checker policy.

The platform does not rely on memory or chat messages to enforce rules. If a rule matters, it belongs in the project guide, submission artifact policy, checker policy, review policy, revision policy, payment policy, or task template.

When a guide or policy changes while work is already in progress, prior submitted attempts remain tied to their locked context. If the task returns for revision, revision policy decides whether the next attempt rebases to the latest active context, and the worker must see what changed.

## 3. Same Lifecycle, Different Domain Language

Projects may differ by domain, language, task format, or review style. The lifecycle remains stable:

```text
Guide -> Task -> Submission -> Checker -> Review -> Revision/Acceptance -> Payment -> Reputation
```

## 4. Automated Checks Protect Human Review

Human reviewers do not spend time on submissions that fail basic gates.

High-severity checker failures block review. Medium and low severity issues are visible to reviewers and can influence decisions.

Blocking pre-submit checker failures block submission creation before a submission version exists.

## 5. Human Judgment Remains Critical

Automated checks catch structural, formatting, packaging, and basic quality problems. Human reviewers judge whether the work actually satisfies the task and project guide.

The system improves reviewer judgment. It does not pretend to replace it.

## 5A. Human Owners Are Accountable For Agent-Assisted Work

Workstream allows humans to use agents and external tools, but the human worker or owner is accountable for the submitted packet.

The first version enforces accountability through assignment ownership, worker attestation, immutable submission versions, evidence, review decisions, and reputation events. A built-in owner-agent execution workspace is later work.

## 6. Revision Is A State, Not A Failure

Needs revision is a normal lifecycle state. The system must preserve feedback, require closure, and make resubmission easy to audit.

Revision must also preserve context. Workers and reviewers need to know which guide and policy versions governed the prior attempt and which versions govern the next attempt.

## 7. Evidence Beats Claims

Every acceptance is backed by evidence. Evidence can include checker logs, test results, screenshots, file hashes, review notes, or before/after diffs.

## 8. Reputation Must Be Earned

Reputation comes from outcomes:

- accepted work
- revision rate
- rejection rate
- review quality
- task difficulty
- skill area
- dispute outcomes

Reputation is not a manual label.

## 9. Payment Must Be Traceable

Even when payment is manual, Workstream must track:

- base amount
- accepted amount
- pending payout
- paid amount
- payment status
- payout date

Accepted work also creates a contribution record. The contribution record certifies accepted work; the payment ledger records money movement.

## 10. Build Internal First

The first version is internal task evaluation and contribution infrastructure. The marketplace, source adapters, external clients, blockchain settlement, and public reputation network come after the core loop works.
