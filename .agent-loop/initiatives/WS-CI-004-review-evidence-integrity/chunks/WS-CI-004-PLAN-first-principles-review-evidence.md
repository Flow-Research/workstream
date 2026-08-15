# Chunk Contract: WS-CI-004-PLAN — First-Principles Review Evidence Design

## Merge state

- Outcome on merge: `planned`

## Parent initiative

WS-CI-004 — Review Evidence Integrity

## Goal

Record the current failure analysis, external principles, threat model, design,
and independently reviewable implementation sequencing guidance without
changing active reviewer or CI behavior.

## Risk class

L1 — engineering-loop trust infrastructure planning.

## SLA

P1.

## Allowed files

```text
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/**
```

## Not allowed

```text
reviewer-agent or skill behavior changes
script or workflow changes
blocking CI gates
product/runtime/API/schema/migration changes
signed starts, leases, merge intents, loop memory, recovery, or post-merge automation
automated merge or contribution authorization
```

## Acceptance criteria

- [ ] Discovery identifies the exact reviewer, skill, template, policy, script,
      and workflow gaps that allowed stale or unsupported passes.
- [ ] PR #338's five missed defects are replayed as concrete design inputs.
- [ ] All nine custom reviewer agents and matching skills have distinct owned
      responsibilities and forward-evaluation requirements.
- [ ] Historical exact-SHA evidence mechanisms are separated from the removed
      circular control system.
- [ ] External principles are drawn from authoritative SLSA, GitHub, NIST, and
      OpenSSF sources and adapted rather than copied ceremonially.
- [ ] The plan separates review subject, evidence, freshness, and human authority.
- [ ] Delivery guidance sequences protocol/tooling, reviewer adoption, and local
      session convergence without pre-creating active implementation contracts.
- [ ] No active reviewer, skill, script, workflow, or product behavior changes.

## Verification commands

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
git diff --check
```

## Required reviewers

Architecture, CI integrity, security, QA/test, senior engineering, documentation,
reuse/dedup, and product/operations.

## Human review focus

Confirm that the plan strengthens evidence without recreating contribution
authorization, self-referential evidence commits, universal reviewer ceremony,
or the removed loop-memory system.

## Stop conditions

Stop if planning requires runtime enforcement, a secret, an external service,
product changes, or a blocking gate before measured evidence.
