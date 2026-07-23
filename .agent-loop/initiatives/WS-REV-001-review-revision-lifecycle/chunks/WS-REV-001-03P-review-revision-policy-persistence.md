# Chunk Contract: WS-REV-001-03P - Review And Revision Policy Persistence

## Status

Active through signed `Loop Memory Explicit Event` run `30014647556` on exact
trusted main `bcf1292e1a591e3e84bf8ee212ee7191d80741fa`. Implementation remains
gated on pre-implementation review of this refreshed contract.

## Goal

Persist only REV-owned immutable ReviewPolicy and RevisionPolicy facts needed by
later routing, lease, decision, and human revision behavior.

## Risk

L1: policy immutability, duration/limit semantics, and later decision authority.

## Allowed files

```text
backend/app/modules/projects/models.py
backend/app/modules/projects/schemas.py
backend/app/modules/projects/repository.py
backend/app/modules/projects/service.py
backend/alembic/versions/0034_review_revision_policy_persistence.py
backend/tests/test_alembic.py
backend/tests/test_projects.py
docs/architecture_data_model.md
docs/template_project_guide.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/{DISCOVERY,PLAN,STATUS,REVIEW_LOG}.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/chunks/WS-REV-001-03P-review-revision-policy-persistence.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/reviews/WS-REV-001-03P-*.md
.agent-loop/merge-intents/WS-REV-001-03P.json
```

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
- Migration revision `0034_review_revision_policy` descends only from
  `0033_authorization_read_rate` and creates no second head.
- `ReviewPolicy` adds nullable positive integer
  `review_preference_window_seconds` and `review_lease_duration_seconds`,
  non-null integer `max_active_review_leases_per_reviewer`, non-null boolean
  `self_review_allowed`, non-null varchar(30) `reject_policy`, non-null
  varchar(30) `finding_evidence_requirement`, non-null boolean
  `legacy_incomplete`, nullable varchar(100) `configured_by_actor`, and nullable
  timestamptz `configured_at`.
- A non-legacy ReviewPolicy requires both positive durations, capacity exactly
  `1`, self-review exactly `false`, reject policy exactly `close_task`, evidence
  policy exactly `optional`, `required_for_blocking`, or `required_for_all`,
  decisions exactly the ordered JSON array `accept`, `needs_revision`,
  `reject`, required finding fields exactly the ordered JSON array
  `description`, `severity`, and non-empty configuring actor/time provenance.
  `finding_evidence_requirement` defaults to `optional` when omitted while
  accepting either other canonical token explicitly. Finding severity
  semantics are only `blocking` and `advisory` and are documented here for the
  later ReviewFinding owner; this chunk persists no finding.
- Existing ReviewPolicy rows are marked `legacy_incomplete=true`, receive no
  invented duration or actor, and preserve retired values losslessly by
  renaming `requires_second_review` to `legacy_requires_second_review` and
  `sla_hours` to `legacy_sla_hours`. New rows are database-constrained to
  `legacy_incomplete=false` and null archival fields. Only migration code may
  create a legacy row: the database role loses no runtime bypass because the
  trigger rejects inserts claiming `legacy_incomplete=true` after migration.
- `RevisionPolicy` retains positive integer `max_revision_rounds` and
  `revision_deadline_hours`, and adds non-null `legacy_incomplete`, nullable
  `configured_by_actor`, and nullable `configured_at`. Existing rows preserve
  retired values losslessly as `legacy_auto_reject_after_limit`,
  `legacy_allowed_resubmission_states`, and
  `legacy_reviewer_reassignment_rule`; new rows require those archival fields
  to be null. The runtime/API no longer accepts or exposes them. Exhaustion
  cannot synthesize a Review or reject.
- All five renamed archival columns are database/migration-only: request schemas
  reject them and responses never expose them. Responses expose
  `legacy_incomplete`; legacy ReviewPolicy durations/configuration provenance
  are nullable, while legacy RevisionPolicy retains its positive active
  limit/deadline plus nullable configuration provenance. Project create/update
  and active/detail reads never reinterpret an archival value as active policy.
