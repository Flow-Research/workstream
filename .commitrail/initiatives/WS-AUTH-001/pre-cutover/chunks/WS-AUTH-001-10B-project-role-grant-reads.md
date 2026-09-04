# Chunk Contract: WS-AUTH-001-10B — Project Role Grant Read Planning Parent

## Parent initiative

`WS-AUTH-001` — Workstream Authorization Service

## Goal

Split durable read abuse control from privacy-safe project-role disclosure.

## Why this chunk exists

Required L1 review proved there is no existing read-rate scope and that current
403/404 translation cannot provide concealment without preserving centralized
denial-evidence handling. The user approved separate 10B1 and 10B2 children.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`
- Decision: D33

## Risk class

L1 authorization and privacy planning.

## SLA

P1

## Allowed files

```text
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-10B.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
application, migration, workflow, test, or public documentation changes
action activation, API routes, or runtime behavior
```

## Acceptance criteria

- D33 records the accepted split and repository-backed rationale.
- 10B1 and 10B2 have exact PR-sized contracts, dependency order, proof, and stop conditions.
- 10B1 is the only declared successor; 10B2 follows 10B1 and 10C follows 10B2.
- No application action changes availability.

## Verification commands

```bash
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Human review focus

Review that the split preserves durable abuse control, audited concealment, and
the exact three-read boundary without runtime edits.

## Stop conditions

Stop if either child mixes rate-control persistence with public disclosure, if
10B2 can start before 10B1, or if this parent requires a runtime edit.
