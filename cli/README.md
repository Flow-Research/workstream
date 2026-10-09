# Workstream CLI

An independent Go client for Workstream's public REST API, for humans and
agents using the terminal. It provides human self-profile reads and editing,
plus draft project/guide declaration and original upload, exact-project inspection, authority reads, manager task browsing and
contributor work discovery, claim/start, locked guide documents and governing
context/intake requirements:

| Command | Public API |
|---|---|
| `workstream whoami` | `GET /api/v1/actors/me` |
| `workstream profile update` | `PATCH /api/v1/actors/me` |
| `workstream project access PROJECT_ID` | `GET /api/v1/actors/me/authorization-context?project_id=PROJECT_ID` |
| `workstream project show PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID` |
| `workstream project create --name TEXT --slug TEXT --idempotency-key UUID` | `POST /api/v1/projects` |
| `workstream project guide create PROJECT_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides` |
| `workstream project guide upload PROJECT_ID GUIDE_ID DOCUMENT_ID --file FILE --media-type MIME --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/documents/DOCUMENT_ID/content` |
| `workstream project guide setup PROJECT_ID GUIDE_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/setup-runs/latest` |
| `workstream project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID` | `GET /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/compilations/COMPILATION_ID/proposal` |
| `workstream project guide approve-pre PROJECT_ID GUIDE_ID COMPILATION_ID --input FILE --idempotency-key UUID` | `POST /api/v1/projects/PROJECT_ID/guides/GUIDE_ID/compilations/COMPILATION_ID/pre-submission-approval` |
| `workstream project tasks PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/tasks` |
| `workstream project task PROJECT_ID TASK_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/TASK_ID` |
| `workstream task ready PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID/tasks/ready` |
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
work context use 2 MiB wire bounds; exact guide proposals use 8 MiB). Original downloads stream to private files,
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
Deliberate intake approval is a separate command below; activation remains future CLI work.

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

## Browse tasks as a project manager

```sh
workstream project tasks PROJECT_ID --limit 10 --output json
workstream project tasks PROJECT_ID --limit 10 --cursor PREVIOUS_NEXT_CURSOR --output json
workstream project task PROJECT_ID TASK_ID --output json
```

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
Hints are observations, not authority
or a claimability guarantee. The CLI never recomputes them or automatically
executes a hinted action. Claim/start independently authorize their requests.

Requirements expose the task's locked guide and intake rules: packet fields,
artifact/evidence requirements, forbidden patterns, attestation, hash/manifest
requirements, storage-reference restrictions, size/entry limits and packaging.
They are not a current-guide lookup, a checker verdict or permission to upload.
Submission intake is still hidden; these commands do not expose it. Described
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
The task rebase operation remains separate planned work.

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
field with escaped terminal controls. This does not expose submission or review
commands, or activate unfinished product lifecycle work.

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
