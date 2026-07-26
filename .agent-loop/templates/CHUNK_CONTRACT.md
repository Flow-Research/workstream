# Chunk Contract: <CHUNK_ID> — <TITLE>

Use this template when a change is large or risky enough to benefit from a
bounded contract. Small changes may state intent, scope, and evidence directly
in the pull request.

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

Record reviewer outcomes when reviewers are used:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

Recommended for higher-risk work:

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

Select reviewers according to risk. Reviews improve confidence; they do not
grant repository authority or replace required GitHub review and checks.

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
