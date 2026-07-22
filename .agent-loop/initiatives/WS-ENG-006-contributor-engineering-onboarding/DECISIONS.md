# Decisions: WS-ENG-006 - Contributor Engineering Onboarding

## D1 - Preserve the strict loop

The initiative changes first-planning merge admission to remove the circular
contract gate. It does not relax signed implementation starts or create a draft,
fork, patch, contributor, administrator, or emergency implementation bypass.

## D2 - Use one human-facing entry point

Root `CONTRIBUTING.md` owns newcomer operations and links canonical policy and
runbooks. `AGENTS.md` remains the mandatory agent instruction surface.

## D3 - Treat pre-existing work as discovery input

A commit or patch created before signed start may be preserved and inspected,
but it is not authorized implementation. Adoption requires a reviewed contract,
signed start, current-main reconciliation, bounded implementation evidence, and
the normal review/PR path.

## D4 - Reconcile and enforce atomically

Documentation corrections, synchronized PR-template provenance, and stable
semantic gate assertions land in the same implementation chunk.

## D5 - Add a planning-only first merge

The durable path validates a first PR as planning-only, signs its trusted merge
evidence, projects stopped state, and requires an explicit start for its
implementation successor.

## D6 - Self-bootstrap exactly once

The root repair uses the existing closed two-merge recovery certificate for
the exact PR #176 PLAN3 checkpoint followed by 00. Reconciliation binds the
ordered pair to signed state and
GitHub-derived PR identity, consumes the exemption before signing, and persists
none of it in signed history. It is not the permanent intake rule.
