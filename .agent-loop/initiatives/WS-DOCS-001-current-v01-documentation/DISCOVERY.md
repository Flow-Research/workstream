# Discovery

## Findings

- `README.md` presents expired day/week plans and early chunk specifications as
  the active planning package.
- `docs/roadmap_status.md` is an early chronological log, not a reliable view of
  current `main`.
- `AGENTS.md` retains a Week 1 implementation rule even though the underlying
  backend-contract-first constraint remains valid without a calendar label.
- `CONTRIBUTING.md` correctly uses the simple engineering loop but does not
  explain which documents are current authority and which are history.
- Architecture and diagram entry pages use "first 30 days" for the current
  v0.1 boundary.
- Historical plans and trial records remain useful evidence and should be
  preserved with explicit archive notices.

## Sources Of Truth

- Product definition: `README.md`, `docs/glossary.md`.
- Architecture boundary: `docs/architecture_lockdown.md` and accepted ADRs.
- Implemented behavior: code, migrations, tests, and merged commits on `main`.
- Work in progress: open pull requests and their reviewed contracts.
- History: imported files under `docs/reference_specs/` unless explicitly
  adopted by a current document, closed initiative records, internal reviews,
  and superseded calendar plans.
