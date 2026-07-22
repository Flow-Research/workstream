# Plan: WS-ENG-006 - Contributor Engineering Onboarding

## Proposed approach

First repair the circular first-new-initiative gate with a planning-only intake
merge class. Then add the human-facing contribution entry point, reconcile loop
documentation, expose signed-start provenance, and enforce future consistency.

## Design chosen

A planning intake is not implementation authority. It is valid only for the
first merge of an initiative absent from signed history, with canonical chunk ID
`<initiative>-PLAN`, exactly one merge intent, one exact new initiative
directory, a closed additive planning-only file set, successful required checks,
a same-initiative implementation successor contract, and explicit-start true.
Automation records trusted GitHub merge evidence in signed memory and projects
the initiative as stopped. Ordinary signed start remains the only way to
activate the successor.

After that repair, root `CONTRIBUTING.md` becomes the operational front door.
Canonical detail remains in `AGENTS.md`, the repository engineering policy, and
the post-merge runbook. Stable Agent Gate assertions protect the canonical loop,
initiative-local concurrency, patch adoption, automated merge memory,
signed-start provenance, and human merge ownership.

## Alternatives considered

### Require a signed start for the first planning PR

Rejected because selection resolves contracts only from exact current `main`;
an unmerged first contract cannot authorize its own merge.

### Relax publication for existing work or drafts

Rejected because that would create unsigned implementation and a bypass.

### Borrow another initiative's active scope

Rejected because it breaks initiative custody and signed evidence.

## Boundaries preserved

- No product authentication, authorization, payment, persistence, API, or
  product Contributor behavior changes.
- No start/cancel permission, secret, environment, or branch-protection changes.
- Planning intake cannot activate work or modify application, workflow, script,
  root-policy, or foreign-initiative files.
- No existing test, coverage, review, PR, or human checkpoint is weakened.

## Rollout/migration strategy

Chunk `WS-ENG-006-00` lands the permanent planning-intake validation by
retargeting the closed schema-v2 `exact_single_target` recovery certificate to
its exact initiative and chunk. Reconciliation requires a one-target plan and
signed first parent, derives exact PR identity from GitHub, and consumes the ephemeral exemption
before signing. This root migration is not the permanent intake rule and cannot
authorize another merge. After signed reconciliation, the already-given user
instruction authorizes the orchestrator
to dispatch the ordinary signed start for `WS-ENG-006-01` without asking again.

## Verification strategy

- Accept only one additive new-initiative planning tree and merge intent.
- Reject existing initiatives, non-PLAN identities, code/config changes,
  deletes/renames, foreign paths, failed checks, invalid successors, replays,
  collisions, and active-state claims.
- Prove accepted intake records a signed stopped projection whose implementation
  successor still requires explicit start.
- Run complete Agent Gates, loop-memory validation, Markdown links, stale wording,
  diff checks, and required internal reviewer tracks.

## Review strategy

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta are required for both chunks.

## Sequencing

1. `WS-ENG-006-00`: permanent first-planning intake plus exact self-bootstrap.
2. `WS-ENG-006-01`: contributor onboarding docs, provenance, and semantic gates.
3. Stop; no successor follows 01.

## Public intake boundary

Chunk 01 must name an existing public request route and exact maintainer adoption
procedure for contributors without write permission. Planning intake accepts
planning artifacts only and never authorizes unsolicited implementation.
