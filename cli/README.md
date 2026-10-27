# Workstream CLI

An independent Go client for Workstream's public REST API, for humans and
agents using the terminal. It provides human self-profile reads and editing,
plus draft project/guide declaration and original upload, exact-project inspection, authority reads, manager task browsing and
administrative actor, identity-link and grant inspection and explicit writes,
active-guide/intake-policy inspection,
contributor work discovery, claim/start, locked guide documents and governing
context/intake requirements, explicit batch import/screen/release, Finance
policy management, explicit ZIP preparation/submission, checker findings,
system-Operator checker registration, terminal recovery and uncertain-delivery reconciliation, and
contribution-evidence exports and exact Audit Authority task reads:

Separate commands record human guide sufficiency diagnostics and warning
acknowledgements; neither approves policy nor activates a guide.

## Interactive contributor workspace

Run `workstream tui` in an interactive terminal using the same
`WORKSTREAM_API_URL` and `WORKSTREAM_TOKEN` environment as explicit commands.
`workstream tui --plain` uses ASCII, no application colors and no alternate
screen; a nonempty `NO_COLOR` also disables application colors. Interactive
cursor controls remain necessary. For redirected input/output or automation,
use the explicit commands below with text or `--output json`; the TUI refuses
non-terminal input/output and JSON mode before making an API request.

Start with your exact-grant projects, then browse **Ready**, **Mine** (active
assignments) and **Submissions**. Enter opens fresh contributor-safe task or
owned Submission detail. Active Mine details offer Context, Intake and Guide
sections after Overview. Submission detail offers Overview and paged Findings.
The header keeps the project, collection and active section visible. At
100×24 or larger, a stable left worklist and scrollable right detail pane keep
long instructions and acceptance criteria readable. Guide confirmation replaces
both panes with a scrollable exact-target review; smaller usable terminals
show one pane at a time, and `--plain` is always single-column. Below 40×10,
the workspace shows only resize/quit guidance and cannot confirm a download.
An unopened row previews only loaded-page facts; Enter makes a fresh exact read.
Each list fetches one page, and filtering searches only that loaded page. The
status line labels loaded rows, page/continuation and local observation time,
not a total or a server-wide search. Project membership, potential locked terms
and action hints are observations, not authority for a later operation.
Instructions and criteria lead task detail; exact IDs, hashes and decimal
terms remain available separately. Workstream rechecks each public read.

| Key | Action |
|---|---|
| Arrows / Enter | Select a row or scroll detail; Enter inspects freshly |
| Tab / Esc | Change section / go back or cancel |
| Shift+Tab | Previous collection or detail section |
| `1` / `2` / `3` | Go directly to Ready / Mine / Submissions from ordinary views |
| `a` in task Overview | Open Claim or Start when the freshly inspected task supports that action |
| `g` | Fetch the project picker again |
| `n` / `r` | Fetch the next page / refresh the current view |
| `/` | Filter loaded names/titles locally; Enter finishes and Esc cancels |
| `c` / `?` | Show inert CLI arguments / keyboard help |
| `d` in Guide | Enter an existing download directory; Enter reviews the scrollable exact target, `y` confirms |
| `q` / Ctrl+C | Quit and cancel outstanding client requests, not committed server effects; `q` is text during text entry, Ctrl+C always quits |

Claim and Start are separate deliberate actions through the existing public
API. Inspect an exact Ready task to claim it; inspect a claimed Mine task to
start it. Supply a UUID key you have saved outside this session, review the
exact action/actor/project/task/key, press `s` to acknowledge the save warning,
then `y` to confirm. Enter alone never sends the action. The workbench does not generate or persist these keys. Save the
action, task ID and key together for recovery; this slice omits the optional
reason. A read or displayed action is not write authority.

There is no automatic retry or claim-to-start chain. A lost response means
unknown outcome, not rollback. Explicit replay uses the unchanged action, task
and key (`p`, then review and acknowledge with `s` and confirm with `y`);
a later denial cannot prove the earlier request failed. Quit cancels
the client request, not any committed server effect. After restarting, use the
explicit CLI with your saved inputs and the same API origin and actor. Do not
substitute a fresh key or infer success from a refreshed list. Automatic
crash-safe recovery is not implemented.

The workspace does not prepare or submit ZIPs, export records, poll, acquire
tokens or save local history. Guide metadata is not proof of downloaded-byte integrity. In Guide,
select one document, enter an existing real directory and confirm its label,
document/task IDs, path, UUID filename, byte count and hash. Verified bytes are
published under that filename without overwriting an existing file. Cancelled
or failed downloads are not published.
PDF/Office documents are downloaded, not rendered or opened automatically.
Findings display each returned run's identity, current flag and checker evidence;
they do not imply the stored Submission outcome or acceptance. `n` fetches one
next findings page. Contribution facts, available through the explicit CLI,
do not establish payment or fulfillment.
Contribution evidence remains a manual CLI handoff: use
`contributions --project PROJECT_ID`. Displayed arguments never execute or copy
automatically.

A denial clears affected content; expired authentication clears the session's
work data. A failed current read clears its content and continuation and is
shown as unavailable, never as an empty queue or successful operation. Refresh
is deliberate. A confirmed write receipt remains distinct from a failed refresh;
minimal inert replay references do not restore protected task content. The
profile read may perform Workstream's existing actor
admission, last-seen and audit effects. This local interface does not establish
a deployed service, payment or complete submission/management workflows. See
the [terminal presentation contract](../docs/design/cli-terminal-experience.md).

## Explicit commands

