# Chunk Contract: WS-REV-001-03P - Review And Revision Policy Persistence

## Status

Reconciled planning input to `WS-XINT-003-02A` and `02B`. It is not an independent
implementation path.

## Goal

Persist only REV-owned immutable ReviewPolicy and RevisionPolicy facts needed by
later routing, lease, decision, and human revision behavior.

REV owns field semantics, version identity, draft/active immutability, and the
facts later lifecycle code consumes. AUTH-12D2 owns authority, PREP, evidence,
and the only mutation surface. XINT-003-02A owns immutable identity/lineage;
02B owns the shared mutation activation.

## Canonical persistence path

Adopt the existing project `ReviewPolicy` and `RevisionPolicy` models/tables as
the sole records and upgrade them for immutable version provenance. Every
external mutation enters only
`ProjectPolicyMutationService.replace_review_policy()` or
`replace_revision_policy()`; that service owns authorization preparation,
grant/resource checks, final PREP consumption, and decision evidence. It alone
invokes the internal append-only persistence primitives
`ProjectRepository.add_review_policy_version()` or
`add_revision_policy_version()`. Those repository methods are never caller-
facing mutation APIs. Retire both repository `upsert_*` methods and
both `ProjectService._*_policy_model()` constructors. Do not add REV-local
duplicate models, tables, repositories, routes, aliases, or fallback writers.

The exact guide must still be a draft at final PREP consumption. Policy
versions selected by guide activation become immutable; changes thereafter
require a new draft guide/version.

## Risk

L1: policy immutability, duration/limit semantics, and later decision authority.

## Allowed files

The exact current-main project models, migration, policy schemas, canonical
writer service/repository, AUTH PREP integration, focused tests, and initiative
evidence must be fixed in the refreshed XINT-003-02A/02B contracts.

## Not allowed

- Task or TaskAssignment states/transitions.
- Project Guide, Submission, Checker, AUTH, ART, or CON owner implementation.
- Queue admission, leases, Reviews, decisions, revision execution,
  FinalAcceptance, routes, adjudication, reputation, or frontend work.

## Acceptance criteria

- ReviewPolicy and RevisionPolicy are immutable, versioned, and attributable to
  the exact upstream context they govern without mutating that context.
- Review preference/lease duration and human revision limits/deadlines have
  explicit typed semantics and are never inferred from unrelated SLA fields.
- Missing upstream Task/Assignment compatibility is reported to its owner and
  cannot be repaired in this chunk.
- No review lifecycle transition is activated.
- PostgreSQL proof refuses update/delete of immutable versions and proves stale
  draft/active guide, stale policy, revocation, replay, wrong grant/resource,
  copied handle, concurrent replacement, and rollback leave no partial policy
  or allowed decision evidence.

## Verification

Fix exact commands at start: focused model/migration tests, PostgreSQL
immutability/refusal proof, downgrade/re-upgrade proof, agent gates, and full
coverage through GitHub Actions.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, test-delta, and CI integrity.

## Stop

Do not implement this parent contract independently. Refresh and implement only
WS-XINT-003-02A/02B after an explicit user request.
