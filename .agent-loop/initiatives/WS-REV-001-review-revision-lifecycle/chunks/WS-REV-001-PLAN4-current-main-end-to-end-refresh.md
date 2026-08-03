# Chunk Contract: WS-REV-001-PLAN4 — Current-Main End-To-End Refresh

## Parent initiative

`WS-REV-001` — Review And Revision Lifecycle.

## Goal

Replace stale historical sequencing with one complete current-main plan after
merged AUTH 02D, preserving REV ownership and explicitly gating ART/TASK/
CHECKER/CON integration.

## Why this chunk exists

Earlier plans corrected boundary crossings but predate immutable policy lineage,
policy mutation, complete REV catalogue/principals, and typed authorization
contracts. They also intermingle historical and live status.

## Risk class

L1 architecture and cross-subsystem lifecycle planning.

## SLA

No expedited SLA.

## Allowed files

```text
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
docs/spec_review_lifecycle.md (only if a normative contradiction is found)
```

## Not allowed changes

- Backend/runtime code, migrations, tests, CI, routes, catalogue, availability,
  dependencies, roadmap, ART, AUTH, TASK, CHECKER, or CON owner plans.
- Editing immutable archival reference specifications.
- Starting a runtime child.

## Acceptance criteria

- The intent, discovery, plan, map, status, risks, decisions, and conformance
  matrix describe one consistent path from `allow_review` through contribution.
- AUTH 02D is the stable authority boundary and no lifecycle action is described
  as active.
- Queue persistence can proceed independently; any REV schema or behavior with
  a foreign invariant remains gated on the exact merged owner contract (for
  example CON-03B before ReviewLease and ART membership identifiers before the
  packet manifest).
- Existing Submission is preserved; no uploaded review evidence or adjudication
  enters v0.1.
- Every Review creates a reviewer contribution through CON; accept alone creates
  FinalAcceptance and the submitter contribution.
- Only 03A1 is proposed for the first later implementation start. Future chunks
  remain skeletons until current-main refresh.

## Verification commands

```text
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA/test, senior engineering, docs,
reuse/dedup, test-delta, and CI integrity.

## Human review focus

REV start/end boundary, independent core work, ART/CON intersections, immutable
history, contribution cardinality, and chunk size/order.

## Stop conditions

Planning only. Await human approval before starting 03A1.
