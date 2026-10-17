# Workstream CLI

An independent Go client for Workstream's public REST API, for humans and
agents using the terminal. It provides human self-profile reads and editing,
plus draft project/guide declaration and original upload, exact-project inspection, authority reads, manager task browsing and
contributor work discovery, claim/start, locked guide documents and governing
context/intake requirements, explicit batch import/screen/release, Finance
policy management, explicit ZIP preparation/submission, checker findings and
contribution-evidence exports:

| Command | Public API |
|---|---|
| `workstream whoami` | `GET /api/v1/actors/me` |
| `workstream profile update` | `PATCH /api/v1/actors/me` |
| `workstream contributions [--project UUID]` | `GET /api/v1/actors/me/contributions` |
| `workstream project contributions PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/contributions/export` |
| `workstream project access PROJECT_ID` | `GET /api/v1/actors/me/authorization-context?project_id=PROJECT_ID` |
| `workstream project show PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID` |
| `workstream project create --name TEXT --slug TEXT --idempotency-key UUID` | `POST /api/v1/projects` |
| `workstream project guide create PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides` |
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
| `workstream project tasks PROJECT_ID [--status S] [--assignee UUID] [--import-batch UUID] [--updated-since TIME]` | `GET /api/v1/projects/PROJECT_ID/tasks` |
| `workstream project task PROJECT_ID TASK_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/TASK_ID` |
| `workstream project submissions PROJECT_ID [--task UUID] [--status S] [--submitter UUID] [--updated-since TIME] [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/submissions` |
| `workstream project assignments PROJECT_ID [--state active\|closed] [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/assignments` |
| `workstream project summary PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/summary` |
| `workstream project import-batches PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/task-import-batches` |
| `workstream project preparations PROJECT_ID [--outcome pending\|passed\|failed\|infrastructure_failed] [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/submission-bundle-preparations` |
| `workstream project task create PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/tasks` |
| `workstream project task screen PROJECT_ID TASK_ID --idempotency-key UUID [--reason TEXT]` | `POST /api/v1/tasks/TASK_ID/screen` |
| `workstream project task release PROJECT_ID TASK_ID --idempotency-key UUID --reason TEXT` | `POST /api/v1/tasks/TASK_ID/release` |
| `workstream project task-batch convert-csv --input FILE --out FILE` | Local CSV-to-JSON conversion; no API call |
| `workstream project task-batch source-declare PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/task-import-sources` |
| `workstream project task-batch source-upload PROJECT_ID SOURCE_ID --input FILE` | `PUT /api/v1/projects/PROJECT_ID/task-import-sources/SOURCE_ID/content` |
| `workstream project task-batch source-status PROJECT_ID SOURCE_ID` | `GET /api/v1/projects/PROJECT_ID/task-import-sources/SOURCE_ID` |
| `workstream project task-batch import PROJECT_ID SOURCE_ID --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/task-import-batches` |
| `workstream project task-batch status PROJECT_ID BATCH_ID` | `GET /api/v1/projects/PROJECT_ID/task-import-batches/BATCH_ID` |
| `workstream project task-batch screen PROJECT_ID BATCH_ID --idempotency-key UUID [--reason TEXT]` | `POST /api/v1/projects/PROJECT_ID/task-import-batches/BATCH_ID/screen` |
| `workstream project task-batch release PROJECT_ID BATCH_ID --idempotency-key UUID --reason TEXT` | `POST /api/v1/projects/PROJECT_ID/task-import-batches/BATCH_ID/release` |
| `workstream project role-grant issue PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/role-grants` |
| `workstream project role-grant revoke PROJECT_ID GRANT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/role-grants/GRANT_ID/revoke` |
| `workstream project role-grant list PROJECT_ID [--status active\|revoked] [--role submitter\|reviewer]` | `GET /api/v1/projects/PROJECT_ID/role-grants` |
| `workstream project role-grant show PROJECT_ID GRANT_ID` | `GET /api/v1/projects/PROJECT_ID/role-grants/GRANT_ID` |
| `workstream project contribution-policy current PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/contribution-policies/current` |
| `workstream project contribution-policy show PROJECT_ID POLICY_ID [--version UUID]` | `GET /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID` with optional `version_id` |
| `workstream project contribution-policy list PROJECT_ID [--limit N] [--cursor TOKEN]` | `GET /api/v1/projects/PROJECT_ID/contribution-policies` |
| `workstream project contribution-policy create PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/contribution-policies/drafts` |
| `workstream project contribution-policy update PROJECT_ID POLICY_ID VERSION_ID --input FILE --idempotency-key UUID` | `PUT /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID/versions/VERSION_ID` |
| `workstream project contribution-policy publish PROJECT_ID POLICY_ID VERSION_ID --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID/versions/VERSION_ID/publication` |
| `workstream project contribution-policy retire PROJECT_ID POLICY_ID VERSION_ID --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/contribution-policies/POLICY_ID/versions/VERSION_ID/retirement` |
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
| `workstream task context TASK_ID` | `GET /api/v1/tasks/TASK_ID/work-context` |
| `workstream task guide TASK_ID [--download DIR]` | Work context, then assigned-task `GET /api/v1/tasks/TASK_ID/guide/documents/DOCUMENT_ID/content` for downloads |
| `workstream task requirements TASK_ID` | `GET /api/v1/tasks/TASK_ID/submission-requirements` |

