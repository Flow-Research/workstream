# Intent: Writer-Directed Workstream Start

## Problem being solved

The signed loop can start only the successor named by the last merge. A trusted
repository writer therefore cannot resume a stopped initiative whose prior
merge intentionally named no successor, or choose a reviewed chunk in another
stopped initiative as the next human-owned priority.

## Why this work matters

Workstream must support human and agent contributors without turning the
zero-trust loop into an administrator-operated queue. Repository evidence,
exact-main binding, review, CI, signatures, and audit history provide trust;
starting ordinary work must not require a second admin checkpoint.

## Current behavior

`Loop Memory Explicit Event` accepts `start` only when the requested chunk is
the basis record's `gate.next_chunk_id`. A null successor makes that initiative
impossible to resume through the supported workflow.

## Target behavior

An authenticated dispatcher with current GitHub `write`/`push`, `maintain`, or `admin`
repository permission may start either the declared successor or one
unique reviewed planning or implementation chunk contract on exact current
`main` in a stopped initiative, provided no planning or implementation chunk is
active anywhere. The signed event records
the writer, exact main SHA, prior state tip, chunk, initiative, reason, and
workflow run, plus the selected phase and exact contract path, title, and blob.
Cancellation retains its distinct environment review. A fresh writer dispatch
may restart or reprioritize after a completed signed cancellation; it never
mutates or reinterprets that cancellation record.

## Design chosen

Extend authenticated start validation with closed declared-successor and
writer-directed selection modes and closed planning/implementation phases.
Resolve the requested regular, non-symlink contract uniquely from its canonical
initiative directory on trusted `main`; bind its title, path, and Git blob;
require globally idle signed state and a stopped initiative; then sign and
publish the ordinary start event. Bootstrap this repair through a
closed, self-consuming recovery certificate bound to this exact recovery chunk.

## Alternatives considered

- Starting AUTH-10A and placing CI work inside it violates chunk scope.
- Hand-editing `automation/loop-memory` breaks generated-state custody.
- Requiring an administrator or environment approval for starts contradicts
  the repository-writer collaboration model.
- Allowing arbitrary chunk strings without trusted-main contract resolution
  weakens the loop and is rejected.

## Boundaries preserved

Exact-main binding, trusted-main permission policy plus current GitHub write
evidence, unique contract resolution,
signed generated state, append-only ledger validation, merge-intent enforcement,
required reviews, CI gates, and explicit user approval before merge remain.

## Expected risks

Selecting stale, ambiguous, foreign-initiative, unreviewed, or concurrently
active work; recovery reuse; bypassing cancellation approval; state divergence.

## What must not change

No product code, auth model, signing key, merge approval rule, coverage floor,
manual generated-state edit, wildcard exemption, or cancellation weakening.

## How this will be proven

Unit and integration tests cover declared and writer-directed starts, exact
contract resolution, global-idle enforcement, wrong-main/replay/ambiguity
rejection, cancellation preservation, self-consuming recovery, state signature,
independent checker, agent gates, and markdown links.

## Human decisions required

The user has explicitly chosen writer-directed starts without an additional
admin checkpoint. The resulting PR still requires explicit human merge approval.
