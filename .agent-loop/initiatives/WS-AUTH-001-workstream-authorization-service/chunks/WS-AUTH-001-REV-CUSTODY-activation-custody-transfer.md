# Chunk Contract: WS-AUTH-001-REV-CUSTODY - REV Activation Custody Transfer

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Atomically transfer all 19 current planned REV actions from historical feature
owner labels to the seven exact AUTH activation custodians in
`ACTIVATION_CUSTODY.md` without changing mappings or availability.

## Why this chunk exists

Merged XINT makes `ActionOwner` an AUTH activation custodian, while the current
19 REV rows still name historical feature owners. The metadata must be corrected
atomically without registering or activating later REV lifecycle actions.

## Risk class

L1.

## SLA

P1. No REV activation may proceed while feature owner values remain in the
closed activation-custody registry.

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-REV-CUSTODY.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
ActionId, PermissionId, mapping, or availability changes
registration of the four proposed lifecycle actions
database migration or audit-history rewrite
REV resource, evaluator, route, job, or lifecycle behavior changes
service identity invention or action activation
partial transfer or retained REV activation-owner enum
```

## Acceptance criteria

- Exactly the 19 canonical rows move to the seven AUTH owner values.
- The exact owner cardinalities are `2/5/3/1/1/5/2` for
  `WS-AUTH-001-REV-05`, `WS-AUTH-001-REV-06`, `WS-AUTH-001-REV-07`,
  `WS-AUTH-001-REV-08`, `WS-AUTH-001-REV-09A`, `WS-AUTH-001-REV-11`, and
  `WS-AUTH-001-REV-12`, respectively.
- All seven REV owner enum values are removed atomically.
- Frozen expectations independent of the modified catalogue bind the entry
  baseline to trusted `main` SHA
  `be2a79a243ec50049c37f1f634322a9b3ab895ba`: all 65
  `(ActionId, PermissionId, availability)` tuples, 74 PermissionIds,
  65 ActionIds, 17 active and 48 planned actions, and the exact seven-identity,
  eleven-membership fixed-service matrix remain unchanged. This chunk has a
  zero-count, zero-mapping, zero-availability, and zero-service-matrix delta.
- The exact 19-row action, permission, owner, and `planned` map is frozen in one
  hand-authored test-only fixture independent of `ACTION_DEFINITIONS`,
  `ACTION_BY_ID`, owner enums, identifier prefixes, grouping logic, and
  documentation. Tests assert all seven new AUTH REV owners are present, all
  seven historical `WS-REV-*` owner values are absent, and catalogue
  construction rejects a missing row, extra or duplicate row, wrong or swapped
  custodian, retained historical or dual custody, changed mapping, and changed
  availability.
- Every non-REV owner assignment remains exactly equal to the frozen trusted
  baseline, including all 25 merged ART AUTH custody rows. The four proposed
  REV lifecycle actions remain absent from the registered catalogue.
- `ActionOwner` changes only in the typed catalogue. PostgreSQL and historical
  audit evidence have no owner field and receive no write or rewrite. Database
  and audit proof preserves the existing ActionId-to-PermissionId and evidence
  contracts; it does not invent persisted owner parity.
- Canonical documentation tables enumerate the same exact 19-row,
  seven-custodian handoff and cardinalities. Documentation parity is parsed and
  checked deterministically in addition to stale-wording and Markdown-link
  scans. Custodian labels grant no reviewer, Operator, or service authority.
- Every one of the 19 REV actions remains unavailable through
  `AuthorizationService.require()` using the real kernel. Each denial is
  sensitive `action_unavailable`, records the exact action and permission, is
  not revalidated, records one bounded denial event, and reaches no grant,
  evaluator, revalidation, route, job, or REV behavior path.
- Alembic remains at the immutable entry head
  `0029_shared_transactional_outbox`; `backend/alembic/**` has no diff and no
  migration is added, edited, reserved, or allocated.
- Existing tests are not removed, skipped, xfailed, deselected, weakened, or
  rewritten to derive expected truth from changed production metadata or docs.
  Modified existing expectations retain all baseline assertions and change only
  the exact 19 owner values.
- This chunk transfers REV custody only. `WS-AUTH-001-PREP` remains a separate
  later human-started chunk; combined REV/PREP work is forbidden.
- Exactly one schema-v2 merge intent is added for this chunk, naming only the
  declared same-initiative `WS-AUTH-001-PREP` successor with a separate explicit
  human start.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
test -z "$(git diff --name-only be2a79a243ec50049c37f1f634322a9b3ab895ba -- backend/alembic)"
(cd backend && test "$(.venv/bin/alembic heads | tr -d '[:space:]')" = "0029_shared_transactional_outbox(head)")
git diff --check
```

After push, the unchanged GitHub `Backend` workflow is the authoritative full
suite gate. It must pass its isolated backend suite, preserve repository-wide
coverage at or above 78 percent, preserve authorization-subsystem coverage at
or above 90 percent, and pass every existing workflow gate. The full suite runs
in GitHub Actions rather than on the user's slow local machine. This chunk does
not change workflows, scripts, exclusions, thresholds, coverage configuration,
or package commands.

## Implementation and test reuse constraints

- Extend the existing exact catalogue expectation and `_index_actions()`
  fail-closed tests in `backend/tests/test_authorization.py`; do not add a
  parallel catalogue validator or a second 65-row fixture.
- Add one hand-authored test-only 19-row REV custody fixture and reuse it for
  owner/cardinality, mutation, real-kernel denial, and documentation-parity
  proof.
- Reuse the existing ART custody table parser pattern, `_runtime_context()`,
  `_runtime_service()`, and decision-evidence abstractions. Exploding
  revalidation, admin/grant, evaluator, and downstream dependencies must prove
  planned actions fail before dispatch.
- Add no production owner-family helper, prefix classifier, compatibility
  alias, new registry abstraction, evaluator, service identity, or matrix path.
- Documentation parity may consume the independent test fixture, but neither
  production metadata nor rendered documentation may derive the other's
  expected values.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
CI integrity, docs, reuse/dedup, and test delta.

## Human review focus

Verify exact 19-row custody transfer, unchanged mappings/counts, and zero
activation.

## Stop conditions

Stop if any mapping or availability must change, or if REV runtime behavior is
required.
