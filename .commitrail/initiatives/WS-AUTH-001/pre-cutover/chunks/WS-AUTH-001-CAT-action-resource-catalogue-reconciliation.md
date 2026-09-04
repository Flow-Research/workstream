# Chunk Contract: WS-AUTH-001-CAT - Action And Resource Catalogue Reconciliation

## Status

Merged through PR #117 as `4c5d4fc` on 2026-07-14 after required internal
reviews, Backend, Agent Gates, CodeRabbit, and explicit human approval passed.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Map the proposed action/resource catalogue against the adopted repository and
carry forward only the safe, domain-aligned design rules into the canonical
authorization specification and owning future chunk contracts.

## Risk class

L1 specification and authorization planning.

## Allowed files

```text
docs/spec_authorization_service.md
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/DECISIONS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-CAT-action-resource-catalogue-reconciliation.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-06-canonical-actor-profile.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-07-authorization-kernel.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-08-bootstrap-admin-grants.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-09-actor-state-service-actors.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-10-project-role-grants.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-11-project-read-cutover.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-12-project-mutation-cutover.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-13-task-assignment-cutover.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-14-submission-checker-cutover.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-15-worker-authority-removal.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-16-evidence-live-proof.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/reviews/WS-AUTH-001-CAT-internal-review-evidence.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/reviews/WS-AUTH-001-CAT-pr-trust-bundle.md
```

The local `canonical_auth.md` input is review material only and is not an
allowed committed file.

## Not allowed

```text
backend runtime, schema, migration, workflow, or CI changes
permission additions, removals, aliases, or renames
the archival `/v1` prefix or a new API alias
new artifact, review, contribution, or compensation aggregates
claiming the reviewed input has independent normative precedence
starting AUTH-05B runtime implementation in this chunk
```

## Acceptance criteria

- The 52 approved permission identifiers remain unchanged. This docs chunk does
  not change AUTH-05A's current 49-identifier typed/PostgreSQL audit base; it
  assigns additive parity for the three approved recovery identifiers to their
  AUTH-13/14 activation chunks.
- `/api/v1` remains the only canonical public API namespace.
- The canonical spec adopts a closed typed action/resource registry, existing
  parent targets for create operations, feature-owned resource composition,
  fixed service authority, pre-count collection filtering, and route/command
  conformance without redefining feature lifecycle behavior.
- Resource contexts use closed typed variants; guard inputs are declared and
  unknown, missing, extra, or mistyped facts fail closed.
- Reserved planned action metadata contains stable `ActionId`, approved
  `PermissionId`, owner, and availability; it cannot authorize or predefine a
  foreign-domain target. Active definitions own one exact target and guard set;
  multiple actions may map to one approved broad permission.
- AUTH-07 assigns `ActionId` to decisions and bounded logs/metrics and plans
  exact typed/PostgreSQL authority-evidence parity. Historical rows remain
  readable; new action-based allowed/denied events require a registered ID.
- AUTH-07 owns registry types and its own definitions, AUTH-07 through AUTH-15
  own incremental surface activation and manifest-delta proof, and AUTH-16 owns
  aggregate generated manifest proof.
- WS-REV, WS-CON, and artifact-storage specifications retain their resource and
  transition ownership.
- AUTH-07 through AUTH-16 retain at least 90 percent authorization-subsystem
  coverage; the repository-wide 78 percent baseline remains unchanged.
- AUTH-05A retains migration `0018`, AUTH-05B solely owns `0019`, and merged
  AUTH schema chunks through AUTH-09B use `0020` through `0024`. Future
  migration custody follows the current AUTH plan and trusted main.
- The rejected root proposal is absent from the working tree and patch.

## Verification commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth and privacy
- product/ops
- architecture
- docs

## Human review focus

Review which proposed rules were adopted or rejected, preservation of the
current permission/audit contract, staged ownership, and the absence of runtime
or cross-domain invention.

## Stop conditions

Stop if adopting a rule requires a permission/migration change, invents a
domain resource, or changes AUTH-05B runtime scope. Such work requires its own
approved specification and chunk.
