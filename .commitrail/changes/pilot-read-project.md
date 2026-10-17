# [PILOT-READ-3] — Project Manager and Finance reads

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: A Project Manager reads a project's guides, guide documents, activation readiness, submissions, assignments, summary, task import batches and failed intake preparations, and Finance lists every contribution policy version, through ten read-only, separately authorized operations that project records the existing PROJECTS, TASK, CHECKERS, ART, compensation, CON and AUTH owners already keep.

## Intent

A Project Manager running a pilot needs to see the whole project, not one
known task at a time, and Finance needs every contribution policy version, not
only the current one. This change adds the C1–C9 and D1 reads from the PILOT
read-API issue, once, in the API, with one response shape for every client.

It is the third of three PRs for the issue (PR1 #575 stored the facts these
reads project; PR2 #577 added the contributor reads A1–A6 and the B3 task-list
filters, and is the template this change follows).

## Current behavior

- Guides: `POST /projects/{id}/guides` and the guide mutation, compilation,
  sufficiency and activation operations exist; `GET /projects/{id}/active-guide`
  reads only the active guide. No route lists guides, reads one guide with its
  declared documents and policy values, or reads back an uploaded guide
  document (only `POST .../documents/{document_id}/content` uploads one).
- Activation: `GuideActivationService.activate` checks every precondition and
  raises the first failure with its refusal code. There is no dry run.
- Submissions and assignments: management reads are per task
  (`GET /projects/{id}/tasks/{task_id}/submissions`, task detail). There is no
  project-wide submission or assignment list and no project summary.
- Task import: `GET /projects/{id}/task-import-batches/{batch_id}` reads one
  batch; there is no list.
- Intake preparations: PR2 lets a contributor read their own preparations on
  one task. Nothing lists a project's failed preparations.
- Contribution policies: `GET /projects/{id}/contribution-policies/current`
  and `/{policy_id}` read selected versions under Finance; there is no list of
  all versions.
