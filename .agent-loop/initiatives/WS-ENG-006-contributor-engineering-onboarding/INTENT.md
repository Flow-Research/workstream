# Intent: WS-ENG-006 - Contributor Engineering Onboarding

## Human-level goal

Make the repository's strict zero-trust engineering process unambiguous to every
human and agent before they write, publish, review, or merge repository changes.

## Why now

An external contributor completed a local CI experiment before discovering that
signed work had not started. The repository correctly refused publication, but
the absence of a root `CONTRIBUTING.md`, inconsistent loop wording, and one stale
global-idle statement made the required path harder to discover than it should
be.

## Success state

- A newcomer can begin at `CONTRIBUTING.md` and follow one exact path from idea
  or existing patch through signed start, evidence, review, PR, merge, automated
  memory, and stop.
- Human and agent instructions state the same canonical engineering loop and
  initiative-local concurrency rule.
- The documentation explains why chat, commits, branches, and worktrees are not
  signed authority and why the controls exist.
- Existing or unsolicited patches have a preservation and adoption path that
  does not grant retroactive authorization or weaken review.
- Deterministic agent-gate tests reject drift in the canonical entry documents.
- A new initiative can land one planning-only intake PR, enter signed stopped
  state, and expose its reviewed contracts without activating implementation.

## Non-goals

- Relaxing signed starts for implementation, internal reviewer requirements,
  evidence gates, coverage floors, merge-intent requirements, or explicit human
  merge approval. Chunk 00 intentionally changes only first-planning merge
  admission and always leaves implementation stopped.
- Creating a privileged contributor bypass, draft-PR bypass, fork bypass, or
  manual post-merge memory path.
- Changing Workstream product Contributor roles or lifecycle behavior.
- Changing GitHub repository permissions, branch protection, secrets, or
  cancellation approval.

## Business/product/engineering context

Workstream coordinates useful human-agent work by binding intent, scope, proof,
and human accountability. Repository contribution must model those same
properties. Strict controls are useful only when an authorized contributor can
discover and execute them without relying on private chat history.

## Human judgment required

- Approve the exact onboarding wording and the distinction between repository
  contributors and Workstream product Contributors.
- Confirm that preserved pre-existing work is discovery input until adopted by
  a reviewed, signed chunk.
- Approve the first-planning intake design and exact self-bootstrap repair.
- Approve each implementation PR for merge; no second start approval is added.

## Initial risk class

L1 - repository policy, loop documentation, and CI gate assertions.
