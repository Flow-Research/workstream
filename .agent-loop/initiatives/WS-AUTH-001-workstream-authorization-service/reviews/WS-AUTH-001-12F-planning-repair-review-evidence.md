# WS-AUTH-001-12F Planning Repair Review Evidence

## Result

PASS after repair. No application code or action availability changed.

## Why implementation stopped

The inherited combined 12F contract failed architecture, security, QA, and
product/operations preimplementation review on 2026-08-05. It did not close
human/service authority, external-agent, replay, transaction, migration,
approval-chain, or 12G ownership boundaries.

## Repair

- Converted 12F into a planning-only parent with zero activation.
- Split execution into sequential L1 chunks 12F1 through 12F4.
- Froze explicit file scope, exact PREP/final matching, UUID replay,
  transaction ownership, migration custody, concurrency/fault proof, and
  non-zero 90-percent coverage commands.
- Made automatic derivation fixed `workstream.project.setup` service-only;
  12F3 removes the public inline derive endpoint.
- Preserved Project Manager manual drafting only as explicit manual provenance;
  manual paths cannot edit or impersonate agent output.
- Bound sufficiency clearance and the non-bypassable Workstream default policy,
  immutable catalogue, compiler, bundle, startup configuration, and effective
  plan facts.
- Limited 12F4's post-submit write to atomic upstream supersession/invalidation;
  12G retains all derivation, compilation, correction, approval, and execution.
- Rebased onto current main with migration `0056`; no REV/CI files are changed.
- Added one exact-line stale-vocabulary exemption for the unavoidable technical
  path `backend/app/workers/project_setup.py`; no narrative wording is exempt.
- External review clarified the mutable replay reservation versus append-only
  decision stream, the cross-chunk total lock order, merged prerequisites,
  current legacy-route timing, and complete provenance dependency chain.

## Final reviewer results

| Track | Result |
|---|---|
| Architecture | PASS |
| Security/auth | PASS |
| Product/operations | PASS |
| QA/test | PASS WITH LOW RISKS |
| Senior engineering | PASS |
| CI integrity | PASS |
| Docs | PASS after stale-wording repair |
| Reuse/dedup | PASS WITH LOW RISKS |
| Test delta | PASS WITH LOW RISKS |

Low-risk implementation guidance is captured in 12F1: reuse existing PREP,
replay, UUID-dependency, and advisory-fence conventions rather than creating a
second protocol.

Implementation remains forbidden until this planning repair is human-merged
and a child is explicitly started. The immediate executable successor is 12F1.
