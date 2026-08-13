# Decisions: WS-CON-001 Contribution And Compensation

## D1 — Canonical authority

Code, migrations, tests, accepted ADRs, canonical subsystem specifications,
`docs/roadmap_status.md`, and merged history establish current behavior.
Imported references, old status snapshots, signed-loop records, and open PRs
are historical or in-progress evidence, not proof that behavior is live.

## D2 — Contribution sources

Every committed human Review creates exactly one reviewer `completed_review`.
Only REV-owned FinalAcceptance creates one submitter `accepted_submission`.
Needs-revision and reject never create submitter contributions.

## D3 — Award policy

ContributionPolicyVersion is the sole award-policy authority. Explicit unpaid
rules create no award; compensated rules create only immutable configured
money/project-points awards. No fallback economic model exists.

## D4 — Transaction ownership

REV owns review orchestration and the single commit. CON receives the caller
AsyncSession, stages and flushes exact rows, and never commits or repairs a
partial review afterward.

## D5 — One upstream policy lock

CON validates the one same-project ContributionPolicyVersion at guide
activation. TASK locks that guide-bound version before claimability and copies
it to TaskAssignment; Submission stamps the attempt value, and REV copies that
immutable Submission value to ReviewLease. Neither task claim nor review claim
performs policy selection. The lease stores a non-null
CON policy-version FK, but that dependency transfers no lease authority to CON.

## D6 — Artifact boundary

CON copies stable accepted Submission/binding/hash lineage supplied by REV.
Core contribution creation has no ART repository, capability, provider, bytes,
scratch, or credential dependency.

## D7 — Corrected implementation order

CON-03A/03B proceed before the dispatcher because they are independent and
03B unblocks REV lease persistence. CON-02C proceeds before REV-04B without
waiting for dispatch. CON-02B moves later, before projection/fulfillment
consumers, after exact AUTH registration.

## D8 — Authorization custody

AUTH owns every CON-related permission/action mapping, principal, context,
prepared capability, evaluator, evidence constraint, and activation. CON may
publish feature manifests and consume typed decisions; it may not add a second
authorization path.

## D9 — Dispatcher isolation

`outbox.dispatch` permits generic claim/invoke/finalize mechanics only. A
handler must present its own approved identity/action/context. Dispatch never
confers feature or provider authority.

## D10 — Legacy migration

Retired economic rows require a deterministic human-approved classification.
Ambiguity fails migration. Planning never reserves Alembic revision numbers.

## D11 — Evidence projection

Contribution evidence is optional preservation for future reputation
projection. It cannot gate core PostgreSQL truth, reads, release, or
fulfillment. Runtime reputation scoring remains deferred.

## D12 — Planning stop

PLAN4 changes planning records only. The recommended next implementation is
03A, and it begins only after human approval from then-current main.

## D13 — Human revision rebases complete current context

Publication or activation never silently changes an active assignment,
Submission, or ReviewLease. Accept and reject finish under the versions frozen
for that attempt. After a human `needs_revision`, revision preparation compares
the complete applicable current Project Guide/source activation,
submission-artifact policy, pre-submit and post-submit checker policies, review
policy, revision policy, task-template/task-execution context, and
ContributionPolicyVersion. It atomically keeps unchanged components or rebases
all changed components on the continuing Task and TaskAssignment for the next
submission attempt; no prior Submission, ReviewLease, Review, contribution, or
award is rewritten.
The completed reviewer contribution retains its lease-frozen policy; the
revised submitter attempt uses the rebased TaskAssignment policy; and the next
ReviewLease copies the version stamped on that Submission. Prior
Submissions, Reviews, ContributionRecords, and CompensationAwards remain
immutable. Incomplete or inconsistent current context blocks rather than
publishing a mixed version set. The Review, reviewer contribution/award, task
and assignment effects, initial preparation or blocked outcome, audit/outbox,
and contributor-visible state commit once or roll back together.
