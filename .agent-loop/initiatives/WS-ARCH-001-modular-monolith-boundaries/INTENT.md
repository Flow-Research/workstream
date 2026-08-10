# Intent: WS-ARCH-001 Modular Monolith Boundaries

## Human goal

Make the existing Workstream backend a strict modular monolith without pausing
v0.1 delivery or rewriting the repository at once. New work may span several
modules, but every fact and mutation must be implemented inside its owning
module and every cross-module call must use a typed public API.

## Success state

- The nine business modules and three supporting modules have one canonical
  ownership map.
- Cross-module runtime imports use only the target module's `api` package.
- Concrete implementations meet only in the application composition root.
- Existing private-import debt is frozen as exact source-to-target edges.
- Every feature chunk repairs the capabilities and debt edges it touches.
- No debt count grows, and final closure requires an empty private-import
  ledger.

## Non-goals

- No repository-wide move or package rename in one PR.
- No new distributed service, generic orchestrator module, service locator, or
  compatibility facade.
- No change to product ownership, authorization semantics, or lifecycle state
  merely to make imports pass.
- No empty public API packages before a real consumer needs them.

## Human decisions already made

- The existing modules are sufficient.
- A coordinating agent may implement code across modules, but code is placed
  only in the module that owns the behavior.
- Boundary debt is removed incrementally alongside delivery chunks.
