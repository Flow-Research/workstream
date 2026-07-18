# Chunk Contract: FN-ART-002-05 Maintenance Cutover Proof

Initiative: `FN-ART-002` | Risk: L1 | Status: Deferred

## Goal

Copy every retained old-namespace object, verify exact bytes, record Flow Node
replicas, and switch one configured adapter during an explicit maintenance
barrier with a tested pre-activation rollback stop condition.

## Allowed Files

- bounded migration command/job and replica-record transitions
- deployment barrier and rollback configuration
- authorized Operator progress/status API additions if required
- audit, metrics, real proof, and operations runbook
- migration, fencing, rollback, and real-provider tests

## Not Allowed

- dual writes, live fallback, or lazy read-through migration;
- physical deletion of the prior provider copy;
- product schema/lifecycle or checker/review behavior changes;
- public traffic while provider selection is heterogeneous;
- unverified replica promotion.

## Acceptance Criteria

- inventory includes every retained replica/object in the old storage namespace,
  including completed but unbound content, and is stable under the maintenance
  barrier;
- every object is copied then fully read/hash/size verified.
- unresolved, missing, or mismatched objects block cutover.
- migration executions are idempotent and stale invocations are fenced.
- rollback restores the prior adapter before public traffic activation.
- zero retained old-namespace replicas remain unmigrated before cutover;
- successful cutover removes prior adapter construction from the active
  composition root; no fallback remains.
- evidence is API/command-visible, bounded, and redacted.
- changed subsystem coverage is at least 90 percent and repository coverage
  does not decrease.

## Verification

```bash
<pre-cutover inventory and dry-run command>
<isolated migration plus full verification command>
<rollback rehearsal command>
<post-cutover real API artifact lifecycle drill>
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

Is the cutover complete, reversible before activation, and free of hidden
dual-runtime behavior?
