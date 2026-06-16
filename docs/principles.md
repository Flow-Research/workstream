# Workstream Principles

## 1. Workstream Owns The Lifecycle

Operators and agents may do the actual work outside Workstream. Workstream owns the source of truth:

- project rules
- task status
- submission history
- checker results
- review decisions
- revision replay
- contribution records
- payment records
- reputation records

The first product is task evaluation and contribution infrastructure, not an execution IDE.

## 2. Project Guides And Policies Are Law

Each project has a human-facing guide and approved machine-readable policies.

The guide explains:

- task types
- base amount
- quality bar
- submission format
- common rejection reasons

The policies enforce:

- submission artifact policy
- generated pre-submit checker policy
- post-submit checker policy
- review policy
- revision policy
- payment policy

If a rule matters, it belongs in the guide, submission artifact policy, checker policy, review policy, revision policy, payment policy, or task template.

Out-of-band guidance is not enforceable until it is moved into those contracts or into a checker that is governed by those contracts.

## 3. Automated Checks Protect Human Time

Human reviewers do not spend time discovering basic package failures. Workstream checkers catch structural issues before review:

- invalid task schema
- missing evidence
- malformed submission packet
- missing required files
- forbidden generated artifacts
- impossible status transitions
- known low-quality signatures

High-severity failures block review.

Blocking pre-submit failures block submission creation before a submission version exists.

## 4. Human Review Provides Judgment

Automated checks can enforce structure. Human reviewers decide whether the work is actually good, useful, original, and aligned with the project guide.

Reviewers must produce actionable findings:

- what failed
- why it matters
- what must change
- severity
- evidence

## 5. Needs Revision Is A First-Class State

Needs revision is not a side note. It is a formal loop:

```text
NEEDS_REVISION -> IN_PROGRESS -> SUBMITTED -> AUTO_CHECKING -> REVIEW_PENDING
```

The system must preserve original feedback, fix notes, evidence, and closure.

The system must also preserve guide and policy context. Prior submissions keep their locked context; revision policy decides whether the next attempt rebases to the latest active context before the worker resumes.

## 6. Payment Follows Acceptance

The first version uses contribution records and a manual payment ledger. Blockchain settlement comes later.

Accepted work creates a contribution record first. Payment and reputation updates attach to that accepted contribution.

Payment records track:

- base amount
- accepted amount
- pending payout
- paid amount
- payment status
- payment date
- payment reference

## 7. Reputation Must Be Earned From Outcomes

Reputation is not a profile badge. It is computed from work history:

- acceptance rate
- revision rate
- rejection rate
- review accuracy
- dispute rate
- average turnaround
- task difficulty
- project weight

## 8. Do Not Copy Private Client Data

Workstream transfers operational ideas and workflow patterns. It must not copy confidential platform data, private task content, client materials, or proprietary evaluation details.

The product is built from our own schemas, rules, examples, and pilot tasks.

## 9. Source-Agnostic Does Not Mean Adapter-First

Workstream accepts work from different sources over time, but v0.1 supports only manual, markdown, and CSV intake.

External origins, webhook drop notifications, automated routing, agent identity, and on-chain settlement are later adapters.
