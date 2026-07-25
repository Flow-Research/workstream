# PR Trust Bundle: WS-ART-001-PLAN2

## Intent

Replace the rejected combined ART-03/future upload design with a bounded plan
that proves the same contributor ZIP is safely checked, immutably stored,
reviewed, accepted, recorded, and delivered.

## Design

```text
one outer ZIP
-> bounded process-local scratch
-> safe outer-tree inspection and canonical manifest
-> exact/semantic unchanged rejection
-> mandatory platform and locked-guide checks
-> one existing ArtifactStore admission
-> complete read-back verification
-> one capacity-charged ready SubmissionBundleAdmission
-> fresh human and fixed-service authorization
-> one immutable Submission binding
```

Nested archives remain opaque in v0.1. Failed or unchecked bytes never enter
object storage. Existing admission, put-attempt, verification, receipt, scanner,
and recovery abstractions are reused.

## Scope

Planning, successor contracts, canonical artifact documentation/templates, and
the exact agent-gate assertions required by the new phase map. No runtime code,
migration, provider, workflow, or authorization availability changes.

Exactly one merge intent is added:
`.agent-loop/merge-intents/WS-ART-001-PLAN2.json`, naming only same-initiative
successor `WS-ART-001-03A` with a separate explicit start.

## Evidence

- diff, stale-contract, markdown-link, and 100 agent-gate tests pass;
- all nine required reviewer tracks pass after repair;
- exact reviewed candidate `25bae979` is based on trusted main `f3ece23e`;
- the stale-authorization documentation gate and its technical-module
  regression repair pass without reopening deprecated product-role vocabulary;
- detailed findings and resolutions are recorded in
  `WS-ART-001-PLAN2-internal-review-evidence.md`.

## Human Review Focus

- Confirm one outer ZIP and no candidate retention are the intended v0.1 UX.
- Confirm process loss before durable intent requiring reupload is acceptable.
- Confirm AUTH must retire planned session actions and register/activate the
  exact bundle action before ART-04A/05 can proceed.
- Confirm ART owns bytes/identity/access capabilities while REV, CON, and
  delivery retain their lifecycle decisions.
- Confirm abandoned ready admissions remain quota-bounded and capacity-charged
  in v0.1, with no expiry, deletion, release, or retention worker.
- Confirm executable intent is semantic manifest data, not permission
  preservation or authority to execute contributor content.
- Confirm authority is freshly revalidated at durable put intent and again at
  atomic Submission consumption through AUTH-owned prepared capabilities.

## Gate

This planning merge starts no implementation. `WS-ART-001-03A` requires a
fresh signed explicit start after human merge approval and automated merge
memory reconciliation.

## External Review

CodeRabbit reported seven valid planning/specification inconsistencies. All
were addressed in the smallest planning-only repair, alongside the two
governance failures exposed by hosted CI. The detailed disposition is recorded
in `WS-ART-001-PLAN2-external-review-response.md`.
