# Intent: WS-QUAL-002 Behavior Ownership Catalogue

## Problem being solved

The blocking mutation gate correctly requires exact changed-callable ownership,
but contributors currently discover and author that ownership during each PR.
AUTH had to pause implementation to build mutation metadata. That interruption
will repeat across every initiative unless durable ownership already exists.

## Why this work matters

Humans and agents should begin implementation with known owning tests and
boundaries. Mutation should verify changed behavior, not force every contributor
to rediscover the repository's test architecture.

## Current behavior

- 168 non-`__init__` Python modules are eligible under `backend/app/` and
  `backend/scripts/`.
- 66 backend test modules exist.
- Only the historical `04M` and `05M` behavior claims exist.
- Any eligible change requires one changed, PR-specific claim with exact
  callable names and pytest nodes.

## Target behavior

Main contains reviewed behavior ownership for every eligible module. A local
command derives the exact changed callables from Git and generates the bounded
PR selection automatically. Contributors update ownership only for new or
materially remapped behavior.

## Design chosen

Create a canonical ownership catalogue separate from transient PR selection.
Catalogue records bind targets and callable ownership to exact tests, observable
outcomes, and required real boundaries. Generation and validation are
deterministic. The mutation engine remains changed-scope and never runs the
whole repository on an ordinary PR.

## Alternatives considered

- One permanent giant claim: rejected; it violates exact changed-scope custody
  and would create excessive mutation runtime.
- One generated claim based only on filenames/imports: rejected; imports do not
  prove behavior ownership.
- Full-repository mutation on every PR: rejected for cost and review noise.
- Disable mutation for AUTH: rejected; subsystem pressure must improve the
  workflow, not weaken evidence.

## Boundaries preserved

- Global 78-percent and protected 90-percent coverage floors remain unchanged.
- Existing Backend semantic lanes and full-suite custody remain authoritative.
- GitHub permissions and human merge remain contribution authority.
- No product, authorization, payment, reputation, migration, or API behavior
  changes.

## Expected risks

False ownership is worse than missing ownership. Automatically inferred
mappings must remain candidates until deterministic coverage evidence and human
engineering review confirm them. Large test modules may exceed mutation runtime if mapped
too broadly.

## What must not change

No arbitrary skips, survivor allowlists, score thresholds, PR-controlled gate
authority, or whole-repository mutation.

## How this will be proven

Schema and generator tests, exact Git-delta tests, catalogue completeness and
staleness checks, coverage-context evidence, subsystem review, an AUTH pilot,
and final hosted changed-scope mutation evidence.

## Human decisions required

Approve the staged plan and first contract. Later cutover requires a separate
human checkpoint after AUTH proves that normal work no longer pauses for manual
claim construction.
