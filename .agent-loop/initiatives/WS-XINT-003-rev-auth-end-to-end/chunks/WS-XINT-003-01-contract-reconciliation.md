# Chunk Contract: WS-XINT-003-01 — REV-AUTH Contract Reconciliation

## Status

Implemented as a docs-only reconciliation. Awaiting human review/merge.
Activates no action.

## Goal

Reconcile the complete review/revision authorization catalogue and settle the
REV-03P/AUTH-12D2 policy ownership collision before runtime implementation.

## Risk class

L1 authorization and product-policy architecture.

## Allowed files

```text
.agent-loop/initiatives/WS-XINT-003-rev-auth-end-to-end/**
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/{PLAN,CHUNK_MAP,STATUS,DECISIONS,RISKS}.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-12D2-guide-bound-policy-mutations.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/ACTIVATION_CUSTODY.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/{PLAN,CHUNK_MAP,STATUS,DECISIONS,RISKS}.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-03P-review-revision-policy-persistence.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/CHUNK_MAP.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-05D-human-review-revision.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-07-review-artifact-activation.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-07A-reviewer-artifact-activation.md
.agent-loop/initiatives/WS-XINT-002-art-auth-end-to-end/chunks/WS-XINT-002-07B-response-artifact-extension.md
docs/operations_authorization_service.md
docs/spec_authorization_service.md
docs/spec_artifact_storage_service.md
docs/spec_review_lifecycle.md
docs/operations_roles_permissions.md
```

## Not allowed

```text
backend application code
Alembic migrations
action activation or service provisioning
review/revision product behavior
compatibility aliases or duplicate policy paths
```

## Acceptance criteria

- One canonical table enumerates every human, Project Manager, Operator, and
  fixed-service action, permission, principal, resource family, surface owner,
  hidden-feature dependency, and activation wave.
- Every fixed-service row additionally names the exact service identity, static
  action membership, server-derived mode/scope, forbidden principal classes,
  and required audit/provenance facts. Class-level “fixed service” labels do
  not substitute for exact identities.
- The table classifies every action as registered planned, missing-to-register,
  externally owned by XINT-002, or out of scope; canonical AUTH and role docs
  are updated or explicitly confirmed.
- The 19 registered planned REV rows move from historical placeholder AUTH-REV
  activation groups to exact XINT-003 waves in the planning custody table
  without any permission, availability, catalogue `ActionOwner`, or runtime
  change in 01. Each refreshed activation chunk updates its runtime owner
  evidence together with activation. XINT-002-owned ART materialization/binding
  and shared submission-artifact rows remain with XINT-002.
- REV-03P owns immutable/versioned policy semantics and AUTH-12D2 owns mutation
  authorization; both contracts name one persistence and writer path. The
  reconciliation names the surviving API/service/repository symbols, existing
  mutators to retire, draft-versus-active immutability boundary, and exact
  denial proof required from chunk 02. Chunk 01 implements none of that runtime
  path.
- Historical counts and signed-start/process-gate language are corrected where
  they could misdirect current implementation.
- XINT-002 artifact/revision boundaries are referenced by exact chunk IDs and
  are not duplicated. XINT-002-07 becomes a split record: 07A activates packet
  materialization and the one evidence-binding ActionId for reviewer-finding
  slots while hard-denying response-slot shapes; 07B changes no availability
  and extends only the response-slot evaluator after the exact human revision
  obligation/preparation exists.
- The XINT-002-07 split is ART-only: packet materialization and evidence binding
  only. XINT-002-05D remains owner of shared human-review submission
  preparation/create activation. Human REV action activation remains in the
  XINT-003 waves.
- Every later activation remains planned and fail closed.

## Verification commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security/auth, product/ops, QA/test, senior engineering, docs,
and reuse/dedup.

## Human review focus

Confirm complete action coverage, one policy owner/writer path, correct
cross-initiative ownership, and absence of premature activation.

## Stop condition

Merge the contract reconciliation and stop. Do not begin policy runtime work.
