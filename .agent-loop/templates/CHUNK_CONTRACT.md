# Chunk Contract: <CHUNK_ID> — <TITLE>

## Parent initiative

<INITIATIVE_ID> — <INITIATIVE_NAME>

## Goal

What this chunk must accomplish.

## Why this chunk exists

How this chunk supports the larger initiative.

## Approved plan reference

- INTENT: `<path>`
- PLAN: `<path>`
- CHUNK_MAP: `<path>`

## Risk class

L0 / L1 / L2 / L3 / L4

## SLA

P0 / P1 / P2 / P3

## Allowed files

```text
<paths>
```

## Not allowed

```text
<explicit boundaries>
```

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Verification commands

```bash
<test/lint/typecheck commands>
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Tell the human exactly where to spend attention.

## Stop conditions

Stop and escalate if:

- scope must expand beyond allowed files
- architecture direction changes
- auth/payment/policy/data boundary changes beyond contract
- CI/test weakening is required to pass
- same blocker remains after 2 repair attempts
- secrets/production data are needed
