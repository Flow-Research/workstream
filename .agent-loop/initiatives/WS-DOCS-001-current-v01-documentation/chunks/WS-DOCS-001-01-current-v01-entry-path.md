# WS-DOCS-001-01: Current v0.1 Entry Path

## Scope

Update repository-facing product, contributor, status, architecture-navigation,
and historical-plan documentation so current guidance is capability-based.

## Allowed Files

- `README.md`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `docs/roadmap_status.md`
- `docs/historical_planning.md`
- `docs/architecture_brief/workstream_architecture_brief.pdf`, as the generated
  companion to its changed Markdown source
- existing calendar-plan, early checker/chunk, architecture, product, reviewer,
  and diagram Markdown documents touched only to remove current calendar
  framing or add a historical notice
- this initiative directory

## Not Allowed

- backend or frontend code
- tests, migrations, workflows, or package configuration
- immutable files below `docs/reference_specs/` or `docs/internal_reviews/`
- product behavior changes

## Acceptance Criteria

- Root entry pages contain no Week 1/Week 2/30-day roadmap framing.
- Current status is organized by capability and does not overclaim draft work.
- Historical plans remain accessible but cannot be mistaken for current
  sequencing or authority.
- Contribution guidance clearly identifies present sources of truth.
- Markdown links and repository stale-wording checks pass.

## Risk

L2 documentation risk: broad discoverability impact, no runtime change.

## Verification

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `git diff --check`

The architecture PDF is regenerated from its changed Markdown source with the
Pandoc/WeasyPrint command documented in
`docs/architecture_brief/render_pdf.sh`. Diagram assets are unchanged.

## Reviewers

- documentation
- product/operations
- architecture
- senior engineering
