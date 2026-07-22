# Plan: Parallel Initiative Execution

1. Remove only the repository-global active-work rejection from start event
   application, ledger transition validation, and the independent checker.
2. Preserve the target initiative basis check so either planning or
   implementation activity blocks another start in that initiative.
3. Prove AUTH implementation, ART implementation, and CI planning can start
   sequentially through signed events with no hidden pairwise or numeric cap.
   Assert exact projection semantics: the work queue marks each initiative gate
   active and names its current gate chunk; loop and initiative views expose the
   explicit active planning or implementation field.
4. Prove merge and cancellation in multiple orders preserve every other active
   initiative. A merge for A cannot consume B's active chunk; cancellation of A
   cannot reuse B's chunk, selection, or event identity.
5. Preserve completed-work, duplicate event/run, stale main/tip, selection,
   permission, same-initiative, and cancellation fail-closed tests.
6. Update engineering policy, operator guidance, AGENTS, and memory-update skill
   from global idle to one-active-chunk-per-initiative language.
7. Bootstrap this otherwise-unstartable process change from real-equivalent
   AUTH-active signed state with schema-v2 exact single-target recovery bound
   only to `WS-ENG-005-01`. Require exact plan `[target]`, signed first parent,
   target identity, no collision or replay; preserve AUTH activity; consume the
   exemption before publication; then successfully sign an ART start.
8. Run updater/checker coverage floors, agent gates, all nine internal reviewer
   tracks, external checks, and explicit human merge approval.

## Verification strategy

Use focused unit and projection tests, full agent gates, both 90 percent branch
coverage commands, stale wording, Markdown links, merge-intent validation, and
a temporary signed-state replay with AUTH active plus ART start.

## Rollback and forward recovery

Before the first parallel start, the process PR may be reverted through the
normal signed WS-ENG lifecycle. After any parallel history exists, the old
global replay invariant can never be restored over that ledger: it would reject
valid signed history even after work drains. Pause new dispatches if necessary,
merge or cancel active initiatives through signed events, and ship a compatible
forward repair that continues accepting historical parallel transitions. Never
reinterpret or rewrite the ledger.
