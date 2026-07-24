# Chunk Contract: WS-ENG-008-01 — Machine-Checkable Chunk Scope

## Parent initiative

`WS-ENG-008` — Repository-Native SDLC Assurance

## Goal

Make the allowed and forbidden path scope of new or materially changed chunks a
versioned, deterministic Agent Gate rather than reviewer-only prose.

## Why this chunk exists

Signed starts bind an exact contract, but ordinary PR delta scope is not yet
universally compared to a machine-readable contract block.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Start phase

`implementation`

## Allowed files

```text
CONTRIBUTING.md
AGENTS.md
.agent-loop/templates/CHUNK_CONTRACT.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/policies/definition-of-done.md
.github/workflows/agent-gates.yml
scripts/check_chunk_contract.py
scripts/check_internal_review_evidence.py
scripts/test_check_chunk_contract.py
scripts/test_agent_gates.py
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/**
.agent-loop/merge-intents/WS-ENG-008-01.json
```

## Not allowed

```text
application, API, database, migration, product lifecycle, or product authority changes
start/cancel/merge authority, loop-memory schema, signing, branch protection, environment, or secret changes
retroactive inference or mass rewrite of unchanged historical contracts
arbitrary shell execution from contract content
absolute paths, traversal, negation, brace expansion, platform-dependent glob behavior, symlink, or submodule acceptance
coverage, test, evidence, reviewer, PR, or human merge gate weakening
```

## Acceptance criteria

- [ ] One strict versioned JSON block has exact typed keys for identity, phase,
      risk, allowed paths, forbidden paths, required reviewers, and verification
      command identifiers; duplicate blocks, duplicate keys/items, unknown keys,
      malformed Unicode, noncanonical separators, and oversized input fail.
- [ ] The block identity and phase match the canonical heading and signed-start
      contract selection; human-readable scope remains required and cannot
      contradict the machine block.
- [ ] A closed repository-relative pattern grammar has deterministic semantics
      for files and recursive directories without arbitrary regex or shell use.
- [ ] Status-aware base-to-head plus staged/dirty/untracked discovery rejects
      every added, modified, deleted, renamed, copied, type-changed, symlinked,
      executable, gitlink, case-colliding, or foreign path not allowed by the
      contract, and rejects every forbidden match even when also allowed.
- [ ] The PR's exact one merge intent, initiative evidence/status, and permitted
      post-review evidence paths are represented explicitly rather than hidden
      exemptions.
- [ ] New/materially changed contracts require schema v1. Unchanged historical
      contracts continue without inferred or retroactive scope.
- [ ] Required reviewer metadata agrees with the internal evidence gate; command
      identifiers bind evidence without executing contract-provided text.
- [ ] Agent Gates invoke the checker on the exact PR base/head and fail closed
      on unresolved refs, shallow history, ambiguity, or malformed contracts.
- [ ] Positive fixtures and one negative mutation per schema, identity, path,
      diff-status, reviewer, command, legacy-ratchet, and workflow drift class pass.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-008-02` and requires a
      separate explicit start.

## Verification commands

```bash
python3 scripts/test_check_chunk_contract.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
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

- Can any changed path escape the signed contract through parsing or Git status semantics?
- Does the ratchet avoid guessing historical scope without creating a new bypass?
- Does the workflow execute only repository-owned checker code?

## Stop conditions

Stop if deterministic path semantics cannot be closed, historical contracts
must be rewritten, or any current evidence/review/coverage gate must weaken.

