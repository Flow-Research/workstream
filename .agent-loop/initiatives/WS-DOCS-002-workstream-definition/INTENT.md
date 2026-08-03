# WS-DOCS-002: Canonical Workstream Definition

## Intent

Define Workstream as standalone, source-agnostic governed work and contribution
infrastructure. Explain its complete lifecycle, trust model, central
`ContributionRecord` outcome, and boundary from source applications, identity
providers, execution environments, and downstream economic systems.

## Why Now

The current canonical entry pages still call Workstream "Flow's task evaluation
and contribution infrastructure" and describe it primarily as a Flow internal
measurement system. That wording is narrower than the architecture and can make
an implementation-specific authentication adapter look like product ownership.

## Success

A new reader can understand:

- what Workstream governs from project definition through durable contribution;
- how exact artifacts, locked rules, authorization, checks, review, and history
  establish trust;
- why `ContributionRecord` is the durable fact consumed downstream;
- what source-agnostic means without claiming v0.1 source adapters already exist;
- why payments, points, reputation, datasets, reporting, and model training are
  consequences or consumers rather than controllers of core lifecycle truth;
- that Flow authentication is the current v0.1 identity adapter, not the
  definition or ownership boundary of Workstream.

## Non-Goals

- No runtime, API, database, migration, workflow, or CI behavior change.
- No claim that deferred adjudication, source adapters, reputation runtime, or
  external economic integrations are implemented in v0.1.
- No rewriting of imported reference specifications, internal review history,
  or superseded calendar plans.
- No change to the current Flow-token verification implementation.
