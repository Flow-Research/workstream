# Modular Monolith Architecture Boundaries

Workstream has nine business modules: `actors`, `authorization`, `projects`,
`tasks`, `artifacts`, `checkers`, `reviews`, `contributions`, and
`compensation`. It has three supporting modules: `audit`, `outbox`, and
`api_controls`. The machine-readable canonical registry is
`.ci/module-boundaries/registry.v1.json`.

Cross-module runtime imports target only `app.modules.<module>.api`. A public
API may expose immutable facts, commands/results, stable errors, opaque
capability protocols, and ports. It may not expose ORM models, repositories,
routers, database sessions, concrete services, kernels, registries, or other
private implementation surfaces. Concrete implementations meet only in an
explicit composition root: the application root or the exact owner adapter
root `backend/app/adapters/<owner>/__init__.py`.

Application-level paths are explicit rather than invisible exceptions:

- `backend/app/main.py` is the application composition root; its current
  product-private imports are frozen debt while future wiring consumes typed
  public ports;
- `backend/app/api/**` and `backend/app/wor&#107;ers/**` are delivery/composition
  entry code and must consume typed module APIs;
- the exact `backend/app/adapters/<owner>/__init__.py` file is that owner's
  adapter composition root and may import its own private implementation solely
  to construct typed public ports; this exception does not apply to nested
  adapter files, cross-owner private imports, product services, or delivery
  code;
- other `backend/app/adapters/**` files implement infrastructure capabilities
  and must consume module public APIs; their existing private imports remain
  frozen debt;
- `backend/app/interfaces/**` is legacy shared-contract debt, not a permanent
  public-contract namespace;
- `backend/app/db/models.py` is the sole metadata-discovery path and may import
  only module model declarations for SQLAlchemy registration. It gains no
  runtime service, repository, command, or authorization capability.

Except for the exact same-owner adapter-root rule above, all current private
imports in the first four surfaces are frozen exact debt.
Every application path is scanned, including paths outside `modules/`.
The one-time bootstrap is permitted only when the protected base contains
neither registry nor ledger and the installing change touches no
`backend/app/**` runtime source. After bootstrap, the current ledger must be a
subset of the protected-base ledger, so code and ledger cannot grow together.

The JSON private-edge ledger is an exact, temporary recovery inventory—not an
allowlist. Every entry binds a source file, target module, imported private
path, and repair owner. New or expanded edges fail CI. An unresolved ordinary
edge uses `owner-unresolved`; an authorization-affecting edge without ownership
requires `security-triage-required` and blocks the touched capability.

AUTH private edges are never copied into the general ledger. WS-AUTH-003 is
their sole canonical source; the general validator directly loads and verifies
that ledger through the existing AUTH parser and fails closed on disagreement.
Recovery is complete only when both protected debt ledgers are empty while the
validators remain enabled.
