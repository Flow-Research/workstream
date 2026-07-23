# Chunk Contract: WS-ENG-007-00R4 — Cross-Initiative Authority Projection Repair

## Parent initiative

`WS-ENG-007` — Concurrent PR Review Reconciliation

## Goal

Restore signed starts for an idle initiative when the latest global merge belongs
to another initiative, without weakening merge-bound evidence validation.

## Why this chunk exists

After PR #190 reconciled trusted `main`, the signed start of `WS-ENG-006-01`
failed closed. Authority-event validation combined ENG-006's earlier signed
lifecycle with ENG-007's latest protected-check evidence, then correctly rejected
that synthetic record because the evidence belonged to a different PR.

## Risk class

L1 / P0 authority-event reliability repair.

## Start phase

Recovery implementation. The signed start mechanism fails before it can record
this repair, so this contract documents the exact bounded recovery exception.

## Allowed files

```text
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_update_post_merge_memory.py
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/**
.agent-loop/merge-intents/WS-ENG-007-00R4.json
```

## Not allowed

```text
workflow, permission, dispatcher, branch-protection, or cancel-authority changes
protected-check, internal-review, CI, coverage, or human-merge weakening
application, API, database, auth, payment, or product changes
automatic successor starts or unsigned implementation authority
```

## Acceptance criteria

- [ ] Authority events retain the latest global merge record as their canonical
      base and retain its exact protected-check evidence unchanged.
- [ ] The selected initiative projection contains only its signed lifecycle
      identity and active/gate transition; it does not borrow evidence from the
      latest global PR.
- [ ] Ledger transition validation still binds the authority source and completed
      chunk byte-for-byte to the selected initiative's latest signed record.
- [ ] Malformed or forged authority sources, initiative identities, chunk
      identities, active state, and gates still fail closed.
- [ ] A regression fixture proves an older idle initiative can start after a
      different initiative's merge-bound evidence becomes the global state.
- [ ] The independent checker applies the same separation and validates the
      complete generated state and ledger.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-007-01` as the stopped
      explicit successor; neither ENG-006 nor ENG-007 starts automatically.

## Verification commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
git diff --check origin/main...HEAD
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Does the repair separate global merge evidence from initiative-local lifecycle
state while keeping both independently and immutably bound?

## Stop conditions

Stop if the repair requires weakening protected evidence, accepting an unsigned
basis, changing start authority, or automatically starting any successor.
