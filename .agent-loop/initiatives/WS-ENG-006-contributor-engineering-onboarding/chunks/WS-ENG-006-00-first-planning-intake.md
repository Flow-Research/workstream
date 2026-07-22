# Chunk Contract: WS-ENG-006-00 — First-New-Initiative Planning Intake

## Parent initiative

`WS-ENG-006` — Contributor Engineering Onboarding

## Goal

Allow one strictly planning-only first PR to establish a new initiative and its
reviewed implementation contracts on trusted `main`, while keeping the
initiative stopped until an ordinary signed explicit start.

## Why this chunk exists

Current starts require a contract already on exact `main`, while post-cutover
merges require an earlier signed start. The circular gate prevents new
initiatives from establishing their first contract.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/CHUNK_MAP.md`

## Risk class

L1

## SLA

P0

## Start phase

`implementation`

## Allowed files

```text
AGENTS.md
.agent-loop/README.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/policies/loop-memory-recovery.json
docs/operations_post_merge_memory.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_agent_gates.py
scripts/test_update_post_merge_memory.py
.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/**
.agent-loop/merge-intents/WS-ENG-006-00.json
```

## Not allowed

```text
application, API, database, product lifecycle, or product Contributor changes
workflow permissions, secrets, environments, branch protection, or start authority changes
manual automation-branch writes or force pushes
planning intake outside one additive new-initiative tree and one merge intent
planning intake that activates work or omits an explicit-start successor
coverage, test, lint, review, PR, or human merge gate weakening
reusable or identity-ambiguous self-bootstrap authorization
```

## Acceptance criteria

- [ ] Intake is accepted only when the initiative is absent at that historical
      signed-ledger point and the chunk is exactly `<initiative>-PLAN`.
- [ ] The authoritative first-parent-to-merge delta equals the reviewed PR-head
      tree delta and adds only mode `100644` blobs: one merge intent plus one
      directory `.agent-loop/initiatives/<initiative>-<slug>/`. Squash, merge,
      and rebase merge shapes are accepted only when GitHub's unique merged PR,
      reviewed head, merge tree, and first parent prove that equality.
- [ ] Independent generated-state validation does not require the reviewed head
      commit to remain reachable after branch deletion. It reconstructs the
      exact additive delta from the signed merge and first parent on trusted
      `main`, then matches its paths, modes, blob identities, tree identities,
      and digest to the signed intake evidence. Pruned-head squash and rebase
      fixtures prove clean replay remains possible.
- [ ] The initiative root adds exactly `INTENT.md`, `DISCOVERY.md`, `PLAN.md`,
      `CHUNK_MAP.md`, `STATUS.md`, `RISKS.md`, `DECISIONS.md`, and optionally
      `REVIEW_LOG.md`; `chunks/` contains one or more mode-100644 Markdown
      contracts; `reviews/` contains exactly `<initiative>-PLAN-internal-review-evidence.md`
      and `<initiative>-PLAN-pr-trust-bundle.md`. No other entry is accepted.
- [ ] Canonical initiative, PLAN chunk, directory, merge-intent, evidence, and
      successor identities agree. Hidden files, executable blobs, symbolic or
      hard links, submodules, generated-state paths, root `AGENTS.md`, policy,
      ADR, specification, code, configuration, script, delete, rename, and
      foreign paths fail closed. `STATUS.md` must use the canonical inactive
      planning-intake form; ordinary Markdown discussion and links are allowed.
- [ ] The reviewed-head successor contract declares `## Start phase`
      `implementation`; the merge intent separately names that same-initiative
      successor and sets `next_requires_explicit_start` to true.
- [ ] Exact reviewed-head `agent-gates` and `test` check runs each resolve to one
      completed success from GitHub Actions app ID `15368`. Wrong app ID/slug,
      stale-head success, duplicate-name/app spoofing, pending, skipped, neutral,
      cancelled, missing, or pagination overflow fails closed. CodeRabbit remains
      required external evidence under the existing merge-record check set, but
      its legacy status is supplementary and is never treated as start or
      authenticated planning authority.
- [ ] Accepted intake records a signed normal merge with no active chunk,
      `stopped_after_merge`, and implementation possible only by later start.
- [ ] Sequential reconciliation, clean trusted-main rebuild, duplicate no-op,
      same-SHA/different-identity collision, later-merge preservation, and
      historical initiative-absence behavior are deterministic.
- [ ] Existing initiatives, replay collisions, malformed metadata, unexpected
      files, and active-state claims fail closed.
- [ ] The 00 root migration uses the existing closed two-merge recovery
      certificate with recovered merge exactly PR #176 / `WS-REV-001-PLAN3` /
      merge `afde967d` and activation exactly `WS-ENG-006/WS-ENG-006-00`.
      It requires that exact ordered plan, unique GitHub merged
      PR/head/base identity, exact protected Actions checks, required external
      evidence, and successful aggregate checks;
      consumes both before signing; rejects extra/changed/reused identities; and
      leaks no exemption into signed state or ledger on initial run or replay.
- [ ] One schema-v2 merge intent declares `WS-ENG-006-01` as the explicit-start
      same-initiative successor.

## Verification commands

```bash
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
# Generated-fixture tests invoke:
python3 scripts/check_loop_memory_state.py --state-root <generated-root> --repository-root <trusted-repo>
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

- Can implementation or an existing initiative use planning intake?
- Does accepted intake remain stopped until ordinary signed start?
- Is self-bootstrap exact, consumed, and non-reusable?
- Does replay reconstruct the same signed state from trusted evidence?

## Stop conditions

Stop if intake cannot be restricted to one additive planning tree, can activate
work, cannot bind required checks, or requires weakening an existing gate.