- The manager task list `GET /projects/{id}/tasks` (with PR2's B3 filters) is
  the only project-wide management list.

## Bounded change

### Allowed

- Ten new active AUTH actions owned by `PILOT-READ-3` and mapped per
  `docs/operations_roles_permissions.md`: `project.guide.list`,
  `project.guide.read`, `project.guide.activation_readiness.read` and
  `project.guide.document.read` (`project.guide.manage`);
  `project.submission.list`, `project.assignment.list`, `project.summary.read`,
  `project.task.import_batch.list` and
  `project.submission_bundle_preparation.list` (`project.task.manage`), all
  Project Manager; `contribution.policy.list` (`compensation.policy.manage`,
  Finance Authority). One closed AUTH evaluator, its request, grant, position
  and port types, adapter and factory, read dispatch, audit resource types,
  runtime resource union, concealment mapping, catalogue counts and active
  boundary, docs and the MCP contract snapshot that embeds the action enum.
  The closed read dispatch returns the resource each read decision records,
  so the management evaluator can bind the summary's locked exact-project
  Finance grant into the decision digest: one kernel line unpacks it (the
  kernel shrinks by two lines and its frozen-debt ledger entry is
  regenerated); every other read family records the resource it was given.
  Migration `0051_project_reads` extends the closed audit action/permission
  vocabulary (the `0050_contributor_reads` precedent) and adds one read index,
  `ix_selected_pre_submit_runs_project_queued` on `selected_pre_submit_runs
  (project_id, queued_at DESC, id DESC)`, mirrored on the ORM model, which the
  C8 page needs to stay within the latency budget; it changes no data.
- Routes, composed in `app/api` from owner ports in one REPEATABLE READ
  response transaction run by one shared project management read runner
  (`app/api/deps/project_management_reads.py`: snapshot, authorize, read,
  validate, commit; `422 project_read_cursor_invalid`,
  `503 project_read_unavailable`; AUTH denials propagate to the concealment
  mapping). The snapshot and run steps live once in
  `app/api/deps/snapshot_reads.py`, which PR2's contributor read operation
  also uses with its own unchanged error codes: `GET /projects/{project_id}/guides`,
  `/guides/{guide_id}`, `/guides/{guide_id}/activation-readiness`,
  `/guides/{guide_id}/documents/{document_id}/content`, `/submissions`,
  `/assignments`, `/summary`, `/task-import-batches`,
  `/submission-bundle-preparations` and `/contribution-policies`.
- PROJECTS (work package 1): a guide list and guide detail read reusing the
  existing guide, document and review/revision policy responses and the latest
  setup run; an activation-readiness read that shares one conditions function
  with `GuideActivationService.activate` (activate raises the first unmet
  condition, readiness returns them all, without activation authority,
  consumption, replay reservation or writes; readiness takes the same row
  locks as the post-policy review read and holds them until its commit); ART: split the task guide document open into resolve
  and verify-and-stream so the guide document content read reuses it.
- TASK (work package 2): a project-wide submission list sharing the
  contributor submission row builder and evidence stamp, an assignment list
  sharing the A2 row builder and batched `read_task_revisions`, summary counts
  beside `count_work`, and a task import batch list with one grouped member
  count query; compensation: project award totals beside `read_award_totals`;
  CHECKERS: a project post-submit infrastructure-failure count.
- CHECKERS/ART (work package 3): a project-scoped selected PRE run query and
  the shared preparation projection with the contributor and a finding count,
  no findings or file contents; CON: a contribution policy version list
  beside the existing current and exact-version reads.
- Signed `limit`/`cursor`/`next_cursor` pagination bound to caller, project,
  resource, filters and order through the existing AUTH cursor codec.
- Test packages `tests/project_reads/` and the AUTH evaluator tests; CLI
  commands, decoders and integration fixtures; lane catalogue,
  behavior-ownership partition, docs and roadmap.

### Not allowed

- No product write, lifecycle rule or stored column; no migration beyond the
  audit vocabulary and the one C8 read index. No new status or outcome the owners do not already record
  (C1 exposes the stored guide statuses only).
- No change to who may read a single task, submission, guide or policy, and
  no change to activation itself beyond extracting its shared conditions.
- No disclosure to a contributor, Operator, Audit Authority or Access
  Administrator through these reads, and no award totals without an
  exact-project Finance Authority grant.
- No listing of these actions in `/actors/me/authorization-context`.
- No frontend, no MCP tool for these reads.

## Design and decisions

- Authority: one closed evaluator for all ten actions. The nine Project
  Manager reads accept only a current Project Manager grant covering the
  project (system or exact); `contribution.policy.list` accepts only a
  covering Finance Authority grant, the same scopes as the existing
  `contribution.policy.read`. The kernel locks actor, matched grant and
  Project in that order (for the summary: actor, Project Manager grant, any
  exact-project Finance grant, then Project); no contributor grant and no
  other administrative role is admitted. Every denial is the concealed 404.
- Guide and guide-document reads name the selected record as the AUTH
  resource inside the project; the owner proves the record belongs to the
  project after the decision and returns the concealed 404 otherwise, as PR2
  does for another contributor's preparation.
- Single-record and summary reads (C2, C3, C6, C9) accept no cursor. Paged
  reads require the cursor secret before any decision is recorded.
- The cursor position, grant and port types mirror PR2's contributor read
  seam. They are separate types because the request carries a project and
  resource rather than an actor-wide scope; the codec, digest shape and
  verification order are shared.
- Defaults chosen (pending user override):
  - C1 exposes the stored guide statuses `draft`, `active` and `superseded`;
    no `retired` guide status exists.
  - C3 assumes the current published contribution policy version; none is an
    unmet condition. Readiness evaluates the current selections it reads, so
    `selection_stale` (a displayed selection that no longer matches) cannot
    appear in a readiness answer and is not in the public reason enum;
    activation keeps it internally. A guide that is no longer a draft is
    reported as `guide_not_draft` with the refusal code activation raises for
    it (the post-policy lock admits only drafts).
  - C5 closed assignments use the A2 own-facts rule: a closed claim projects
    only the facts PR2 shows its contributor (decided below).
  - C6 `award_totals` is null without a current exact-project Finance
    Authority grant (a system Finance grant does not add them; the PILOT-10
    precedent) and a list (possibly empty) with one. The closed evaluator
    resolves and locks that grant after the Project Manager grant and before
    Project, and binds it into the recorded decision's resource digest
    (recomputable from the request and the candidate grant; the grant id
    itself is not stored); the Project Manager grant stays
    the matched grant. Acceptance rate is accepted over decided attempts
    (accepted, needs_revision, rejected); checker infrastructure failures
    count post-submit checker runs whose status is `infrastructure_failed`.
  - C9 answers `409 guide_document_not_uploaded` for a declared document with
    no uploaded original and `503 guide_document_integrity_unavailable` when
    the stored original fails verification; no bytes are served then.
  - `ContributionPolicyView` types `policy_status` (`draft`, `active`,
    `retired`) and `version_status` (`draft`, `published`, `retired`) as
    closed enums; this also tightens the existing current and exact-version
    read schemas.
  - C8 `outcome` accepts all four typed values (`pending`, `passed`,
    `failed`, `infrastructure_failed`).
  - The new actions are not listed in `/actors/me/authorization-context`.
- Decided by the maintainer (2026-10-17):
  - C5 lists a project's closed assignments with the A2 own-facts rule: a
    closed claim projects only the facts PR2 shows its contributor.
  - C6 award totals require an exact-project Finance Authority grant
    alongside the Project Manager grant, as the roles table states. The
    evaluator matches only a Finance Authority grant for this, so the
    Project Manager's `compensation.award.read` entry in `policy.py` grants
    nothing here; no current action consumes it, and aligning that role
    matrix with the roles table is a separate authorization change.
  - C3 readiness keeps activation's `FOR UPDATE` row locks for the length of
    one read (Human review focus) so readiness and activation cannot disagree.
- Latency budget: the PR2 budget applies, one list page or summary within
  1 second on 10,000 tasks and 20,000 submissions on the isolated PostgreSQL
  test database, with indexed queries and no per-row queries. C8 uses the new
  project/queued index; C4 and C5 order by a computed activity time, which no
  index can serve, so no assignment index is added. The C1 guide list and
  the D1 policy version list are low-cardinality per project and are not
  timed.

## Acceptance criteria

- [ ] Each endpoint is in the OpenAPI with its own action ID (roles per
  `docs/operations_roles_permissions.md`) and typed enums.
- [ ] Each endpoint has authorization tests: allowed role, denied role and
  concealed resource.
- [ ] Pagination keeps a stable order without gaps or duplicates, rejects a
  cursor reused with other filters, and `updated_since` returns exactly the
  changed rows.
- [ ] C5 `revision` equals the work-context `revision_context`.
- [ ] C3 shares activation's conditions: removing a shared check removes it
  from readiness (`test_disposition_check_is_the_one_activation_runs`), and
  PostgreSQL scenarios prove `unmet[0].code` equals real activation's refusal
  code, with no side effects, for `project_not_activatable`,
  `post_policy_not_approved`, `contribution_policy_unpublished`,
  `human_review_required_by_guide`, `guide_not_draft` and
  `checker_capability_missing` (with the same capability list).
- [ ] List pages and the summary stay within the budget on 10,000 tasks and
  20,000 submissions.
- [ ] CLI and MCP contract snapshots are current; the journey probe still
  passes.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: `security`, `architecture`, `qa`, `test_delta`,
  `reuse_dedup`, `documentation`
- Human review focus: the Project Manager coverage rule (system or exact) and
  the Finance-only policy list; award totals behind an exact-project Finance
  grant, resolved in the evaluator and evidenced in the decision digest
  through the read dispatch's returned resource (the one kernel line); the
  three maintainer decisions; C3 sharing activation's conditions without side effects.
  C3 row locks: readiness takes the same `FOR UPDATE` row locks as
  activation's checks (project, post policy and its lineage, active guide,
  review and revision policies, source snapshot items) and holds them until
  its response commits, so a Project Manager with a covering grant can delay
  a concurrent activation or guide/policy mutation for the length of one
  read, and a concurrent change that makes the read fail yields the
  retryable `503 project_read_unavailable`.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| AUTH evaluator and adapter | `tests/authorization/test_management_read_scope.py`, catalogue and audit contract tests | Recorded in the PR | PostgreSQL custody runs in the focused suites |
