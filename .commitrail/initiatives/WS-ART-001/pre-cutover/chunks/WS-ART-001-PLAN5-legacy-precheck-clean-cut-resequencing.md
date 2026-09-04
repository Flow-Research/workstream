# Chunk Contract: WS-ART-001-PLAN5 — Legacy Precheck Clean-Cut Resequencing

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Planning complete; PR pending

## Goal

Correct PLAN4 sequencing so Workstream removes the complete legacy contributor
precheck path only when verified admission consumption becomes the sole live
Submission path.

## Why This Chunk Exists

Implementation discovery found that live `TaskService.create_submission` still
uses the same checker service as the standalone caller-owned precheck route.
Deleting that service before the admission-backed replacement exists would
either permit unchecked legacy Submission creation, break the live path, or
require a forbidden compatibility seam. The clean cut therefore belongs to
05B, after 04B1-04C2, AUTH activation, and 05A provide the replacement.

## Allowed Files

- ART initiative PLAN, CHUNK_MAP, STATUS, RISKS, DECISIONS, REVIEW_LOG, and chunk
  contracts;
- canonical checker, artifact-policy, data-model, authorization, and roadmap
  documentation where sequencing is stated;
- planning review evidence and PR trust bundle;
- CI metadata only when needed to preserve existing documentation gates.

## Not Allowed Changes

- application code, migrations, runtime schemas, routes, services, or tests;
- AUTH action availability or grants;
- partial removal or replacement of the legacy precheck;
- catalogue, execution, admission, Submission, checker, review, or contribution
  behavior.

## Acceptance Criteria

- 04A4 is explicitly superseded and authorizes no runtime implementation;
- 04B1 is the next ART implementation chunk;
- 05B owns removal of the standalone route, OpenAPI schemas, public service
  entry point, internal legacy Submission guard, and caller-owned package facts;
- the legacy path remains frozen and receives no new features or adapters;
- no unchecked Submission path, alias, redirect, fallback, private
  compatibility service, or second checker registry is introduced;
- canonical sequencing and risk records agree;
- required L1 planning reviewers approve the correction.

## Verification Commands

```bash
git diff --check
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
```

## Required Reviewers

Architecture, security/auth, product/ops, senior engineering, QA/test, docs,
reuse/dedup, CI integrity, and test delta.

## Human Review Focus

- Does this produce one complete deletion rather than a partial cleanup?
- Is legacy safety preserved until verified admission is authoritative?
- Is 04B1 unblocked without adding runtime scope to this planning PR?

## Stop Conditions

Stop if the replacement path is assumed live before 04C2, 05A, and required
AUTH activation merge, or if any runtime behavior is needed to make the plan
internally consistent.
