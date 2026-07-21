# WS-ENG-004-01 PR Trust Bundle

## Chunk

`WS-ENG-004-01` — Writer-Directed Reviewed-Contract Start

## Goal

Allow current repository writers to start exact reviewed work without an extra
admin checkpoint while retaining signed, fail-closed zero-trust evidence.

## Human-approved intent

The user explicitly required the loop to support other contributors with write
access and instructed the orchestrator to start this repair. Start must be one
checkpoint; cancellation remains separately reviewed.

## What changed and why

- Starts may select a declared successor or a unique reviewed contract while
  global signed state is idle and the chunk has not already completed.
- Exact Git tree/blob evidence binds path, title, phase, mode, and main SHA.
- Current GitHub write-level repository permission replaces a static actor list
  and is stored in the signed event.
- Planning placeholders declare `## Start phase`; CI-02 is planning-only until
  its executable amendment is reviewed.
- Independent validation rechecks the exact historical Git object.
- A version-two one-target certificate bootstraps this otherwise-unstartable
  repair and is consumed before publication.

## Design and rejected alternatives

Repository evidence and GitHub permission supply trust. Chat is instruction,
not canonical proof. Starting AUTH work to smuggle in CI changes, manual state
edits, administrator approval, arbitrary phase input, and reusable exemptions
were rejected.

## Scope control and product behavior

Only loop workflows, policies, validators, tests, engineering guidance, and
initiative memory change. Workstream APIs, database, authentication, product
review decisions, payments, coverage floors, dependencies, and signing keys do
not change.

## Acceptance proof

The focused tests cover exact selection, phase, current permission,
global-idle parity, completed identity, cancellation/restart, independent tree
checking, hostile contract shapes, exact recovery, consumption, and replay.
The GitHub-equivalent coverage run passes 206 tests and reports 90.18 percent
branch coverage for the independently implemented loop-memory checker.

## Test delta and CI integrity

No test was removed, skipped, or weakened. Both state workflows now pass the
repository root to the independent exact-tree checker. No CI, coverage,
permission, timeout, or failure gate was weakened.

## Reviewer results

Plan passed with repaired conditions. Senior engineering passed with low risk;
QA, security, product/ops, architecture, CI integrity, docs, reuse/dedup, and
test-delta passed with no blocker.

## External review

Agent Gates initially found checker branch coverage at 88.27 percent against the
unchanged 90 percent floor. Focused negative tests raise it to 90.18 percent.
Fresh GitHub checks and CodeRabbit remain pending on the repaired head.

## Remaining risks and follow-up

This bootstrap PR must be the direct next first-parent merge; another merge
invalidates its exact recovery plan. After successful signed reconciliation,
dispatch `WS-CI-001-02` with `phase=planning`, then replace its placeholder
scope with the measured shard-timing amendment. Do not begin CI implementation
until that amendment is reviewed.

## Human review focus

Verify current-writer permission evidence, exact Git selection, global idle,
completed-work rejection, planning classification, cancellation approval, and
one-target recovery consumption.

## Human merge ownership

Only the user may approve merging the specific PR. Automation must not merge it.
