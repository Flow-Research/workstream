# Intent: WS-CI-004 Review Evidence Integrity

## Problem being solved

Internal reviewer results can currently say `PASS` without proving which exact
revision, merge base, unchanged implementation, prior findings, or raw evidence
the reviewer inspected. A later push can make an earlier pass stale without a
mandatory replay. Review prose can also claim that a command passed when the
exact-head check did not.

## Why this work matters

Workstream is critical governed-contribution infrastructure. Authorization,
artifact, review, contribution, and compensation boundaries cannot depend on
review records whose subject or proof is ambiguous. A false pass can be more
dangerous than no review because it gives humans confidence that was not earned.

## Current behavior

- GitHub Actions binds repository checks to the pull-request head.
- GitHub permissions, branch protection, and human approval control merge.
- Reviewer agents have useful specialties but only generic shared instructions.
- Optional review templates can record a SHA, but the reviewer workflow does not
  require or validate it.
- Head changes do not automatically invalidate affected internal reviewer passes.
- Prior findings have no stable replay/closure identity.

## Target behavior

Every applicable internal reviewer result identifies one exact review subject,
proves what was inspected, distinguishes executed evidence from claims, replays
prior findings, traces affected ownership and boundaries, and becomes stale when
the relevant pull-request delta changes. All final reviewer results and hosted
checks must refer to the same final head before merge readiness is reported.

## Design chosen

Use a small shared Reviewer Evidence Protocol plus deterministic Git target
inspection. Specialty agents keep their focused review responsibilities while
the shared protocol owns revision identity, evidence provenance, prior-finding
replay, final-head freshness, and common output fields.

Adopt the protocol in measured stages without a committed or hosted receipt
gate. Internal receipts remain user-private, out-of-tree session evidence;
GitHub checks/reviews and merged Git history remain durable evidence.

## Alternatives considered

- **Restore the deleted internal-review gate:** rejected. Its exact-SHA core was
  sound, but it became coupled to signed starts, leases, merge intents, loop
  memory, recovery certificates, chunk-scope authorization, and a 7,870-line
  mixed regression suite.
- **Prompt-only reminders in nine agent files:** rejected. Universal rules would
  drift and remain difficult to test.
- **Require a committed exact-head attestation immediately:** rejected. Evidence
  created after review changes the commit it attempts to attest to and recreates
  evidence-only commit ceremony unless a carefully bounded subject model is
  proven first.
- **Treat all head changes as requiring all nine reviews:** rejected. Review must
  be conservative but proportionate; unaffected specialties need not repeat
  ceremonial work.
- **Let CI or AI approval authorize merge:** rejected. Review is evidence, not
  repository authority.

## Boundaries preserved

- No Workstream product lifecycle, API, schema, migration, authorization grant,
  payment, artifact, review, or contribution behavior changes.
- No signed-start, loop-memory, merge-intent, lease, recovery, or post-merge
  automation returns.
- No automated merge or replacement of GitHub branch protection.
- No universal reviewer fanout for low-risk work.
- No external service, secret, token, or new hosted infrastructure is required.

## Expected risks

- Reintroducing the self-blocking process complexity removed in PR #207.
- Creating review ceremony without improving defect detection.
- Allowing a reviewer to attest only to the changed lines while missing relevant
  unchanged consumers, owners, or debt ledgers.
- Treating a commit SHA as sufficient proof without evidence provenance.
- Letting mutable PR text silently substitute for reviewer execution.
- Over-invalidating unaffected reviews after documentation-only evidence updates.

## What must not change

The simple loop remains:

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> PR -> Human Merge
```

GitHub remains contribution and merge authority. Internal agents, CodeRabbit,
and CI remain independent sensors. Historical review evidence never becomes an
active-work queue or implementation authorization source.

## How this will be proven

- Deterministic Git fixtures for head/base/merge-base identity, dirty state, and
  head-change invalidation.
- Reviewer contract tests proving required provenance and prior-finding replay.
- Negative tests for stale passes, false evidence claims, missing commands,
  unknown findings, private-import/ownership omissions, and final-head mismatch.
- Replay of the five defects missed during PR #338 planning review.
- Out-of-tree create-once receipt fixtures and exact-target convergence tests.

## Human decisions required

- Approve this plan and each implementation chunk separately.
- Continue to own every merge and every accepted remaining risk.
