# Plan

## Strategy

Use an incremental strangler recovery, not a repository-wide rewrite.

```text
record existing private imports
        ↓
merge a no-new-violations gate and minimal AUTH public API
        ↓
resume the next approved product chunk
        ↓
repair only the AUTH capability that chunk touches
        ↓
migrate its exact consumers and remove ledger entries
        ↓
repeat until the ledger is empty
```

The boundary foundation changes no authorization behavior. Subsequent product
chunks cannot introduce a private AUTH import and must remove any existing
violation they touch.

## Target public boundary

```text
app/modules/authorization/
├── api/
│   ├── __init__.py
│   ├── action_ids.py
│   ├── commands.py
│   ├── decisions.py
│   ├── errors.py
│   ├── facts.py
│   └── ports.py
├── domain/          # introduced capability by capability
├── services/        # introduced capability by capability
├── persistence/     # introduced capability by capability
├── transport/       # introduced capability by capability
└── composition.py   # AUTH-only assembly from injected ports
```

The foundation creates only the smallest API package and enforcement needed by
the next consumer. It does not create empty directories or move runtime logic.

## Permanent dependency rules

- Outside AUTH, the only allowed AUTH runtime import prefix is
  `app.modules.authorization.api`.
- AUTH API contains typed identifiers, immutable facts, stable decisions,
  stable errors, opaque capabilities, and ports.
- AUTH API never exposes ORM models, repositories, SQLAlchemy sessions,
  concrete services, capability registries, or mutable product records.
- AUTH does not import product models, repositories, services, or routers.
- A feature locks its own rows and supplies canonical typed facts to AUTH.
- Application composition is the only concrete cross-module meeting point.
- Package-local AUTH composition may assemble AUTH-owned services using
  injected ports but cannot import concrete product implementations.
- No compatibility aliases, second evaluator, fallback factory, or service
  locator is introduced.

## Chunk sequence

### 01: Boundary foundation

One small PR:

- capture exact inbound and outbound private-import debt in
  `IMPORT_LEDGER.md`;
- add a static validator that rejects unlisted or newly added violations;
- create the minimal `authorization.api` namespace and public-surface leak test;
- add the consumer/API matrix;
- make CI run the boundary validator;
- move no product behavior and reorganize no large test suite.

The existing debt is temporarily accepted only because it is frozen and
machine-counted in both directions. Neither count may ever increase.

### First incremental repair: POL-03A

After 01 merges, resume the preserved POL-03A branch. Before its implementation
continues:

- identify its exact AUTH capability and consumers;
- expose that capability through `authorization.api`;
- place new capability behavior under cohesive AUTH service/domain files rather
  than adding to a container file;
- migrate only those consumers;
- remove their ledger entries;
- split only the tests required to prove that capability;
- preserve PREP, lock, transaction, evidence, replay, and denial semantics.

POL-03A therefore becomes the first small real-world proof that the boundary is
usable, not a reason to restructure all AUTH at once.

### Later feature chunks

Every AUTH/ART/POL/REV/CON chunk performs the same touched-boundary repair.
Untouched legacy imports remain frozen, not expanded. A feature PR may not
claim completion while its newly touched AUTH dependency remains private.

Before REV `allow_reviews` implementation starts, REV's required AUTH and ART
ports must already be public and clean. REV is never permitted to begin with a
private import exception.

### Final closure

After active feature paths have migrated their capabilities, bounded cleanup
chunks remove untouched legacy entries. Completion requires an empty ledger.

## Capability-level file organization

Files are split when a capability is actively repaired. Example:

```text
authorization/services/prepared.py
authorization/domain/prepared.py
authorization/persistence/prepared.py
tests/modules/authorization/services/test_prepared.py
tests/modules/authorization/integration/test_prepared_transactions.py
```

This preserves behavioral cohesion. It avoids both giant layer containers and
arbitrary file splitting performed only to satisfy a line count.

Changed/new code guardrails:

- one primary behavioral invariant per test;
- functions above 100 lines require explicit reviewer justification;
- new files above 1,000 lines are rejected;
- a touched legacy container cannot grow unless an architecture reviewer
  records why extraction would break a transaction boundary;
- helpers create state but do not hide the behavior or assertions under test.

## Foundation verification

Exact commands for chunk 01 are defined in its contract. It proves import
topology and public API safety, not runtime authorization behavior because no
runtime behavior moves.

Each later capability repair adds its own exact behavior-preservation ledger,
focused PostgreSQL/concurrency proof, and GitHub-hosted full coverage. Full
coverage is not run locally.

## Rejected alternatives

- Defer all recovery until REV: allows current work to deepen the violation.
- Move all AUTH code/tests in one PR: too broad to localize behavioral defects.
- Cosmetic file split: does not restore dependency direction.
- Permanent debt allowlist: makes the temporary bridge the architecture.
- Immediate HTTP/gRPC service: adds deployment complexity before the in-process
  contract is trustworthy.
