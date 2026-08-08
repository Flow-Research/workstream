# Plan: WS-POL-002 - Post-Submit Checker Foundation

## Current authority

Merged chunks 01-03 established useful compiler, persistence, approval, and
visibility foundations. Their standalone `PostSubmitCheckerPolicyDerivationAgent`
call graph is historical and must not be invoked by any remaining work.

`WS-POL-003` now owns all future guide inference. One logical/provider guide
compilation produces the post-submit proposal together with sufficiency,
artifact, and pre-submit proposals. The stored post-submit component is
deterministically validated, projected, approved, locked, and executed without
another model call.

## Remaining work

`WS-POL-002-04` may harden locked runtime execution only after reconciliation
with `WS-POL-003-06B/07`, ART-06A/06B, and XINT-06B. It consumes the exact
unified compilation/component/catalogue/compiled-plan lineage through the sole
checker service port. It cannot infer policy, select an out-of-plan checker, or
expose a standalone/caller-selectable trigger.

`WS-POL-002-05` is proof-only. It proves automatic Submission-bound execution,
default-plus-project compiled checker coverage, deterministic retry, safe
visibility, review/revision handoff, and zero post-submit model calls.

## Ownership

- POL owns deterministic policy validation/projection and checker orchestration.
- ART owns immutable input/output bytes, materialization, and bindings.
- AUTH/XINT own exact service/human authorization activation and evidence.
- REV owns human review and revision lifecycle decisions.

No remaining WS-POL-002 chunk starts automatically.
