# [PILOT-04] Publish The External Checker Contract And Registry

- Initiative: None
- Durable disposition: Planned
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
- The minimum CHECKERS registry registration action, resource context, prepared
  authority adapter, audit projection and exports under
  `backend/app/modules/authorization/**` and `backend/app/modules/audit/**`.
  Registration is a system-scoped human Operator action; metadata is never an
  execution grant.
- One next-linear migration, currently reserved as
  `0028_external_checker_registry` after merged
  `0027_markdown_guide_media`, plus Alembic environment/current-head, schema
  fingerprint/reset/inventory and model-registration consumers. If another
  migration lands first, this branch must reconcile to the actual main head and
  rename the unpublished revision rather than creating a second head.
- Focused contract, service, authorization, replay, concurrency and real
  PostgreSQL direct-SQL append-only tests. Required boundary/lane catalogues may
  change only for these new exact test modules after coordination.
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

## Acceptance criteria

- [ ] Strict pre-submit and post-submit external request variants accept only
  their real existing owner identities; pre-submit cannot carry a Submission,
  and post-submit cannot omit Submission/request/reservation/current-lease
  identity.
- [ ] One normalized result validates the complete request/registry/config
  identity, separates completed findings from the existing closed
  infrastructure-failure family, and rejects extra, mismatched, oversized or
  phase-incompatible data.
- [ ] An authorized system Operator can register one digest-pinned external
  checker in a caller-owned root transaction without a backend deploy; exact
  replay returns the same immutable entry and changed replay fails closed.
- [ ] Registration stores capability/version/phase, OCI digest, exact schema
  identities and hashes, CPU/memory/deadline/output limits and a recomputable
  entry digest. Unknown schema identities, mutable image tags and unbounded
  limits are rejected before persistence.
- [ ] Registration metadata grants no policy selection, activation, execution,
  task routing or result currentness. No public route or runtime factory is
  enabled.
- [ ] Real PostgreSQL proves direct INSERT without exact authority closure,
  mismatched digest, duplicate identity, UPDATE, DELETE and TRUNCATE all fail;
  rollback and concurrent/replayed registration cannot create partial or
  duplicate rows.
- [ ] Existing pre/post catalogue behavior and hashes remain unchanged; current
  schema graph remains one linear head and every schema fingerprint/inventory
  consumer recognizes the new append-only table and revision.
- [ ] Current ADR/checker architecture/roadmap text distinguishes the delivered
  contract/registry from pending policy binding, default replacement, runtime,
  sandbox and catalogue cutover.
- [ ] The future replacement map retains ART's safe-ZIP/platform-limit,
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
| Current owner and dependency map | Source inspection of CHECKERS pre/post APIs, ART pre-submit attempt custody, CHECKERS reservation/lease custody, AUTH prepared actions and PILOT-00 result | Complete for planning; no implementation proof claimed | Final default-checker enumeration remains product-owner input |
| Normalized external contract | Focused strict-schema, phase-substitution, identity-substitution, result-family and size-bound tests | Pending | Runtime transport and sandbox remain later chunks |
| Authorized immutable registry | Real PostgreSQL service/replay/rollback/concurrency and direct-SQL mutation/refusal tests | Pending | No public registration route in this chunk |
| Migration and schema custody | Predecessor-to-head upgrade, graph/current/fingerprint/reset/inventory checks on PostgreSQL 16 | Pending | Revision number must be reconciled if another migration lands first |
| Existing behavior unchanged | Existing pre/post contract/catalogue hash and caller regression set | Pending | Catalogue replacement remains later PILOT-04 work |

## Review findings

- Planning inspection found inconsistent historical default lists. The product
  owner supplied the superseding four-behavior list above; implementation and
  catalogue-removal proof remain later bounded PILOT-04 work.

## Reconciliation

- Current-source reconciliation: Started from merged main
  `697a321b7691633ddb2b81cc173d6b3e193ed9f2`, whose linear migration head is
  `0027_markdown_guide_media`. Open PR #516 still carries a conflicting
  predecessor-based `0027_lifecycle_transitions` and must reconcile its own
  revision if it lands; this branch will recheck actual main before publishing.
- Parallel-lane reconciliation: PILOT-02 owns task-import product/ART behavior
  and has handed migration authorship to this lane. Its DDL remains a later
  separate linear revision after this registry migration lands; no PILOT-02
  application files or schema are included here.
- Remaining risks: Default-checker implementation and replacement proof, policy
  binding, F-020, external runtime, hosted gVisor hardening, representative resource limits, cleanup
  after host loss and complete catalogue cutover remain future bounded work.
