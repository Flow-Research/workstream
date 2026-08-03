# Discovery

## Current Drift

- `README.md` and `AGENTS.md` define Workstream as Flow-owned infrastructure.
- `docs/glossary.md` repeats the same narrow definition even though it is a
  canonical terminology source.
- `docs/product_brief.md`, `docs/architecture_brief/workstream_architecture_brief.md`,
  and ADR 0001 retain the Flow-owned framing.
- The system-context prose and diagram place Workstream only inside the Flow
  ecosystem instead of showing Flow Identity as the current external identity
  provider.
- Current principles explain source independence and lifecycle ownership but do
  not make the trusted contribution fact and downstream-consumer boundary
  explicit.

## Existing Truth To Preserve

- `ContributionRecord` is immutable and produced only by the canonical review
  transaction: each valid review creates the reviewer record, and `accept`
  additionally creates the submitter record through `FinalAcceptance`.
- Identity and authority are separate; local grants and lifecycle guards decide
  product authority after external identity verification.
- Submitted artifacts and their bindings are immutable, content-addressed, and
  verified against exact bytes before trusted facts are published.
- Project guides and policies are versioned and locked into assignment, review,
  and contribution lineage.
- Review decisions are only `accept`, `needs_revision`, and `reject`.
- v0.1 is manual-first. External source adapters, adjudication runtime, and
  reputation projection remain deferred.
- Compensation is evaluated from immutable contribution lineage but does not
  define whether the contribution occurred.

## Current And Historical Boundaries

Current entry and architecture documents should be updated together. Historical
calendar plans, imported specifications, and internal reviews should retain
their original wording with their existing historical labels.
