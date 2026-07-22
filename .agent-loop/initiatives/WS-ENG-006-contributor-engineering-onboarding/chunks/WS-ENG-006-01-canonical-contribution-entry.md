# Chunk Contract: WS-ENG-006-01 — Canonical Human And Agent Contribution Entry

## Parent initiative

`WS-ENG-006` — Contributor Engineering Onboarding

## Goal

Give every human and agent one consistent, enforced path into Workstream
repository engineering without relaxing signed starts, evidence, review, merge,
or automated-memory controls.

## Why this chunk exists

The strict policy is substantially implemented but lacks a root contribution
guide and contains conflicting public loop and concurrency wording.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Start phase

`implementation`

## Allowed files

```text
CONTRIBUTING.md
README.md
AGENTS.md
.agent-loop/README.md
.agent-loop/policies/repository-engineering-policy.md
docs/operations_post_merge_memory.md
.github/pull_request_template.md
.agent-loop/templates/PR_TRUST_BUNDLE.md
scripts/test_agent_gates.py
.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/**
.agent-loop/merge-intents/WS-ENG-006-01.json
```

## Not allowed

```text
GitHub workflow behavior or permissions
loop-memory generator, checker, signer, or state schema
start/cancel authority policy
branch protection, environments, secrets, or repository permissions
application, API, database, product lifecycle, or product Contributor behavior
coverage, test, lint, review, PR, signed-start, or merge gate weakening
any bypass for drafts, forks, existing patches, agents, humans, or administrators
```

## Acceptance criteria

- [ ] Root `CONTRIBUTING.md` distinguishes repository contributors from product
      Contributors, explains why the controls exist, and provides exact
      before-work, implementation, pre-PR, merge, and stop procedures.
- [ ] Existing commits and patches are explicitly preservation/discovery input,
      never retroactive authorization.
- [ ] The guide names an existing public request route and exact maintainer
      adoption procedure for contributors without write permission, without
      private-chat dependency or unsigned implementation publication. If no
      route is approved, this chunk remains blocked rather than inventing one.
- [ ] `CONTRIBUTING.md`, `README.md`, `AGENTS.md`, and `.agent-loop/README.md`
      use `Automated Merge Memory` and initiative-local concurrency with one
      active planning or implementation chunk per initiative.
- [ ] Manual post-merge memory PRs and automatic successor starts remain
      prohibited.
- [ ] Synchronized PR trust-bundle templates expose the signed start run,
      authorized main SHA, phase, contract path, signed contract blob SHA, and
      reviewed implementation SHA as navigation evidence, and state that only
      independently verified signed automation state is canonical authority.
- [ ] Agent Gates include positive fixtures and one negative mutation per drift
      class for the root contribution guide, canonical loop, initiative-local
      concurrency, existing-patch adoption, automated merge memory, canonical
      signed-state warning, and explicit human merge ownership.
- [ ] Agent Gates verify that both PR templates expose the same signed-start
      provenance field set without requiring unrelated presentation text to be
      identical.
- [ ] Exactly one schema-v2 merge intent records no same-initiative successor.

## Verification commands

```bash
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
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

- Does any sentence authorize work, publication, review, or merge without the
  existing signed and reviewed loop?
- Can a newcomer distinguish repository contribution from product Contributor
  authority and follow the process without private chat?
- Do semantic tests protect stable policy without freezing incidental prose or
  workflow implementation details?

## Stop conditions

Stop and escalate if implementation requires workflow, authority, permission,
generated-state, product, or application changes; if a strict gate must weaken;
if the first-new-initiative contract cannot enter trusted `main` through an
already reviewed non-exempt path; or if the same blocker survives two repair
attempts.
