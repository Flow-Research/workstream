# Plan: WS-XINT-001 Lifecycle Boundary Reconciliation

## Approach

Publish one planning-only coordination PR that gives all parallel initiatives a
single immutable vocabulary for ownership, activation, typed capabilities,
transactions, and release gates. Keep runtime work in each owning initiative.

## Canonical delivery protocol

```text
AUTH registration checkpoint
  - closed ActionId and PermissionId mapping
  - AUTH activation custodian
  - principal class and typed context contract
  - planned and non-executable

Feature hidden-behavior checkpoint
  - canonical feature row loader
  - bounded typed resource facts
  - lifecycle guards and transaction participant
  - routes/commands remain unavailable through the real kernel

AUTH activation checkpoint
  - evaluator and matched authority
  - exact static service-action matrix row or human grant path
  - transaction-local revalidation
  - active availability and end-to-end negative proof

Joint release checkpoint
  - all required actions active
  - all feature participants merged
  - startup parity and real API proof
```

## Transaction protocol

Mutation order is fixed:

```text
1. Resolve verified human or fixed service principal.
2. AUTH prepares action, locking human actor/link/grant rows or service
   actor/link rows and validating the exact static service-action matrix row.
3. Owning feature locks canonical product rows in documented order.
4. Owning feature recomposes final typed facts from locked rows.
5. AUTH evaluates exactly once and stages bounded decision evidence.
6. Feature participants stage lifecycle, audit, idempotency and outbox rows.
7. Request boundary or Celery execution commits once; dependency teardown rolls back abandonment.
8. Provider or external I/O runs only after commit from durable work.
```

No serialized, reusable, cross-session, or cross-action authorization handle is
accepted. Missing or stale authority, evidence failure, or feature conflict
produces zero canonical feature mutation.

## Boundary sequence

### AUTH and ART

Transfer complete activation custody, provision exact services, build inactive
ART admission/verification/recovery/operator behavior, then activate internal
and Operator actions independently through AUTH. AWS provider release remains a
separate ART live-proof gate.

### AUTH project roles and fixed services

Replace the combined contributor-role model with independent `submitter`,
`reviewer`, and `adjudicator` ProjectRoleGrants before AUTH-10 creates the grant
table. The adjudicator grant creates no adjudication capability until WS-REV
defines the lifecycle and AUTH activates exact adjudication actions. Add the
missing fixed-service runtime-admission chunk after controlled provisioning
and before any ART, REV, or CON protected service command executes. The exact
owner actions are in `AUTH_ROLE_SERVICE_HANDOFF.md`.

### ART and REV

ART supplies typed packet-read, evidence-intake, binding, verification, and
recovery capabilities. REV supplies canonical lease, packet membership, finding,
response, and decision context. AUTH authorizes the review action; neither side
creates a generic artifact-retrieval permission.

### AUTH and REV

AUTH registers planned review actions and typed context contracts. REV and its
required CON participants build hidden behavior. AUTH then integrates evaluators
and activates exact actions. REV never queries grants or activates availability.

### REV, AUTH and CON

The final Review mutation is authorized once through AUTH, then invokes the
CON participant in the caller transaction. CON independently authorizes only
its public reads, policy/binding administration, callbacks, and operations.
Core contribution creation performs no ART call and no external I/O.

The participant loads the `ContributionPolicyVersion` frozen on the originating
`TaskAssignment` or `ReviewLease`, creates the immutable `ContributionRecord`,
and evaluates the matching `ContributionRule`. Unpaid rules create no award.
Payable rules create immutable `CompensationAward` rows from
`ContributionAwardDefinition`; post-commit delivery routes money and
project-points instruments to separate adapters.

## Verification strategy

- Exact matrices cover every current ART action and fixed service identity.
- Independent project roles, role-specific invalidation consumers, and fixed
  service/human admission isolation are explicit.
- Handoffs identify resource owner, activation custodian, principal, action,
  canonical facts, transaction owner, and release gate.
- Stale scans reject wording that a feature chunk registers or activates AUTH.
- Markdown links and repository terminology checks pass.
- Required internal architecture, security/auth, product/ops, senior, QA, docs,
  and reuse reviewers approve the final planning SHA.

## Non-goals

- Runtime code, schemas, migrations, routes, providers, Celery tasks, grants,
  evaluators, availability changes, review behavior, contributions, payments,
  or external settlement.
- Editing another agent's active worktree.
- Starting any downstream implementation automatically.
