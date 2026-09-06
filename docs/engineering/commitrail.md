# Commitrail operating guide

Workstream uses Commitrail: a repository-native method for turning human intent
into bounded, evidenced, reviewed pull requests while preserving enough context
to govern the work later.

The method is:

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> PR -> Human Merge
```

## Principles

1. Git, current code, tests, canonical specifications, and the repository host
   remain authoritative for behavior and integration.
2. Planning explains work; it never grants permission to contribute.
3. Use the smallest record that controls the actual risk.
4. One bounded implementation change maps to one PR.
5. Claims require evidence capable of detecting the excluded failure.
6. Review is routed by impact, not by a fixed reviewer count.
7. Review binds to an exact committed candidate; rerun only what a later push
   affects.
8. GitHub owns transient CI, review, approval, and merge state.
9. Humans retain product judgment, material-risk acceptance, and merge
   authority.
10. Historical evidence is not current truth; Git history is the archive.

## Proportional records

A small obvious correction may use its PR description. A meaningful one-PR
change uses one combined change record. Multi-PR work adds one concise
initiative overview. Extra assurance or decision records are exceptional and
must earn their maintenance cost.

The combined record owns durable intent, design, scope, acceptance criteria, and
remaining risks. Its PR links those sections and owns exact-head command/review
results and transient GitHub state. The overview links the current change record
before historical material. Do not put a record's own candidate SHA inside it;
keep freshness in the PR/session evidence to avoid self-invalidating commits.

## Review layers

Every meaningful change receives implementation and evidence-adequacy review.
Specialty review runs only for affected security, authorization, payment,
architecture, CI, documentation, product-operations, reuse, or test-delta
surfaces. Protection-delta review is mandatory when tests, workflows,
evaluators, coverage, thresholds, or reviewer machinery change.

The lead uses Astra and delegates scoped work to Sol high through repository
configuration. Each reviewer loads the shared protocol plus its specialty, not
copied instructions in three locations. The lead supplies a frozen clean target,
bounded prior findings, and shared check artifacts. Reviewers independently
inspect their impact cone and run additional falsification probes as needed.
The lead collects a complete wave, batches repairs, and replays affected tracks;
a formerly passing review is not fresh if the repair invalidated its evidence.

Full backend/coverage checks run in hosted CI. A failed command or reviewer
session requires diagnosis/recovery, not an arbitrary permission gate or a false
completion claim. Scope or missing product intent may still require the human.

## Evidence and privacy

Evidence identifies the claim, command or inspection, result, execution
custody, discriminating probe where needed, and remaining uncertainty. Never
commit credentials, access tokens, raw private chat, unnecessary personal
data, or private session receipts.

## Status

This is Workstream's operating copy derived from Commitrail v0.1. It is not the
canonical public Commitrail publication. Public release status requires
assigned publication terms, a canonical location, and evaluation evidence.
