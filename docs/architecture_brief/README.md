# Workstream Architecture Brief

This folder contains the shareable Workstream architecture brief.

- Source: [workstream_architecture_brief.md](workstream_architecture_brief.md)
- PDF: [retained prior render](workstream_architecture_brief.pdf)
- Render script: [render_pdf.sh](render_pdf.sh)

The brief uses the C4-PlantUML diagrams from `docs/diagrams/` and packages them into a single PDF for team review.

The Markdown source describes current public ZIP preparation,
admission-backed Submission entry and the bounded local public/Celery drill.
The PDF is a retained prior render; current Markdown and diagram sources
include the atomic claim correction. Use the
[roadmap](../roadmap_status.md) for current capability status. Lifecycle
diagrams remain target views.

## Render

```bash
docs/architecture_brief/render_pdf.sh
```

The script regenerates image assets from the current diagram SVGs, renders the lifecycle sequence asset when PlantUML is available, then produces `workstream_architecture_brief.pdf`.
