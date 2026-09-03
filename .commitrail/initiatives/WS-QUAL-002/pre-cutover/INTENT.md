# Intent: WS-QUAL-002 Behavior Ownership Catalogue

## Problem being solved

The retired 05M mutation gate required exact changed-callable ownership, but
contributors had to discover and author that ownership during each PR. AUTH
paused implementation to build mutation metadata, while callable-wide mutation
also evaluated unchanged executable lines. PR #289 retired that blocking
workflow. Durable ownership and changed-line selection are both required before
mutation enforcement can safely return.

## Why this work matters

Humans and agents should begin implementation with known owning tests and
boundaries. Mutation should verify changed behavior, not force every contributor
to rediscover the repository's test architecture.

## Current behavior

- 168 non-`__init__` Python modules are eligible under `backend/app/` and
  `backend/scripts/`.
- 66 backend test modules exist.
- Only the historical `04M` and `05M` behavior claims exist.
- The hosted mutation workflow is retired; Backend lanes, coverage, lint,
  review, and human merge remain active.

## Target behavior

Main contains reviewed behavior ownership for every eligible module. A local
command derives exact changed executable lines and their containing callables
from Git and generates bounded PR selection automatically. Contributors update
ownership only for new or materially remapped behavior.

## Design chosen

Create a canonical ownership catalogue separate from transient PR selection.
Catalogue records bind targets and callable ownership to exact tests, observable
outcomes, and required real boundaries. Generation and validation are
deterministic. Any future mutation engine is changed-line-aware, never mutates
unchanged executable lines, and never runs the whole repository on an ordinary
PR.

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
and final hosted changed-line mutation evidence before reactivation.

## Human decisions required

Approve the staged plan and first contract. Later mutation reactivation requires
a separate human checkpoint after AUTH proves that normal work no longer pauses
for manual claim construction and unchanged lines cannot enter selection.
