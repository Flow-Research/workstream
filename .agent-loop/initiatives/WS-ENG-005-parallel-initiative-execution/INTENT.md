# Intent: Parallel Initiative Execution

## Problem being solved

The signed loop permits only one active planning or implementation chunk across
the entire repository. Independent initiatives in separate worktrees therefore
queue behind unrelated work even though the ledger already models lifecycle
state per initiative.

## Why this work matters

Workstream needs high-throughput human-agent collaboration. Zero trust should
prevent ambiguous ownership, replay, and unsafe merge behavior; it should not
serialize unrelated AUTH, ART, REV, CON, CI, and other initiative work.

## Current behavior

Start application, ledger replay validation, and the independent checker each
reject a start whenever any initiative is active. One AUTH chunk therefore
blocks a reviewed ART chunk even when each has its own initiative and worktree.

## Target behavior

Any number of distinct initiatives may each have one active chunk. Within one
initiative, planning and implementation remain mutually exclusive and a second
start fails closed until the active chunk merges or is cancelled. Existing
exact-main, signed contract, permission, replay, completion, and cancellation
controls remain.

## Design chosen

Replace global-idle admission with initiative-local idle admission consistently
at event application, ledger transition validation, and independent checking.
Retain the existing per-initiative active projection and append-only global
ledger. Do not create worktree registrations or a second scheduler.

## Alternatives considered

- Keep the global lock: rejected because it defeats independent workstreams.
- Permit multiple active chunks in one initiative: rejected because successor,
  cancellation, and ownership semantics would become ambiguous.
- Trust local worktree paths as concurrency authority: rejected because local
  filesystem state is not signed repository evidence.
- Parse and lock every contract file glob at start: deferred because contract
  scope is human-readable, patterns are not yet a canonical lock schema, and
  Git/CI/review already serialize actual merges.
- Add an arbitrary global concurrency cap: rejected because no repository
  invariant justifies one and the user requested maximum safe parallelism.

## Boundaries preserved

One active chunk per initiative, one canonical ledger, exact main and prior tip,
signed authority events, immutable contract selection, current writer
permission, cancellation approval, review fanout, CI, and human merge ownership.

## Expected risks

Cross-initiative branches may touch shared files, require rebasing, or expose
semantic conflicts. A rebase and fresh proof never replace or reauthorize the
immutable selected start contract; scope drift remains an internal-review
failure. Concurrent start dispatches may race on the automation
branch; only one publication wins and losers must inspect state and redispatch.

## What must not change

No parallel active chunks inside one initiative; no automatic starts; no local
worktree authority; no force push; no manual automation edits; no CI, signature,
ledger, cancellation, review, or merge-approval weakening.

## How this will be proven

Tests will start AUTH and ART concurrently, preserve both in queue/projections,
merge or cancel either in both orders, reject a second same-initiative start,
reject replay/completed/stale events, and require updater/checker parity.

## Human decisions required

The user chose parallel execution across different initiatives. This plan
retains one active chunk per initiative and serialized reviewed merges.