- The migration adds these exact checks:
  `ck_review_policies_fixed_v01`, `ck_review_policies_decisions_v01`,
  `ck_review_policies_finding_fields_v01`,
  `ck_review_policies_evidence_requirement`,
  `ck_review_policies_complete_or_legacy`,
  `ck_review_policies_archival_shape`,
  `ck_revision_policies_positive_limits`,
  `ck_revision_policies_complete_or_legacy`, and
  `ck_revision_policies_archival_shape`. The JSON checks require the exact
  canonical arrays, thereby rejecting missing, extra, duplicated, reordered,
  null, blank, number, or object values. Direct SQL cannot insert an incomplete
  new policy or arbitrary decision/state token.
- No index, unique constraint, or foreign key changes. Existing project/guide
  uniqueness and composite guide-context foreign keys remain authoritative.
- Trigger function `guard_review_revision_policy_write` and triggers
  `trg_review_policies_guard_write` and
  `trg_revision_policies_guard_write` lock the matching `project_guides` row
  `FOR UPDATE`. Insert and update are permitted only while that guide remains
  an unactivated draft (`status='draft'`, `effective_at is null`, and
  `superseded_at is null`); delete is always rejected.
- Policy `id`, `project_id`, `guide_version`, and `created_at` are immutable from
  insert. Draft replacement updates the existing row only and may change only
  canonical policy fields plus configuring provenance. The trigger overwrites
  `configured_at` with database transaction time. It rejects moving a policy
  between guide/project contexts or editing archival fields independently.
  This consumes guide state read-only and changes no Guide route, activation
  rule, state, or response.
- A legacy draft may convert exactly once and atomically to a complete policy:
  `legacy_incomplete` becomes false, every canonical field becomes complete,
  all archival fields become null, and verified configuring actor/database time
  become non-null. Partial conversion, conversion after publication, or a
  complete-to-legacy transition is rejected. This deliberate replacement makes
  downgrade refuse because the original archival truth no longer exists.
- Draft replacement updates `configured_by_actor` and `configured_at` to the
  verified Flow `ActorContext.actor_id` and database time. Current project setup
  does not expose canonical `actor_profile_id`; 03P records this exact upstream
  attribution gap and does not add an AUTH lookup, compatibility path, or
  ActorProfile lifecycle rule.
- Two-session PostgreSQL tests race policy update/delete/insert against direct
  guide publication in both lock orders. The guide-row lock must serialize the
  operations: either the draft policy write commits before publication, or the
  post-publication write is rejected; no write observed against draft may
  commit after publication unnoticed.
- Downgrade is lossless only for migration-existing legacy rows. It locks
  `project_guides`, `review_policies`, then `revision_policies` in that exact
  order with `ACCESS EXCLUSIVE`, and refuses before DDL if any non-legacy policy exists,
  any archival field/provenance invariant drifted, or any protected row cannot
  reconstruct the exact 0033 columns. Refusal preserves schema, head, and data;
  clean prior-head upgrade/downgrade/re-upgrade restores every legacy value.
- Missing upstream Task/Assignment compatibility is reported to its owner and
  cannot be repaired in this chunk.
- 03P does not change Project Guide activation. Legacy policy completeness is
  exposed deterministically for the later REV queue-admission owner to reject;
  no activation test may assert new behavior.
- No review lifecycle transition is activated.

## Verification

```text
cd backend && .venv/bin/alembic heads
cd backend && .venv/bin/pytest -q tests/test_alembic.py -k review_revision_policy
cd backend && .venv/bin/pytest -q tests/test_projects.py -k 'review_policy or revision_policy'
cd backend && .venv/bin/ruff check app/modules/projects tests/test_alembic.py tests/test_projects.py alembic/versions/0034_review_revision_policy_persistence.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
git diff --check
```

Migration proof must cover prior-head upgrade, all direct-SQL constraints,
legacy-incomplete preservation, update/delete refusal, both-order independent
transaction publication races, every downgrade refusal predicate, lossless
clean-head downgrade/re-upgrade, and restoration of the sole head.
The full backend suite and repository/subsystem coverage gates run in GitHub
Actions, not locally.

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture,
reuse/dedup, docs, test-delta, and CI integrity.

## Stop

After focused proof, required internal reviews, trust-bundle publication, and
PR creation, stop. Do not begin 03A.