| Command | Public API |
|---|---|
| `workstream whoami` | `GET /api/v1/actors/me` |
| `workstream profile update` | `PATCH /api/v1/actors/me` |
| `workstream admin actor show ACTOR_ID` | `GET /api/v1/actors/ACTOR_ID` |
| `workstream admin actor identity-links ACTOR_ID` | `GET /api/v1/actors/ACTOR_ID/identity-links` (one link object) |
| `workstream admin actor role-grants ACTOR_ID --scope system\|project [--project-id UUID]` | `GET /api/v1/actors/ACTOR_ID/admin-role-grants` |
| `workstream admin role-grants --scope system\|project [--project-id UUID]` | `GET /api/v1/admin-role-grants` |
| `workstream admin permissions` | `GET /api/v1/authorization/permissions` |
| `workstream admin role-definitions` | `GET /api/v1/authorization/admin-role-definitions` |
| `workstream admin service-actor provision --input FILE --idempotency-key UUID` | `POST /api/v1/service-actors` |
| `workstream admin actor suspend\|reactivate\|deactivate ACTOR_ID --input FILE --idempotency-key UUID` | `POST /api/v1/actors/ACTOR_ID/{action}` |
| `workstream admin identity-link revoke\|reactivate LINK_ID --input FILE --idempotency-key UUID` | `POST /api/v1/actor-identity-links/LINK_ID/{action}` |
| `workstream admin role-grants issue --input FILE --idempotency-key UUID` | `POST /api/v1/admin-role-grants` |
| `workstream admin role-grants revoke GRANT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/admin-role-grants/GRANT_ID/revoke` |
| `workstream contributions [--project UUID]` | `GET /api/v1/actors/me/contributions` |
| `workstream project contributions PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/contributions/export` |
| `workstream project access PROJECT_ID` | `GET /api/v1/actors/me/authorization-context?project_id=PROJECT_ID` |
| `workstream project list [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects` |
| `workstream project show PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID` |
| `workstream project create --name TEXT --slug TEXT --idempotency-key UUID` | `POST /api/v1/projects` |
| `workstream project guide create PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides` |
| `workstream project guide edit PROJECT_ID GUIDE_ID --input FILE --idempotency-key UUID` | `PATCH /api/v1/projects/PROJECT_ID/guides/GUIDE_ID` |
| `workstream project guide set-review-policy PROJECT_ID GUIDE_ID --input FILE --if-match ETAG --idempotency-key UUID` | `PUT /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/review-policy` |
| `workstream project guide set-revision-policy PROJECT_ID GUIDE_ID --input FILE --if-match ETAG --idempotency-key UUID` | `PUT /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/revision-policy` |
| `workstream project guide upload PROJECT_ID GUIDE_ID DOCUMENT_ID --file FILE --media-type MIME --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/documents/DOCUMENT_ID/content` |
| `workstream project guide setup PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/setup-runs/latest` |
| `workstream project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/compilations/COMPILATION_ID/proposal` |
| `workstream project guide approve-pre PROJECT_ID GUIDE_ID COMPILATION_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/compilations/COMPILATION_ID/pre-submission-approval` |
| `workstream project guide post-policy PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/compilations/COMPILATION_ID/post-submission-policies/POLICY_ID` |
| `workstream project guide approve-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID --input FILE --idempotency-key UUID` | Exact policy `POST .../post-submission-policies/POLICY_ID/approval` |
| `workstream project guide correct-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID --input FILE --idempotency-key UUID` | Exact policy `POST .../post-submission-policies/POLICY_ID/corrections` |
| `workstream project guide correct PROJECT_ID GUIDE_ID COMPILATION_ID --input FILE --idempotency-key UUID` | Exact compilation `POST .../corrections` |
| `workstream project guide dispatch-correction PROJECT_ID GUIDE_ID COMPILATION_ID --input FILE` | Exact saved correction `POST .../corrections/OPERATION_ID/dispatch` |
| `workstream project guide activate PROJECT_ID GUIDE_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/activate` |
| `workstream project guide list PROJECT_ID [--status draft\|active\|superseded] [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/guides` |
| `workstream project guide show PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID` |
| `workstream project guide readiness PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/activation-readiness` |
| `workstream project guide document PROJECT_ID GUIDE_ID DOCUMENT_ID --download DIR` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/documents/DOCUMENT_ID/content` |
| `workstream project active-guide PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/active-guide` |
| `workstream project guide sufficiency list PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/sufficiency-reports` |
| `workstream project guide sufficiency show PROJECT_ID GUIDE_ID REPORT_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/sufficiency-reports/REPORT_ID` |
| `workstream project guide sufficiency create PROJECT_ID GUIDE_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/sufficiency-reports` |
| `workstream project guide sufficiency acknowledge-warnings PROJECT_ID GUIDE_ID REPORT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/sufficiency-reports/REPORT_ID/acknowledge-warnings` |
| `workstream project guide artifact-policy list PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/submission-artifact-policies` |
| `workstream project guide artifact-policy show PROJECT_ID GUIDE_ID POLICY_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/submission-artifact-policies/POLICY_ID` |
| `workstream project guide artifact-policy create PROJECT_ID GUIDE_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/submission-artifact-policies` |
| `workstream project guide artifact-policy update PROJECT_ID GUIDE_ID POLICY_ID --input FILE --idempotency-key UUID` | `PATCH /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/submission-artifact-policies/POLICY_ID` |
| `workstream project guide artifact-policy effective PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/effective-submission-artifact-policy` |
| `workstream project guide pre-submit-policy PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/pre-submit-checker-policy` |
| `workstream project tasks PROJECT_ID [--status S] [--assignee UUID] [--import-batch UUID] [--updated-since TIME]` | `GET /api/v1/projects/PROJECT_ID/tasks` |
| `workstream project task PROJECT_ID TASK_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/TASK_ID` |
| `workstream audit task locked-context PROJECT_ID TASK_ID` | `GET /api/v1/audit/projects/PROJECT_ID/tasks/TASK_ID/locked-context` |
| `workstream audit task evidence PROJECT_ID TASK_ID [--limit N] [--cursor JSON]` | `GET /api/v1/audit/projects/PROJECT_ID/tasks/TASK_ID/evidence` |
| `workstream project task-requirements PROJECT_ID TASK_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/TASK_ID/submission-requirements` |
| `workstream project task-locked-context PROJECT_ID TASK_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/TASK_ID/locked-context` |
| `workstream project task-context PROJECT_ID TASK_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/TASK_ID/work-context` |
| `workstream project task-submissions PROJECT_ID TASK_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/tasks/TASK_ID/submissions` |
| `workstream project submission PROJECT_ID SUBMISSION_ID` | `GET /api/v1/projects/PROJECT_ID/submissions/SUBMISSION_ID` |
| `workstream project checker-runs PROJECT_ID SUBMISSION_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/submissions/SUBMISSION_ID/checker-runs` |
| `workstream project checker-runs PROJECT_ID SUBMISSION_ID --run RUN_ID` | `GET /api/v1/projects/PROJECT_ID/submissions/SUBMISSION_ID/checker-runs/RUN_ID` |
| `workstream project submissions PROJECT_ID [--task UUID] [--status S] [--submitter UUID] [--updated-since TIME] [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/submissions` |
| `workstream project assignments PROJECT_ID [--state active\|closed] [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/assignments` |
| `workstream project summary PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/summary` |
| `workstream project import-batches PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/task-import-batches` |
| `workstream project preparations PROJECT_ID [--outcome pending\|passed\|failed\|infrastructure_failed] [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/submission-bundle-preparations` |
| `workstream project task create PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/tasks` |
| `workstream project task screen PROJECT_ID TASK_ID --idempotency-key UUID [--reason TEXT]` | `POST /api/v1/tasks/TASK_ID/screen` |
| `workstream project task release PROJECT_ID TASK_ID --idempotency-key UUID --reason TEXT` | `POST /api/v1/tasks/TASK_ID/release` |
| `workstream project task repair-revision PROJECT_ID TASK_ID --idempotency-key UUID --reason TEXT` with exact parent pair or routing manifest | `POST /api/v1/projects/PROJECT_ID/tasks/TASK_ID/revision-context/repair` |
| `workstream project task-batch convert-csv --input FILE --out FILE` | Local CSV-to-JSON conversion; no API call |
| `workstream project task-batch source-declare PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/task-import-sources` |
| `workstream project task-batch source-upload PROJECT_ID SOURCE_ID --input FILE` | `PUT /api/v1/projects/PROJECT_ID/task-import-sources/SOURCE_ID/content` |
| `workstream project task-batch source-status PROJECT_ID SOURCE_ID` | `GET /api/v1/projects/PROJECT_ID/task-import-sources/SOURCE_ID` |
| `workstream project task-batch source-download PROJECT_ID SOURCE_ID --download DIR` | Authorized source status and `GET /api/v1/projects/PROJECT_ID/task-import-sources/SOURCE_ID/content` |
| `workstream project task-batch import PROJECT_ID SOURCE_ID --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/task-import-batches` |
| `workstream project task-batch status PROJECT_ID BATCH_ID` | `GET /api/v1/projects/PROJECT_ID/task-import-batches/BATCH_ID` |
| `workstream project task-batch screen PROJECT_ID BATCH_ID --idempotency-key UUID [--reason TEXT]` | `POST /api/v1/projects/PROJECT_ID/task-import-batches/BATCH_ID/screen` |
| `workstream project task-batch release PROJECT_ID BATCH_ID --idempotency-key UUID --reason TEXT` | `POST /api/v1/projects/PROJECT_ID/task-import-batches/BATCH_ID/release` |
| `workstream project role-grant issue PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/role-grants` |
| `workstream project role-grant revoke PROJECT_ID GRANT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/role-grants/GRANT_ID/revoke` |
| `workstream project role-grant list PROJECT_ID [--status active\|revoked] [--role submitter\|reviewer]` | `GET /api/v1/projects/PROJECT_ID/role-grants` |
| `workstream project role-grant show PROJECT_ID GRANT_ID` | `GET /api/v1/projects/PROJECT_ID/role-grants/GRANT_ID` |
| `workstream project role-grant candidates PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/contributor-candidates` |
| `workstream project contribution-policy current PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/contribution-policies/current` |
| `workstream project contribution-policy show PROJECT_ID POLICY_ID [--version UUID]` | `GET /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID` with optional `version_id` |
| `workstream project contribution-policy list PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/contribution-policies` |
| `workstream project contribution-policy create PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/contribution-policies/drafts` |
| `workstream project contribution-policy update PROJECT_ID POLICY_ID VERSION_ID --input FILE --idempotency-key UUID` | `PUT /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID/versions/VERSION_ID` |
| `workstream project contribution-policy publish PROJECT_ID POLICY_ID VERSION_ID --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID/versions/VERSION_ID/publication` |
| `workstream project contribution-policy retire PROJECT_ID POLICY_ID VERSION_ID --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID/versions/VERSION_ID/retirement` |
| `workstream operations checker registry register --input FILE --idempotency-key UUID` | `POST /api/v1/operations/external-checker-registry` |
| `workstream operations checker registry read ENTRY_ID` | `GET /api/v1/operations/external-checker-registry/ENTRY_ID` |
| `workstream operations checker retry-sources PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/operations/projects/PROJECT_ID/checker-retry-sources` |
| `workstream operations checker retry PROJECT_ID SOURCE_RUN_ID --reason TEXT --idempotency-key UUID` | `POST /api/v1/operations/projects/PROJECT_ID/checker-runs/SOURCE_RUN_ID/retry` |
| `workstream operations delivery list PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/operations/projects/PROJECT_ID/post-submit-deliveries` |
| `workstream operations delivery reconcile PROJECT_ID EVENT_ID --reason TEXT --idempotency-key UUID` | `POST /api/v1/operations/projects/PROJECT_ID/post-submit-deliveries/EVENT_ID/reconcile` |
| `workstream task ready PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/ready` |
| `workstream task prepare TASK_ID --assignment UUID --file ZIP --idempotency-key UUID` (revision: add predecessor and exact preparation ID/SHA-256) | `POST /api/v1/tasks/TASK_ID/submission-bundle-preparations` |
| `workstream task submit TASK_ID --assignment UUID --admission UUID` | `POST /api/v1/tasks/TASK_ID/submissions` |
| `workstream task submissions TASK_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/tasks/TASK_ID/submissions` |
| `workstream submission show SUBMISSION_ID` | `GET /api/v1/submissions/SUBMISSION_ID` |
| `workstream submission findings SUBMISSION_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/submissions/SUBMISSION_ID/checker-runs` |
| `workstream submission findings SUBMISSION_ID --run UUID` | `GET /api/v1/submissions/SUBMISSION_ID/checker-runs/UUID` |
| `workstream task preparations TASK_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/tasks/TASK_ID/submission-bundle-preparations` |
| `workstream task preparation TASK_ID PREPARATION_ID` | `GET /api/v1/tasks/TASK_ID/submission-bundle-preparations/PREPARATION_ID` |
| `workstream me projects` | `GET /api/v1/actors/me/projects` |
| `workstream me assignments [--project UUID] [--state active\|closed] [--updated-since TIME]` | `GET /api/v1/actors/me/assignments` |
| `workstream me submissions [--project UUID] [--task UUID] [--status S] [--updated-since TIME]` | `GET /api/v1/actors/me/submissions` |
| `workstream me summary [--project UUID]` | `GET /api/v1/actors/me/summary` |
| `workstream task show TASK_ID` | `GET /api/v1/tasks/TASK_ID` |
| `workstream task claim TASK_ID --idempotency-key UUID` | `POST /api/v1/tasks/TASK_ID/claim` |
| `workstream task start TASK_ID --idempotency-key UUID` | `POST /api/v1/tasks/TASK_ID/start` |
| `workstream operations task list PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/operations/projects/PROJECT_ID/tasks` |
| `workstream operations task locked-context PROJECT_ID TASK_ID` | `GET /api/v1/operations/projects/PROJECT_ID/tasks/TASK_ID/locked-context` |
| `workstream operations task start TASK_ID --reason TEXT --idempotency-key UUID` | `POST /api/v1/operations/tasks/TASK_ID/start` |
| `workstream task context TASK_ID` | `GET /api/v1/tasks/TASK_ID/work-context` |
| `workstream task guide TASK_ID [--download DIR]` | Work context, then assigned-task `GET /api/v1/tasks/TASK_ID/guide/documents/DOCUMENT_ID/content` for downloads |
| `workstream task requirements TASK_ID` | `GET /api/v1/tasks/TASK_ID/submission-requirements` |
| `workstream operations artifact bindings RESOURCE_TYPE RESOURCE_ID` | `GET /api/v1/operator/artifacts/bindings` |
| `workstream operations artifact replicas CONTENT_ID` | `GET /api/v1/operator/artifacts/contents/CONTENT_ID/replicas` |
| `workstream operations artifact receipts REPLICA_ID` | `GET /api/v1/operator/artifacts/replicas/REPLICA_ID/receipts` |
| `workstream operations artifact verification-job JOB_ID` | `GET /api/v1/operator/artifacts/verification-jobs/JOB_ID` |
| `workstream operations artifact recovery-attempt ATTEMPT_ID` | `GET /api/v1/operator/artifacts/recovery-attempts/ATTEMPT_ID` |
| `workstream operations artifact audit-events RESOURCE_TYPE RESOURCE_ID` | `GET /api/v1/operator/artifacts/audit-events` |
| `workstream operations artifact admission-usage PROJECT_ID` | `GET /api/v1/operator/artifacts/admission-usage` |
| `workstream operations artifact readiness` | `GET /api/v1/operator/artifacts/readiness` |
| `workstream operations artifact retry JOB_ID` (explicit scope, reason, key and CAS) | `POST /api/v1/operator/artifacts/verification-jobs/JOB_ID/retry` |

Workstream verifies the caller's Flow bearer and owns identity resolution,
authorization and lifecycle decisions. Reading a profile can admit a first-time
caller and update server-owned last-seen/audit data. Project access is a current
snapshot; each later API operation must independently authorize the caller.

## Read the system-covered project catalogue

```sh
workstream project list
workstream project list --limit 10 --output json
workstream project list --limit 10 --cursor PREVIOUS_NEXT_CURSOR --output json
```

This separate catalogue requires a current system-wide Project Manager,
Operator, Finance Authority, or Audit Authority grant. Access Administrator
alone, exact-project grants, and contributor grants do not authorize it.
The backend checks current authority on every page; the CLI does not infer
authority from a role, cached result, or cursor.

Each invocation requests one page with `--limit` 1–100 (default 50) and never
follows continuation automatically. JSON preserves the validated public
`{"items":[{"project_id":"…","name":"…","status":"draft"}],"next_cursor":null}`
shape. Rows contain no roles, guide, task, or payment details. Text prints
Project, Name, and Status for each row, then Next cursor; terminal controls
are escaped. Pass the opaque cursor unchanged with the same limit; null ends
continuation. Invalid, substituted, or stale-authority continuations fail
through the existing structured error output, without partial stdout.

`workstream me projects` still lists exact-grant projects and is not global
discovery. `project show` and `project access` remain exact-project reads.
Catalogue visibility is an observation, not permission for a later operation.

## Read and export contribution evidence

```sh
workstream contributions --output json
workstream contributions --project PROJECT_ID --type accepted_submission
workstream project contributions PROJECT_ID --recorded-from 2026-01-01T00:00:00Z --recorded-before 2027-01-01T00:00:00Z --output json
workstream project contributions PROJECT_ID --csv earned.csv
```

Self reads bind the current human on the server; there is no actor selector.
Project exports require a covering Project Manager or exact-project Finance
Authority. Every invocation calls the public API with fresh authority; owning a
Submitter/Reviewer grant alone does not authorize project export.

Both commands accept `--type accepted_submission|completed_review` and aware
RFC3339 `--recorded-from` (inclusive) / `--recorded-before` (exclusive) filters.
Times are normalized to UTC microsecond precision before dispatch. Omitted
filters select all authorized records. The paginated REST change exposes JSON
`next_cursor` and CSV `X-Workstream-Next-Cursor` for selections through 100,000.
The CLI follows either continuation internally with the same normalized filters
and a 1,000-contribution page limit. Cursors are transport details: the complete
JSON result retains `exported_at` from page one plus `items`, without exposing a
cursor or adding pagination flags.

Text and JSON retain every public source/acceptance identity and award, including
exact decimal strings and unpaid empty award sets. These are **earned facts,
not payment status**. A completed-review record is evidence of an actual Review;
reading existing records does not activate unfinished human review or its
revision workflow.

`--csv FILE` requests the server's formula-neutralized CSV, one row per award
or one row for an unpaid contribution. It preserves those exact bytes after
validation across every page, emits the server header once, writes a new 0600
file in an existing directory and refuses existing files or destination
symlinks. It never writes raw CSV to the terminal or reconstructs CSV from a
separate JSON read. `--output json` with `--csv` returns only
`{"format":"csv","saved":true}` after successful publication. JSON and CSV
are staged privately until traversal completes; later-page failures leave no
successful stdout or published/temporary export. Keep exported personal data
private.
Invalid destinations or empty explicit flags exit 2 (`invalid_arguments`);
local file creation/write/persistence/publication failures exit 1
(`file_io_error`). Text errors explain the failure without echoing paths.

Responses are bounded at 32 MiB with the existing 12-second read deadline.
Oversized, malformed, wrong-scope or credential-reflecting responses are errors,
not partial exports. Backend authorization errors and over-limit refusals remain
distinct from client response validation failures.

The table above is the delivered command inventory. Privileged `admin` reads
are separate from `whoami` and caller-owned `profile update`. Actor selectors
must be exact UUIDs; there is no actor enumeration. `identity-links` returns
one privacy-bounded link object despite the plural route. Both grant-history
commands require `--scope system|project`; project scope additionally requires
`--project-id UUID`, which system scope forbids. They accept optional `--status
active|revoked|all` (default active), `--limit 1..100` (default 50), and an
opaque `--cursor` from a prior page with the same selectors. Each invocation
fetches one page and sends the caller's bearer to the public API; the backend
checks current scope and authority. Grant histories and catalogues are
observations, not authorization for a later action. Output is text or complete
JSON, with bounded responses and no credential reflection.

PILOT-02 supplies the
[batch conversion/import/screen/release commands](#prepare-a-task-import-json-source)
in the same CLI; contribution-evidence reads do not depend on using batch import.
Submission preparation, creation, history and manager revision repair commands
are described below; human-review commands remain outside this CLI inventory.

## Read task audit context and evidence

```sh
workstream audit task locked-context PROJECT_ID TASK_ID --output json
workstream audit task evidence PROJECT_ID TASK_ID --limit 50 --output json
workstream audit task evidence PROJECT_ID TASK_ID --limit 50 --cursor '{"project_id":"...","task_id":"...","created_at":"...","event_id":"..."}' --output json
```

These are separate covered Audit Authority reads, not manager or contributor
views. Locked context contains historical lineage IDs, generations and hashes,
not policy bodies, work content or the manager-only checker summary. Evidence
returns only fixed lifecycle event facts, stored actor attribution and optional
assignment/authorization-decision references. Both commands require exact
project/task UUIDs; the server checks current authority on every request and
conceals absent, foreign and denied resources. A successful read is no grant for
a later page or write.

Evidence returns one page of 1–100 events (default 50). To continue, pass the
JSON object from `next_cursor` as one `--cursor` argument with the same project,
task and limit. The CLI validates its four-field structure and exact scope,
then forwards it unchanged; it neither follows pages automatically nor treats
the cursor as authorization. A page is one statement snapshot, not a durable
full audit export. Output remains bounded and terminal-safe. Keep audit output
private; it includes stored actor attribution.

## Build and use

### Install a released binary

The CLI release channel is [GitHub Releases](https://github.com/Flow-Research/workstream/releases).
When a `cli-vMAJOR.MINOR.PATCH` release is published, its initial supported
targets are Linux x86-64 (`linux-amd64`), Intel macOS (`darwin-amd64`), Apple
Silicon macOS (`darwin-arm64`), and Windows x86-64 (`windows-amd64`). Linux
ARM64 and Windows ARM64 are not part of this first contract. Use the archive
whose platform matches your host; a different architecture or OS will not run.
There is no package-manager or automatic-update channel.

### What publication means

Users download from the Releases page, not from an Actions run. Maintainers
create an approved annotated tag; GitHub Actions builds and tests all four
platforms, assembles the archives and checksums, then waits for independent
approval of the `cli-release` environment. Only after approval and successful
publication do those files become public release downloads. A tag or green
build alone is not a release. If no published CLI release is listed, use the
source build below. Maintainers should follow the
[release runbook](../docs/engineering/cli-release.md); users do not need to
approve or run that workflow.

### Verify your installation and connection

After verifying and installing the archive as described below, run
`workstream --version`. Configure `WORKSTREAM_API_URL` with your deployed API
origin and supply `WORKSTREAM_TOKEN` through your existing secret environment
mechanism, then run `workstream whoami` and `workstream me projects`.
The first confirms an authenticated self-read; the second lists exact-grant
project membership, which may legitimately be empty. Neither proves an entire
task lifecycle or grants management authority. Do not put tokens in commands,
screenshots or issue reports.

The connected local CLI journey has separately exercised manager-authored
setup, task work, ZIP intake, durable evaluation, unpaid automated acceptance
and contribution evidence with PostgreSQL, MinIO and Celery; see
[the journey evidence](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-43.md).
That proof is not hosted deployment verification or proof of human review.
The [capability ledger](../docs/roadmap_status.md) identifies those remaining
product boundaries. The interactive workspace exposes claim/start alongside
contributor reads and guide downloads; explicit commands remain the interface
for preparation, submission and the other supported mutations.

### Download and install

Download the exact platform archive and `SHA256SUMS` from the same GitHub
release over HTTPS. Compare the archive's SHA-256 with its exact filename line
in `SHA256SUMS` before extracting. On Linux/macOS, for example:

```sh
sha256sum -c SHA256SUMS --ignore-missing  # Linux; require exactly your archive to say OK
# macOS: shasum -a 256 ARCHIVE.tar.gz; compare the output manually to SHA256SUMS
tar -xzf ARCHIVE.tar.gz
mkdir -p "$HOME/.local/bin"
install -m 755 workstream "$HOME/.local/bin/workstream"
"$HOME/.local/bin/workstream" --version
```

On Windows, compare `Get-FileHash ARCHIVE.zip -Algorithm SHA256` with the
matching `SHA256SUMS` line, extract the ZIP, and put `workstream.exe` in a
user-owned directory on `PATH` (add `$HOME/.local/bin` to `PATH` on Unix if
needed). Keep the included `LICENSE`. `--version`
prints `vMAJOR.MINOR.PATCH+gFULL_COMMIT_SHA`; that SHA is the exact release
source commit. For upgrades, first retain the installed binary privately,
verify the new archive, then replace the binary. Rollback replaces it with a
previously verified binary; removal deletes the installed executable and any
PATH entry you added. The CLI does not store tokens or create state to migrate.

Checksums detect mismatch against the release page, not a compromised page or
repository account; these binaries are not cryptographically signed. The macOS
archives are currently unsigned and unnotarized, so platform security controls
may block them. Do not disable those controls automatically. A first release
has no prior published version to prove cross-release rollback compatibility.
Release automation and native smoke proof are prepared by
[WS-CLI-001-44](../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-44.md), but
until an approved tag and protected release run actually publish assets, use
the source build below; CI preview artifacts are not public releases.

If execution fails, check the archive suffix and host architecture first, then
compare the hash and run `--version`. If the CLI executes but an API call fails,
check the configured API origin and whether that deployed server supports the
requested public route/response contract; there is no server-version negotiation
or universal CLI/backend compatibility guarantee. Do not paste bearer tokens
into issue reports, command arguments or diagnostic logs.

### Build from source

Use Go 1.27.1, matching `go.mod` and CI. From this directory:

```sh
go build -trimpath -o /tmp/workstream-cli ./cmd/workstream
export WORKSTREAM_API_URL=https://your-workstream-api.example
# Supply WORKSTREAM_TOKEN through your existing secret environment mechanism.
/tmp/workstream-cli whoami
/tmp/workstream-cli project access PROJECT_ID --output json
/tmp/workstream-cli project show PROJECT_ID --output json
```

`WORKSTREAM_API_URL` is the API origin, without `/api/v1`, credentials, query or
fragment. HTTPS is required except for loopback HTTP during local development.
`WORKSTREAM_TOKEN` contains the caller's unprefixed bearer value. It is forwarded
unchanged in the Authorization header. Avoid putting tokens in shell history;
the CLI reads its environment and does not save credentials. Configure the API
origin you trust to receive that credential. Redirects and ambient HTTP proxies
are disabled; system certificate verification remains enabled.

The binary runs independently of Python, the backend source tree and MCP. The
[CLI initiative](../.commitrail/initiatives/WS-CLI-001/OVERVIEW.md) describes
subsequent public workflows and an optional TUI.

## Output and automation

Commands need no TTY or interactive prompts. Default human output escapes
terminal control characters in API text. `--output json` (or `-o json`) writes
the successful API object to stdout without a wrapper. Failures leave stdout
empty and write bounded error metadata to stderr; JSON errors use an `error`
object with `code`, optional HTTP `status`, and optional `correlation_id`.
For machine-readable argument errors, place `--output json` before the command;
flag parsing can stop at an invalid argument before reading later flags.
Raw error bodies and transport exceptions are not printed.
Server error codes and correlation headers containing the caller's bearer
are suppressed, including case-only reflections. Success responses require
valid UUID identities and non-null string array members. Project access compares
UUID identity rather than spelling, while sending the supplied selector unchanged
and preserving the successful API JSON.

Exit status is `0` for success, `1` for API/network/response failure, and `2`
for invalid arguments or configuration. JSON requests time out after 12 seconds;
JSON responses default to a 64 KiB bound (guide declaration and document-bearing
work context and grant history use 2 MiB wire bounds; exact guide proposals use 8 MiB;
single/current administrative guide inspection uses 16 MiB; its two historical
collections admit the backend's complete newest-100 response with a 4 MiB per-row
bound). Original downloads stream to private files,
bounded by the advertised byte count and ART's 512 MiB hard ceiling. Downloads
and original uploads allow up to two minutes for response headers and ten minutes overall,
including transfer; connection/TLS timeouts and redirect/proxy refusal remain.
Interrupted transfers are not reported as a digest mismatch or published. Requests
are not automatically retried by the CLI.
Use `--help`, `--version` and `completion bash|zsh|fish|powershell` without a
credential or network connection.

## Inspect a project

Use `workstream project show PROJECT_ID` for a project whose ID you know.
Workstream selects the response: an exact contributor grant receives only
`id`, `name` and `status`; applicable administrative authority receives those
fields plus `slug`, nullable `description`, `created_at` and `updated_at`.
The CLI prints only the returned fields and never chooses a projection from
cached roles. `project access` remains a separate snapshot, not a preflight
or an authorization token for `project show`.

Project selectors must be UUIDs of at most 100 bytes. Supported compact, brace and `urn:uuid:`
spellings are sent as one escaped path segment and compared by UUID identity.
Invalid selectors fail before any request. Success requires a complete public
response shape, with no duplicate or unknown fields, null required strings,
invalid timestamps or mismatched identity. JSON output preserves that API
object; text escapes terminal controls. Foreign or revoked authority remains
a server denial with empty stdout, not an empty successful project.
This command does not list projects, edit setup, activate guides or claim tasks.

## Explicit contributor-role decisions

```sh
workstream project role-grant issue PROJECT_ID --input issue.json --idempotency-key ISSUE_UUID -o json
workstream project role-grant revoke PROJECT_ID GRANT_ID --input revoke.json --idempotency-key REVOKE_UUID -o json
```

Issuance requires the exact public decision, including qualification evidence:

```json
{
  "target_actor_profile_id": "019f79b0-1111-7000-8000-000000000001",
  "role": "submitter",
  "qualification": {
    "skills_snapshot": {
      "availability": "available",
      "reference_ids": ["skill:analysis"],
      "unavailable_reason": null
    },
    "reputation_snapshot": {
      "availability": "unavailable",
      "reference_ids": [],
      "unavailable_reason": "no_record"
    },
    "prior_project_work_refs": [],
    "external_expertise_refs": []
  },
  "reason": "Approved project contribution"
}
```

Use `reviewer` for an independent Reviewer grant. The caller supplies real
evidence, including unavailable reasons; the CLI does not collect, score or
default it. Both availability objects require `unavailable_reason`, even when
null. Available evidence requires references and null reason; unavailable evidence
requires an empty reference list and `not_collected`, `source_unavailable` or
`no_record`. Reference lists are bounded to 20; prior-work references are UUIDs,
other references are the public bounded tokens, not URLs. Revocation accepts
only `{"reason":"Project participation ended"}`. Reasons are nonempty, at most
500 UTF-8 bytes, with no edge whitespace or control characters. Input is a
regular UTF-8 JSON file bounded to 1 MiB; unknown/duplicate members and malformed
required fields fail before sending. Original JSON is forwarded unchanged.

Each invocation sends one POST, not a preflight or a retry loop. AUTH verifies
current admission, exact-project manager authority, eligible targets and
self-protection, including on replay; the CLI never derives permission from a
receipt. Project Manager is an AdminRole, not a contributor role. Issuing a
Reviewer grant alone does not authorize claim/start or activate human review.

The complete seven-field receipt identifies the grant, qualification snapshot,
project, actor, role, status and version. Issue expects HTTP 201 with active/1
and binds project/target/role; revoke expects HTTP 200 with revoked/2 and binds
project/grant. No earlier read is used to infer the revoked grant's actor or role.
JSON preserves the exact valid response; text escapes terminal controls. Missing,
malformed, substituted or credential-reflecting success is `outcome_unknown`
with empty stdout. Retry only manually with unchanged selectors, file contents
and key. A read is observation, not rollback proof; an old issue replay after
revocation is denied by the backend's retained-state check. No unscoped actor
enumeration, automatic role assignment or AdminRole mutation is added.

### Discover possible grant targets

```sh
workstream project role-grant candidates PROJECT_ID --limit 50 -o json
```

This calls the existing exact-project, covered-Project-Manager candidate read.
Each count-free page contains only `actor_profile_id` and nullable `display_name`
for backend-selected active human candidates, plus nullable `next_cursor`; no
contact or identity-provider fields are disclosed. Continue explicitly with
`--cursor` and the same project and limit. The CLI neither interprets the
opaque cursor nor follows it automatically. Invalid or cross-project/limit
cursors are rejected by the backend, which checks current manager authority on
every request. JSON preserves the public response; text escapes terminal controls.

Candidates are possible targets, not qualification, eligibility decisions,
active grant holders or authority for a later write. Discovery never issues a
grant. Use the separate `role-grant issue` command with caller-supplied evidence
and a fresh backend decision; the page is not a global actor directory.

### Inspect retained contributor grants

```sh
workstream project role-grant list PROJECT_ID --status active --role submitter --limit 50 -o json
workstream project role-grant show PROJECT_ID GRANT_ID -o json
```

List returns exactly one count-free page: `items` and nullable `next_cursor`.
Continue explicitly with `--cursor` and the same project, status, role and limit.
Omit status/role to include both supported values; `all` is not a filter token.
These are live keyset pages, not a fixed-membership export. The CLI never follows
a cursor automatically or interprets/signs it; the backend rejects invalid or
query-mismatched cursors and rechecks current authority for each request.

Show reads the exact grant under its project. Both commands retain the complete
public qualification snapshot, grant provenance/reason and nullable revocation
facts, with no count, private contact data or identity-provider subjects. JSON
preserves the authorized response; text escapes terminal controls. Malformed or
substituted responses, normalized duplicate grant IDs, filter contradictions
and credential reflection fail with empty stdout. These reads require the
backend's covered Project Manager or Audit Authority, not a contributor grant.
They do not cache permission, authorize a later write, or establish rollback.

## Inspect contribution policies

```sh
workstream project contribution-policy current PROJECT_ID -o json
workstream project contribution-policy show PROJECT_ID POLICY_ID -o json
workstream project contribution-policy show PROJECT_ID POLICY_ID --version VERSION_ID -o json
workstream project contribution-policy list PROJECT_ID --limit 20 -o json
```

`list` returns every stored version of the project's policies, oldest first,
with its `draft`, `published` or `retired` version status and its created,
published and retired instants; continue with `--cursor` and the same
`--limit`.

These are Finance Authority reads, not Project Manager permissions. Workstream
requires current covering Finance authority and active admission for each call;
PM-only, foreign-project or withdrawn authority remains a concealed server denial.
Each command sends one public GET, without a preflight or automatic selector fetch.

`current` returns the aggregate ID and nullable published/open-draft version IDs.
`show` without `--version` uses backend selection: the published version takes
precedence over an open successor draft. Supply `--version` to inspect that draft
or an exact retained historical version. Retired aggregates are excluded from
current discovery but exact historical inspection remains authorized separately.
An explicitly empty or invalid selector fails before HTTP; UUID spelling is
preserved in the request and compared by identity in the response.

Both output formats retain all authorized fields: policy/version identity and
status, positive integer version number, complete rules and award definitions,
including binding IDs and exact decimal-string quantities. Empty drafts are
valid observations, not readiness. JSON preserves the API object; complete text
escapes terminal controls. Missing, null, unknown, duplicate, substituted or
credential-reflecting facts fail with empty stdout. These commands never publish,
retire, pay, activate a guide or authorize a later write.

## Manage contribution policies

Finance Authority can make four separate decisions:

```sh
workstream project contribution-policy create PROJECT_ID --input name.json --idempotency-key CREATE_UUID
workstream project contribution-policy update PROJECT_ID POLICY_ID VERSION_ID --input rules.json --idempotency-key UPDATE_UUID
workstream project contribution-policy publish PROJECT_ID POLICY_ID VERSION_ID --idempotency-key PUBLISH_UUID
workstream project contribution-policy retire PROJECT_ID POLICY_ID VERSION_ID --idempotency-key RETIRE_UUID
```

`name.json` contains `{"name":"Project contributions"}`. A successor draft keeps
the aggregate's existing name. `rules.json` replaces the complete draft graph:

```json
{"rules":[
  {"contribution_type":"accepted_submission","compensation_mode":"unpaid","definitions":[]},
  {"contribution_type":"completed_review","compensation_mode":"unpaid","definitions":[]}
]}
```

For a compensated rule, each definition contains `instrument_type` (`money` or
`project_points`), `unit_code`, exact string `quantity`, and `adapter_binding_id`.
Workstream checks currency/unit registration, binding eligibility and the complete
graph. The CLI preserves supplied quantities without rounding. Omitted
`definitions` retains the API's empty default. Input files are limited to 1 MiB;
unknown fields and malformed types fail before dispatch.

Use selectors from the returned receipt or an explicit policy read. Publication
replaces the previously published version; retirement ends the selected current
policy. Guide activation remains a separate manager decision. Each command sends
one request and requires current backend authority. No command automatically
fetches selectors, retries, activates a guide or issues payment.

Save the action, exact selectors, input contents and key together. If the outcome
is unknown, manually replay only that unchanged request. Reusing a key for changed
intent conflicts. Replay returns the original immutable event, even after later
publication/retirement, subject to current authorization. Both output formats
retain all receipt fields; malformed or mismatched success is an unknown outcome,
and a subsequent read cannot prove rollback.

Native proof extends the existing public guide-activation journey with empty
drafts, unpaid publication, simultaneous published/draft selection, exact history,
foreign stored policies/versions, and public Finance suspension/revocation with
restored positive controls. Policy/guide SQL snapshots remain unchanged by the
reads; legitimate AUTH read evidence is excluded. Compensated precision and
malformed nested definitions are process-boundary proof, not a new native payout
or compensated-policy certification. Full backend integration proof remains in CI.

## Declare a guide and its setup inputs

```sh
workstream project guide create PROJECT_ID --input guide.json --idempotency-key GUIDE_CREATE_UUID --output json
```

The regular UTF-8 JSON file contains the public guide-creation request, not the
guide document's contents or a storage URL. For example:

```json
{
  "version": "evaluation-guide",
  "change_summary": "Initial project instructions",
  "task_examples": [
    {"content": "Evaluate the supplied experiment's evidence.", "title": "Evidence evaluation", "labels": ["research"]}
  ],
  "documents": [
    {"label": "Guide.md", "media_type": "text/markdown"}
  ]
}
```

`version`, `task_examples` and `documents` are required. `change_summary` and
example `title` may be omitted or null; example `labels` defaults to an empty
array. Unknown/duplicate members, malformed JSON and null required fields or
array members are rejected. The file is sent unchanged; the API owns semantic
limits and validation. PDF, DOCX, PPTX and UTF-8 Markdown (`.md`) declarations
use the media types in OpenAPI. The API normalizes document-label whitespace;
example text is preserved.

The CLI bounds this input to 1MiB and this response to 2MiB because declarations
include example text and document selectors. These are client wire envelopes,
not backend policy limits. Existing operations retain their 64KiB response
limit and small mutations their 8KiB input limit.

The API checks current Project Manager authority for the exact project, including
manual replay. A successful HTTP 201 returns the complete draft creation receipt,
declared document IDs and `setup.status = awaiting_documents`. JSON output
preserves the response; text renders every field with terminal escaping.
Policy, activation, approval, effective and supersession fields must be null
in this fixed creation receipt, including stored replay.
The command does not upload files, poll setup, approve policies or activate a
guide. The stored creation receipt is not a live readiness or authority snapshot.

Retain the project selector, exact input contents and caller-owned UUID key.
There is no preflight, generated key or automatic retry, including HTTP/2 replay.
Changed input conflicts. Lost, malformed, redirected or unexpected replies
report an unknown outcome, not rollback; manually replay only the unchanged
input and key. A complete canonical 4xx is a known denial. Local file errors
never echo file paths, contents or OS error details.

## Edit a draft guide and select its review/revision policies

```sh
workstream project guide edit PROJECT_ID GUIDE_ID --input guide-edit.json --idempotency-key EDIT_UUID --output json
workstream project guide set-review-policy PROJECT_ID GUIDE_ID --input review-policy.json --if-match '"no-current-policy"' --idempotency-key REVIEW_UUID --output json
workstream project guide set-revision-policy PROJECT_ID GUIDE_ID --input revision-policy.json --if-match '"no-current-policy"' --idempotency-key REVISION_UUID --output json
```

`guide-edit.json` is a closed public PATCH body: `{}` leaves fields omitted,
`{"change_summary":null}` clears the draft summary, and a string sets it. A
review-policy input requires integer `review_preference_window_seconds` and
`review_lease_duration_seconds`; it may explicitly provide
`human_review_required` (otherwise the backend applies its documented default
or inherits the selected mode), `max_active_review_leases_per_reviewer`,
`self_review_allowed`, `reject_policy`, `finding_evidence_requirement`,
`requires_second_review`, `allowed_decisions`, and `minimum_finding_fields`.
For example:

```json
{"review_preference_window_seconds":3600,"review_lease_duration_seconds":1800,"human_review_required":false}
```

A revision-policy input requires integer `max_revision_rounds` and
`revision_deadline_hours`; it may supply `allowed_resubmission_states` and
nullable `reviewer_reassignment_rule`. For example:

```json
{"max_revision_rounds":7,"revision_deadline_hours":48,"reviewer_reassignment_rule":null}
```

Use `"no-current-policy"` only when that policy has no current selection. To
replace one, inspect `project guide show` and supply the exact quoted selector
`"POLICY_ID.GENERATION.HASH_HEX"`, using its selected policy ID, generation and
the 64 lowercase hexadecimal characters after `sha256:` in its policy hash.
The CLI sends `If-Match` exactly as supplied; it never fetches a new selector
or overwrites after a stale-precondition conflict. The server checks current
Project Manager authority, draft status and policy lineage for a new mutation.
An exact-key committed replay may return its historical receipt after a later
change; that receipt is not current guide readiness or policy-selection proof.
The two policies are independent; setting one does not approve or activate a
guide, and `human_review_required=false` is a backend-governed mode, not CLI
acceptance.

All three commands require a regular JSON file of at most 1MiB and a
caller-owned UUID idempotency key. The CLI preserves JSON field omission, null
where supported and full integer values, while backend validation decides
numeric and policy admissibility. JSON output is the complete validated public
response; text output escapes terminal controls. Retain the exact project,
guide, input bytes, key and (for PUT) `If-Match` for a deliberate replay.
Changed-input/key reuse and stale selection are known conflicts; dropped or
malformed responses leave the outcome unknown. No write is retried
automatically, and a read is not proof of later write authority.

## Upload a declared guide original

```sh
workstream project guide upload PROJECT_ID GUIDE_ID DOCUMENT_ID --file Guide.pdf --media-type application/pdf --idempotency-key UPLOAD_UUID --output json
```

Use the guide and document IDs returned by `project guide create`. Supply the
document's declared media type explicitly: PDF, DOCX, PPTX or UTF-8 Markdown as listed in
OpenAPI. The CLI sends raw original bytes, not extracted text, JSON or multipart.
It requires a nonempty regular file up to ART's 512MiB hard ceiling; Workstream
can enforce smaller configured document or aggregate limits. Files are hashed
and streamed through the same open descriptor without whole-file buffering.
Before confirming storage, the CLI rechecks that descriptor's size,
modification time and full hash. An observed change fails with
`guide_document_upload_source_changed`, `outcome_unknown: true` and no success
output, because the server may have stored the original bytes already. This is
not a filesystem lock or an immutable local snapshot.
Keep the file unchanged during the operation and any later manual replay.

The API owns current exact-project authority, declared-document membership,
immutable original storage and asynchronous setup continuation. Exact HTTP 202
with a complete five-field receipt matching the selected document and file
SHA-256/byte count establishes stored-original success only for `document_stored`
or `object_confirmed`. JSON preserves that receipt; text renders it safely.
Neither proves setup completion, policy approval or guide activation.

No preflight, redirect, proxy, generated key or automatic transport retry is
performed. Preserve the same project/guide/document selectors, original bytes,
media type and caller-owned key for deliberate replay. A complete canonical 4xx
is a known denial; dropped, malformed, mismatching or unexpected responses are
unknown outcomes. An otherwise valid unconfirmed-storage status also exits 1,
sets `outcome_unknown` and leaves stdout empty rather than reporting success.
Diagnostics never include file paths, contents or raw provider/transport errors.

## Inspect current guide setup

```sh
workstream project guide setup PROJECT_ID GUIDE_ID --output json
```

This reads the latest setup for that exact guide, rather than replaying its
initial creation receipt. The API owns current scoped diagnostic authority,
actor lifecycle, project/guide membership and compilation lineage. The CLI
makes one public GET with the caller's bearer; no polling, role preflight,
follow-up calls, setup execution or retry is added.

JSON output preserves the complete validated API object. Text renders all
fields with terminal escaping, including nullable diagnostic and compilation
selectors. UUID identities and timestamps are checked; the generation integer
retains the backend response range. A pending, blocked, failed or finalized
setup can be read successfully (exit 0); this is not a successful compilation,
policy approval, guide activation or authority for another operation.
Denials, malformed/substituted replies, oversized JSON and network failures
leave stdout empty and exit 1. The normal 12-second/64KiB JSON bounds apply.
Deliberate intake approval, evaluation approval and guide activation are separate
commands below; none is implied by reading setup status.

## Inspect an exact finalized guide proposal

```sh
workstream project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID --output json
```

Use the explicit finalized compilation ID from setup inspection. The command
makes one public GET and never substitutes the latest result, polls, fetches
documents, or executes a decision. Workstream owns fresh scoped manager
authority and exact project/guide/compilation membership.

JSON retains the complete public package: exact target and hashes, findings
with display-only source locations, requirement inventory, proposed intake
policy, pre-submission intake bindings, distinct post-submission evaluation
bindings, suggestions, notes and nullable approval/post-policy references.
Text starts with concise proposal and approval status, then renders the intake
policy, findings and evidence document numbers. It groups requirements into
PRE, POST and non-checker sections and expands each available engineering
specification into its inputs, ordered steps, pass conditions, coded failure
findings, positive/negative tests, execution budget, runtime dependencies and
infrastructure-failure behavior. Suggestions and every setup note follow those
requirements. Dynamic text remains terminal escaped; private runtime document
handles are not part of this public projection. Unknown/duplicate members,
missing/null required facts, malformed nested types or substituted identities
fail with empty stdout. Integer facts retain the backend range.

New checker requirements can carry a typed `check_specification` and a
`classification_rationale`. PRE specifications describe bounded work of at most
60 seconds before Submission creation; POST specifications describe background
work and may declare up to a one-hour budget. Both PRE and POST bindings can
show their exact catalogue parameters. Earlier retained proposals may omit the
two new requirement fields and empty PRE parameters; the reader preserves and
labels that absence without manufacturing content. When any new field is
present, its nested object remains closed and strictly validated.

Project file, expanded-package, compressed-archive and entry-count limits may
be null or omitted. The reader
preserves those values: absence means no additional project restriction, while
Workstream's platform upload and archive limits still apply. Explicit project
limits must remain positive integers within the backend range.

A blocked, warning-bearing or historical (`current=false`) proposal is still a
successful read (exit 0), not readiness or authority to approve, correct or
activate it. Post-submission policy inspection is a separate later operation
after upstream approval/derivation. No automatic decision, local catalogue
matching or digest recomputation is added. The existing 12-second deadline
applies; the 8 MiB wire bound accommodates the stored compilation's 4 MiB
envelope plus public target/projection overhead without raising other limits.

## Approve an exact pre-submission proposal

Inspect and retain the exact proposal first. Prepare the public approval request
from that displayed target; this separate preparation does not authorize it:

```sh
workstream project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID -o json > proposal.json
jq '{target: .target, acknowledged_warning_hashes: []}' proposal.json > approval.json
# Read the findings. Edit approval.json to acknowledge only the exact displayed
# warning_hashes you deliberately accept; the backend requires the complete order.
workstream project guide approve-pre PROJECT_ID GUIDE_ID COMPILATION_ID --input approval.json --idempotency-key APPROVAL_UUID -o json
```

`--input` is a regular UTF-8 JSON file of at most 1 MiB containing the public
`GuideProposalApprovalInput`, not the entire display package. It requires
`target`; omitted `acknowledged_warning_hashes` means an empty list, never
automatic acknowledgment. When replacing an earlier approval, supply both
`expected_previous_approval_operation_id` and
`expected_previous_approval_output_digest` from the inspected prior approval.
The CLI validates the closed wire shape and target/path membership, preserves
the original JSON bytes, and makes one POST with the caller's bearer and UUID
key. It does not refetch latest or decide currentness, authority, policy validity
or which warnings are acceptable. Workstream makes those decisions atomically.

The validated immutable receipt is printed in JSON or escaped text. Its four
record identities are RFC UUIDv7; its selected artifact policy and exact ordered
acknowledgments must match the request. Business digests are returned backend
facts, not recomputed client-side. Success establishes intake approval only:
post-submission policy approval and guide activation remain separate decisions.
The API can publish post-policy derivation after commit; this receipt does not
prove publication, post-policy job delivery, derivation or successful runtime checks.

There is no preflight, automatic retry or HTTP/2 body replay. A complete canonical
4xx is a known rejection; unconfirmed writes, including malformed/substituted
success, lost reply, redirect, oversized response or server error, exit nonzero
with empty stdout and JSON `error.outcome_unknown: true`. Text gives a manual
replay hint. Retain the exact project, guide, compilation, input contents and key
if retrying; do not mint a new key or change acknowledgment/previous-target
facts to recover an uncertain result. Replay still requires fresh backend
authority. The common 12-second/64 KiB response bounds apply.

Process tests prove request/receipt boundaries and no-replay uncertainty. A real
socket/Flow/PREP/PostgreSQL journey proves deliberate warning rejection, exact
approval/replay custody, foreign concealment, suspended and revoked replay denial.
Retained compilation prerequisites are seeded canonical test custody. The API
is configured for non-eager in-memory publication and no post-policy worker is
started. This does not prove broker publication, job delivery, deployed Flow or
live setup-provider execution.

## Request an exact evaluation-policy correction

Prepare the public `PostPolicyCorrectionInput` from the inspected `post-policy`
response: `{"target": <complete displayed target>, "reason": "Manager feedback"}`.

```sh
workstream project guide correct-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID \
  --input post-correction.json --idempotency-key CORRECTION_UUID -o json
```

One POST to the existing public `/corrections` route sends the original bounded
UTF-8 JSON file (at most 1 MiB). The four selectors and caller-owned replay key
are explicit UUIDs; unknown, duplicate or null required fields are rejected.
The backend normalizes and validates feedback, checks both manager authorities,
supersedes the inspected policy and saves one unified setup successor atomically.
This command does not edit policy content, approve anything, activate a guide,
fetch latest or dispatch setup. Use the existing `setup` and `post-policy` reads
to discover retained state; explicit correction dispatch is described below.

Success requires HTTP 201 and a closed `PostPolicyReceipt` with kind `correction`,
the complete submitted target and a non-null correction bound to its proposal
digest. The successor generation must be the inspected generation plus one,
including values beyond signed 64-bit range. Record identities are UUIDv7;
feedback hashes are structurally checked, not locally recomputed or certified.
Text escapes terminal controls; JSON preserves the validated response.
The usual 12-second deadline and 64 KiB write-response limit apply.

New requests require current upstream custody and a usable policy. Exact replay
recovers the saved historical receipt after fresh actor/grant checks and retained
target validation; it does not allocate another successor or audit operation.
Different feedback under the same key conflicts. Canonically equivalent backend
feedback (NFC-normalized and trimmed) replays; retain the original file rather
than rely on that normalization when recovering an uncertain write.

A malformed receipt or unconfirmed write returns nonzero and empty stdout with
`outcome_unknown` and a manual-replay hint. There is no automatic retry, including
HTTP/2 transport replay. Replay only the unchanged selectors, file and key.
Canonical backend 4xx responses remain known denials.

Built-process hostile HTTP tests and a real Flow-verifier/uvicorn/PREP/PostgreSQL
journey prove receipt binding, saved successor lineage, immutable policy bytes,
exact replay, foreign-project concealment, suspension and revocation denial.
Canonical retained source fixtures and an explicitly executed actual Celery
derivation task arrange prerequisites; this is not live setup inference, queued
broker delivery or deployed Flow proof.

## Correct a guide proposal and dispatch its saved successor

Inspect the exact finalized proposal and prepare its closed public correction
input. This is a separate manager decision, not an automatic interpretation of
the findings:

```sh
workstream project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID -o json > proposal.json
jq '{target: .target, reason: "Clarify the evidence requirement"}' proposal.json > correction.json
workstream project guide correct PROJECT_ID GUIDE_ID COMPILATION_ID \
  --input correction.json --idempotency-key CORRECTION_UUID -o json > saved-correction.json
# Dispatch is a separate, explicit request using the retained receipt.
workstream project guide dispatch-correction PROJECT_ID GUIDE_ID COMPILATION_ID \
  --input saved-correction.json -o json
```

Saving sends the original UTF-8 JSON once (regular file, at most 1 MiB), with
the caller's token and UUID key. It validates the closed public receipt,
UUIDv7 identities, hashes and exact successor generation using arbitrary-range
integers. The backend owns target/feedback hashes, feedback normalization and
fresh exact-project authorization. The CLI does not locally certify those
digests, edit proposal content, select latest, approve or activate anything.

Dispatch accepts exactly `GuideProposalCorrectionReceipt`, not a proposal,
`PostPolicyReceipt` wrapper or setup-status object. For `correct-post`, extract
the nested `correction` object into the file. The saved operation ID selects
one public bodyless POST; no new idempotency key or JSON request payload is
invented. The four-field HTTP 202 response must match that operation's successor
ID and generation. JSON preserves it; text escapes terminal controls. The
backend's open diagnostic status is not a CLI enum: exit 0 means a valid status
was observed, even for `enqueue_failed`, not that work completed or publication
succeeded. Inspect `status`; use `setup` for subsequent diagnostics if needed.
The normal 12-second deadline and 64 KiB response bound apply.

Both writes distinguish canonical backend 4xx denial from an unknown outcome.
Unknown writes exit 1 with empty stdout and a manual recovery hint; the CLI
never automatically retries, including zero-byte HTTP/2 POSTs. For save, retain
unchanged selectors, input and key. For dispatch, inspect status and deliberately
redispatch only the same selectors and saved receipt. Backend recovery remains
freshly authorized and does not allocate another successor.

Built-process hostile HTTP tests prove receipt identity, response shape,
diagnostic/credential safety and GOAWAY no-replay. A real local
Flow-verifier/uvicorn/PREP/PostgreSQL journey proves one saved successor, exact
replay, explicit dispatch and current authority after suspension/revocation,
including stored foreign-project concealment. Canonical retained prerequisites
and Celery publication to an in-memory test broker do not prove distributed
delivery, worker completion, live setup inference or deployed Flow behavior.

## Prepare, submit and inspect contributor work

```sh
workstream task prepare TASK_ID --assignment ASSIGNMENT_ID --file work.zip \
  --idempotency-key CALLER_UUID --summary 'Completed work' --attestation 'My attestation'
# If still pending, wait for server verification and explicitly repeat the same
# preparation command, key, file bytes and packet. There is no polling GET.
workstream task submit TASK_ID --assignment ASSIGNMENT_ID --admission READY_ADMISSION_ID \
  --summary 'Completed work' --attestation 'My attestation'
# For a checker-requested revision, inspect the current task context first.
workstream task context TASK_ID --output json
workstream task prepare TASK_ID --assignment ASSIGNMENT_ID --file revision.zip \
  --predecessor SOURCE_SUBMISSION_ID --revision-preparation-id PREPARATION_ID \
  --revision-preparation-sha256 "$PREPARATION_SHA256" \
  --idempotency-key REVISION_KEY --summary 'Revised work'
workstream task submit TASK_ID --assignment ASSIGNMENT_ID --admission READY_REVISION_ADMISSION_ID \
  --predecessor SOURCE_SUBMISSION_ID --summary 'Revised work'
workstream task submissions TASK_ID --limit 25
workstream submission show SUBMISSION_ID
workstream submission findings SUBMISSION_ID --limit 25
workstream submission findings SUBMISSION_ID --run CHECKER_RUN_ID
```

Preparation streams one nonempty regular ZIP (at most 512MiB) to the public
authenticated API. Server project limits can be smaller. It never creates a
Submission, automatically retries or polls. A `ready` receipt supplies the
admission for the separate submit command. Other statuses must not be interpreted
as readiness. Before confirming a successful upload, the CLI checks file size,
modification time and SHA-256 again; a changed source reports an uncertain outcome.

Both commands accept optional `--summary`, `--attestation` and `--predecessor`.
Revision preparation additionally requires the exact `revision_context.preparation_id`
and `revision_context.preparation_sha256` from the authorized task context as
`--revision-preparation-id` and `--revision-preparation-sha256`. Both flags are
forbidden for initial preparation and are sent as preparation headers only; they
are not part of the Submission JSON. Keep the pair unchanged for explicit
preparation replay. A fresh server check rejects a stale pair after a rebase,
deadline or source change; the CLI never selects a replacement automatically.
Use the same packet for preparation, creation and explicit replay. The current
preparation API transports text in headers: printable ASCII only, at most 64KiB
per text field, with no leading/trailing whitespace. Unsupported text is rejected
before dispatch, not rewritten. Omitted or explicitly empty text is supported;
the server supplies warning-only defaults where applicable. The API owns all
policy checks, predecessor/currentness rules and authorization.

Submission creation is keyed by the exact admission and packet; there is no
additional client-generated creation key. A lost or malformed write response
exits 1 with `outcome_unknown: true`, empty stdout and a text-mode recovery hint.
Inspect task history and explicitly replay only unchanged inputs. Do not generate
a new preparation key simply because a response was lost. Each replay requires
fresh server authority, including after a CLI restart.

Blocked pre-submission intake prints the validated contributor findings in error
`details`; it creates no Submission. Infrastructure failures are not quality
findings. After creation, `submission findings` reads contributor-visible durable
checker runs/results. Run status is not human review or final acceptance, and the
CLI never follows finding paths or exposes provider/private management fields.
History and findings lists fetch one page only; use the returned opaque cursor
explicitly (up to 1024 characters; no local decoding). `--run` cannot be combined with pagination flags. Revision change
summary is available through `task context` as `revision_context.changes`,
not in the current public history rows. Human-readable submission/history output
points to that separate current-context read; it does not fetch or attach today's
revision context to a historical submission. JSON output remains the exact
authorized submission/history response.
History projects `rejected` with `status_reason=revision_limit_reached` after
immediate exhaustion, or `revision_deadline_expired` after timeout. Both come
from immutable TASK receipts without editing the original Submission.
`task show` and PM task reads expose `last_assignment_outcome`; the contributor
view includes only that actor's closed work. `next_action=none` applies to that
closed assignment, while the task is ready for a fresh claim.

The cap comes from the task's locked project RevisionPolicy. N=2 permits
attempts 0, 1 and 2; N=0 permits only attempt 0. Final-attempt failure immediately
closes the assignment and returns the task to ready, without another window.
A fixable failure with revisions remaining starts a fresh PostgreSQL-time
allowance. Setup-blocked revision contexts show `clock_state=paused`, a null
`deadline_at` and the frozen `remaining_microseconds`. Repair resumes that
remainder; running repair preserves its deadline. Only immutable resubmission
ends a running opportunity. Timeout also returns the task to ready. Anyone
eligible may claim a new assignment at round 0, including a previous claimant;
there is no contributor-count limit. Human decision integration remains #554.


The native process test uses real HTTP, PostgreSQL and local ART custody, with
approved-policy/assignment prerequisites arranged by fixtures. It drives the real
independent verifier directly; it does not certify distributed scheduling, S3 or
the complete public guide-setup journey owned by PILOT #552.

## Inspect an exact derived post-submission policy

After backend derivation, the proposal read supplies `post_submit_policy_id`:

```sh
workstream project guide post-policy PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID -o json
```

One public GET returns the complete canonical evaluation policy, its exact
upstream intake receipt, unified proposal/findings, activation selectors,
lifecycle/currentness and any saved correction. The four IDs are explicit;
there is no latest selection, polling, derivation, approval or activation.
Compiled, approved and superseded/non-current packages can be read while the
backend still authorizes the caller. Nullable activation selections do not
imply readiness. A correction shows its exact successor setup identifiers;
reading it does not dispatch the successor.

JSON preserves the complete response; text escapes untrusted terminal content.
The CLI validates closed wire shapes and repeated resource identities, not
catalogue membership, business hashes, authority or lifecycle decisions. Reads
use the shared 12-second deadline and 8 MiB proposal-response bound. Invalid
selectors make no request; denied, malformed or substituted responses return
nonzero with empty stdout.

Built-process tests exercise malformed responses and retained history. The
real socket/Flow/PREP/PostgreSQL test arranges canonical source prerequisites,
approves intake through REST, explicitly executes the actual derivation task
in an isolated subprocess, and checks CLI/REST/SQL parity. REST approval and
correction arrange later states; CLI reads add neither policy operations nor
activation. This proves executed worker/SQL derivation, not queued broker
delivery, live setup inference or deployed Flow. Suspension, revoked authority,
outsiders and stored foreign-project substitutions remain denied.

## Approve an exact post-submission policy

Inspect the derived evaluation policy first; approval is a separate manager
decision, not a consequence of reading it:

```sh
workstream project guide post-policy PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID -o json > post-policy.json
jq '{target: .target}' post-policy.json > post-approval.json
workstream project guide approve-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID --input post-approval.json --idempotency-key APPROVAL_UUID -o json
```

The regular UTF-8 JSON input, at most 1 MiB, is the closed public
`PostPolicyApprovalInput`: exactly `target` from the displayed policy package.
No editable policy body, warning auto-acknowledgment, latest selection or
preflight request is added. The CLI sends the original bytes and caller's
bearer/key in one public POST. Workstream checks currentness and lifecycle for
a new approval. Exact manual replay rechecks fresh actor/grant authority and
retained target custody, and can recover the historical immutable receipt.

A successful response is a closed `PostPolicyReceipt` with an RFC UUIDv7
operation ID, `kind=approve`, null correction and the exact submitted target.
UUID identity is compared independently of supported text spelling; all source,
upstream, generation, hash and predecessor facts must match. The CLI does not
recompute business digests, decide readiness or authorize later operations.
JSON and escaped text return the validated immutable receipt. Approval never
activates the guide, executes a checker or accepts submitted work.

The existing 12-second deadline and 64 KiB receipt limit apply. A complete
canonical 4xx is a known rejection. Malformed/substituted success, an oversized
response, redirect, server error or lost reply reports an unconfirmed write:
empty stdout, nonzero exit and JSON `error.outcome_unknown: true`. Text explains
manual replay with the unchanged project, guide, compilation, policy, input
bytes and idempotency key. There is no automatic retry, including HTTP/2 replay.
A prior receipt never exempts the caller from fresh actor/grant authority and
retained target-custody checks. Replay does not repeat the new-approval
currentness checks; a second fresh key is not an instruction to approve twice.

Built-process hostile HTTP tests cover full-target substitution and transport
uncertainty. The real Flow/socket/PREP/PostgreSQL journey arranges canonical
source prerequisites, publicly approves intake, explicitly applies the actual
derivation worker, then approves through the CLI. It proves exact REST/SQL
receipt parity, no duplicate operation/audit on replay, no activation or policy
body replacement, and denial after suspension or grant revocation. Stored
foreign projects and unauthenticated/unauthorized callers are also denied.
Explicit worker application is not queued broker-delivery, live setup inference
or deployment proof.

## Prepare a task-import JSON source

```sh
workstream project task-batch convert-csv --input briefs.csv --out briefs.json --label 'Evaluation briefs' --output json
workstream project task-batch source-declare PROJECT_ID --input briefs.json --idempotency-key SOURCE_UUID --output json
workstream project task-batch source-upload PROJECT_ID SOURCE_ID --input briefs.json --output json
workstream project task-batch source-status PROJECT_ID SOURCE_ID --output json
mkdir source-originals
workstream project task-batch source-download PROJECT_ID SOURCE_ID --download source-originals --output json
```

Conversion is local and needs no token or API configuration. It accepts quoted
UTF-8 CSV, including embedded commas/newlines and one optional UTF-8 BOM. It
requires 1..500 task rows and bounds both input CSV and generated JSON to 8MiB.
Invalid input produces no JSON file. `--out` must name a new file; an existing
file is never overwritten. The report names the SHA-256 and byte count of the
complete generated JSON, including its final newline. Upload those exact bytes.
Workstream retains the converted JSON source; this does not retain the original
CSV. Retain that original separately if your own workflow requires it.
Download requires a currently verified source and an existing real directory.
The CLI reads current source metadata, then independently asks the public API
for its content; both requests remain subject to backend authorization. It
checks the exact original SHA-256 and byte count and writes `SOURCE_ID.json`
privately before publishing. An existing file or symlink is never overwritten;
failed reads leave no partial download. JSON output names the downloaded file
and source metadata, not the source bytes or storage coordinates. A successful
read does not authorize a later import or other write.

| CSV header | JSON task field | Conversion |
| --- | --- | --- |
| `external_task_id` or `source_id` | `external_task_id` | Required exact, case-sensitive source identifier |
| `title`, `description` | Same names | Required nonblank instruction text, preserved without trimming |
| `task_type` or `category` | `task_type` | Optional category, preserved |
| `skill_tags`, `languages`, `tools` | `skill_tags` | Semicolon segments concatenate in this order; trim segments and omit blank segments |
| `difficulty`, `acceptance_criteria`, `rejection_criteria` | Same names | Optional text, preserved |
| `estimated_time_minutes` | Same name | Optional whole minutes in 1..525600 |

Unknown/duplicate headers, simultaneous alias/canonical headers, duplicate IDs,
padded/control-character IDs, invalid UTF-8/NUL, malformed quoting and row/field
limits are refused. No Task identities, guide locks or creator authority can be
supplied through CSV. The canonical JSON contract is
[`contracts/task-import.schema.json`](../contracts/task-import.schema.json).
JSON files also receive bounded canonical validation before declaration/upload,
including duplicate object members, strict field types and exact external IDs.
Their original whitespace/bytes are preserved for the commitment and upload.

Declaration, upload and status are separate operations under current covered-PM
authority. Declaration sends only the exact JSON SHA/count with the caller's
UUID key and returns a source ID. Upload sends one raw `application/json` PUT
to that explicit project/source and carries no separate idempotency key; retained
source custody controls its replay. Status reads the actual retained ART state.
The CLI verifies returned selectors and, for writes, the exact file commitment.
A returned source/status establishes byte custody only; it does not create,
screen or release Tasks.

Continue with explicit batch operations after source verification:

```sh
workstream project task-batch import PROJECT_ID SOURCE_ID --idempotency-key IMPORT_UUID --output json
workstream project task-batch status PROJECT_ID BATCH_ID --output json
workstream project task-batch screen PROJECT_ID BATCH_ID --idempotency-key SCREEN_UUID --reason 'Briefs meet the approved guide' --output json
workstream project task-batch release PROJECT_ID BATCH_ID --idempotency-key RELEASE_UUID --reason 'All members are ready for work' --output json
```

Import returns the complete original ordered DRAFT creation facts. Status keeps
those originals separate from the current member states. SCREEN and RELEASE
select every member from immutable native membership and return ordered compact
Task IDs, statuses and locked lineage. Normal guide/policy prerequisites still
apply; release requires a nonblank reason. Each write requires its own retained
caller UUID. No command combines upload/import/screen/release or chooses per-row
retry keys. Responses are limited to 1..500 complete members: original/status
JSON is bounded to 16MiB and compact transition JSON to 2MiB. Invalid, crossed,
duplicate or partial responses are refused without partial output.

A different verified source with identical SHA and byte count can recover the
original batch with a new import key. The response retains the original source
ID and rows; the CLI checks the selected source's public verified status before
displaying it. Changing the source selector under an existing key conflicts.
If the verification read fails after import, the write outcome remains unknown.

Batch writes never retry automatically. An unknown outcome requires inspection
of `status` as an observation, followed by manual replay of the unchanged project,
source/batch, action, reason and key. SCREEN/RELEASE replay also requires every
member to retain its original post-state, locked context and unassigned custody;
later Task changes or revoked authority can prevent recovery with the same key.
Import, SCREEN and RELEASE wait up to three minutes for their complete atomic
response. Source download uses the bounded original-transfer budget; status and
other source operations retain the normal twelve-second deadline.
These are request budgets; an interrupted or timed-out write can still require
the same manual recovery above.

Source writes never retry automatically, including after HTTP/2 GOAWAY. If a
declaration outcome is unknown, manually replay only the unchanged project,
JSON file bytes and caller key. For an uncertain upload, inspect `source-status`
and then manually replay the unchanged project/source/file if appropriate.
Server storage recovery can remain pending; inspect the actual returned status
instead of treating every successful HTTP response as verified storage.

## Create a draft project shell

```sh
workstream project create --name 'Evaluation project' --slug evaluation --idempotency-key CREATE_UUID --output json
workstream project create --name 'Research project' --slug research --description 'Evaluate the supplied evidence.' --idempotency-key ANOTHER_CREATE_UUID
```

Both `--name` and `--slug` must be supplied; their explicit empty values and
whitespace are preserved because the API accepts them. Name and slug accept
at most 200 and 120 Unicode characters. All text must be valid UTF-8 without
NUL. Description is optional: omission sends no member, while an explicit empty
flag sends an empty string. The complete encoded JSON request is capped at
8 KiB; description has no additional character limit in the backend.

Creation requires system-scoped Project Manager authority. Access Administrator
or project-scoped Project Manager authority alone cannot create a project.
The CLI sends one public POST with the unchanged caller bearer and UUID key;
there is no role preflight, generated key or automatic retry. Only HTTP 201
with the full seven-field ProjectResponse establishes success. Nullable
description is valid, but missing members, malformed identity/timestamps,
unknown or duplicate fields and the minimal contributor GET shape are rejected.
JSON preserves the API response; text shows every field with terminal escaping.

This creates a draft shell, not an uploaded or approved guide, activated project
or claimable task. Project identity is generated by Workstream, not the key.
Retain the key with the exact name, slug and description omission/value.
An exact manual replay recovers the stored project, whose state may since have
changed. Changed fields conflict; a different key with the same slug conflicts
rather than overwriting a project.

Unlike task claim/start, the current project-create API recovers a committed
result before fresh creation authorization, including after the creation grant
is revoked. This recovery is not permission for another creation. Do not assume
every mutation has task replay semantics or that a replay certifies current
authority. Fresh creation is denied after revocation or suspension.

Lost, malformed, oversized, redirected, unexpected-status, server-error and
noncanonical error replies leave an unknown outcome: nonzero exit, empty stdout
and `error.outcome_unknown: true`. Only a complete canonical Workstream 4xx
establishes a known denial. If manually retrying, use the unchanged fields and
key; do not invent a project ID, assume rollback or switch to a fresh key.

## Activate explicitly selected guide policies

Use the existing `post-policy` read to inspect the exact separately approved
evaluation policy and its `activation_context`. Review and revision selections,
post-approval identity/digest and the published contribution-policy binding must
be present. A null selection is not permission to invent one. Contribution-policy
publication remains a separate Finance API operation; this command does not
publish it or approve missing policies.

From an inspected `post-policy.json`, prepare the closed public input:

```sh
jq '{target, post_approval_operation_id: .activation_context.post_approval_operation_id,
  post_approval_output_digest: .activation_context.post_approval_output_digest,
  guide_mutation_generation: .activation_context.guide_mutation_generation,
  review: .activation_context.review, revision: .activation_context.revision,
  contribution_policy_id: .activation_context.contribution.contribution_policy_id,
  contribution_policy_version_id: .activation_context.contribution.contribution_policy_version_id,
  expected_previous_active_guide_id: .activation_context.expected_previous_active_guide_id,
  expected_previous_active_guide_generation: .activation_context.expected_previous_active_guide_generation}' \
  post-policy.json > activation.json
workstream project guide activate PROJECT_ID GUIDE_ID \
  --input activation.json --idempotency-key CALLER_OWNED_UUID --output json
```

The command sends the original input bytes once, with the unchanged bearer and
caller key in headers. It does not fetch latest, poll, infer readiness, approve
policies or dispatch jobs. Workstream authorizes the manager afresh and owns the
atomic activation, exact policy/source locks and predecessor supersession.

Success validates the complete immutable receipt: UUIDv7 operation, exact echoed
command/key, matching contribution project/policy/version, selected generation
plus one, timezone-bearing effective time and prior project status. Integer
fields retain the backend range and UUIDs compare by identity, not spelling.
JSON returns the validated API object; text renders every field with terminal
escaping. A replay receipt proves that operation, not that its guide is still
current after later supersession. Supported `human_review_required=false` guides
can activate when their approved inventory has no `human_review` disposition;
new false/pass effects still require a live REV generation. The CLI does not
change those backend-owned readiness gates.

Malformed or substituted receipts, lost responses and other uncertain writes
exit 1 with empty stdout and `outcome_unknown: true`. Retain the original input
and key; recovery is a deliberate invocation with unchanged selectors, input
contents and key. Never generate a new key merely because the response was lost.
Replay still requires current actor lifecycle and manager authority.

Process tests cover closed inputs, exact receipt binding, credential reflection,
large integers, terminal escaping and one POST under HTTP/2 GOAWAY. The real
socket/Flow/PREP/PostgreSQL journey prepares canonical stored source evidence,
executes the real derivation task explicitly, approves and publishes through
public APIs, then proves activation/replay against SQL and denial after grant
revocation or suspension. It is not live setup inference, broker-delivery or
deployment certification.

## Prepare tasks as a project manager

```sh
workstream project task create PROJECT_ID --input task.json --idempotency-key CREATE_KEY --output json
workstream project task screen PROJECT_ID TASK_ID --idempotency-key SCREEN_KEY --reason "Guide requirements inspected" --output json
workstream project task release PROJECT_ID TASK_ID --idempotency-key RELEASE_KEY --reason "Ready for contribution" --output json
```

The input is the public `TaskCreate` JSON, for example:

```json
{
  "title": "Assess the supplied evidence",
  "description": "Produce the deliverables specified by the project guide.",
  "task_type": "evaluation",
  "skill_tags": ["analysis"],
  "acceptance_criteria": "Complete, attributable evidence for every conclusion."
}
```

All public declaration fields are supported; omitted/null values retain their
API semantics. Creation requires a canonical hyphenated project UUID, as does
the backend create route. Inputs are bounded to 1MiB; management responses to
2MiB. Transition selectors accept supported UUID spellings without changing the
supplied task selector on the wire. The project selector binds the returned
project, not a client-side grant check or an additional backend request.

Creation returns a draft. Screening locks the backend-selected active guide and
policies; release checks those locks and installed plans and requires an explicit
nonblank decision reason. These are three independent calls, never automatic
steps. Only Workstream decides authority, readiness and lifecycle transitions.
Text and JSON output retain the complete authorized management receipt, not
the narrower contributor projection. Supply deadlines as RFC3339 timestamps;
creation binds the returned instant, allowing timezone normalization and the
backend's microsecond precision. Import-batch identifiers are nullable text,
not Workstream record UUIDs.

Keep each key with its unchanged request. Immediate replay returns the original
receipt only while current authority, lifecycle and locked context permit it;
for example, a draft-create key cannot replay after screening changes its locks.
Malformed success or transport uncertainty exits 1 with empty stdout. Text errors
include deliberate unchanged-input/key recovery; JSON sets `outcome_unknown`.
Do not substitute a new key because a task read appears unchanged.

Built-process tests cover exact bodies/keys, complete response binding, malformed
lineage, credential/terminal safety and no automatic replay. The existing real
socket/Flow/PREP/PostgreSQL journey prepares a task using these commands, verifies
stored locks and single command/audit facts, tests foreign-project, suspension and
revocation denials, then exercises contributor discovery/claim/start. Canonical
guide setup fixtures are not live inference or deployed-service certification.

## Repair a blocked revision context as a project manager

```sh
workstream project task PROJECT_ID TASK_ID --output json
workstream project task repair-revision PROJECT_ID TASK_ID \
  --parent-preparation-id PREPARATION_ID \
  --parent-preparation-sha256 sha256:LOWERCASE_64_HEX \
  --reason "Adopt corrected approved context" --idempotency-key REPAIR_KEY --output json

# Only for a retained failure missing its preparation, select its exact routing source instead:
workstream project task repair-revision PROJECT_ID TASK_ID \
  --routing-manifest-id ROUTING_MANIFEST_ID \
  --reason "Recover missing revision root" --idempotency-key ROOT_KEY --output json
```

Choose exactly one source form. `--reason` must be nonblank, at most 1000
Unicode characters, and at most 1000 UTF-8 bytes after surrounding whitespace
is stripped; the backend makes every eligibility, authority, lineage and clock
decision again at the POST. The preceding manager detail is only an observation:
it does not reserve a repair or authorize a later write. Each invocation makes
one keyed POST without an automatic read, retry, guide rebase or deadline reset.
The JSON output is the complete `ContributorRevisionContext` returned by that
POST, not a manager task or acceptance receipt. `clock_state=paused` has a null
deadline, positive `remaining_microseconds` and `context_blocked` disposition;
`clock_state=running` has a deadline and null allowance. A repair may still be
blocked under the backend's current policy. Text output escapes terminal controls.

Keep the original project, task, exact source, reason and key together for
deliberate replay after an uncertain write. A read is not rollback proof, and
changing the key can conflict with the already committed child. A canonical
denial is not a success; current Project Manager authority is required even to
replay. This command does not create a human Review or decide acceptance.

## Browse tasks as a project manager

```sh
workstream project tasks PROJECT_ID --limit 10 --output json
workstream project tasks PROJECT_ID --limit 10 --cursor PREVIOUS_NEXT_CURSOR --output json
workstream project tasks PROJECT_ID --status needs_revision --updated-since 2026-10-01T00:00:00Z
workstream project task PROJECT_ID TASK_ID --output json
```

`--status`, `--assignee` (current assignee actor UUID), `--import-batch`
(native import batch membership) and `--updated-since` (RFC 3339, inclusive)
narrow the list. Workstream binds a continuation to the same filters, so keep
them unchanged when using `--cursor`.

These commands use the management queue and management detail routes; they
require covering Project Manager authority, not a Submitter/Reviewer grant.
Workstream reauthorizes each request, including continuation after revocation
or suspension. No role preflight, local filtering or hidden operation is used.
They inspect all task states, including drafts; they do not make work claimable,
create tasks, claim assignments or complete unfinished submission integration.

The list makes one request for one page. `--limit` defaults to 50 (range 1–100).
Use the returned `next_cursor` unchanged with the same limit and project;
Workstream binds it to the action, project and page size. A null cursor ends
continuation. The cursor is neither authority nor a reservation, and live pages
are not a frozen snapshot. The CLI never follows a returned URL or fetches all
pages automatically. Supplied cursors must contain 1–512 valid UTF-8 characters.
Both UUID selectors are escaped separately and responses must match their
identity, regardless of supported spelling.

JSON preserves the exact public response. Text shows every management summary
field and the continuation, plus detail instructions, criteria, source and
assignment fields for `project task`. Nullable detail fields may be omitted by
the API and display as `—`; source identifiers are not treated as URLs to fetch.
Required data, tag arrays, timestamps and identities are validated before
output. Foreign items, duplicate identities, unknown/duplicate fields and
malformed replies fail with empty stdout. The existing 64 KiB response bound
applies to a whole page: an oversized response fails without partial output;
request a smaller `--limit` if needed.

The manager's task-evidence reads are separate from contributor `task context`,
`task requirements`, `task submissions` and `submission` commands:

```sh
workstream project task-requirements PROJECT_ID TASK_ID --output json
workstream project task-locked-context PROJECT_ID TASK_ID --output json
workstream project task-context PROJECT_ID TASK_ID --output json
workstream project task-submissions PROJECT_ID TASK_ID --limit 25 --output json
workstream project submission PROJECT_ID SUBMISSION_ID --output json
workstream project checker-runs PROJECT_ID SUBMISSION_ID --limit 25 --output json
workstream project checker-runs PROJECT_ID SUBMISSION_ID --run RUN_ID --output json
```

`task-requirements` shows locked intake rules; `task-locked-context` shows
historical policy identities and the bounded post-submit policy summary;
`task-context` shows current management instructions and provenance, without
contributor action hints or compensation terms. History reads show exact
manager Submission lineage and checker routing evidence; checker results are
not acceptance decisions. Supply the exact project/task, project/submission or
project/submission/run identity; the CLI never substitutes the latest record.
Lists make one request for one page (`--limit` 1–100, default 25) and display an
opaque `next_cursor`; pass it back unchanged with the same limit and selectors.
Workstream binds and reauthorizes each page. These reads never grant later
write authority or fetch artifact bytes. Text escapes terminal controls and
prints complete nested facts; `--output json` preserves the public response.

## See your own work

```sh
workstream me projects
workstream me assignments --state active
workstream me submissions --status needs_revision --output json
workstream me summary --project PROJECT_ID
workstream task preparations TASK_ID
workstream task preparation TASK_ID PREPARATION_ID --output json
```

These read only your own records. `me projects` lists projects where you hold
an exact grant, with your roles and the active guide version. The other reads
return your assignments, attempts, preparations and totals only in projects
where you currently hold a Submitter grant; another project, a task you never
held or someone else's preparation is reported as not found. Each assignment
carries the server's `next_action` (`start`, `prepare_submission`,
`awaiting_evaluation`, `revise` or `none`) and, while a revision is open, the
same revision fields as `task context`. Lists page with `--limit` and an opaque
`--cursor` bound to the same filters; `--updated-since` is inclusive. Award
totals are immutable earned terms, not payment status. Text output summarizes;
use `--output json` for complete records, including preparation findings.

## See a whole project as a Project Manager

```sh
workstream project guide list PROJECT_ID --status active
workstream project guide show PROJECT_ID GUIDE_ID --output json
workstream project guide readiness PROJECT_ID GUIDE_ID
workstream project guide document PROJECT_ID GUIDE_ID DOCUMENT_ID --download ./originals
workstream project active-guide PROJECT_ID --output json
workstream project guide sufficiency list PROJECT_ID GUIDE_ID --output json
workstream project guide sufficiency show PROJECT_ID GUIDE_ID REPORT_ID --output json
workstream project guide sufficiency create PROJECT_ID GUIDE_ID --input ./report.json --idempotency-key UUID
workstream project guide sufficiency acknowledge-warnings PROJECT_ID GUIDE_ID REPORT_ID --input ./acknowledgement.json --idempotency-key UUID
workstream project guide artifact-policy list PROJECT_ID GUIDE_ID --output json
workstream project guide artifact-policy show PROJECT_ID GUIDE_ID POLICY_ID --output json
workstream project guide artifact-policy create PROJECT_ID GUIDE_ID --input ./manual-policy.json --idempotency-key UUID
workstream project guide artifact-policy update PROJECT_ID GUIDE_ID POLICY_ID --input ./manual-successor.json --idempotency-key UUID
workstream project guide artifact-policy effective PROJECT_ID GUIDE_ID --output json
workstream project guide pre-submit-policy PROJECT_ID GUIDE_ID --output json
workstream project submissions PROJECT_ID --status review_pending --updated-since 2026-10-01T00:00:00Z
workstream project assignments PROJECT_ID --state active
workstream project summary PROJECT_ID --output json
workstream project import-batches PROJECT_ID
workstream project preparations PROJECT_ID --outcome failed
```

The existing guide list/detail/readiness/document and project-wide queue reads
require a current Project Manager grant covering the project; another caller,
project, guide or document is reported as not found. `guide list`
shows each guide version with its stored `draft`, `active` or `superseded`
status. `guide show` returns the declared documents with ingest state and
SHA-256, the selected review and revision policy values and the latest setup
run and compilation IDs. `guide readiness` is a dry run of activation's own
conditions: it reports `ready` or the unmet conditions it evaluates, each with
the same refusal code activation would return (a check whose inputs are
missing is not evaluated), and it activates, consumes and reserves nothing.
`guide document` downloads one uploaded original into an existing directory,
verifies it against the declared SHA-256 and never overwrites a file; a
declared document that is not uploaded fails with `guide_document_not_uploaded`.

The seven administrative inspection commands above read existing public API
projections. A covering Project Manager, scoped Audit Authority or system
Operator may inspect them; Finance, Access Administrator, contributor and service
credentials cannot. `sufficiency list` and `artifact-policy list` return the
server's newest 100 canonical rows without a cursor. Use their exact `show`
commands for a known older report or policy ID. The effective, pre-submit and
active-guide reads concern the current approved chain only; draft, superseded,
incomplete or stale bindings remain concealed by the backend. `active-guide`
includes the locked non-compensation policy context, not a readiness calculation
or a credential for a later write. Every invocation reauthorizes through the
backend. Text is terminal-escaped; `--output json` preserves the complete
successful public response.

The two sufficiency writes require a current covering human Project Manager
grant. `create` records one human diagnostic against the current draft guide's
source snapshot; its JSON file needs `source_snapshot_id`, `status` (`passed`,
`blocked` or `passed_with_warnings`), and may include `findings` and `summary`.
`acknowledge-warnings` accepts a JSON object with an optional
`acknowledgement_note` (use `{}` for no note) for an eligible warning report.
The backend checks guide/snapshot lineage, report status, authority, duplicates
and exact replay; neither command runs setup, approves policy or activates a
guide. Retain the same UUID key and unchanged input file for a manual replay
after an uncertain outcome. These commands do not create or update artifact
policies.

The two `artifact-policy` writes are manual draft operations for a current
covering human Project Manager, not a second setup or approval path. Create
requires a genuinely finalized authoritative setup report for the exact guide
and a JSON file with `source_snapshot_id`, a caller-chosen `policy_version`
(not beginning `agent-`), and `policy_body` following the public submission
artifact-policy schema; `change_summary` is optional. For example:

```json
{"source_snapshot_id":"SNAPSHOT_UUID","policy_version":"manual-v1","policy_body":{},"change_summary":"Manual draft"}
```

Update selects one exact current manual draft by `POLICY_ID` and appends a
successor. Its JSON file must include `expected_policy_hash` copied from that
draft's exact `policy_hash` and a new `successor_policy_version`; optional
`policy_body` replaces the body, while omission or explicit `null` retains it. Optional
`change_summary` replaces the prior summary when supplied. For example:

```json
{"expected_policy_hash":"sha256:64_lowercase_hex_digits","successor_policy_version":"manual-v2","change_summary":"Revised draft"}
```

The backend rechecks authority, finalized setup lineage, exact predecessor,
current draft status, hash precondition and same-key replay on every write.
Keep the same UUID key and unchanged file for manual replay if a response is
uncertain; the CLI never retries automatically. A manual policy remains a
retained draft even after a successful write. It is not the compiled unified
policy used for approval, effective-policy selection or guide activation;
`artifact-policy effective` is an observation, not authority for a later write.

`submissions` and `assignments` list every attempt and claim in the project
with the submitter or contributor and the same fields as `me submissions` and
`me assignments`. `summary` counts tasks by status, claims by state and attempts
by outcome, with the acceptance rate (accepted over decided attempts) and
post-submission checker infrastructure failures, and the project's award totals
per instrument and unit (none when no award exists).
`import-batches` lists native task import batches with state and member counts.
`preparations` lists every contributor's ZIP preparations, newest first, with
finding counts only; `--outcome failed` shows intake checks that blocked a ZIP.
Lists page with `--limit` and an opaque `--cursor` bound to the same filters;
`--updated-since` is inclusive. Text output summarizes; use `--output json` for
complete records.

## Discover work as a contributor

```sh
workstream task ready PROJECT_ID --limit 10 --output json
workstream task ready PROJECT_ID --limit 10 --cursor PREVIOUS_NEXT_CURSOR --output json
workstream task show TASK_ID --output json
```

These are contributor routes, not aliases for manager browsing. The ready queue
requires an active project and an exact active Submitter or Reviewer grant;
Manager authority alone does not permit it. It lists only unassigned ready
tasks. Contributor detail shows unassigned ready work to either contributor role,
or the caller's own active assignment under current Submitter authority. It does not expose management
source/actor/assignment metadata, and a different same-project Submitter cannot
read your claimed task. Workstream makes these decisions on every request.

The same one-page limit/cursor bounds, UUID selector encoding, strict response
validation and safe text/raw-JSON output apply. Ready summaries contain task and
project IDs, title, nullable type/difficulty/estimated minutes, skills and creation
time. Detail adds instructions, criteria, status, deadline and update time;
nullable detail fields may be omitted by the API and display as `—`.
Both responses include compensation from the task's locked
ContributionPolicyVersion: the exact version UUID and, for accepted submissions
and completed reviews, either `unpaid` or award rows containing only instrument,
unit and exact decimal-string quantity. The CLI rejects binding IDs, route keys,
binding status and other unknown Finance fields.
`task show` takes only a task selector; Workstream resolves its project and
authorizes that resource. No project preflight or locally inferred permission
is added. Management-only fields in a contributor reply are rejected rather
than silently displayed or ignored.

Discovery is live, not a reservation or a claimability guarantee. A later claim
still requires a Submitter grant and must revalidate current authority and state.
Cursors are action/project/limit
bound and cannot be reused as manager cursors; the CLI never decodes them or
automatically fetches another page. These reads do not claim/start tasks,
upload submissions or complete unfinished acceptance integration.

## Inspect governing work and intake rules

```sh
workstream task context TASK_ID --output json
workstream task requirements TASK_ID
```

Each command makes one existing public contributor GET, with the same selector,
bearer and safe errors as `task show`. Document-bearing work context has a
2 MiB response bound; requirements retain the 64 KiB default. Workstream checks current
Submitter authority and assignment visibility on each read. Other roles alone,
foreign-project or peer-owned work, revoked grants and suspension do not confer
access. Denial statuses follow the individual API contract; a denied read is
not an empty successful result.

Context returns contributor instructions, project/guide display facts, exact
review/revision policy identities and contribution-policy version, plus the
server's current assignment/action hints and `guide_documents`. An active own
assignment receives the exact locked originals' IDs, order, labels, media types,
sizes, SHA-256 commitments and task-scoped read references; ready unassigned
browsing receives an empty document list. Task examples are never included.
For a task awaiting revision, the optional `revision_context` gives the current
preparation ID and digest, source Submission, deadline, eligibility disposition
and bounded change summary. It may be absent or null on other tasks. Use its
exact preparation pair for a revision ZIP preparation; the read does not reserve
or authorize later intake.
Hints are observations, not authority
or a claimability guarantee. The CLI never recomputes them or automatically
executes a hinted action. Claim/start independently authorize their requests.

Requirements expose the task's locked guide and intake rules: packet fields,
artifact/evidence requirements, forbidden patterns, attestation, hash/manifest
requirements, storage-reference restrictions, size/entry limits and packaging.
They are not a current-guide lookup, a checker verdict or permission to upload.
These reads do not invoke the separate `task prepare`/`task submit` commands. Described
paths and storage references are displayed only, never read, downloaded or executed.

### Read the assigned guide

```sh
workstream task guide TASK_ID --output json
mkdir guide-documents
workstream task guide TASK_ID --download guide-documents
```

This requires an active assignment and current exact-project Submitter authority.
Each download reauthorizes independently; neither a cached list nor a read
reference grants access. Workstream reads the task's locked snapshot, not the
latest guide or drafts. A successor activation alone never changes its documents.
Checker-requested revision preparation can atomically rebase the complete task
and assignment context for the next attempt. Inspect `task context` for its
frozen change summary and acknowledge the exact preparation pair when running
`task prepare`; this guide download does not initiate a rebase. Covered-manager
repair is a separate backend operation with no CLI command. Genuine human
Review revision integration remains #554 work.

The API verifies the complete original against retained ART size/SHA-256 before
responding. Missing, corrupt or wrong-namespace originals fail with
`guide_document_integrity_unavailable`, not partial successful content. Responses
are private/no-store; setup-agent run-scoped access remains unchanged.

The CLI reconstructs fixed same-origin paths and verifies size/SHA-256 again.
Files use canonical document UUID names with `.pdf`, `.docx`, `.pptx` or `.md`,
never labels as paths. The destination must already exist and must not be a symlink.
Downloads use private bounded temporary files and atomic no-overwrite publication;
existing targets/symlinks are refused and failed unpublished files are removed.
Documents completed before a later document fails remain valid local files.
The `task guide` command does not expose examples, upload originals or execute
document content. Manager uploads use the separate `project guide upload` command.

JSON preserves the exact public response. Human output labels every root field
and uses compact, terminal-safe JSON for complete nested rules and facts;
nullable omissions display as null. The two reads are separate observations,
not an atomic combined snapshot. Context rejects substituted task/project/guide
identities; requirements bind the selected task identity and validate the returned
project UUID shape, without independently resolving its project. Both reject
malformed nested members, null required fields, duplicate/unknown fields and
management-only task metadata before success.
Optional null/omitted fields remain valid. The four optional limits preserve
backend integer precision in JSON and human output without a 64-bit ceiling or
floating-point conversion. Non-integer values remain invalid. The CLI checks public response
shape, not business policy or contributor eligibility.

## Claim and start contributor work

```sh
workstream task claim TASK_ID --idempotency-key CLAIM_UUID --reason 'Begin this work' --output json
workstream task start TASK_ID --idempotency-key START_UUID --output json
```

Supply your own UUID key and retain it with the action, task and optional reason.
These commands send exactly one public POST, with no preflight, automatic key,
retry or operator override. Reason is optional (at most 1000 UTF-8 characters);
an omitted flag sends `{}`, while an explicit empty flag sends an empty string.
The caller's Flow bearer and key are forwarded unchanged. Only Workstream
decides whether current identity, lifecycle, exact Submitter grant, task state,
assignment ownership and locked policy permit the write.

Claim returns the contributor-safe task and its assignment; start returns the
contributor-safe task in progress. The CLI validates the requested task identity,
assignment/task/project/policy consistency, claim contributor/assigner identity,
active/unreleased assignment and required timestamps before output. It rejects
management-only fields. JSON preserves the API object; text prints every public
field with escaped terminal controls. Separate submission commands are described
below; claim/start does not invoke them or activate unfinished human review.

The API scopes keys by actor and action, and checks current authority before
recovering a committed result. An exact retry can recover the same result only
while the required state remains current. Changed reason/task conflicts;
claim replay after start can be denied. A key never grants permission. Revocation
and suspension deny further writes/replays; assignment invalidation is a separate
asynchronous consequence, not a CLI effect or immediate API guarantee.

If the response is lost, malformed, oversized, redirected, an unexpected success
status, a server error or a noncanonical/intermediary denial, the CLI exits
nonzero with `error.outcome_unknown: true`. Only a complete strictly decoded
canonical Workstream 4xx error envelope establishes a known denial. Inspect with
`workstream task show TASK_ID`; this observes current state, not rollback or
global ordering. If manually retrying, preserve the unchanged action, task,
reason and key. Do not invent a new key or assume recovery will still succeed.

## Inspect and start tasks as a system Operator

```sh
workstream operations task list PROJECT_ID --limit 50 --output json
workstream operations task list PROJECT_ID --limit 50 --cursor PREVIOUS_NEXT_CURSOR --output json
workstream operations task locked-context PROJECT_ID TASK_ID --output json
workstream operations task start TASK_ID --reason 'Verified the active assignment' --idempotency-key START_UUID --output json
```

These are separate system-Operator routes, not aliases for contributor or
Project Manager commands. The queue contains only task/project IDs, status and
creation/update times. Its signed cursor is opaque, scoped to the exact
project/caller/page size and reauthorized on continuation. Locked context
contains immutable policy identities, hashes and positive generations, not
policy bodies or task instructions. Both are observations, not authority for a
later start.

`operations task start` sends one explicit override POST with a nonblank
explanation of at most 1000 Unicode characters and a caller-owned UUID key.
Workstream rechecks the current human Operator grant, exact task/assignment,
locked context and lifecycle, then records its own authorization decision and
audit event. The response is the contributor-safe in-progress task, not an
assignment receipt; the CLI does not infer or alter the assignee. It never
falls back to `task start`, which requires the assigned Submitter's different
authority. The three commands use bounded closed response validation, exact
UUID binding and terminal-safe text/JSON output.

Keep the override action, exact task, reason and key together. Changed inputs
conflict; exact replay still requires current Operator authority. The CLI does
not preflight or automatically retry, including after uncertain transport
delivery. A lost, malformed or unsafe success is `outcome_unknown`; a later
read may help inspect current state but cannot prove rollback. Manually replay
only the unchanged override request if appropriate.

## Make explicit administrative decisions

The eight administrative POSTs are separate from `whoami`, caller-owned
`profile update`, project contributor grants and the six privileged `admin`
reads. Each command requires a caller-authored JSON file (at most 1 MiB) and
UUID idempotency key. For example:

```sh
workstream admin service-actor provision --input service-actor.json --idempotency-key PROVISION_UUID --output json
workstream admin actor suspend ACTOR_ID --input reason.json --idempotency-key SUSPEND_UUID --output json
workstream admin identity-link revoke LINK_ID --input reason.json --idempotency-key LINK_UUID --output json
workstream admin role-grants issue --input admin-grant.json --idempotency-key ISSUE_UUID --output json
workstream admin role-grants revoke GRANT_ID --input reason.json --idempotency-key REVOKE_UUID --output json
```

The provision input has `service_identity`, `subject` and `reason`; the
service identity must be a registered fixed principal. Actor and link
transitions and grant revocation take `{"reason":"Explicit decision"}`.
Grant issuance takes `target_actor_profile_id`, `role`, `scope_type`, optional
`scope_project_id`, and `reason`. Project scope requires an exact project UUID;
system scope omits that field or sets it to null. Workstream alone decides
current Access Administrator authority, role/scope compatibility, lifecycle
guards and final-administrator protection. A previous read never authorizes
a later write. Profile suspension, identity-link revocation and grant
revocation are distinct; reactivating one does not reverse the others.

The three reason contracts differ: service provisioning preserves any nonempty
1–500 UTF-8-byte reason; actor/link lifecycle reasons are trimmed by the API
before its 1–500-byte check and cannot contain NUL; grant reasons are untrimmed,
nonempty 1–500 bytes and cannot contain NUL. Service subjects are nonblank,
untrimmed and at most 200 UTF-8 bytes without NUL. The CLI sends the original
file bytes once and validates the bounded response, selected resource identity,
status and nullable version before printing. JSON retains the complete
authorized receipt; text escapes controls. A complete canonical API 4xx is a
known denial. Lost, malformed or unsafe write replies are `outcome_unknown`;
inspect the exact resource only as an observation, then deliberately replay
the unchanged action, selectors, file bytes and key if appropriate. The CLI
never preflights authority or retries automatically.

## Edit your profile

```sh
workstream profile update --display-name 'Ada' --contact-email 'ada@example.test'
workstream profile update --clear-contact-email --output json
```

Only human caller-owned `display_name` and `contact_email` are writable.
An omitted flag leaves its field unchanged; a clear flag sends explicit JSON
null. You can also use `--clear-display-name`. Select at least one field; setting
and clearing the same field is invalid. Text must be valid UTF-8 and the JSON
request is capped at 8 KiB. Workstream validates and normalizes the text:
display name has a 200-character limit, contact text 320, and blank or NUL text
is rejected. Contact text does not change your Flow login or identity.
Caller-owned profile editing cannot provision service actors or change
authority/lifecycle state; use the separate explicit `admin` commands above.

A successful update prints the validated API profile, using the same text/JSON
output as `whoami`. No preflight read or automatic retry is performed, and no
idempotency/version mechanism is invented. If the server might have received
the update but no trustworthy result arrives (including lost connection,
malformed success, redirect or server error), exit status is nonzero and JSON
includes `error.outcome_unknown: true`; text explains the uncertainty. Do not
assume rollback or blindly retry: use `workstream whoami` to inspect the current
profile. That observation cannot establish global order against concurrent
later edits. Complete 4xx replies with a parseable Workstream error envelope
(a nonempty string `error.code`) remain known denials or validation failures,
even when sensitive metadata is suppressed. A gateway 4xx without that envelope
is uncertain too; HTTP status alone does not establish a Workstream denial.

## Operator checker registration and terminal recovery

The `operations checker` commands consume four existing public `/api/v1`
operations. They require a current system Operator grant on every call; a prior
read is not authority for a later write. Registry publication stores an
immutable definition but does not select, enable, execute or activate a checker.

```sh
workstream operations checker registry register --input checker.json --idempotency-key UUID -o json
workstream operations checker registry read ENTRY_ID -o json
workstream operations checker retry-sources PROJECT_ID --limit 50 -o json
workstream operations checker retry-sources PROJECT_ID --limit 50 --cursor 'OPAQUE_CURSOR' -o json
workstream operations checker retry PROJECT_ID SOURCE_RUN_ID --reason 'Verified infrastructure restored' --idempotency-key UUID -o json
```

`checker.json` is one closed `ExternalCheckerRegistrySpec` object with
`capability_id`, `capability_version`, `phase` (`pre_submit` or `post_submit`),
`image_digest` (`sha256:` and 64 lowercase hexadecimal digits),
`configuration_schema`, `input_schema`, `output_schema` and `resources`.
Each schema has `schema_id`, `schema_version`, an object `document`, and
`schema_sha256`; input schema IDs are
`external_checker_pre_submit_input` or
`external_checker_post_submit_input` according to phase, and the output schema
ID is `external_checker_result`. Resources are `cpu_millis` (100..64000),
`memory_bytes` (16777216..68719476736), `deadline_ms` (100..3600000) and
`maximum_output_bytes` (256..65536). The file is read once as a regular JSON
file, at most 1 MiB, and sent unchanged. The CLI checks its closed wire shape,
phase identities and bounds; the backend validates JSON Schema semantics and
computes each canonical schema/entry digest. An entry read returns the exact
server-selected UUIDv7 entry and immutable specification, not a latest alias.

`retry-sources` returns only one project-bound page (1..100 items) and its
opaque `next_cursor`; the CLI never follows pages automatically. The backend
marks each source `eligible`, `retried` with its retained successor, or
`not_current`. Only an exact finalized post-submit infrastructure failure can
be retried, after the named problem has been restored. The retry command
requires an explicit reason of 1..500 characters without ASCII controls and a
caller-owned UUID key. It sends one POST, creates no Review, acceptance,
contribution or award, and never enables an external checker. On a lost or
malformed response, `error.outcome_unknown` is true: manually replay the
unchanged project, source run, reason and key. A fresh backend authority check
also applies to exact replay. There is no preflight authority check, automatic
retry, cached source eligibility or local policy decision. JSON output is the
complete validated public response; text output safely escapes terminal
controls.

## Inspect uncertain post-submit deliveries

The separate `operations delivery` commands consume the two public UNKNOWN
delivery routes. A system Operator can read one project page at a time (1..100
items, default 50), carrying the opaque `next_cursor` to another explicit read.
The page reports exact finalized request or completion events and the backend's
current classification; a read neither grants write authority nor determines
eligibility locally.

```sh
workstream operations delivery list PROJECT_ID --limit 50 -o json
workstream operations delivery list PROJECT_ID --limit 50 --cursor 'OPAQUE_CURSOR' -o json
workstream operations delivery reconcile PROJECT_ID EVENT_ID --reason 'Verified original UNKNOWN attempt' --idempotency-key UUID -o json
```

`reconcile` sends one POST for the selected event, a required 1..500-character
reason without surrounding whitespace or ASCII controls, and a caller-owned
UUID key. Fresh backend authority and exact source/child guards decide whether
one immutable reconciliation child may be appended. The CLI does not classify
the original effect, invoke a checker, infer retry safety, or silently replay
the write. On an uncertain response, JSON has `error.outcome_unknown: true`;
text advises manual replay only with the unchanged project, event, reason and
key. An existing child can later be active, acknowledged or held on exact
replay. This is distinct from `operations checker retry`, which selects a
known-terminal infrastructure-failed checker run.

## Inspect artifact custody and explicitly retry verification

`operations artifact` uses the existing public `/api/v1/operator/artifacts`
routes. It requires current system-Operator authority; observations do not
authorize a later mutation, reveal provider coordinates or establish readiness
locally.

```sh
workstream operations artifact bindings submission SUBMISSION_ID -o json
workstream operations artifact replicas CONTENT_ID -o json
workstream operations artifact receipts REPLICA_ID -o json
workstream operations artifact verification-job JOB_ID -o json
workstream operations artifact recovery-attempt ATTEMPT_ID -o json
workstream operations artifact audit-events artifact_binding BINDING_ID -o json
workstream operations artifact admission-usage PROJECT_ID --task-id TASK_ID -o json
workstream operations artifact readiness -o json
workstream operations artifact retry JOB_ID --project-id PROJECT_ID --task-id TASK_ID --submission-id SUBMISSION_ID --reason 'Provider availability restored' --idempotency-key UUID --expected-source-job-cas-version 3 -o json
```

Bindings, replicas, receipts, audit events and admission usage return one bounded page. Continue
explicitly with `--cursor` and the same selectors and `--limit` (1..100, default
50). The backend determines which resource types and facts the caller may read.
Retry uses the exact source job and current CAS version, project, task, optional
submission, reason and caller-owned key. It sends one POST; it does not retry
automatically or infer eligibility from a successful read. An uncertain outcome
must be reconciled by manually replaying those unchanged inputs. Fresh authority
is required even for replay. A successful upload is not a failed verification
job and should not be retried through this operation.

## Verification

### Public API handoff for MCP and other clients

The command-to-operation table above is a navigation aid for the existing
public API, not a second contract. Use the running API's `/docs` and
`/openapi.json` for exact request/response fields, required headers and error
schemas. Compare against the same backend commit: later API changes can make a
static inventory stale.

For each operation, the corresponding files in `internal/api/` show the CLI's
wire mapping and response checks. The built-process tests in `tests/integration/`
show valid input, malformed responses, denial and replay cases; files ending
`_public_api.py` exercise the real backend with isolated prerequisites. These
focused tests do not all establish a connected user journey; the separate
journey below does that for its stated policy branch.

An MCP tool should call that same public REST operation directly, forwarding
the caller's bearer. Do not invoke the CLI binary, import backend internals,
copy authorization decisions or infer permission from a previous read. Keep
opaque pagination and explicit unchanged-payload mutation replay. The CLI is
an implementation and test reference, not an additional service dependency.

Behavior tests invoke the built executable from outside the repository, with
no import of Go internals. One suite uses a controlled HTTP server to exercise
credential/destination safety, output and failure boundaries. The other uses
the current FastAPI app with isolated real PostgreSQL to prove first admission,
profile fields, authorized exact-project context and foreign-project denial.
It also proves persisted profile edits, normalization, omission/null semantics,
field limits, caller isolation and suspended denial. The HTTP fixture proves
the exact PATCH body, invalid local input, redirect refusal and no-retry behavior
when a response is lost after body receipt.
Project inspection adds full/minimal projection parity, encoded selectors and
malformed/substituted response rejection at the process boundary. Real API
proof creates two projects and an exact contributor grant through public APIs,
then verifies foreign-project, revoked-grant and suspended-actor concealment.
Manager task proof creates draft work in two stored projects through public
POSTs, then compares real paginated and detail responses with direct REST reads.
It separates signed-cursor substitution (authorized caller receives 422) from
foreign authority denial, and proves a restored grant permits both reads before
suspension denies them. Hostile HTTP process tests validate complete field
output, one-request pagination, malformed/substituted replies and redirect refusal.
Contributor proof reuses that API process and bootstrap, arranging approved
upstream guide inputs through canonical fixtures. Guide inference and storage
are scripted prerequisites, not live-provider proof; real AUTH activates the
projects. Public task create/screen/release/claim operations supply persisted
ready and assigned work. Reads prove pagination parity, draft/claimed exclusion,
same-project non-owner concealment, independent authorized cursor substitution,
exact Submitter grants, Reviewer-only/foreign/revoked denial and suspension after
restored positive authority. The process fixture verifies the separate contributor
shapes, complete field output and refusal of management-only data.
Contributor mutation proof extends the same API/bootstrap journey with CLI
claim/start, persisted assignment and locked lineage, exact replay parity,
reason/task mismatch, same-project non-owner denial, foreign/Reviewer-only
authority, revocation and suspension. Denied writes are compared with the
publicly observed post-administration task baseline, not an assumed pre-revoke
state. Process tests prove the exact POST/key/body, strict claim/start response
identity, safe text, canonical errors and uncertain/no-retry behavior.
Local Flow-compatible tokens are test fixtures, not deployed-provider proof.
No coverage percentage or test-count target is used.

Batch proof covers the built CLI's CSV conversion, source upload, atomic import,
status, screen and release against real PostgreSQL/MinIO. Contribution-export
proof covers self and authorized project reads, exact server CSV, fresh grant
and lifecycle denials, and safe local publication failures. These are separate
journeys in one binary, not proof of a complete public setup-to-acceptance journey.
Hosted CLI verification partitions the complete integration directory into
task/general HTTP, guide HTTP, native API, native self-service and native batch
groups. The contribution HTTP and native API tests remain included; no group
replaces or skips another. Local conversion rule tests supplement process tests.
Operator checker proof uses the built binary against adversarial HTTP and one
isolated signed FastAPI/PostgreSQL journey: exact registry publication/read and
replay, terminal-source discovery, explicit retry/replay, foreign selection and
grant-revocation denial. The source's infrastructure failure is arranged by a
real backend worker fixture. This does not prove hosted OCI execution, external
Flow issuer integration or S3 custody.
Delivery CLI built-process hostile HTTP proof covers response boundaries. A
separate signed public FastAPI/PostgreSQL test is present for an owner-produced
UNKNOWN source, one keyed child, exact replay and fresh revocation denial; its
native run remains pending. Neither test establishes a hosted interruption or
S3 custody drill.

```sh
go mod verify
go vet ./...
go build -trimpath -o /tmp/workstream-cli ./cmd/workstream
# With the backend test environment installed:
WORKSTREAM_CLI_EXECUTABLE=/tmp/workstream-cli python -m pytest -q tests/integration/test_http_boundary.py
# From backend/, with a local disposable PostgreSQL admin URL in the environment:
WORKSTREAM_CLI_EXECUTABLE=/tmp/workstream-cli python scripts/run_isolated_tests.py --metadata-json /tmp/workstream-cli-isolation.json -- python -m pytest -q ../cli/tests/integration
```

The real API fixture uses the documented local administrator bootstrap solely
to arrange test authority, then creates its project through public APIs. These
test dependencies are absent from the shipped CLI. See the workflow for the
complete [hosted check](../.github/workflows/cli.yml).
That reusable check runs in parallel with Backend lanes; its failure also fails
the existing required Backend `test` result. No separate optional PR workflow
or extra branch-protection setting is needed.

### Connected local journey

`tests/journey/bootstrap.py` exercises the built CLI against a fresh migrated
PostgreSQL database, real MinIO, a private Redis broker, prefork Celery workers
and the real external checker service. It creates product prerequisites through
public CLI operations. The documented local administrator bootstrap and lifecycle
deployment transition are explicit deployment prerequisites, not fixture-created
project, submission or acceptance records.

This drill currently targets a Linux Docker host whose daemon can bind-mount the
same local scratch paths. Install the backend environment, Go, Rust, Docker and
`redis-server`. Use the local PostgreSQL/MinIO prerequisites and proof-checker
publication instructions in the [local agent loop](../docs/engineering/local-agent-loop.md)
to generate `.local-agent-loop/checker-service.json`, `registry-pre.json` and
`registry-post.json`. The drill starts its own native API, worker and checker
processes; it does not use an already-running application database or broker.

From the repository root:

```sh
(cd cli && go build -trimpath -o ../.local-agent-loop/workstream ./cmd/workstream)
cargo build --manifest-path external_checkers/Cargo.toml --locked --release \
  -p workstream-checker-service --jobs 2
export WORKSTREAM_CLI_EXECUTABLE="$PWD/.local-agent-loop/workstream"
export WORKSTREAM_CLI_JOURNEY_SETUP=1
export WORKSTREAM_CLI_JOURNEY_TASKS=1
export WORKSTREAM_CLI_JOURNEY_SUBMIT=1
# Optional private raw CLI receipts for independent review; keep outside git.
export WORKSTREAM_CLI_JOURNEY_EVIDENCE="$(mktemp -d /tmp/workstream-journey-evidence.XXXXXX)"
# Supply a disposable local PostgreSQL admin URL and the local MinIO endpoint
# through WORKSTREAM_TEST_ADMIN_DATABASE_URL and WORKSTREAM_TEST_MINIO_ENDPOINT.
cd backend
.venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json /tmp/workstream-cli-journey-isolation.json \
  --lane cli_full_journey --timeout-seconds 900 -- \
  .venv/bin/python ../cli/tests/journey/bootstrap.py
```

Use the isolated runner's fixed local test MinIO credentials, never production
credentials. Each run owns a unique database/role and bucket/prefix. Require its
cleanup metadata as well as exit zero; neither a completed migration nor a
successful intermediate stage proves the remaining journey. Do not bypass a
failed prerequisite or substitute a synthetic checker result.
The optional evidence directory retains command arguments, exit codes and raw
stdout/stderr after checking for bearer disclosure. It contains local project
data: keep it private and do not commit it. Use a fresh directory for each run.
Setup-enabled runs also retain private runtime logs after stopping their owned
processes. These logs are diagnostic evidence, not proof that a failed stage
succeeded. To verify an explicitly reviewed checker repair before merge, set
`WORKSTREAM_CLI_JOURNEY_CHECKER_EXECUTABLE` to its built binary and record that
binary's SHA-256 and source commit; this is cross-branch integration evidence.

The scope is manager-authored setup, an explicitly unpaid policy and the locked
no-human-review acceptance branch. The example checker validates declared proof
fields, not the truth of remote GitHub work. This is not hosted deployment,
external Flow issuer, live model inference, human review/revision or compensation
fulfillment certification. The connected proof also reads the exact submission's
artifact binding, replica and verification evidence through the Operator CLI,
and checks non-Operator concealment. The separate signed API test exercises
retry only on a genuinely exhausted verification job. A successful upload is
never used as an eligible retry fixture.
