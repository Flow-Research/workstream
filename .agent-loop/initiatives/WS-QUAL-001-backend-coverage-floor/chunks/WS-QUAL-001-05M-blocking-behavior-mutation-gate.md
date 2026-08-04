# Chunk Contract: WS-QUAL-001-05M — Blocking Behavior-Mutation Gate

## Parent initiative

`WS-QUAL-001` — Behavior And Mutation Assurance

## Goal

After accepted pilot evidence and separate human approval, make complete
mutation outcomes blocking for eligible changed production logic and explicit
test-only behavior claims.

## Why this chunk exists

The pilot measures feasibility. This separate chunk converts only calibrated,
deterministic evidence into contributor protection.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/CHUNK_MAP.md`
- Required input: accepted exact hosted `WS-QUAL-001-04M` pilot evidence.

## Risk class

L1 — blocking CI/test policy.

## SLA

P2.

## Allowed files

Exact files must be refreshed from the merged 04M implementation before start.
Expected ownership is limited to its mutation policy/tests, independent
workflow, backend testing operations guide, Agent Gate invariant, and QUAL
initiative evidence. Test-only inputs use only schema-v1
`.ci/behavior-claims/<chunk-id>.json` files validated by the merged policy.
The refreshed allowed list must explicitly include `CONTRIBUTING.md`,
`.ci/behavior-claims/README.md`, the policy-owned schema, and a copyable example
so external contributors see the exact blocking workflow before it is enabled.

## Not allowed

```text
start without accepted 04M evidence and explicit human instruction
global mutation percentage
change to 78-percent global or protected 90-percent coverage floors
free-form exemptions, source mutation pragmas, silent timeout/error success
full-repository mutation on ordinary PRs
production behavior, migration, or dependency changes
```

## Acceptance criteria

- [ ] Eligibility and evidence grammar are unchanged from accepted pilot proof
      unless a separately reviewed correction is explicit.
- [ ] Every eligible surviving mutant blocks by default.
- [ ] Any allowed classification is narrow, typed, evidence-bound, and tested;
      missing, stale, broad, or free-form classifications fail closed.
- [ ] Timeout, suspicious, and error outcomes never count as killed.
- [ ] Test-only behavior/coverage claims cannot bypass target mutation.
- [ ] `CONTRIBUTING.md` and the canonical claim README/schema/example explain
      when a claim is required, the permitted typed non-behavioral cases, local
      verification, evidence interpretation, and repair of surviving mutants.
- [ ] Non-eligible maintenance/docs/generated changes do not run irrelevant
      mutants.
- [ ] Hosted p95 and critical-path impact satisfy the accepted pilot bound.
- [ ] Backend, Agent Gates, 78-percent global floor, and protected 90-percent
      floors remain authoritative and green.

## Verification commands

Refresh exact commands from merged 04M; at minimum run mutation-policy unit and
integration tests, strong/weak seeded behavior proof, Ruff, Agent Gates,
Markdown/stale checks, full hosted Backend, and exact blocking-workflow proof.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

- Does the gate block weak behavior proof without blocking unrelated work?
- Can classifications or test selection be used as an escape hatch?
- Does the gate remain practical for external contributors?

## Stop conditions

Stop on missing pilot evidence, unreviewed policy change, unacceptable hosted
latency/noise, coverage/Backend weakening, or need for broad exemptions.
