# Intent: WS-ENG-008 — Repository-Native SDLC Assurance

## Problem being solved

Workstream's repository-native human-agent engineering loop now binds intent,
signed starts, evidence, review, merge decisions, and generated memory. Its
remaining assurance gaps are that most chunk scope is still interpreted from
prose, signed-state integrity is checked only on merge/start rather than on an
independent schedule, adversarial proof is implicit across reviewer tracks,
invariant tests are predominantly example-based, mutation quality is not
measured, and the root review log has grown to about 147 KB.

## Why this work matters

The loop is trustworthy only if authorization, scope, proof quality, and durable
memory remain independently verifiable as the repository and contributor count
grow. These controls must become stronger without slowing every change with
unbounded tests or creating a second authority path.

## Current behavior

- Signed starts and generated merge memory are canonical and initiative-local.
- Agent Gates bind merge intent and internal-review evidence to reviewed code.
- Chunk contracts state allowed files and non-goals in Markdown, but there is no
  universal machine-enforced path contract for ordinary implementation PRs.
- No scheduled workflow independently audits the signed automation branch.
- Nine internal reviewer tracks exist; adversarial attempts are not represented
  by a stable proof schema.
- Neither Hypothesis nor a mutation-testing engine is installed.
- Detailed initiative reviews coexist with a 147,017-byte root `REVIEW_LOG.md`.

## Target behavior

- New or materially changed chunk contracts carry a strict versioned scope block
  that Agent Gates compare to the exact PR delta.
- A read-only schedule verifies signed-state custody, ancestry, ledger,
  projections, active contracts, and closed-tree integrity without repairing.
- High-risk work records attacks attempted, observed denials, findings, and
  untested surfaces through risk routing.
- Bounded property tests exercise loop-memory and authorization invariants with
  deterministic replay evidence.
- A changed-module mutation pilot measures meaningful survivors before any
  carefully calibrated blocking policy is proposed.
- Root review memory becomes a compact index with lossless archives and
  initiative-owned detailed evidence.

## Design chosen

Deliver one assurance mechanism per reviewed chunk. Ratchet new enforcement
forward without retroactively rewriting hundreds of historical contracts.
Reuse the current signed-state verifier, internal evidence gate, risk router,
reviewer files, Backend aggregation, and initiative review directories.

## Alternatives considered

- A global mutation gate immediately was rejected because runtime, exclusions,
  and baseline quality are not yet measured.
- A universal tenth reviewer was rejected because it would duplicate existing
  security, QA, architecture, and test-delta tracks; adversarial proof will be
  risk-routed instead.
- One scheduled job covering all runtime architecture was rejected because
  signed-memory custody and subsystem runtime reachability have different
  owners and failure semantics.
- Truncating `REVIEW_LOG.md` was rejected because review history must remain
  lossless and linkable.

## Boundaries preserved

- Existing signed starts, start authority, cancellation approval, human merge
  ownership, merge intent, coverage floors, and automated merge memory remain.
- ART, AUTH, and REV keep their current initiative-local signed authority.
- Existing patches and dormant QUALITY work are discovery input only.
- Scheduled verification is read-only and receives no signing secret or write
  permission.
- Property and mutation testing do not change product behavior.

## Expected risks

- A scope schema could reject valid changes or permit path-pattern ambiguity.
- Scheduled auditing could produce noisy failures or accidentally gain write
  authority.
- Property and mutation suites could destabilize or lengthen CI.
- Adversarial review could become duplicative checkbox evidence.
- Review-log migration could break historical links or collide with active PRs.

## What must not change

- No bypass for humans, agents, forks, administrators, existing patches, drafts,
  or emergency work.
- No automatic start, merge, state repair, or review approval.
- No weakening of the 78 percent global or protected 90 percent coverage floors.
- No application behavior, product authorization, payment, or artifact-custody
  change may be hidden inside this engineering initiative.

## How this will be proven

Each chunk has adversarial fixtures, exact allowed paths, required reviewers,
bounded runtime expectations, and a null or same-initiative successor. Hosted
CI remains authoritative. Concurrent active initiatives are reconciled against
exact current `main` before implementation, review, publication, and merge.

## Human decisions required

- Approve each implementation chunk's exact scope and PR independently.
- Decide after the mutation pilot whether any score becomes blocking.
- Approve the lossless review-log archive layout before migration.
