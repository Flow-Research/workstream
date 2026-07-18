# Chunk Contract: <CHUNK_ID> — <TITLE>

Keep the first line in this exact form. The internal review evidence gate binds
evidence to the complete `<CHUNK_ID>` from this canonical heading and fails
closed when a changed contract has no readable canonical heading.

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

Every listed reviewer must end with one exact result value:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

Baseline:

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops

Conditional:

- [ ] architecture, when the chunk touches architecture, `.agent-loop/`,
  `.agents/`, `.codex/`, backend application code, or migrations
- [ ] CI integrity, when the chunk touches workflows, scripts, package files, or
  test/build configuration
- [ ] docs, when the chunk touches Markdown, docs, README, AGENTS, or loop docs
- [ ] reuse/dedup, when the chunk touches skills, agents, backend app code, or
  scripts
- [ ] test delta, when the chunk touches tests or test-like files

Use `N/A - with approved reason` only when the reviewer track is explicitly
unrelated to the chunk. Security and architecture cannot be marked N/A when the
chunk touches their surfaces.

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