Workstream verifies the caller's Flow bearer and owns identity resolution,
authorization and lifecycle decisions. Reading a profile can admit a first-time
caller and update server-owned last-seen/audit data. Project access is a current
snapshot; each later API operation must independently authorize the caller.

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

The table above is the delivered command inventory. PILOT-02 supplies the
[batch conversion/import/screen/release commands](#prepare-a-task-import-json-source)
in the same CLI; contribution-evidence reads do not depend on using batch import.
Submission preparation, creation and history commands are described below;
manager revision repair and human-review commands are outside this CLI inventory.

## Build and use

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
source package is buildable; published binaries, installers and signing are a
later release boundary. The [CLI initiative](../.commitrail/initiatives/WS-CLI-001/OVERVIEW.md)
describes subsequent public workflows and an optional TUI.

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
work context and grant history use 2 MiB wire bounds; exact guide proposals use 8 MiB). Original downloads stream to private files,
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
revocation is denied by the backend's retained-state check. No actor discovery,
automatic role assignment or AdminRole mutation is added.

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
Text renders that same complete object with terminal escaping. Private runtime
document handles are not part of this public projection. Unknown/duplicate
members, missing/null required facts, malformed nested types or substituted
identities fail with empty stdout. Integer facts retain the backend range.

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
not in the current public history rows.
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
```

Conversion is local and needs no token or API configuration. It accepts quoted
UTF-8 CSV, including embedded commas/newlines and one optional UTF-8 BOM. It
requires 1..500 task rows and bounds both input CSV and generated JSON to 8MiB.
Invalid input produces no JSON file. `--out` must name a new file; an existing
file is never overwritten. The report names the SHA-256 and byte count of the
complete generated JSON, including its final newline. Upload those exact bytes.
Workstream retains the converted JSON source; this does not retain the original
CSV. Retain that original separately if your own workflow requires it.

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
response. Status and source operations retain the normal twelve-second deadline.
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
workstream project submissions PROJECT_ID --status review_pending --updated-since 2026-10-01T00:00:00Z
workstream project assignments PROJECT_ID --state active
workstream project summary PROJECT_ID --output json
workstream project import-batches PROJECT_ID
workstream project preparations PROJECT_ID --outcome failed
```

These reads require a current Project Manager grant covering the project; any
other caller, project, guide or document is reported as not found. `guide list`
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

`submissions` and `assignments` list every attempt and claim in the project
with the submitter or contributor and the same fields as `me submissions` and
`me assignments`. `summary` counts tasks by status, claims by state and attempts
by outcome, with the acceptance rate (accepted over decided attempts) and
post-submission checker infrastructure failures; award totals appear only when
you also hold an exact-project Finance Authority grant and are otherwise null.
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
Service-actor editing and authority/lifecycle changes are not CLI operations.

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

## Verification

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
