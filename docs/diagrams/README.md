# Workstream Architecture Diagrams

This diagram pack explains Workstream at two levels:

- the bounded v0.1 implementation that is being built now
- the broader Workstream ecosystem that can connect later to external origins, agent identity, task contracts, settlement rails, and portable reputation

The context and container diagrams use standalone PlantUML sources with explicit
boxes and relationships; no remote C4 library includes are required. The backend component view and task lifecycle sequence use Mermaid, rendered directly by GitHub.

## Diagram Index

- [System Context](workstream_context.md)
- [v0.1 Container View](workstream_v01_container.md)
- [v0.1 Backend Component View](backend_v01_components.md)
- [Task Lifecycle Sequence](task_lifecycle_sequence.md)
- [Future Identity, Task Contract, Settlement, And Reputation View](future_identity_payment_reputation.md)

## PlantUML Sources

- [workstream_context.puml](workstream_context.puml)
- [workstream_v01_container.puml](workstream_v01_container.puml)
- [future_identity_payment_reputation.puml](future_identity_payment_reputation.puml)

## Legend

- blue: current v0.1 Workstream implementation
- green: durable Workstream records
- gray: external people or systems
- yellow: later adapter boundary

## Render Locally

Install PlantUML or point `PLANTUML_JAR` at a local PlantUML jar, then run:

```bash
docs/diagrams/render_plantuml.sh
```

The rendered SVGs are written to `docs/diagrams/rendered/` and are committed so the architecture pages display directly in GitHub.

## Reading Order

Start with the [System Context](workstream_context.md) to explain what
Workstream is and what it does not own. Then use the
[v0.1 Container View](workstream_v01_container.md) to show the bounded v0.1
implementation. Use the backend component and lifecycle diagrams when the
discussion moves from product architecture into implementation design.
