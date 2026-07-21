# Chunk Contract: WS-ENG-004-01 — Writer-Directed Reviewed-Contract Start

## Parent initiative

`WS-ENG-004` — Writer-Directed Workstream Start

## Goal

Let an authenticated repository writer start a unique reviewed chunk on exact
current main without an extra admin checkpoint, while preserving signed,
fail-closed zero-trust evidence.

## Why this chunk exists

Successor-only starts strand stopped initiatives and prevent human-owned
cross-initiative prioritization.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-004-writer-directed-start/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-004-writer-directed-start/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-004-writer-directed-start/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
.github/workflows/loop-memory-start.yml
.github/workflows/loop-memory.yml
AGENTS.md
.agents/skills/memory-update/SKILL.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_update_post_merge_memory.py
scripts/test_check_loop_memory_state.py
scripts/test_agent_gates.py
.agent-loop/policies/loop-memory-recovery.json
.agent-loop/policies/loop-memory-start-authorities.json
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/initiatives/WS-ENG-004-writer-directed-start/**
.agent-loop/merge-intents/WS-ENG-004-01.json
.agent-loop/initiatives/WS-CI-001-backend-ci-acceleration/chunks/WS-CI-001-02-safe-routing-cache-timing.md
.agent-loop/REVIEW_LOG.md
docs/operations_post_merge_memory.md
```

## Not allowed

```text
Product, API, database, dependency, coverage, or signing-key changes
Manual automation-branch edits or force pushes
Admin/environment approval for ordinary start
Cancellation approval weakening
Unsigned, wildcard, persistent, chat-derived, or local-state authority
Parallel active implementation chunks
Automatic start without an explicit writer dispatch
Merge without explicit approval of this specific PR
```

## Acceptance criteria

- [ ] Declared-successor starts continue to pass unchanged.
- [ ] A dispatcher with current GitHub `write`/`push`, `maintain`, or `admin`
      repository permission can start a unique reviewed chunk
      contract from exact current main when signed state is globally idle, with
      a closed planning or implementation phase.
- [ ] Missing, ambiguous, malformed, foreign-initiative, and title-mismatched
      contracts plus symlink/non-regular files and blob mismatches fail closed.
- [ ] Signed selection evidence binds mode, phase, canonical path, exact heading
      title, and Git blob SHA.
- [ ] Writer-directed phase is derived from an explicit trusted-main contract
      declaration; the dispatcher cannot promote planning work to implementation.
- [ ] Any active planning or implementation chunk in any initiative blocks a
      start at apply time, ledger-transition validation, and independent check.
- [ ] The signed event retains dispatcher, run, reason, exact-main, prior-tip,
      initiative, chunk, current repository permission, and GitHub authority evidence.
- [ ] A current read-only/non-collaborator dispatcher fails even if formerly
      trusted; no static one-user admission list remains.
- [ ] Cancel still requires the distinct environment approval and exact active
      chunk.
- [ ] A fresh authenticated dispatch may start after cancellation while the
      prior cancel record and approval evidence remain immutable.
- [ ] Bootstrap recovery activates only for the exact merged WS-ENG-004-01
      target with plan `[target]` and first parent equal to signed current main;
      it consumes itself before ledger publication, leaves no state, projection,
      manifest, or ledger exemption, and cannot replay.
- [ ] Generated state signature, independent checker, workflow invariants,
      stale wording, and markdown links pass.

## Verification commands

```bash
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
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

Confirm ordinary starts need no second admin checkpoint while exact-main,
reviewed-contract, phase, global-idle, signature, audit, and merge controls
remain. Confirm CI-02 starts only as planning until its executable amendment is
reviewed.

## Stop conditions

Stop if the change needs a new secret, manual state edit, force push, reusable
exemption, cancellation weakening, test/coverage weakening, or product changes.
