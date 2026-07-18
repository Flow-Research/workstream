# Intent: WS-POL-002 - Post-Submit Checker Foundation

## Human Intent

Make post-submit checkers work with the same discipline as the pre-submit
checker pipeline, while preserving the correct lifecycle boundary:

```text
Project guide/source material
-> setup-time agent derivation
-> trusted Workstream compiler
-> project-scoped PostSubmitCheckerPolicy
-> task locks the project policy
-> finalized submission runs deterministic checks
```

The agent may help derive a constrained policy specification during project
setup. The agent must not judge worker submissions at runtime. Runtime
submission evaluation is performed by deterministic Workstream checkers under a
locked project policy context.

## Product Intent

Post-submit checks answer whether a finalized submission is ready for human
review. They do not replace reviewer judgment and they do not create product
review decisions.

The user-facing review decision values remain:

- `accept`
- `needs_revision`
- `reject`

Post-submit checker routing may internally produce:

- `allow_review`
- `needs_revision`
- `task_setup_blocked`
- `checker_retry`

Only worker-fixable checker failures surface as `needs_revision`. Setup defects
and trusted checker infrastructure failures remain internal repair routes.

## Architecture Intent

Workstream already has a durable post-submit checker gate:

```text
finalize submission
-> evaluation_pending
-> CheckerRun
-> review_pending | needs_revision | internal repair route
```

This initiative strengthens the setup side of that gate. Today,
`PostSubmitCheckerPolicy` exists and is locked into tasks/submissions, but the
project-specific policy is still too manual compared with the pre-submit
pipeline. The new work must derive, validate, compile, approve, lock, expose,
and prove the post-submit policy with the same zero-trust shape as pre-submit.

## Non-Negotiable Boundaries

- Post-submit checker policy is project-scoped, not task-specific.
- Tasks lock references to the project policy; tasks do not derive or compile
  their own checker bundles.
- Workstream default post-submit checkers always run and cannot be weakened by
  project policy.
- A project-specific policy may add registered deterministic checkers or tighten
  severity/routing. It must not remove defaults.
- v0.1 must not execute arbitrary agent-generated checker code.
- Any unsupported project-specific checker requirement blocks setup or becomes a
  documented implementation gap; it must not silently pass.
- Project owner material remains human-facing guide/source input. Workstream
  owns the derived checker policy and approval workflow.
- No backward compatibility aliases are added for obsolete request fields.
- No frontend, blockchain, settlement, marketplace, external source adapter, or
  agent workspace expansion is included.

## Success Definition

The system is ready when a real project can show through APIs:

1. Guide/source material is captured as an immutable bundle.
2. Setup runs sufficiency first.
3. A post-submit policy derivation agent receives the same locked guide/source
   context and produces a constrained spec.
4. Workstream compiles that spec into a deterministic project
   `PostSubmitCheckerPolicy`.
5. Setup-authorized admin or project_manager can inspect and approve the
   generated post-submit policy through APIs under the current v0.1 bootstrap
   authorization boundary.
6. Guide activation requires the setup-approved compiled post-submit policy.
7. Tasks lock the policy id/version/hash/body.
8. Finalized submissions execute that locked policy and produce durable
   `CheckerRun` evidence.
9. Worker-fixable failures become `needs_revision`; setup/internal failures are
   hidden from workers and held for trusted repair.
10. A Terminal Benchmark-style live API drill proves the flow without database
    inspection.
