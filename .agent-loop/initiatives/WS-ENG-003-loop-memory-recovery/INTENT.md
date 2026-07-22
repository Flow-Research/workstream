# INTENT: WS-ENG-003 — Loop Memory Recovery

## Problem being solved

PR #166 merged without a predecessor signed start because it implemented the single-checkpoint start mechanism itself. Post-merge memory therefore failed closed and cannot advance past merge `6445ce62`.

## Why this work matters

Canonical memory must reconcile merged work without weakening future start authorization or requiring hand-edited signed state.

## Current behavior

Replay rejects PR #166 as an unstarted post-cutover merge. Any later merge also remains blocked behind it.

## Target behavior

One reviewed recovery merge supplies a closed recovery certificate that exempts exactly PR #166 and the recovery merge itself during that single reconciliation. Both exemptions are consumed, signed canonical state advances, and future merges retain normal start enforcement.

## Design chosen

Before reconciliation, load a versioned recovery certificate from the immutable resolved target merge. Require that target to be the final planned merge and its canonical record to be `WS-ENG-003-01`, derive its exact PR identity through the existing unique GitHub merge collector, and require the plan to contain exactly PR #166 followed by that target. Inject both entries ephemerally, consume them through the existing reducer, and assert neither remains before signing.

## Alternatives considered

- Hand-edit automation state: rejected because it breaks signed deterministic ownership.
- Permanently weaken start enforcement: rejected.
- Add PR #166 to the old cutover inventory: rejected because that inventory is immutable at the cutover merge.

## Boundaries preserved

No product code, manual state edits, force push, new secret, automatic start, or reusable wildcard exemption.

## Expected risks

Recovery reuse, accepting a different PR, persisting the self-exemption, or activating from a non-recovery target.

## What must not change

Normal explicit-start enforcement, signatures, first-parent ordering, exact merge intent, replay behavior, and cancellation controls.

## How this will be proven

Tests cover exact activation, wrong target/chunk/PR rejection, two-record consumption, no residual recovery exemption, replay, and future unstarted-merge rejection.

## Human decisions required

The user authorized immediate repair on 2026-07-21. Merge remains explicitly user-owned.
