# Architecture Boundaries

Workstream is a modular monolith. Boundaries exist so product rules remain
auditable and later adapters can be added without rewriting the core loop.

## Non-Negotiable Boundaries

- Routers translate HTTP to service calls; they do not own business rules.
- Services own lifecycle rules, permission checks, and domain decisions.
- Repositories own persistence queries and do not make policy decisions.
- Adapters isolate external systems such as Flow auth and future object storage.
- Project guide, submission artifact policy, checker policy, review policy,
  revision policy, and payment policy remain separate contracts.
- Pre-submit checks and post-submit/internal checker runs remain separate phases.
- Workstream engineering loop artifacts under `.agent-loop/` do not define
  Workstream product runtime behavior.

## Review Questions

- Did this mix engineering process state with product runtime state?
- Did this bypass service-layer lifecycle rules?
- Did this hide a policy decision inside persistence, tests, or UI copy?
- Did this create vague naming that could confuse operators, workers, reviewers,
  or engineering reviewers?
- Did this preserve locked v0.1 scope?

