# WS-DOCS-001-02: Current-State Documentation Reconciliation

## Problem being solved

The primary v0.1 entry path is current, but a small number of current-facing
documents still use expired calendar language and the documentation
initiative's own status still describes its merged first chunk as local work.
Some preserved early reviews also lack one index that clearly classifies them
as historical evidence.

## Why this work matters

Contributors and agents need one unambiguous current entry path. Historical
evidence must remain available without being mistaken for current priority,
implementation state, or contribution authority.

## Current behavior

- `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, and `docs/roadmap_status.md` use
  the current capability-based v0.1 framing.
- One current architecture diagram still refers to a numbered delivery week.
- Early plans are indexed as historical, but early strategy/review records are
  not all reachable from that classification page.
- `WS-DOCS-001-01` is merged but its initiative status says it is locally
  complete and awaiting PR review.

## Target behavior

- Current-facing documentation contains no delivery-week or rolling-calendar
  authority.
- Preserved calendar plans, early specifications, and review records are
  explicitly discoverable as history.
- The current capability ledger reflects merged REV/AUTH readiness without
  claiming the unimplemented review lifecycle is live.
- The DOCS initiative accurately records its merged and current chunks.

## Design chosen

Correct only current-facing prose and indexes. Preserve historical documents
and their original statements instead of rewriting the evidence they contain.

## Allowed files

- `docs/current_system_data_flow.html`
- `docs/historical_planning.md`
- `docs/roadmap_status.md`
- `.agent-loop/initiatives/WS-DOCS-001-current-v01-documentation/**`

## Not allowed changes

- Backend, frontend, migration, test, CI, or workflow behavior.
- AUTH, ART, REV, CON, QUAL, or XINT implementation records.
- Historical document bodies whose old terminology is part of the record.
- Open pull requests #149, #138, #62, or #249.

## Acceptance criteria

1. Current-facing documentation no longer describes v0.1 through numbered
   delivery weeks or a 30-day schedule.
2. Historical plans and early review records are clearly classified and linked.
3. The current status ledger distinguishes merged readiness from unimplemented
   review/revision behavior.
4. The DOCS initiative no longer reports its merged first chunk as in progress.
5. Stale-wording, Markdown-link, and lightweight documentation gates pass.

## Risk class and reviewers

Risk: L2 documentation-only. Required review: docs, senior engineering, QA,
and product/operations. Security review is unnecessary because authority and
runtime security behavior do not change.

## How this will be proven

- Repository stale-wording scan.
- Repository Markdown-link check.
- Targeted search for calendar language outside classified historical paths.
- Lightweight Agent Gates tests.
- Internal reviewer results recorded before PR readiness.

## Human review focus

Confirm that the capability ledger is accurate, that historical evidence was
preserved, and that no active implementation initiative was re-prioritized.
