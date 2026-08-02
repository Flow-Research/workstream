# WS-DOCS-001: Current v0.1 Documentation

## Intent

Make the repository entry path describe Workstream's current v0.1 product,
architecture, implementation state, and contribution workflow without using an
expired calendar as the roadmap.

## Why Now

The root README still presents a 30-day plan, week plans, and early chunk
specifications as the primary planning package. `docs/roadmap_status.md` still
describes the authorization foundation as the current phase even though later
authorization, artifact, project-guide, and cross-initiative work has merged.
That makes current capability, historical implementation evidence, and future
work difficult to distinguish.

## Non-Goals

- No runtime, API, schema, migration, workflow, or CI behavior changes.
- No deletion or rewriting of immutable reference specifications, internal
  review evidence, or initiative history.
- No promise of release dates or completion dates.
- No claim that a planned or draft capability is available.

## Success

A new contributor can start with `README.md`, `AGENTS.md`, and
`CONTRIBUTING.md`, understand the v0.1 boundary, locate current status, tell
current guidance from history, and contribute through the simple engineering
loop.