| Authorization, pagination, projection | Focused backend suites through `run_isolated_tests.py` on PostgreSQL 16 | Recorded in the PR | Hosted lanes run in CI |
| Scale | 10k-task/20k-submission latency test | Recorded in the PR | Hosted runner timing differs |
| CLI | `go build`, `go vet`, `go test` with Go 1.27.1, gofmt; CLI HTTP integration tests | Recorded in the PR | Hosted `cli-public-contract` runs in CI |
| Known test gaps | — | Open | C3 reasons beyond the listed PostgreSQL scenarios rely on the shared conditions path; the C8 PostgreSQL test discriminates `passed` from `failed` through the stored eligibility, and the scale test times `outcome=failed` over pending runs only; C6 exclusion of another project's awards is shown against an empty project, not a second awarded project |

## Review findings

Internal security, architecture, qa, test_delta, reuse_dedup and
documentation tracks at `b4b34a39a`.

- Fixed: C6 award-total disclosure was decided in the adapter after the
  decision, locked the Finance grant after Project and left no evidence (now
  resolved and locked by the closed evaluator in actor, grant(s), Project
  order and bound into the recorded decision digest; pure digest and
  caller-claim tests, a PostgreSQL audit test). `guide_not_draft` was
  unreachable (a non-draft guide now reports it with activation's refusal
  code; the dead post-lock branch is removed) and `selection_stale` was in
  the public readiness enum though readiness never returns it (removed).
  Missing proof: C3 `checker_capability_missing` parity with the capability
  list; a real `authority_revoked` closed assignment in C5; C6 totals over
  real awards against a SQL sum; C8 in the timed scale loop over 10,000
  seeded runs; the shared runner's REPEATABLE READ snapshot and its
  owner-fault 503 with rollback. Duplication: the runner's snapshot and run
  steps were a copy of PR2's (one shared helper); the CLI had three page-flag
  binders and three query encoders (one each). Docs said readiness reports
  every unmet condition (it reports the conditions it evaluates); the record
  stated the C6 default twice, claimed a table test for every C3 reason and
  called the issue complete with two OPEN decisions.
