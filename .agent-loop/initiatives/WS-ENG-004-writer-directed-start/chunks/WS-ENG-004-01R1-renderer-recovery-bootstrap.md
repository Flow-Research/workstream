# Chunk Contract: WS-ENG-004-01R1 — Renderer-Safe Recovery Bootstrap

## Parent initiative

`WS-ENG-004` — Writer-Directed Workstream Start

## Goal

Allow the signed post-merge branch to cross a deterministic renderer upgrade,
then reconcile PR #169 and this repair through one exact self-consuming recovery.

## Why this chunk exists

PR #169 changed initiative projections. Rebuild authentication incorrectly ran
the new renderer before authenticating the existing signed manifest, discarded
valid semantic state, and left recovery with no canonical input.

## Risk class

L1

## Allowed files

```text
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_agent_gates.py
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/initiatives/WS-ENG-004-writer-directed-start/**
.agent-loop/merge-intents/WS-ENG-004-01R1.json
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
Signature, ledger, manifest, state-schema, or final-render validation weakening
Manual automation-branch edits or force pushes
Reusable, wildcard, or unsigned recovery authority
Workflow, product, dependency, coverage-floor, or cancellation changes
Starting another chunk
```

## Acceptance criteria

- [ ] Rebuild authentication requires valid state schema, complete ledger chain,
      exact state/ledger tail, closed ordered manifest paths and digests, safe
      regular files, exact generated tree, and a valid Ed25519 signature.
- [ ] Rebuild authentication alone may accept cryptographically authenticated
      projection bytes produced by the prior deterministic renderer.
- [ ] Only `STATE.json` and `MERGE_LOG.jsonl` are copied as semantic inputs;
      every projection and manifest is regenerated in a fresh output root.
- [ ] Strict verification elsewhere continues to require current renderer output.
- [ ] The recovery certificate binds recovered PR #169 at exact merge
      `dda60ed0cb97d9de4a375df4147f31172cb3839b` and activates only for this
      repair chunk, with exact two-merge order and complete consumption.
- [ ] A local replay against the real signed automation tip reconciles PR #169,
      consumes recovery, and passes the independent checker.

## Verification commands

```bash
ruff check scripts/update_post_merge_memory.py scripts/test_agent_gates.py
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
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

Confirm renderer drift is tolerated only after structural and cryptographic
authentication, all derived files are regenerated, strict publication remains
unchanged, and recovery is exact and self-consuming.

## Stop conditions

Stop if repair requires a manual state edit, force push, persistent exemption,
signature/ledger/manifest weakening, new secret, or coverage reduction.
