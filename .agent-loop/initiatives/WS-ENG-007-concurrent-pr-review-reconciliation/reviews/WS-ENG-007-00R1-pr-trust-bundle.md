# PR Trust Bundle: WS-ENG-007-00R1

## Goal

Repair the signed planning-intake reconciliation failure without weakening
ordinary start authority or changing workflow permissions.

## Root Cause And Fix

GitHub's recursive tree API included six directory objects in PR #187's
19-entry tree response, while the PR inventory and independent `git ls-tree -r`
checker correctly contained 13 leaf files. The updater now validates the full
response, rejects malformed or ambiguous prefix structure, and excludes only
exact `tree`/`040000` directory entries from the canonical leaf map.

## Recovery Boundary

The one-use certificate names only PR #187, merge
`8928ba80eeaf31e609dbdeda7d2cc22e9ea482c8`, `WS-ENG-007-PLAN`, and the direct
next merge `WS-ENG-007-00R1`. Both temporary exemptions are consumed before
signing and never persist. Replay, wrong identity, wrong order, intervening
merge, partial consumption, or failed required checks fails closed.

## Evidence

- 217 focused updater, agent-gate, and independent-checker tests passed.
- 97 manual agent-gate tests passed.
- Merge intent, Markdown links, stale wording, and diff checks passed.
- All nine required internal review tracks passed exact code SHA
  `c620610e20061b9755c825ed2dc1f89ba80bef4a` after findings were repaired.
- No workflow, coverage threshold, dependency, secret, permission, signing key,
  branch protection, product lifecycle, or human merge authority changed.

## Human Review Focus

Confirm canonical tree comparison excludes only validated directory entries,
the production recovery identities are exact, and recovery cannot start either
successor.

## Human Merge Ownership

Only the user may approve and merge this PR. Because recovery is adjacency
bound, no other PR may merge first. After successful post-merge reconciliation,
`WS-ENG-007-01` and `WS-ENG-006-01` still require separate explicit signed
starts.
