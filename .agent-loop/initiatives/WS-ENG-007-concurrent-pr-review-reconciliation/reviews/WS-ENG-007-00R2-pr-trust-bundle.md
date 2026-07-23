# PR Trust Bundle: WS-ENG-007-00R2

## Goal

Make signed loop-memory reconciliation stable under legitimate trusted check
reruns and recover the exact PR #187 → PR #188 → 00R2 sequence once.

## Design

Every same-name protected check candidate is validated before selection.
Completed trusted invocations are ordered by timezone-normalized `started_at`
and strict positive check-run ID. Completion time cannot reorder invocations;
the newest invocation must succeed. Any malformed, foreign, incomplete,
wrong-head, unknown-conclusion, or duplicate-ID evidence fails closed.

Policy schema v3 names at most two recovered merges and the activation. The
production certificate pins PR #187, PR #188, and direct-next 00R2 in exact
first-parent order. Protected provenance is checked on every head. Temporary
identities are consumed before signing and never serialize or replay.

Recovery-file schema v1 remains limited to two identities. Schema v2 is emitted
only for an exact three-identity result and requires exactly three on every
reload.

## Evidence

- 231 focused tests passed.
- 98 manual agent-gate tests passed.
- The real PR #187 duplicate-success and PR #188 check histories validate.
- Legacy schema-v1 and new schema-v2 CLI recovery round trips pass.
- Merge intent, Markdown links, stale wording, and committed diff checks pass.
- All nine internal tracks passed exact reviewed SHA
  `bb3f03b3b9026a7eb3a9adb40e657e07c4eafac3` after findings were repaired.
- No workflow, required-check name, coverage, dependency, signing key, secret,
  permission, product behavior, or human merge authority changed.

## External Review

CodeRabbit raised one valid minor Markdown finding. The PR `#187` reference in
the operations runbook was reflowed so it cannot be parsed as a malformed
heading. No external finding was deferred.

## Human Review Focus

Confirm newer invocation failure cannot be hidden, all three merge heads receive
protected provenance validation, and recovery transport/policy versions remain
closed and non-reusable.

## Human Merge Ownership

Only the user may approve and merge this PR. No other PR may merge first. After
signed reconciliation, both successors remain stopped pending separate explicit
starts.
