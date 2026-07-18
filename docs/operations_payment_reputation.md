# Compensation And Reputation

## Status

Existing compensation records retain their owning implementation status. The
Review-, FinalAcceptance-, and revision-sourced behavior below is planned and
unavailable until its owning REV/CON chunks, exact AUTH activation, and REV-13
joint release complete. Reputation behavior is deferred entirely.

## Compensation Principle

External fulfillment can be manual in the first version, but Workstream records
the authorized award and immutable fulfillment result with the same discipline
as automated settlement.

Every valid recorded human Review creates a reviewer `completed_review`
contribution through the mandatory CON reviewer operation. After that operation,
the `Review(accept)` branch creates REV-owned FinalAcceptance, then sets the Task
to `accepted` and the TaskAssignment to `completed`, then runs the CON submitter
operation. FinalAcceptance is the sole source of that submitter
`accepted_submission` contribution. Compensation is evaluated independently
for each record from its frozen policy version; an explicit unpaid rule creates
no award. Awards, fulfillment receipts, and projections attach to contributions
and never replace them. Reputation events are deferred.

## Compensation Status Projection

```text
delivery_status: pending_delivery | acknowledged_by_adapter
fulfillment_status: pending | failed | fulfilled
```

Compensation status is not task lifecycle status. A Review can be complete and a
task can be `ACCEPTED` while an award remains pending or failed. Explicitly
unpaid contributions have no award and therefore no compensation projection.

## Compensation Award And Fulfillment

An immutable CompensationAward records:

- contribution record id
- project id
- beneficiary actor id
- frozen contribution policy version and award definition
- adapter binding
- instrument: `money | project_points`
- unit code and exact decimal quantity

An immutable CompensationFulfillmentReceipt records:

- award, project, and adapter-binding ids
- external event id
- `fulfilled | failed`
- external reference and exact fulfilled quantity for success
- failure code for failure
- reported, received, and fulfillment timestamps

## Contribution Award Rules

Default:

- DRAFT through REVIEW_PENDING: no contribution or award is created
- a valid human `needs_revision`, `accept`, or `reject` decision creates one
  reviewer `completed_review`; the ReviewLease-frozen
  `ContributionPolicyVersion` decides whether it creates an award
- `accept` creates one FinalAcceptance and exactly one submitter
  `accepted_submission` from it; the TaskAssignment-frozen
  `ContributionPolicyVersion` decides whether it creates an award
- `needs_revision` and `reject` create no FinalAcceptance, submitter
  contribution, or submitter award
- fulfillment is recorded only by an authenticated adapter callback bound to the
  award's frozen adapter binding
- a fulfilled award requires an immutable receipt, exact quantity, and external
  reference
- canonical Review, FinalAcceptance, contributions, and eligible awards commit
  once; external fulfillment begins only after commit through the outbox

Review decisions, FinalAcceptance, contribution recognition, award creation,
and fulfillment remain separate facts. FinalAcceptance has no manual API/action
and v0.1 has no adjudication or reopen path.

`ACCEPTED` means the work met the guide. `fulfilled` means the bound adapter
reported completion with an immutable receipt and external reference.

The dashboard must always show:

- payable awards pending delivery
- adapter-acknowledged awards pending fulfillment
- failed awards
- fulfilled awards by instrument and unit

## Deferred Reputation Principle

Reputation policy, events, scoring, and projections are not implemented by the
v0.1 review lifecycle. The review decision transaction writes no reputation
side effect. The remaining sections are future product guidance only.

When separately implemented, reputation is not a badge. It is an outcome ledger.

It updates from:

- contribution records
- submitter `accepted_submission` contributions
- reviewer `completed_review` contributions
- needs revision
- rejection
- compensation fulfillment completion
- reviewer decision quality
- task difficulty
- skill area

## Contributor Reputation

Track:

- accepted count
- needs revision count
- rejected count
- acceptance rate
- revision rate
- average turnaround
- skill-specific quality
- compensation fulfillment reliability

Possible future contributor events:

| Event | Default Delta | Notes |
| --- | ---: | --- |
| accepted | +3 | Weight by task difficulty and project trust. |
| needs_revision | -1 | Do not over-penalize if revision closes cleanly. |
| rejected | -3 | Higher penalty for policy/originality issues. |
| late_submission | -1 | Only if deadline policy was explicit. |
| revision_closed | +1 | Rewards learning and recovery. |

## Reviewer Reputation

Track:

- completed reviews
- decision distribution
- non-mutating offline quality-analysis findings
- unclear feedback reports
- average turnaround
- offline sampled-quality signals

Possible future reviewer events:

| Event | Default Delta | Notes |
| --- | ---: | --- |
| clear_review | +2 | Structured findings or clear acceptance evidence. |
| unclear_feedback | -2 | Finding lacks issue, evidence, or required fix. |
| sampled_quality_concern | -3 | Offline evidence flags review quality without changing the product decision. |
| missed_prior_finding | -2 | Resubmission accepted with unresolved prior issue. |

These are future reputation inputs only. Sampling creates no product Review,
decision, queue, lease, or adjudication state and cannot mutate existing review
history.

## Skill Tags

Reputation is tagged by skill so a contributor can be strong in one domain and weak in another.

Examples:

- coding
- rubric-review
- data-qa
- technical-writing
- research
- security
- database
- frontend
- long-context

## External Settlement Compatibility

Fulfillment adapters can attach opaque references such as:

- bank transfer reference
- stablecoin transaction hash
- Stripe transfer id
- ERC-8183 job id
- x402 payment id

The first version does not depend on these.

## Reconciliation Rules

Finance Authority reconciles daily:

- payable contributions without their expected award or fulfillment projection
- pending award delivery older than agreed SLA
- adapter acknowledgement without a fulfillment receipt
- fulfilled receipts missing external references
- fulfilled quantity mismatches

Any mismatch becomes an operations issue, not a silent spreadsheet correction.
