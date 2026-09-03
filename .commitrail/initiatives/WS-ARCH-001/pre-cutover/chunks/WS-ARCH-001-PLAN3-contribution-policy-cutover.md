# Chunk Contract: WS-ARCH-001-PLAN3 — Contribution Policy Cutover Sequence

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Replace the stale CON-05A start instruction with one dependency-ordered,
owner-separated path from persisted ContributionPolicy data to guide binding,
task-attempt inheritance, and removal of the retired guide-bound economic path.

## Why this chunk exists

PLAN2 established the correct lifecycle but its first implementation dependency
is not executable. CON-05A currently assumes unavailable CON policy behavior,
missing AUTH registration/activation, a cross-owner schema mutation, and
historical-row classification that no longer applies after the v0.1 baseline
consolidation.

## Approved plan reference

- INTENT: `../INTENT.md`
- PLAN: `../PLAN.md`
- CHUNK_MAP: `../CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/**
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/{CHUNK_MAP,STATUS}.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{CHUNK_MAP,STATUS,DISCOVERY,RISKS,CONFORMANCE_MATRIX,RUNTIME_VERIFICATION}.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/{AUTHORIZATION_HANDOFF,JOINT_RELEASE_HANDOFF}.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-{04A,04B,05A,05B}*.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-06-review-lease-contribution-policy-freeze.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/chunks/WS-CON-001-08A-outbound-compensation-delivery.md
docs/roadmap_status.md
```

## Not allowed

```text
backend application, migration, test, workflow, or dependency changes
action activation or product behavior
editing merged chunk outcomes as if they were current executable contracts
compatibility aliases, historical backfills, guessed row conversion
```

## Acceptance criteria

- [ ] One linear sequence separates AUTH registration, hidden owner behavior,
  AUTH activation, CON validation, PROJECT guide binding, TASK attempt lineage,
  and legacy removal.
- [ ] No chunk imports another product module's models/repositories; owner
  composition uses public typed ports.
- [ ] Adapter-binding authority is separated from future fulfillment callback
  authority.
- [ ] CON validation owns no ProjectGuide, Task, Assignment, Submission, claim,
  or review write.
- [ ] PROJECTS alone binds `ProjectGuide.contribution_policy_version_id`.
- [ ] TASKS alone locks/copies/stamps the Task, TaskAssignment, and Submission
  policy-version lineage.
- [ ] ReviewLease continues to copy only the immutable Submission stamp.
- [ ] The consolidated v0.1 baseline is treated as the current schema source;
  no deployed-history compatibility or data backfill is invented.
- [ ] Every implementation child remains proposed/non-executable until a
  current-main contract supplies exact files, schema head, tests, and reviewers.

## Verification commands

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref "$(git merge-base HEAD origin/main)"
git diff --check
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Confirm the dependency order, authority split, absence of claim-time selection,
and clean v0.1 legacy removal before approving any runtime child.

## Stop conditions

Stop if an implementation child must combine AUTH and product behavior, if a
product owner must write another module's aggregate, or if compatibility work
is proposed without an actual deployed-data requirement.

## Merge state

- Outcome on merge: `planned`