- Fixed on replay: the CLI's shared page query was named for contributor
  lists though management lists use it (renamed `PageQuery`); every list but
  the preparation lists accepted `--outcome` and PR2's contributor-list
  validation message gained outcome text (rejected outside preparations, PR2
  message restored, Go unit test); the timed preparations page did not prove
  the seeding (now asserts a full 100-item page and the empty `failed` page);
  the C6 test compared the port with the same grouped-sum SQL (now asserts
  the fixture's configured award quantities; two awards in one
  instrument/unit would need a second accepted contribution, since an award
  set holds one award per instrument); the docs said the evidence shows the
  disclosure (the decision digest binds the Finance grant and is recomputable
  from the request and the candidate grant; the grant id is not stored).
- Decided: the C3 `FOR UPDATE` row locks held until the response commits
  (Human review focus), accepted by the maintainer.

- External review at `82f88192`:
  - `shared_foundations_a` was interrupted at the 1500 s lane deadline after
    284 of 1,854 tests; no test failed. The lane evidence names the
    unfinished test,
    `test_real_authority_publication_and_retirement_serialize_with_validation[True-publish]`
    (shared contribution-policy lock serialization). PR3 changes no code on
    its validation, publication or lock path (its CON changes are the
    lock-free version list and an extracted view), and no backend code
    changed between the passing `9d4a21853` and `82f881927`. In the last 60
    hosted Backend runs, this was the only interruption of the lane; the
    other lane failures completed every test. Twenty-eight local runs of
    that test on PostgreSQL 16, with `faulthandler_timeout=150`, all passed
    in 77–175 s per group of four. Its cause is not established; the test
    bounds its two calls at 60 s, so a stall beyond that lies in fixture
    setup, cancellation cleanup or the final unbounded validation read.
    Complete hosted verification is the rerun on this head.
  - Decisions recorded as the maintainer's (Design and decisions).
  - Added the superseded-guide C1 and retired-version D1 list regressions.
  - D1 reads through `ContributionPolicyVersionListPort` and its own adapter
    instead of the policy operations port.

## Reconciliation

- Current-source reconciliation: stacked on PILOT-READ-2 (#577). The audit
  migration is `0051_project_reads` after `0050_contributor_reads`; the
  public schema fingerprint (`EXPECTED_PUBLIC_SCHEMA_SHA256`) is recomputed
  after the migration, including the new index, runs on PostgreSQL 16.
- Next usable boundary: with this change the PILOT read-API issue's reads
  are delivered, with the C5, C6 and C3 decisions made. Live human review and revision follow per the delivery priority.
- Retained state needing explicit handling: none known beyond PR2's retained
  selected PRE body note.
