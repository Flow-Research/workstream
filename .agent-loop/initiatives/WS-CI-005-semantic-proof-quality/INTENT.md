# Intent: WS-CI-005 Semantic Proof Quality

## Problem being solved

Exact-head receipts, named tests, traceability rows, and adversarial prose can
still produce a false `PASS` when the proof does not discriminate the claimed
behavior. PR #349 passed internal review before later probes found duplicated
quantity rules, partial owner-fact validation, malformed-input leakage, mocked
rollback, simulated handle semantics, nullable SQL guard bypass, incomplete
composite ownership, and a cross-project test that was only a missing-row test.

## Why this work matters

Workstream is governed contribution infrastructure. A confident but vacuous
review can allow an authorization, tenant-isolation, lifecycle, compensation,
or audit defect to become durable. Repeated full review cycles also exhaust
maintainers and contributors. Review must become sharper, not larger.

## Current behavior

- WS-CI-004 binds reviews to exact clean Git targets and requires atomic
  traceability, impact-cone inspection, adversarial probes, and residual-escape
  analysis.
- Nine specialty reviewers have structural contract and blind-evaluation tests.
- Proof rows name tests and execution custody, but do not use a closed proof-
  strength vocabulary.
- A mock can be cited for a database, transaction, isolation, or prepared-handle
  claim even when it cannot exercise that behavior.
- Escaped defects are documented per PR but are not promoted into reusable
  reviewer failure classes.

## Target behavior

Every material review claim declares the weakest acceptable proof custody.
Reviewers attempt a concrete test-of-the-test, reject proofs that cannot observe
the claimed failure, reuse canonical owner rules, and apply shared database and
tenant-isolation probes where relevant. Escaped defects become compact reusable
evaluation fixtures so the same blind spot is not rediscovered manually.

## Design chosen

Extend the existing reviewer protocol and evaluator with:

1. a closed proof-strength vocabulary;
2. machine-validated claim-to-proof compatibility;
3. shared escaped-failure patterns derived from real PRs;
4. strict-fake, database-integrity, tenant-isolation, and canonical-rule reuse
   obligations;
5. specialty-specific blind evaluations proving the requirements change
   reviewer behavior.

## Alternatives considered

- Add more generic reviewers: rejected because overlapping prompts reproduce
  the same blind spots and increase latency.
- Require PostgreSQL and full fanout for every PR: rejected as disproportionate.
- Depend on CodeRabbit to catch internal misses: rejected because it is an
  independent external sensor, can rate-limit or skip, and does not own repo
  architecture.
- Add a new contribution permission or merge gate: rejected. GitHub remains the
  only repository authority.

## Boundaries preserved

- No Workstream product, API, authorization, payment, artifact, review, task,
  contribution, compensation, or database behavior changes.
- No new hosted service, secret, model provider, merge automation, signed start,
  loop memory, or post-merge reconciliation.
- Reviewer routing remains proportionate; low-risk work does not receive
  ceremonial fanout.
- CodeRabbit, CI, internal review, and human review remain independent sensors.

## Expected risks

- Turning useful heuristics into rigid bureaucracy.
- Misclassifying proof strength and forcing infrastructure where pure proof is
  sufficient.
- Adding token-heavy duplicated instructions to every skill and agent.
- Creating fixtures that leak their expected answer to reviewers.
- Mistaking a proof taxonomy for proof that a reviewer reasoned correctly.

## What must not change

The engineering loop remains:

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> PR -> Human Merge
```

One implementation chunk remains one PR. Planning artifacts explain work; they
do not authorize contribution or merge.

## How this will be proven

- Validator mutation tests remove each proof-quality requirement and fail.
- Raw blind fixtures replay the missed defects from PRs #338, #346, and #349.
- Tests prove mock proof cannot satisfy database, transaction, concurrency, or
  real-isolation custody.
- Tests prove each specialty catches its owned failure while valid controls
  remain clear.
- Final-head reviewer replay validates the initiative against its own rules.

## Human decisions required

- Approve this plan before implementation.
- Approve each implementation PR and any explicitly accepted Medium risk.
