# Workstream Architecture Brief

This folder contains the shareable Workstream architecture brief.

- Source: [workstream_architecture_brief.md](workstream_architecture_brief.md)
- PDF: generated locally with the render script; not tracked.
- Render script: [render_pdf.sh](render_pdf.sh)

The brief uses the C4-PlantUML diagrams from `docs/diagrams/` and packages them into a single PDF for team review.

The Markdown source describes current public ZIP preparation,
admission-backed Submission entry and the bounded local public/Celery drill.
The obsolete PDF export has been removed. Current Markdown and diagram sources
include the atomic claim correction. Generate a fresh PDF when sharing the brief. Use the
[roadmap](../roadmap_status.md) for current capability status. Lifecycle
diagrams remain target views.

## Render

```bash
docs/architecture_brief/render_pdf.sh
```

The script regenerates image assets from the current diagram SVGs, renders the lifecycle sequence asset when PlantUML is available, then produces `workstream_architecture_brief.pdf`.
