# WS-ART-001-04B2 Internal Review Evidence

## Scope

Hidden fixed-service materialization and Workstream-default pre-submission
execution only. Project-policy execution, durable checker evidence, admission,
Submission creation, route exposure, provider I/O, and AUTH activation remain
out of scope.

## Deterministic evidence

- Focused materialization/default execution: 29 tests passed.
- Contract-focused ART/catalogue/preparation/archive/manifest/change/config
  suite passed.
- Ruff passed for the backend application, tests, and changed lane script.
- Hosted semantic-lane collection and evidence validation passed after adding
  both new test modules to the canonical lane inventory.
- Stale artifact contracts, lightweight agent gates, Markdown links, stale
  wording, and diff integrity passed.
- Hosted full Backend Gates remain required for repository coverage at 78
  percent and the ART/checker/core/interface 90 percent reports.

## Reviewer results

- Architecture: PASS after removing the public unauthorized
  `PreparedArtifact` processing seam.
- Security/auth: PASS after removing reachable filesystem authority and
  clearing retained callback bytes and entries during close.
- QA: PASS after direct stale/unknown/duplicate/disabled, cancellation,
  timeout, adapter-failure, cleanup, and project-policy isolation proofs.
- Senior engineering: PASS after replacing the fd-bearing tree capability and
  correcting warning metadata.
- Reuse/dedup: PASS after sharing pure attestation/quality semantics and using
  the typed platform capability enum.
- Product/ops: PASS WITH LOW RISK; no lifecycle, review, compensation, or
  reputation effect. The platform/default slice is canonically derived from
  the locked full plan and remains hidden.
- CI integrity: PASS after adding both new modules to semantic test lanes; no
  coverage floor was weakened.
- Test delta: PASS; no removed, skipped, weakened, or bypassed test.
- Docs: PASS after repairing roadmap structure and reconciling canonical ART,
  checker, AUTH, glossary, roadmap, and template wording.

## Resolved findings

- Closed the unauthorized prepared-artifact workspace bypass.
- Removed mutable directory-fd authority from checker callbacks.
- Revoked retained byte and entry facts when callback scope closes.
- Propagated cancellation/deadline abort before checker execution while still
  completing scratch cleanup.
- Restored the shared guide-extraction workspace cleanup bound.
- Consolidated duplicated default semantics and enum-backed dispatch.
- Added direct fail-closed and terminal-path tests plus CI lane ownership.

## Remaining external gates

GitHub Backend Gates, CodeRabbit, and human review are external checks. Human
merge ownership remains with the repository owner; this evidence does not
authorize merge.
