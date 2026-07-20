# WS-ENG-001-04A PR Trust Bundle

## Goal

Make one trusted merge run generate, sign, validate, and publish mutually
consistent loop state, work queue, and per-initiative projections without a
manual bookkeeping PR.

## Changes and design

- Reduces the authenticated merge ledger to latest state per initiative.
- Generates deterministic loop, queue, and initiative Markdown projections.
- Adds an ordered SHA-256 payload manifest and signs manifest plus payload bytes.
- Independently validates renderers, manifest, exact paths, types, and digests.
- Migrates the 626-file legacy branch through an empty output root and temporary
  Git index, preserving history with a normal fast-forward child commit.
- Validates staged Git paths, `100644` modes, and blob bytes before commit.
- Supports absent-branch signed root bootstrap and parented replay recovery.

## Scope control

No backend/frontend behavior, schema, migration, dependency, authorization,
artifact lifecycle, explicit-start event, automatic successor activation,
coverage threshold, PR approval, or merge authority changed. 04B is not started.

## Proof and CI integrity

- 91 agent-gate tests pass.
- Changed updater/checker branch coverage is 92/93 percent.
- Ruff, compilation, merge-intent validation, stale scans, Markdown links,
  authored loop-state validation, scope, test-delta, and diff checks pass.
- Tests execute real Git index/tree/commit plumbing for legacy, parented, root,
  unsafe-mode, exact-byte, and outside-sentinel cases.
- No check, assertion, skip, dependency, or threshold was weakened.

## Internal review

Implementation SHA `e5679d4c721f8fa829d61426063cd272c5f8d5f9` and final evidence head
`dcaa7091b8808acd086028bf517ffb9e5d2027d2` pass senior engineering, QA/test,
security/auth, product/ops, architecture, CI integrity, docs, reuse/dedup, and
test-delta review after all valid findings were repaired.

## Remaining risk and follow-up

Hosted checks and human merge review remain. After merge, trusted Loop Memory
must replay current protected `main` and prove the actual closed signed branch.
04B remains a separately approved future chunk for signed start/cancel events.

## Human review focus

Review the signature/manifest domain, exact staged-tree validation, fresh-tree
migration, root versus parent commit handling, fixed automation-branch write,
and the explicit absence of 04B activation behavior.

## Human merge ownership

Only the human may approve and merge this PR. Automation records deterministic
post-merge state only after that merge and never writes protected `main`.
