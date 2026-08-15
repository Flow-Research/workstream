# WS-ARCH-001-CP03 Planning PR Trust Bundle

## Intent

Replace the stale non-executable CP03 activation skeleton with current-main,
reviewed, PR-sized contracts that can be implemented without boundary shortcuts
or accidental service authority.

## Scope

- Record CP03 as a split/non-executable parent.
- Add executable CP03A for the closed compensation-adapter target identity,
  PROJECTS/ACTORS owner eligibility, and migration proof while actions remain
  unavailable.
- Add executable CP03B for exact human Finance Authority read/PREP activation
  after CP03A merges.
- Reconcile all current planning, status, custody, handoff, risk, conformance,
  roadmap, and canonical specification records affected by the split.

## Non-goals

This PR adds no production code, migration, identity, matrix row, route,
evaluator, action activation, CON behavior, ContributionPolicy behavior,
provider integration, callback, fulfillment, delivery, or reputation behavior.

## Key safety decision

`workstream.compensation.adapter` is a future binding target, not an AUTH
caller. CP03A must allow controlled provisioning and owner locking but must not
give it any action or matrix membership. CP03B admits only an authenticated
human Finance Authority covering the exact project.

## Verification

- stale authorization wording scan: pass;
- chunk-state synchronization: pass;
- changed Markdown links: pass;
- module-boundary and test-structure validation: pass;
- `git diff --check`: pass.

Hosted CI will provide the exact-head repository gates for this documentation
change. Future CP03A/CP03B implementation PRs own their focused PostgreSQL and
coverage commands plus GitHub's full distributed backend suite.

## Reviewer result

Architecture, security, product/operations, reuse/QA/test-delta, CI-integrity,
senior-engineering, and documentation plan reviews passed after the contracts
were corrected. The detailed dispositions are in
`WS-ARCH-001-CP03-plan-review-evidence.md`.

## Human review focus

Confirm the linear CP03A-before-CP03B dependency, target-only identity with no
matrix authority, ACTORS-owned public identity contracts with no AUTH private
import, owner-module lock custody, exact Finance Authority principal, no public
route, and complete exclusion of adjacent compensation behavior.

Only an authorized human may merge the planning PR. CP03A implementation must
not start until this plan merges.
