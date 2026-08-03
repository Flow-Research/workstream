# Chunk Contract: WS-DOCS-002-01 — Canonical Workstream Definition

## Parent Initiative

`WS-DOCS-002-workstream-definition`

## Goal

Make the current repository define Workstream consistently as source-agnostic,
governed contribution infrastructure and explain its complete lifecycle, trust
model, central contribution fact, and external-system boundary.

## Why This Chunk Exists

Current authoritative documents still use a Flow-owned definition that
contradicts the broader architecture and obscures the purpose of Workstream.

## Risk Class

L2 — broad product and architecture documentation; no runtime change.

## Allowed Files

- `README.md`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `docs/glossary.md`
- `docs/product_brief.md`
- `docs/product_principles.md`
- `docs/principles.md`
- `docs/architecture_lockdown.md`
- `docs/architecture_system_architecture.md`
- `docs/roadmap_status.md`
- `docs/decision_0001_core_scope.md`
- `docs/diagrams/workstream_context.md`
- `docs/diagrams/workstream_context.puml`
- `docs/diagrams/rendered/workstream_context.svg`
- `docs/architecture_brief/workstream_architecture_brief.md`
- `docs/architecture_brief/images/workstream_context.png`
- `docs/architecture_brief/workstream_architecture_brief.pdf`
- this initiative directory

## Not Allowed Changes

- application code, migrations, schemas, API behavior, tests, or workflows
- authentication or authorization behavior
- v0.1 scope expansion
- imported reference specifications, internal review history, or historical
  calendar plans

## Acceptance Criteria

- No current canonical entry document defines Workstream as Flow-owned.
- README explains the end-to-end lifecycle, trust controls, source independence,
  `ContributionRecord` semantics, and consequence boundary.
- Current documents distinguish product identity from the Flow auth adapter.
- Complete-product wording does not claim deferred capabilities are implemented.
- Context diagram and generated architecture brief match their sources.
- Terminology, links, stale contracts, and diff checks pass.

## Verification Commands

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_stale_review_contracts.py`
- `docs/architecture_brief/render_pdf.sh`
- targeted current-document terminology scan
- `git diff --check`

## Required Reviewers

- documentation
- product/operations
- architecture
- senior engineering

## Human Review Focus

- Does the definition capture Workstream end to end without tying it to Flow?
- Is `ContributionRecord` described accurately for reviewers and submitters?
- Are trust guarantees supported by current contracts rather than marketing
  language?
- Is the complete product model clearly separated from v0.1 implementation?

## Stop Conditions

- A proposed definition contradicts current authorization, artifact, review, or
  contribution specifications.
- Updating generated architecture artifacts requires unrelated diagram changes.
- The change begins to alter runtime scope rather than documentation.
