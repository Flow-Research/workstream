# Chunk Contract: WS-ARCH-001-PLAN4 — Incremental Debt Retirement

## Parent initiative

WS-ARCH-001 — Modular Monolith Boundaries

## Goal

Make technical-debt retirement measurable and delivery-coupled without turning
unrelated legacy debt into a prerequisite for v0.1 capability work.

## Why this chunk exists

The architecture already requires an incremental strangler, but contributors
need an exact rule for what a bounded PR must repair, what it must merely avoid
growing, and what belongs to later stranded-debt closure. Without that split,
the rule can either permit debt indefinitely or expand every feature into an
unreviewable cleanup.

## Current-main baseline

- General protected private-edge ledger: 115 exact edges.
- WS-AUTH-003 import ledger: 63 inbound and 36 outbound AUTH private edges.
- WS-AUTH-003 structural ledger: 89 findings across production and test files,
  functions, and helpers.
- WS-QUAL-002 behavior ownership: foundation exists; subsystem population is
  incomplete.

The general and AUTH import ledgers have different authorities and overlapping
views. Their counts are reported separately and must not be summed.

## Approved plan reference

- INTENT: `../INTENT.md`
- PLAN: `../PLAN.md`
- CHUNK_MAP: `../CHUNK_MAP.md`
- DECISIONS: `../DECISIONS.md#d18-debt-retirement-follows-delivery-without-blocking-unrelated-work`

## Risk class

L1

## Allowed files

```text
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-ARCH-001-modular-monolith-boundaries/**
```

## Not allowed

```text
backend application, migration, test, workflow, or dependency changes
product behavior, authority, schema, lifecycle, or public API changes
a new cleanup initiative or a competing debt ledger
fixed per-PR debt quotas or repository-wide cleanup prerequisites
mutation or coverage gate changes
```

## Acceptance criteria

- [ ] Unrelated frozen debt is explicitly non-blocking for bounded v0.1 work.
- [ ] New private edges, structural debt, duplicated behavior ownership,
  compatibility paths, and weakened tests remain prohibited.
- [ ] A PR directly exercising indexed debt must identify and remove its exact
  relevant entries in the same capability boundary.
- [ ] Unsafe adjacent debt may be deferred only with an exact record, no
  growth, and a later owner-sized closure boundary. The durable initiative
  record names the ledger edge or structural-finding identifier, owner, reason
  removal exceeds the chunk, and intended closure contract.
- [ ] General, AUTH, structural, and behavior-ownership measurements retain
  their existing authoritative owners and are never combined misleadingly.
- [ ] Existing 78 percent global and 90 percent changed-subsystem coverage
  floors remain unchanged; mutation remains outside the current merge gates.
- [ ] WS-ARCH-001-07 remains non-executable until refreshed against then-current
  `main` and split into reviewable stranded-debt contracts.
- [ ] No runtime or CI behavior changes.

## Verification commands

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref "$(git merge-base HEAD origin/main)"
git diff --check
```

## Required reviewers

- [ ] architecture
- [ ] senior engineering
- [ ] docs

## Human review focus

Confirm that the policy prevents new debt and retires debt encountered by
delivery without making unrelated historical debt a feature prerequisite.

## Stop conditions

Stop if the plan changes product behavior, weakens a test or CI gate, creates a
second debt authority, or makes repository-wide cleanup a delivery gate.

## Merge state

- Outcome on merge: `planned`
- Implementation starts only through an approved capability contract; this
  planning PR does not start WS-ARCH-001-07.
