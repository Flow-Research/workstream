---
name: memory-update
description: Update durable repo memory after planning, merge, rejection, blocker, or repeated agent mistake.
---

# Memory Update

Use before publication to provide bounded next-state metadata, and use the
generated state after merge.

## Before Merge

- Add one `.agent-loop/merge-intents/<chunk-id>.json` file to the reviewed PR.
- Use merge-intent schema version 2.
- Record the initiative, completed chunk, title, next chunk or `null`, and
  whether the next chunk requires a separate explicit start.
- A non-null next chunk must belong to the same initiative and match exactly
  one existing chunk contract ID and title. Use `null` when this initiative has
  no declared successor; never use merge intent to prioritize another
  initiative.
- Keep implementation/specification memory in the owning PR where it can be
  reviewed with the change.

## Generated After Merge

The trusted `Loop Memory` workflow records:

- `.agent-loop/STATE.json`
- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/MERGE_LOG.jsonl`
- `.agent-loop/WORK_QUEUE.md`
- `.agent-loop/INITIATIVE_STATE/<initiative-id>.md`
- `.agent-loop/MANIFEST.json`
- `.agent-loop/STATE.sig`

on `automation/loop-memory`.

Do not open a manual post-merge memory PR or rerun internal reviewers when this
automation succeeds.

## Explicit Start And Cancel

Use `.github/workflows/loop-memory-start.yml` on exact protected `main` to start
the recorded same-initiative successor or a unique reviewed contract, or cancel
that exact active chunk. A start requires globally idle signed state and the
dispatcher's current GitHub `write`/`push`, `maintain`, or `admin` permission;
that authenticated dispatch is the single authority checkpoint. Cancellation
retains the distinct protected-environment approval. Never infer a start from
chat, a worktree, or PR prose. Do not rerun a failed dispatch: inspect
authenticated state and create a fresh attributable dispatch.

The generated queue and initiative files reduce signed merge, start, and cancel
events. They never attest work started only in conversation or an unmerged
worktree. Verify the complete manifest/signature rather than trusting one file
in isolation.

## Manual Updates As Applicable

- `.agent-loop/LOOP_STATE.md`
- `.agent-loop/WORK_QUEUE.md`
- `.agent-loop/REVIEW_LOG.md`
- initiative `STATUS.md`
- initiative `DECISIONS.md`
- initiative `RISKS.md`
- chunk contract status notes

## Capture

- What was completed
- What was merged/rejected/blocked
- PR links
- Remaining risks
- Follow-up items
- Repeated agent mistakes
- Policy/skill improvements needed

## Rules

- Durable repo memory beats chat memory.
- Do not bury decisions in conversation only.
- If a repeated issue appears, suggest policy/skill update.
- Generated state is exempt from repeated review only on
  `automation/loop-memory`, only when written by the trusted workflow, and only
  while its public-key signature verifies.
- If `.github/workflows/loop-memory.yml` fails, send the documented
  `loop-memory-replay` `repository_dispatch` with the current protected-main SHA
  after correcting permissions. Stale replay targets fail closed. A failed
  `.github/workflows/loop-memory-start.yml` run instead requires a fresh,
  attributable dispatch through its protected approval path.
  Merge-intent content is immutable after merge; do not edit generated state.
