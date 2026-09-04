# External Review Response: WS-ART-001-PLAN

## Pull Request

PR #97 - Plan immutable artifact storage and Flow Node integration

## CodeRabbit

Review run: `59fdeb37-d69f-4aa0-b116-d604a8b6b6bf`

Actionable comments: 7

### Comments Addressed

1. Added `WS-ART-001-PLAN` as the first dependency gate.
2. Replaced developer-machine absolute Flow Node paths with checkout-relative
   verification commands in all three Flow Node chunks.
3. Required a full immutable registry image digest plus registry identity,
   source/contract digest, and available build-provenance verification.
4. Corrected WS-ART-001-02 to prove adapter-level authenticated provider calls,
   not a public Workstream artifact API before product cutover.
5. Required populated-legacy migration refusal to preserve every row and leave
   the prior schema unchanged while returning rebuild guidance.
6. Made production encryption explicit for both storage and backups.
7. Replaced ambiguous issuer/algorithm wording with a pinned issuer and an
   explicit permitted asymmetric-algorithm allowlist.

Fix commit: `567a052b5303fe4dd4ed8aafe84fdba1dc55955c`

### Comments Deferred

None.

### Human Decisions Needed

The planning architecture and chunk sequence still require human approval
before merge. No external comment requires a separate unresolved design choice.

## GitHub Checks

Before the fix push:

- Agent Gates: passed (including the explicit-review-trigger rerun).
- Backend: passed in 7m51s.
- CodeRabbit status: passed in 5m11s, with the seven actionable comments above.

All checks must rerun on the pushed external-fix head.

## Commands Rerun

```bash
git diff --check
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/test_agent_gates.py
```

Results: all passed; 31 agent-gate regression tests passed.

## Remaining Risks

- The PR remains planning-only; runtime/provider proof belongs to each approved
  implementation chunk.
- All nine internal tracks passed the external-fix/durable-memory head and the
  evidence was rebound. Fresh GitHub/CodeRabbit checks still must pass before
  human merge.
