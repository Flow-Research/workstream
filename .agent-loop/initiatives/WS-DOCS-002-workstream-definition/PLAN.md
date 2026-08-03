# Plan

1. Establish one short canonical definition and one fuller end-to-end
   explanation in `README.md`.
2. Align `AGENTS.md`, `CONTRIBUTING.md`, the glossary, product brief,
   architecture lockdown, system architecture, current status, principles, and
   ADR 0001 with that definition.
3. Reframe the C4 context so Workstream is the governed lifecycle core, while
   Flow Identity is the current v0.1 external identity provider and source and
   consequence systems remain adapters.
4. Update the architecture brief source and regenerate its diagrams and PDF.
5. Preserve capability accuracy: distinguish the complete product model from
   what is implemented on `main` and what remains deferred.
6. Run repository terminology, stale-contract, Markdown-link, generated-PDF,
   and diff checks, then focused documentation, product/operations,
   architecture, and senior-engineering reviews.

## Definition Strategy

Use the following short definition consistently:

> Workstream is governed contribution infrastructure for coordinating,
> verifying, and recording work performed by humans, AI agents, or both. It
> transforms project-defined tasks, immutable submissions, deterministic checks,
> and authorized review into trusted ContributionRecords that applications,
> organizations, and economic systems can consume.

The README and product brief may carry the fuller definition and lifecycle. The
glossary, AGENTS entry, architecture brief, and diagram use compact forms with a
link back to the canonical explanation.

## Alternatives Rejected

- Retaining “Flow's infrastructure”: confuses a current adapter/deployment with
  the product boundary.
- Describing only “task evaluation”: omits governance, immutable artifact
  custody, contribution lineage, and downstream reuse.
- Claiming all possible source and consequence integrations are current:
  overstates v0.1 implementation.
- Rewriting historical evidence: damages traceability without improving current
  guidance.
