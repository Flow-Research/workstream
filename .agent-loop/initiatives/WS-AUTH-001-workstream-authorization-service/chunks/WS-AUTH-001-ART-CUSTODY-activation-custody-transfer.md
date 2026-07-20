# Chunk Contract: WS-AUTH-001-ART-CUSTODY - ART Activation Custody Transfer

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Atomically transfer all 25 current planned ART actions from historical feature
owner labels to the eight exact AUTH activation custodians in
`ACTIVATION_CUSTODY.md` without changing mappings or availability.

## Why this chunk exists

Merged XINT makes `ActionOwner` an AUTH activation custodian, while the current
25 ART rows still name historical feature owners. The metadata must be corrected
atomically before any ART action can be activated.

## Risk class

L1.

## SLA

P1. No ART activation may proceed while feature owner values remain in the
closed activation-custody registry.

## Allowed files

```text
backend/app/modules/authorization/catalogue.py
backend/tests/test_authorization.py
backend/tests/test_auth.py
docs/spec_authorization_service.md
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-ART-CUSTODY.json
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
```

## Not allowed

```text
ActionId, PermissionId, mapping, or availability changes
database migration or audit-history rewrite
resource composer, evaluator, route, command, ART behavior, or adapter changes
service provisioning or action activation
partial transfer or retained ART activation-owner enum
```

## Acceptance criteria

- Exactly the 25 canonical rows move to the eight AUTH owner values.
- The exact owner cardinalities are `8/3/3/6/1/1/1/2` for
  `WS-AUTH-001-ART-02D-OPERATOR`, `WS-AUTH-001-ART-02D-INTERNAL`,
  `WS-AUTH-001-ART-03`, `WS-AUTH-001-ART-04A`,
  `WS-AUTH-001-ART-04B`, `WS-AUTH-001-ART-05`,
  `WS-AUTH-001-ART-06A`, and `WS-AUTH-001-ART-06B`, respectively.
- All seven ART owner enum values are removed atomically.
- Frozen expectations independent of the modified catalogue bind the entry
  baseline to trusted `main` SHA `42a89b2deac8fc7672556a567a6124f8a4e5d423`:
  all 65 `(ActionId, PermissionId, availability)` tuples, 74 PermissionIds,
  65 ActionIds, 17 active and 48 planned actions, and the exact seven-identity,
  eleven-membership fixed-service matrix remain unchanged. This chunk has a
  zero-count and zero-availability delta.
- The exact 25-row owner map is frozen independently of
  `ACTION_DEFINITIONS`. Tests assert the eight new AUTH ART owners are present,
  all seven historical ART owners are absent, and the catalogue rejects a
  missing row, extra or duplicate row, wrong custodian, retained historical or
  dual custody, changed mapping, and changed availability.
- Every non-ART owner assignment remains exactly equal to the frozen trusted
  baseline, including all 19 REV rows and all seven historical REV owner enum
  values.
- `WS-AUTH-001-ART-02D-OPERATOR` is only a future AUTH activation-custody
  grouping. It grants no Operator authority and changes no permission, grant,
  evaluator, route, service identity, or availability. In particular,
  `artifact.verification_job.retry` remains planned and requires its own later
  evaluator, guards, and independent activation proof; read/status proof cannot
  activate retry.
- `ActionOwner` changes only in the typed catalogue. PostgreSQL and historical
  audit evidence have no owner field and receive no write or rewrite. Database
  and audit proof preserves the existing ActionId-to-PermissionId and evidence
  contracts; it does not invent persisted owner parity.
- Canonical documentation tables enumerate the same 25-row/eight-owner handoff
  and exact counts; documentation parity is checked deterministically in
  addition to the stale-wording scan.
- Every one of the 25 ART actions remains unavailable through
  `AuthorizationService.require()` using the real kernel. Each denial is
  `action_unavailable`, is sensitive, records the exact action and permission,
  and reaches no grant, evaluator, or ART behavior path.
- Alembic remains at the immutable entry head
  `0029_shared_transactional_outbox`; `backend/alembic/**` has no diff and no
  migration is added, edited, or allocated.
- This chunk transfers ART custody only. `WS-AUTH-001-REV-CUSTODY` remains a
  separate later human-started chunk, followed by separately started
  `WS-AUTH-001-PREP`; a combined ART/REV transfer is forbidden.

## Verification commands

```bash
(cd backend && .venv/bin/python -m ruff check app tests)
(cd backend && WORKSTREAM_DATABASE_URL=<test-db> .venv/bin/python -m pytest -q tests/test_authorization.py tests/test_auth.py --cov=app.modules.authorization --cov-report=term-missing --cov-fail-under=90)
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
test -z "$(git diff --name-only 42a89b2deac8fc7672556a567a6124f8a4e5d423 -- backend/alembic)"
(cd backend && test "$(.venv/bin/alembic heads | tr -d '[:space:]')" = "0029_shared_transactional_outbox(head)")
git diff --check
```

After push, the existing GitHub `Backend` workflow is the authoritative full
suite gate. It must pass its isolated backend suite, preserve repository-wide
coverage at or above 78 percent, preserve authorization-subsystem coverage at
or above 90 percent, and pass every existing workflow gate. The full suite runs
in GitHub Actions rather than on the user's slow local machine. This chunk does
not change workflows, scripts, exclusions, thresholds, or package commands.

## Implementation and test reuse constraints

- Extend the existing exact catalogue expectation and `_index_actions()`
  fail-closed tests in `backend/tests/test_authorization.py`; do not add a
  parallel catalogue validator or a second 65-row fixture.
- Add one hand-authored test-only 25-row ART custody fixture, independent of
  `ACTION_DEFINITIONS`, `ACTION_BY_ID`, enum-name prefixes, and production
  grouping logic. Reuse that one fixture for owner cardinality, mutation,
  real-kernel denial, and documentation-parity proof.
- Reuse the existing `_runtime_context()`, `_runtime_service()`, and decision
  evidence test abstractions for all 25 real-kernel denial cases; do not add a
  duplicate fake authorization stack.
- Add no production owner-family helper, prefix classifier, compatibility
  alias, or new registry abstraction for this metadata-only transfer.
- Documentation parity may consume the independent test fixture, but neither
  production metadata nor rendered documentation may derive the other's
  expected values.
- Existing tests may not be removed, weakened, skipped, xfailed, deselected,
  or have assertions relaxed. Every modified existing expectation retains all
  trusted-baseline assertions and changes only the exact 25 ART owner values.
  Tests removed, skipped, or xfailed by this chunk must remain zero.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
CI integrity, docs, reuse/dedup, and test delta.

## Human review focus

Verify the exact 25-row/eight-custodian ART transfer; all non-ART owners,
especially the 19 REV rows, remain unchanged; `OPERATOR` means a future custody
group rather than runtime entitlement; all 25 ART actions remain planned and
unavailable; and ART -> REV -> PREP remains separate and human-gated.

## Stop conditions

Stop if any mapping or availability must change, or if ART runtime behavior is
required.
