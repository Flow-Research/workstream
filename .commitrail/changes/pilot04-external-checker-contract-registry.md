# [PILOT-04] Publish The External Checker Contract And Registry

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Publish one normalized pre/post external-checker
  request/result contract and one immutable, hidden, authorized digest-pinned
  checker registry without enabling external execution or changing current
  checker policy behavior.

## Intent

Deliver the smallest independent backend foundation from
[issue #491](https://github.com/Flow-Research/workstream/issues/491). Later
PILOT-04 and PILOT-07 work needs one stable protocol for digest-pinned external
images and one durable registration owner. Registration must not require a
Workstream deploy, but registration alone must grant no execution, policy,
activation or routing authority.

## Current behavior

Current CHECKERS contracts describe separate in-process pre-submit catalogue
entries and post-submit structural members. The installed post-submit handlers
share the constant `workstream-structural` implementation identity, so a code
change can alter behavior without changing an image digest. There is no durable
external-image registry, external execution protocol or authorized registration
operation.

The current pre-submit catalogue contains platform, policy and advisory entries,
while the post-submit catalogue contains eight structural definitions. Those
catalogues remain active in this chunk. The product owner has superseded those
lists with one future Workstream default checker and exactly four blocking
defaults:

1. Safe archive opening: exactly one valid ZIP, no encryption, symbolic links,
   special files or traversal paths, within platform size limits.
2. Exact receipt identity: Workstream computes SHA-256, verifies the stored
   bytes and builds the file manifest itself.
3. No high-confidence secrets: private keys, cloud credentials and API tokens
   are blocked.
4. Unchanged resubmission: the same files as the preceding attempt are blocked
   unless the task rules changed, such as after rebase.

Summary and attestation are warning-only. Project required-file, size and
forbidden-file checks belong to external project images. This first chunk
records the stable target and maps its later replacement proof, but does not
implement the default checker or remove either current catalogue.

PILOT-00 established only a feasibility input: a trusted launcher can use a
sealed digest-bound cache and bounded Kaniko build inside `runsc`, then run an
oracle in a separate sandbox. Its small fixture was not byte-reproducible across
builds, so the registry pins the approved OCI image digest and this contract
binds each attempt's exact verified material identity; it does not promise
reproducible builds or implement a launcher.

## Bounded change

### Allowed

- `.commitrail/changes/pilot04-external-checker-contract-registry.md` for this
  bounded intent, evidence and final disposition.
- `backend/app/modules/checkers/api/**` for one strict normalized external
  request/result and immutable registry port. Phase-specific identity must reuse
  the existing pre-submit preparation/attempt request and post-submit
  Submission/evaluation reservation/lease facts; no caller-selected replacement
  identity is allowed.
- `backend/app/modules/checkers/{models,external_registry}.py` for the append-only
  registry row and a hidden caller-transaction service/repository. Registration
  owns exact replay, current fresh authority and immutable publication only.
- The minimum CHECKERS registry registration action, resource context, direct
  authority adapter, audit projection and exports under
  `backend/app/modules/authorization/**` and `backend/app/modules/audit/**`.
  Registration is a system-scoped human Operator action; metadata is never an
  execution grant.
- `mcp_server/contracts/authorization_context_get.json` for the generated
  authorization-context ActionId enum/hash change caused solely by the new
  registration action.
- One next-linear migration, reconciled as
  `0029_external_checker_registry` after merged
  `0028_lifecycle_transitions`, plus Alembic environment/current-head, schema
  fingerprint/reset/inventory and model-registration consumers. If another
  migration lands first, this branch must reconcile to the actual main head and
  rename the unpublished revision rather than creating a second head.
- Focused contract, service, authorization, replay, concurrency and real
  PostgreSQL direct-SQL append-only tests. `backend/scripts/test_lane_catalogue.py`,
  `backend/tests/test_ci_lane_catalogue.py`, `backend/scripts/behavior_ownership.py`
  and `.ci/behavior-ownership/partition.v1.json` may register only the new
  checker modules and tests under their existing owners. The AUTH structural
  debt ledger may refresh only for the touched kernel/runtime structures with
  no exemption or growth.
- `docs/decision_0014_external_service_adapter_convention.md`,
  `docs/architecture_checker_framework.md` and the exact PILOT-04 current-status
  lines in `docs/roadmap_status.md` for the delivered registry/contract boundary
  and PILOT-00 qualifications, after shared-document coordination.

### Not allowed

- No external image build, pull, cache, sandbox, network, Docker socket, gVisor,
  `docker-dev`, SDK, launcher, scheduler, worker or composition-root execution.
- No policy compilation or approval binding, guide activation guard F-020 or
  default-checker implementation.
- No deletion, replacement, bypass or parallel execution of either built-in
  catalogue; no compatibility aliases, generic rule engine, plugin discovery,
  runtime service locator or caller-selected callable.
- No Submission creation, task import, routing, acceptance, remediation,
  contribution, compensation or payment behavior; no PILOT-02 application code
  or migration content.
- No public route or CLI, deployment, merge, issue closure, data rewrite,
  downgrade, prior evidence mutation, test removal/skip, CI weakening or work on
  held PILOT-05, PILOT-06 or PILOT-09.

## Design and decisions

The external protocol is one closed family. Every request binds an immutable
registry entry and configuration digest, one phase-specific owner identity and
bounded ART-verified read-only material descriptors. Pre-submit requests bind
the existing prepared generation, attempt and attempt-request digest and carry
no Submission identity. Post-submit requests bind the existing Submission,
evaluation request, attempt/result reservation and current lease. The result
echoes the complete request identity and uses the existing closed
`completed|infrastructure_failed` split. Missing implementation/material,
deadline/capacity exhaustion and malformed or oversized output use the existing
infrastructure-failure family; checker findings remain work results.

Registry entries are canonical immutable values containing capability ID and
version, phase, exact OCI `sha256` digest, configuration/input/output schema
identities and hashes, and CPU, memory, deadline and output ceilings. The entry
digest commits to every field. The database enforces identity shape,
uniqueness, authority closure and append-only behavior even for direct SQL.
Registration requires one caller-owned root transaction, fresh system-scoped
Operator authority over the exact request digest, and deterministic replay of
the original row. Same-operation or same capability/version substitution fails
closed without adding a row or consuming unrelated authority.

No execution factory is installed in this chunk. ADR 0014 records that a later
typed external-checker capability must use explicit composition-root
registration and that registry data selects immutable inputs, never Python
code, plugins or authority.

The later cutover has one strict journey: ART computes and verifies the ZIP
digest and manifest before exposing bounded private read-only files; one
Workstream default checker implements all four blocking defaults; every
required digest-pinned project pre-submit image must pass; and only then does a
caller-owned transaction create the immutable Submission, persist
`evaluation_pending` and commit initial dispatch. Work findings create no
Submission and leave the task `in_progress`; infrastructure outcomes remain
distinct and recoverable. Required post-submit images start only from that
committed custody. The target launcher and SDK are Rust, while registered OCI
images may use other implementations. Replacement proof must remove both
legacy catalogues without a parallel compatibility path. This chunk publishes
only the contract and registry needed by that future journey.

## Acceptance criteria

- [x] Strict pre-submit and post-submit external request variants accept only
  their real existing owner identities; pre-submit cannot carry a Submission,
  and post-submit cannot omit Submission/request/reservation/current-lease
  identity.
- [x] One normalized result validates the complete request/registry/config
  identity, separates completed findings from the existing closed
  infrastructure-failure family, and rejects extra, mismatched, oversized or
  phase-incompatible data.
- [x] An authorized system Operator can register one digest-pinned external
  checker in a caller-owned root transaction without a backend deploy; exact
  replay returns the same immutable entry and changed replay fails closed.
- [x] Registration stores capability/version/phase, OCI digest, exact schema
  identities and hashes, CPU/memory/deadline/output limits and a recomputable
  entry digest. Unknown schema identities, mutable image tags and unbounded
  limits are rejected before persistence.
- [x] Registration metadata grants no policy selection, activation, execution,
  task routing or result currentness. No public route or runtime factory is
  enabled.
- [x] Real PostgreSQL proves direct INSERT without exact authority closure,
  mismatched digest, duplicate identity, UPDATE, DELETE and TRUNCATE all fail;
  rollback and concurrent/replayed registration cannot create partial or
  duplicate rows.
- [x] Existing pre/post catalogue behavior and hashes remain unchanged; current
  schema graph remains one linear head and every schema fingerprint/inventory
  consumer recognizes the new append-only table and revision.
- [x] Current ADR/checker architecture/roadmap text distinguishes the delivered
  contract/registry from pending policy binding, default replacement, runtime,
  sandbox and catalogue cutover.
- [x] The future replacement map retains ART's safe-ZIP/platform-limit,
  server-computed receipt/manifest, high-confidence secret and task-rule-aware
  unchanged-work proofs as exactly the four blocking defaults; summary and
  attestation stay warning-only and project rules stay external.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, reuse, qa, test_delta,
  documentation, product_ops, database, ci_integrity
- Human review focus: Exact reuse of existing phase identities and failure
  vocabulary; immutable digest/schema/resource binding; real fresh Operator
  authority and replay; database append-only closure; absence of runtime or
  policy authority; one linear migration.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current owner and dependency map | Source inspection of CHECKERS pre/post APIs, ART pre-submit attempt custody, CHECKERS reservation/lease custody, AUTH actions and the PILOT-00 result | Complete; the product owner supplied the exact four-default cutover target | Runtime, policy binding, activation and catalogue cutover remain later chunks |
| Normalized external contract | `pytest` over `tests/checkers/external/test_contracts.py`, registry service, catalogue and bounded audit/schema consumers | PASS: 25 tests on `002deda91b2d0a6ed5b6e72ab4bd325f1e76c881`; Ruff also passed | Runtime transport and sandbox remain later chunks |
| Authorized immutable registry | Isolated PostgreSQL 16 `test_postgresql.py`, hostile-search-path migration and repeated-head test; metadata `/tmp/ws-pilot-checkers-491-final-head.json` | PASS: 7 tests in 141.60s at `002deda91`; database and role cleanup true | No public registration route in this chunk |
| Migration and schema custody | PostgreSQL 16 predecessor/head upgrade, hostile `search_path`, graph, fixed-baseline manifest, repeated upgrade, current fingerprint/reset/inventory | PASS: focused schema batch 5 tests in 136.96s and exact-head migration coverage above | Reconciled proof against merged lifecycle revision remains required before publication |
| Existing behavior unchanged | Exact current pre-submit catalogue identity/manifest and post-submit catalogue contract/hash tests | PASS: 19 tests in 11.22s; neither catalogue source nor hash changed | Catalogue replacement remains later PILOT-04 work |
| CI and owner registration | Exact lane inventory, deterministic checker-delivery partition and behavior-ownership catalogue regressions | PASS: 199 tests in 5.22s; four new test modules are assigned once and four new production targets are additive | Hosted full-suite timing remains CI evidence |
| Review repair: canonical bytes and replay | Focused real PostgreSQL numeric-schema, exact 65,536-byte schema, oversized-schema refusal and same-operation four-field substitution tests; metadata `/tmp/ws-pilot-checkers-491-review-repair-new2.json` | PASS: 2 tests in 29.15s; database and role cleanup true | Final exact-head replay remains required after the repair commit |
| Review repair: result closure | Focused contract and registry service tests for result self-revalidation, both-outcome byte ceilings and changed-payload replay discrimination | PASS: 16 tests in 1.55s | Runtime consumption remains a later chunk |
| Review repair: schema graph | Hostile-search-path registry upgrade, one-root/one-head graph, fixed baseline and repeated-head tests; metadata `/tmp/ws-pilot-checkers-491-review-repair-schema.json` | PASS: 4 tests in 93.21s; database and role cleanup true | Hosted full migration matrix remains CI evidence |

## Review findings

- Planning inspection found inconsistent historical default lists. The product
  owner supplied the superseding four-behavior list above; implementation and
  catalogue-removal proof remain later bounded PILOT-04 work.
- The structural-debt validator rejected a first mechanical AUTH ledger refresh.
  The final integration shrinks the touched oversized kernel, preparation
  function and runtime facade with no exemption or limit change.
- The fixed migration-0001 schema manifest rejected an attempted head-schema
  regeneration. That change was removed; the PostgreSQL 16 head fingerprint and
  reset inventory alone carry the new 0028 objects.
- Independent review found that the first checker digest reused a historical SQL
  canonicalizer whose decimal-number representation differs from Python, and
  that the schema-size SQL constraint counted JSONB display whitespace. The
  registry now owns one Python/SQL canonical representation for its schemas,
  specifications, requests, results, authority resources and size limits without
  changing historical policy hashes.
- Independent review also found that result/request binding trusted
  `model_copy` values and applied the registry output ceiling only to completed
  results. Binding now revalidates the result itself and applies the exact byte
  ceiling to both completed and infrastructure outcomes.
- Replay coverage did not discriminate a same-operation changed payload from an
  unconditional match. Focused service and PostgreSQL regressions now vary the
  registry ID, image, schema and resources with valid derived request digests and
  prove conflict, audit rollback and unchanged stored facts.
- Independent review found that JSON strings or object keys containing U+0000
  passed the DTO canonicalizer but PostgreSQL JSONB cannot store them. The
  checker canonical boundary now rejects U+0000 recursively while retaining
  ordinary Unicode and every other JSON-escaped control character.
- Reconciliation with the lifecycle-authority extraction initially retained
  prepared Operator filtering but omitted the registry action from the direct
  kernel dispatch, resource and role-filter classifications. The complete
  registry classification is restored and one direct-kernel regression binds
  system scope, exact resource dispatch and the Operator-only grant filter.

## Reconciliation

- Current-source reconciliation: Started from merged main
  `baa7ae7c1bce9c3769453620f4aa0b22fe13fe3e`, then reconciled after PR #516
  merged as `dfea06a33acf4657c0a58291670233ff6f1b1a1b` with linear revision
  `0028_lifecycle_transitions`. The registry revision moved from its unpublished
  `0028` identifier to `0029_external_checker_registry`; lifecycle authority,
  docs and custody remain intact and the combined graph has one head.
- Parallel-lane reconciliation: PILOT-02 owns task-import product/ART behavior
  and has handed migration authorship to this lane. Its DDL remains a later
  separate linear revision after this registry migration lands; no PILOT-02
  application files or schema are included here.
- Remaining risks: Default-checker implementation and replacement proof, policy
  binding, F-020, the Rust launcher/SDK and OCI-image runtime, verified-material
  private workspace, caller-atomic intake/public integration, hosted gVisor
  hardening, representative resource limits, cleanup after host loss and
  complete removal of both legacy catalogues remain future bounded work.
