# Remote MCP submission upload authorization

## 1. Status and decision

This is the implementation contract for **planned** remote MCP ZIP transport.
This design change enables no endpoint, credential, tool or deployment. Its
dependency is [PR #708](https://github.com/Flow-Research/workstream/pull/708),
inspected at `4b763013920e79b6d70c99639f2d84e72341952a`, with main at
`5c47b924208e4245bb5575e90df310b1b524aae0`. Reconcile these owners again at
implementation time. The [submission execution specification](spec_submission_execution.md)
continues to own submission, PRE, source custody, T4 acceptance, T5 finalization
and POST. [WS-MCP-002-14](../.commitrail/initiatives/WS-MCP-002/WS-MCP-002-14.md)
records this design's scope and review.

The contributor's execution environment creates and keeps the ZIP. It calls a
remote MCP tool with small metadata, receives a temporary credential, and streams
that local ZIP over HTTPS to the existing Workstream submission endpoint. MCP
never opens the client's filesystem or receives its ZIP bytes. Its normal Flow
exchange/API credential stays inside MCP.

The credential authorizes **one admission of one exact submission attempt**.
Unused credentials expire after ten minutes. A successful admission transaction
consumes the credential permanently, before body processing; completing an upload
does not leave it usable until its timestamp expires. The credential grants no
general API access, status-read authority, task claim, storage access, refresh or
ability to issue another credential.

This replaces the affected Base64 submission tool when implemented. It does not
add another upload pipeline, a presigned storage PUT, a staging bucket, a finalize
call, or Workstream primary authentication. Initial work and governed revisions
use the same existing raw-ZIP endpoint.

## 2. Participants and end-to-end behavior

```mermaid
sequenceDiagram
    participant C as Agent runtime
    participant M as Remote MCP
    participant A as Workstream API
    participant D as PostgreSQL
    C->>C: Create ZIP; measure bytes and SHA-256
    C->>M: Authorize task, assignment, key and exact file
    M->>A: Small JSON request with same-caller API credential
    A->>D: Check current authority; persist credential digest and allow evidence
    A-->>M: Temporary submission credential
    M-->>C: Public upload descriptor
    C->>A: Raw ZIP with SubmissionUpload credential
    A->>D: Atomically consume credential and admit operation
    A->>A: Stream, verify exact bytes and run existing PRE
    A->>D: Existing T4 accepted handoff or terminal failure
    A-->>C: Existing accepted receipt or bounded failure
    opt Response unavailable or progress needed
        C->>M: Read operation with original task and key
        M->>A: Existing authenticated operation read
        A-->>C: Retained operation outcome via MCP
    end
```

The raw-ZIP response is the existing `202` durable acceptance receipt or bounded
failure/PRE feedback. `202` does not mean POST, review, final acceptance or a
ContributionRecord has completed. T5 and POST continue under their existing
durable owners; no fabricated Submission ID is returned before one exists.

The client must provide local-file read/stat/hash and streaming HTTPS abilities
outside MCP, accept the structured descriptor, set its exact headers, disable
redirects and automatic mutation retries, and preserve the original recovery
key. A client offering only remote JSON tool calls cannot execute the byte leg.
Its honest fallback is a user/runtime uploader with these capabilities, not a
local pathname handed to the remote server. Browser-only clients also need a
qualified upload integration and applicable CORS policy; this contract does not
enable arbitrary browser origins.

### Current owners being extended

| Concern | Inspected owner | Required extension |
| --- | --- | --- |
| Remote submission input | [`tools/task_execution.py`](../mcp_server/workstream_mcp/tools/task_execution.py), [`schemas.py`](../mcp_server/workstream_mcp/schemas.py) | Replace `submission_create` / `zip_base64` with metadata-only authorization. |
| Same-user API exchange and dispatch | [`http_gateway.py`](../mcp_server/workstream_mcp/http_gateway.py) | Keep the existing exchange; dispatch one fixed JSON authorization operation. |
| Raw-ZIP route | [`artifact_submissions.py`](../backend/app/api/routes/artifact_submissions.py), [`submission_intake.py`](../backend/app/api/submission_intake.py) | Select exactly one authentication mode; retain existing command and selectors. |
| AUTH context and prepared decisions | [`runtime.py`](../backend/app/modules/authorization/runtime.py), [`submission_intake.py`](../backend/app/modules/authorization/submission_intake.py), [`prepared.py`](../backend/app/modules/authorization/prepared.py) | Add an explicit submission-only credential context and evidence, never fabricate Flow authentication. |
| Admission and accepted handoff | [`foreground_admission.py`](../backend/app/modules/artifacts/intake/foreground_admission.py) | Bind credential validation/consumption to T1 and preserve PRE/T4 authority checks. |
| Byte receipt and cleanup | [`foreground_upload.py`](../backend/app/modules/artifacts/intake/foreground_upload.py), [`streaming.py`](../backend/app/modules/artifacts/intake/streaming.py) | Compare actual bytes/hash before recording EOF; reuse source cleanup and accounting. |
| Operation recovery | Existing `GET /api/v1/tasks/{task_id}/submission-operations` and `workstream_submission_operation_get` | Recover under ordinary current MCP/Flow authority; the upload credential cannot read. |

## 3. Public contracts

All new JSON models are closed (`extra=forbid`), and parsing never coerces booleans
to integers. Record IDs use the repository's UUIDv7 generator; caller keys remain
caller-supplied UUIDs. No request takes an actor, project authority, arbitrary
URL, header map, filesystem path, general access token, revision selector or
compensation selector. The backend derives those facts through current owners.

### 3.1 Authorization API

Add `POST /api/v1/tasks/{task_id}/submission-upload-authorizations`.

- Authentication: existing Flow-backed human API credential only.
- Header: one `Idempotency-Key`, the key of the **eventual submission attempt**.
- Content type: `application/json`; bounded by existing small-JSON controls.
- AUTH action: `submission.upload_authorize` / `SUBMISSION_UPLOAD_AUTHORIZE`,
  mapped to the existing `submission.create` permission and exact-project
  Submitter authority. A manager role alone is insufficient.
- Resource type: `submission_upload_authorization`, identified by the generated
  credential record ID and exact generation.

| JSON input | Rule |
| --- | --- |
| `assignment_id` | Required UUID; must belong to this task and current actor. |
| `byte_count` | Required integer, `1..524288000` (500 MiB), further bounded by current locked project limits and the qualified API profile. |
| `sha256` | Required `sha256:` followed by 64 lowercase hexadecimal characters, computed over the exact raw ZIP file. |
| `feedback` | Optional/null or the existing nonempty printable ASCII feedback, maximum 4096 bytes, without leading/trailing whitespace. Omission and null both mean absent feedback. |

The API checks current actor/link, exact Submitter grant, assignment, task
eligibility, revision requirements and current governing policy using the same
public owners as admission. Issuance reserves no source bytes, task guard, PRE
slot or submission operation. It promises no future admission: authority,
eligibility and capacity are checked again when the token is presented.

Both first issuance and replacement return `200 OK`, with
`Cache-Control: no-store`, after a positively acknowledged database commit:

```json
{
  "authorization_id": "<generated UUIDv7>",
  "generation": 1,
  "task_id": "<requested task UUID>",
  "assignment_id": "<requested assignment UUID>",
  "idempotency_key": "<original caller UUID>",
  "byte_count": 104857600,
  "sha256": "sha256:<64 lowercase hexadecimal characters>",
  "feedback": null,
  "expires_at": "<UTC RFC3339 timestamp>",
  "token_type": "SubmissionUpload",
  "upload_token": "wsu1.<authorization UUIDv7>.<random secret>",
  "upload_path": "/api/v1/tasks/<task UUID>/submissions"
}
```

Placeholders are illustrative, not valid request fixtures. The API returns a
relative canonical path; it never trusts a request Host or forwarding header to
construct a credential destination. It returns no storage address or ordinary
API token. Secrets are excluded from model reprs and HTTP error/validation bodies.

The single caller key is sufficient. Issuance is deliberately **not** an
idempotent secret-replay operation: an authenticated repeat with identical
binding replaces an unused secret, advances `generation`, resets the ten-minute
expiry and invalidates the previous secret. No plaintext or reversible token
store is needed to recover a lost issuance response. A client must serialize
authorization requests for one key; overlapping issuance responses may arrive
out of order, and only the latest committed generation works.

If the key already owns any admitted intake operation, including an ordinary
Flow upload or a terminal failed operation, return a bounded `409
submission_operation_exists` with `next_action=read_submission_operation` and
the original task/key recovery selectors. Return no credential. A key bound to
different file/metadata/identity-link facts returns `409
submission_upload_binding_conflict`. Neither condition starts another operation.

### 3.2 MCP tool and result

Replace `workstream_submission_create` with
`workstream_submission_upload_authorize` (internal name
`submission_upload_authorize`). Its input contains `task_id`, `assignment_id`,
`idempotency_key`, `byte_count`, `sha256` and optional `feedback`, with exactly
the API rules above. MCP forwards the key as the API header; it does not generate
one, calculate hashes remotely or change file metadata. It uses its ordinary
per-call, same-subject API exchange for this request.

Declare this a mutation with `readOnlyHint=false`, `idempotentHint=false` and
`openWorldHint=false`; the presence of `idempotency_key` must not make the current
annotation helper report repeat-safe issuance. Rotation invalidates a prior
unused credential, so retain the mutation's conservative destructive hint.

Validate the backend's closed response schema **and** every echoed binding,
token type, bounded token syntax, timestamp and exact task-specific upload path
before returning a descriptor. A malformed response is a safe, uncertain
issuance failure; do not echo its raw body or automatically retry it.

Return this closed shape as `structuredContent`:

```json
{
  "status": "upload_authorized",
  "authorization_id": "<UUIDv7>",
  "generation": 1,
  "expires_at": "<UTC RFC3339 timestamp>",
  "byte_count": 104857600,
  "sha256": "sha256:<64 lowercase hexadecimal characters>",
  "upload": {
    "method": "POST",
    "url": "https://<configured public API origin>/api/v1/tasks/<task UUID>/submissions",
    "headers": {
      "Authorization": "SubmissionUpload wsu1.<UUIDv7>.<random secret>",
      "Content-Type": "application/zip",
      "Content-Length": "104857600",
      "Idempotency-Key": "<original caller UUID>",
      "X-Task-Assignment-Id": "<assignment UUID>"
    }
  },
  "recovery": {
    "tool": "workstream_submission_operation_get",
    "arguments": {
      "task_id": "<task UUID>",
      "idempotency_key": "<original caller UUID>"
    }
  }
}
```

Include `X-Submission-Feedback` only for non-null authorized feedback. The
Authorization header is the token's sole location in the descriptor; do not also
return an `upload_token` field. Build the fixed method, path, allowed header
names and recovery tool locally from validated facts. Never relay arbitrary
backend headers or instructions. User feedback remains untrusted data.

Use the SDK's explicit `CallToolResult(content=[],
structured_content=validated_output)` after explicitly validating the composed
output against its closed schema. The installed low-level SDK returns an explicit
result without its automatic output-schema validation, so the adapter owns this
check. The current generic task renderer JSON-serializes the
entire result into text as well; this new result needs a focused branch to avoid
that duplicate. This limits server duplication, not client visibility: clients
may display or retain structured results. The scoped credential is intentionally
visible to the agent; normal OAuth, refresh and exchange credentials are not.
Do not claim MCP provides a hidden secret channel or guarantee client transcript
redaction. An authorization result must never say the ZIP was submitted.

### 3.3 Upload request

Use the existing `POST /api/v1/tasks/{task_id}/submissions`, with raw binary body
and `Authorization: SubmissionUpload <token>`.

The canonical parser still requires `Idempotency-Key` and
`X-Task-Assignment-Id`. Require their parsed UUIDs to match the credential;
require feedback bytes to match exactly. Null feedback requires header absence.
Require one decimal `Content-Length` equal to `byte_count`, one
`Content-Type: application/zip`, and absent/identity `Content-Encoding`.
Credential mode rejects `Transfer-Encoding` and missing/ambiguous framing;
ordinary Flow mode keeps its existing streaming contract. Reject duplicate
Authorization and selector headers using the same case-insensitive raw header
collection, not a last-value-wins parser. Missing/ambiguous syntax is rejected
before body consumption. Cross-task, cross-assignment or changed-key presentation
never redirects the credential's authority.

Select authentication **before** constructing the command's principal:

| Mode | Composition |
| --- | --- |
| `Bearer` | Existing Flow verifier, actor admission and human AUTH context. |
| `SubmissionUpload` | AUTH-owned credential locator and narrow submission-only context. No Flow token verification or identity admission is fabricated. |
| Missing, duplicated, unknown or mixed scheme | Bounded authentication error. No fallback from one scheme to the other. |

The current route eagerly depends on both `get_authorization_actor_identity`
and `get_submission_intake_command`, whose authorization dependency resolves
Flow identity. Merely adding a second parser would still execute those Flow
dependencies. Replace them **for this route** with one discriminated dependency
that supplies the correct principal/command composition. All other endpoints,
including authorization issuance and operation reads, retain ordinary Flow auth.
Describe the two alternatives in OpenAPI as route-specific alternatives; never
install `SubmissionUpload` as a global bearer verifier or a query parameter.

### 3.4 Errors and safe next actions

Use the existing structured API error envelope and correlation IDs. Additional
codes below must appear in the closed schemas and MCP-safe error mapping.

| Condition | HTTP/code | Effect and recovery |
| --- | --- | --- |
| Invalid issuance JSON/header | Existing `422` validation/packet error | No credential or operation; correct metadata. Redact credential-like inputs. |
| Issuance caller lacks current authority or cannot see task | Existing concealed `404 submission_unavailable` (Flow authentication errors remain `401`) | No credential; restore ordinary authority through existing owners. |
| Issuance key has another binding | `409 submission_upload_binding_conflict` | Preserve old binding; choose a new submission key for changed work. |
| Issuance key already has an operation | `409 submission_operation_exists` | No credential; read the original operation. |
| Invalid, unknown, expired, replaced or spent token; valid token with mismatched binding | `401 submission_upload_unauthorized`, `WWW-Authenticate: SubmissionUpload` | Same bounded message; no body, storage or PRE work. Do not expose token state or another caller's operation. |
| Valid credential but current authority/assignment unavailable | Existing concealed `404 submission_unavailable` | No T1 admission; normal MCP reads require their own current authority. |
| Active task guard or governed revision conflict | Existing `409` code | No new admission; inspect current assignment/operation. |
| Declared size over API/project bound | Existing `413 submission_archive_limit_exceeded` | Reject before consumption; changing the file requires a new key. |
| Scoped length absent/ambiguous, unsupported type/encoding | Existing `422 submission_packet_invalid` / `415 submission_media_type_unsupported` | No body or credential consumption. |
| Streamed count or hash differs from authorization | `422 submission_upload_content_mismatch` | Credential already spent; no EOF seal/PRE/Submission; existing terminalization and cleanup apply. |
| Admission capacity exhausted | Existing `429 submission_capacity_exceeded` | T1 rolls back, so no spent credential or new operation. Respect bounded retry guidance. |
| Upload/PRE timeout, PRE rejection, provider failure | Existing `408` / `504` / `422` / `503` distinctions | Status read determines whether the attempt is terminal or uncertain. Never replay a spent token. |
| Commit acknowledgement or response lost | Existing `503 submission_outcome_unknown` where a response is possible | Read using the original key through MCP; transport failure alone proves neither acceptance nor rollback. |

For credential mode, `submission_outcome_unknown` and other recovery messages
must say to **read the original operation**, replacing the ordinary API's
optional same-key body-replay advice. Keep ordinary Flow replay behavior intact.
Token validation errors do not offer a direct status URL authenticated by that
token. Admission creates no success receipt until existing T4 requirements hold.

## 4. Credential authority and persistence

### 4.1 Format and scope

AUTH generates `wsu1.<credential UUIDv7>.<secret>`, with a cryptographically
random 32-byte secret encoded as unpadded base64url (43 characters). Bound total
token syntax/length before lookup; the UUID is a locator, never authority. Store
only a SHA-256 digest of the full ASCII token with the fixed domain prefix
`workstream:submission-upload:credential:v1` plus a zero byte. Compare digests in constant
time. The 256-bit random secret permits a fast digest; this is not password
hashing or a self-contained signed JWT. No signing key, plaintext token column,
encrypted replay cache or refresh credential is introduced.

Scope is fixed to the issuing API deployment and the canonical POST for exactly
one actor, identity link, project, task, assignment, submission key, feedback,
raw byte count and raw SHA-256. Identity is inferred from authenticated issuance,
not from the token presenter. The credential is a bearer capability: whoever
holds it can start that exact upload; same-file binding does not prove who owns
the client process. It cannot authorize different content or another action.

Expiry is `issued_at + 10 minutes`, evaluated with the database clock after
waiting for T1 locks (`now < expires_at`). It limits when an unused upload can
start. After T1, existing upload/PRE deadlines and leases govern progress; an
expiry timestamp cannot kill or reopen an admitted operation.

Local suspension, link revocation, project-role loss and assignment/policy
changes are checked at issuance, T1 and the existing later authority boundaries.
Require the generation's issuing Submitter grant to remain active at T1 and
PRE/T4; revoke-and-regrant does not resurrect that credential. A fresh unused
generation may be issued under a newly valid grant through ordinary Flow auth.
Upstream issuer-session revocation is not automatically propagated to a detached
capability without an existing authoritative signal. This design promises the
ten-minute start bound and fresh Workstream checks, not instant upstream token
revocation. Do not retain or refresh the original API token to simulate it.

### 4.2 AUTH owns the credential

Add an AUTH model/table `SubmissionUploadCredential` /
`submission_upload_credentials`, with the following required facts:

| Fields | Custody |
| --- | --- |
| `id` | Generated UUIDv7 native PostgreSQL UUID; exposed as `authorization_id`. |
| `actor_profile_id`, `identity_link_id`, `project_id`, `task_id`, `assignment_id`, `idempotency_key` | Immutable principal/resource/key binding; unique `(actor_profile_id, idempotency_key)`. |
| `feedback`, `metadata_sha256`, `expected_raw_byte_count`, `expected_raw_sha256` | Immutable exact input; reuse `SubmissionIntakeMetadata.metadata_sha256()` for shared metadata semantics. |
| `generation`, `token_digest`, `issued_at`, `expires_at` | Current unused generation, positive version, digest only and database timestamps. |
| `issuance_decision_id`, `issuance_resource_sha256`, `issuing_grant_id` | Current generation's exact allowed `submission.upload_authorize` event, canonical resource digest and matched Submitter grant. Previous allow events remain immutable audit history. |
| `consumed_at`, `consumed_operation_id`, `redemption_decision_id` | All null while unused; all populated exactly once at T1. Operation reference is unique. The decision is the existing `submission.intake.reserve` allow. |

There is one record per actor/key, not a row per reissuance. Only the generation,
digest, issued/expiry and issuance-evidence fields may change while unused; the
binding cannot. Once consumed, all credential fields are immutable. Expiry is
derived from time, not a background job that races redemption. Unused records
are small retained authority facts; do not delete them and permit a prior key
to silently bind different work. Bulk retention/erasure remains governed by the
existing retention policy, not this upload feature.

Extend ART's `SubmissionIntakeOperation` with an all-null-or-complete credential
lineage group: `upload_credential_id`, `upload_credential_generation`,
`upload_issuance_decision_id`, `upload_redemption_decision_id`,
`expected_raw_byte_count`, `expected_raw_sha256`. Ordinary Flow operations have
null credential lineage. Retain expected values immutably so every stream,
recovery and audit check can prove the exact authorized bytes. No raw secret
enters ART, source metadata, checker inputs, queue payloads or receipts.

Use native UUID/composite foreign keys and deferred closure checks to prove
identity-link/actor, assignment/task/actor, task/project and credential/operation
ownership. A UUID existence check alone is insufficient. Enforce format/range,
expiry interval, state shape, immutable binding, generation transitions and
single consumption in PostgreSQL as well as models. Reuse the existing
constraint/migration conventions; do not disable guards for fixture insertion.

The deferred authorization closure must join the credential, its current
issuance allow, its redemption allow and the exact intake operation. Require
matching actor/link/project/task/assignment/key, credential ID/generation,
size/hash/metadata, exact resource digests, action/permission, matched grant and
request/correlation evidence. T4's closure must include the same credential
lineage in its `submission.create` resource and accepted receipt evidence. A
direct-SQL write must not attach a foreign allow event, clear lineage to mimic
Flow mode, reset consumption, or bind a second operation.

### 4.3 A distinct submission-only AUTH context

Current `HumanAuthorizationContext` assumes the trusted Flow-verification
composition root supplied it. Reconstructing it from credential-row actor/link
IDs would pass many existing type/SQL checks while falsely claiming that trust
path. This implementation must not do that.

AUTH exposes a narrow `SubmissionUploadCredentialAuthorizationPort` and an
AUTH-constructed `SubmissionUploadAuthorizationContext`, distinct from both
human Flow and service contexts. Use a private constructor/opaque handle pattern
like the existing prepared-authority machinery. Carry the credential ID and
generation, issuance decision/digest, `issuing_grant_id`, exact binding, actor/link state and this
request's IDs. Contexts are not accepted from JSON or arbitrary adapter callers.

Only the prepared submission intake reservation and submission acceptance
actions may accept this context. Reject it before generic human/service action
dispatch for all other actions, including issuance, reads, claim, administration
and review. The actor remains the actual contributor; no agent identity, service
impersonation or general delegation role is created.

Keep the public Flow `AuthorizationContext` identity contract unchanged. Admit
the new context only at the internal submission composition/prepared-kernel
boundary, with an explicit action allowlist before generic principal dispatch.
Do not make a scoped upload context satisfy generic human-context checks.

Extend the closed `IntakeReservationPreflightFacts`,
`IntakeReservationAuthorityFacts` and `IntakeAcceptanceAuthorityFacts` with the
credential evidence group. Direct Flow mode requires the group absent;
credential mode requires exact populated facts, including expected raw bytes.
Include it in canonical AUTH resource hashes and prepared-handle comparisons.
Retain the reservation decision UUID currently discarded by T1 as
`redemption_decision_id`; a second generic redeem action is unnecessary.

Exact issuing-grant continuity needs a concrete kernel change. The current
`lock_submitter_authority` selects any active Submitter grant. For credential
context, use an AUTH-owned exact-grant lock/check for ID, actor, project, role and
active status, with no fallback to another active grant. Propagate the issued
grant through existing `PreparedAuthorityScope.grant_id`, preflight matching,
`PreparedAuthorizationService._scope_from_resource()` and the reserve/acceptance
resource evidence. Require context, scope, resource and matched grant IDs to
agree. Direct Flow submission scopes continue to require no caller-selected
grant. SQL closure requires issue, reserve and acceptance allow events to match
the credential generation's grant; historical acceptance remains valid after a
later revocation.

The public port needs bounded operations for a non-authoritative locator read,
candidate actor/grant prelocking, unused-credential validation, issuance or
rotation, T1 consumption recording, and reconstruction from already-consumed
operation evidence. Typed facts cross owner boundaries; ART/TASK must not import
AUTH private tables or construct AUTH contexts. AUTH must not implement artifact
storage or task lifecycle policy. Existing transaction roots own commits.

## 5. Transactions, races and source binding

### 5.1 Issuance transaction

Resolve ordinary Flow identity. Lock TASK, then current actor/link and the exact
Submitter grant, then assignment/project policy through existing owner ports.
Check visibility before disclosing eligibility or a key conflict. Resolve the
actor/key credential and any existing operation using database uniqueness as the
backstop; current operations prohibit issuance even if no credential row exists.
Lock the existing credential only after these owner locks.

On the first call, generate the record ID and secret. On an identical unused
repeat, preserve immutable binding and replace the generation/secret. Prepare
and consume `submission.upload_authorize` with exact canonical facts including
generation, byte/hash/metadata and expiry. Persist the current issuance decision
and digest with the credential in the same transaction. Return the plaintext
secret only after commit acknowledgement; drop it on rollback or uncertain
commit. An authenticated identical retry safely rotates after uncertain issuance.
No storage I/O or body reading occurs under these locks.

Use the existing small-request admission/rate controls for this mutation and
validate eligibility before creating rows. A client can request many new keys,
so operational qualification must measure issuance abuse and retained-row growth;
do not call the 500 MiB upload bound an issuance-rate bound. No general token
management API or background credential garbage collector is needed for v0.1.

### 5.2 Atomic T1 redemption

Parse and validate the headers. A bounded, non-locking AUTH lookup by credential
UUID supplies candidate lock selectors only. It must not return a reusable
principal, disclose state, read body bytes or authorize provider work.

Preserve the existing **new-operation T1** order:

1. Lock the canonical TASK row.
2. Lock/refresh actor and identity link, then the exact issued Submitter grant.
3. Lock and validate current assignment, revision and project policy.
4. Lock the credential row; constant-time verify its current secret digest,
   generation's issuance evidence, unused state, database-clock expiry and every
   header/binding field. Recompare all facts from the earlier locator read.
5. Through `SubmissionIntakeRepository.reserve`, create the exact operation,
   task pointer and existing capacity reservations, with expected byte/hash and
   credential lineage. An existing actor/key is never a credential-mode replay.
6. Prepare/consume existing `submission.intake.reserve` with the operation's
   locked-context facts and credential evidence. Record the returned decision
   UUID; recheck database-clock expiry after any capacity-lock wait and mark the
   credential consumed by this exact operation and decision, with
   `issued_at <= consumed_at < expires_at`.
7. Commit once. Only positive acknowledgement returns a foreground owner that
   can read the body and start provider writes.

The credential row lock precedes ART operation/capacity writes, but consumption
is recorded after final reserve authorization because that decision needs the
ART-created locked-context facts. Deferred checks close the temporarily cyclic
references at commit. A failure at any step rolls back credential consumption,
operation, task pointer, charges and allowed decision together; canonical denial
restaging follows existing AUTH rules. No durable `uploading` token state or
distributed transaction is introduced.

Issuance/rotation uses the same lock prefix. If rotation wins, the old secret
fails; if redemption wins, rotation observes the operation/consumption and returns
the recovery conflict. Two redemptions produce at most one operation/foreground
owner. Different keys retain the existing one-active-operation task guard.
Across tasks, the actor/key uniqueness race must be handled after rollback,
without acquiring a second TASK lock in the old transaction. Recheck ownership
and binding in a fresh root; never return a foreign result or retry body work.

On a T1 commit acknowledgement loss, never invoke the ordinary `_read` fallback
under a fabricated human context and never grant another foreground lease.
Return an uncertain outcome; the caller uses authenticated MCP recovery. A
confirmed rollback permits a later use of an unexpired unused credential. A
transport failure itself is not proof of rollback.

### 5.3 Streaming and later roots

Pass the same bounded async body iterator to `ForegroundSourceUpload.receive`.
Track actual bytes and the existing incremental SHA-256; do not buffer the whole
ZIP or add a second hashing pass on the server. Stop at the expected count/global
or project bound, and verify both count and SHA before `record_eof`, source seal,
PRE reservation or any accepted handoff. A declared header alone proves nothing.
Same-length wrong bytes, short reads and unexpected additional bytes all fail.
Enforce actual-equals-expected again in `SubmissionIntakeRepository.record_eof`
and effective database guards, so bypassing the streaming helper cannot seal
unauthorized content. Compare measured identity without exposing hashes or
credentials in mismatch errors.
The HTTP server/proxy must reject ambiguous framing; qualification includes the
real ingress because bytes outside a framed request are not application EOF data.

Hash/count failure uses `submission_upload_content_mismatch`; timeout/provider
failures retain their existing distinctions. The spent credential stays spent.
Existing lease-fenced terminalization, partial multipart cleanup, physical
accounting and exact-version retention decide when task/capacity guards release.
Do not immediately reuse a task simply because the network socket closed.

Preserve the current PRE/T4 lock order. These later roots already lock TASK and
the owned ART operation before fresh actor/grant/policy checks. The consumed
credential is immutable, so reconstruct the narrow context from exact durable
operation/issuance/redemption evidence without taking a new mutable credential
lock. Recheck current authority and policy at the same existing boundaries; do
not extend the credential TTL, run PRE twice or let it supply status-read
authority. Existing T4 acceptance evidence and T5 fixed-service finalization
retain their roles. Cleanup uses existing exact operation custody, not the secret.

The current `accept`, its commit-unknown recovery, and
`settle_expired_foreground` call `authorize_read`; `_accepted_receipt` also
assumes a human public-read context. Credential mode cannot use those gates.
Add a non-public `validate_foreground_continuation` method to the intake AUTH
port, with exact operation/credential/issuance/redemption binding, original
foreground lease ID/generation and phase. It validates immutable custody and,
before new PRE/T4 effects, current actor/link and the exact issuing grant. It
grants no public projection, replacement lease or body replay. Use it for these
in-flight branches only; `_read`, `replay_failure`, `replay` and the public
operation endpoint remain Flow-only.

Make receipt observation explicit: `_accepted_receipt` requires opaque
`IntakeReceiptObservationEvidence` from either current public read authority or
the exact in-flight continuation. `validate_acceptance_receipt` validates retained
T4/SQL evidence against that observation. After a committed T4 whose acknowledgement
was lost, the original in-flight call may return that exact receipt even if
authority changed after acceptance; this observes an existing effect and never
renews authority. Expiry/terminal settlement similarly returns only the original
invocation's bounded result under its lease/evidence. `finish` already uses exact
owner custody. A later HTTP call with the consumed credential cannot enter any
of these continuation branches.

## 6. Recovery contract

The same submission idempotency key identifies issuance and the eventual intake
operation, but it does not make a consumed credential replayable. Ordinary Flow
API callers keep their existing bounded same-key replay behavior. The remote
MCP upload flow uses current authenticated reads after admission.

| Observation | Permitted next action | Forbidden effect |
| --- | --- | --- |
| Authorization response lost; no operation admitted | Repeat authorization with the same exact metadata/key; the new generation replaces any unused token. | Recovering plaintext from storage or retaining two usable generations. |
| Unused token expired | Same authenticated replacement, if current authority/eligibility still allows it. | Extending expiry by merely presenting the old token. |
| Definite pre-T1 validation/capacity rollback | Correct framing or wait, then use the still-unused token before expiry; reauthorize if needed. | Treating a generic network error as confirmed rollback. |
| Upload response missing, operation unknown to client | First read `workstream_submission_operation_get` with original task/key. A concealed 404 is not proof that no effect occurred. An authorized issuance retry may resolve unused state, but must refuse if any operation exists. | Automatic second body POST or new-key retry while the first operation may be active/accepted. |
| `receiving` / PRE in progress | Read/wait with bounded client backoff; retain original key and descriptor metadata. | New token for the same key, resumed multipart upload or takeover of its lease. |
| Disconnect/hash mismatch/timeout before T4 | Wait for retained terminal failure and released task guard, then use a new key and new authorization if retry remains eligible. | Resetting the spent credential or starting another active source. |
| PRE rejects | Present bounded findings; correct the ZIP, compute new count/hash, choose new key and authorize again. | Rebinding an old key to corrected bytes or bypassing PRE. |
| `finalization_pending` / finalized | Read the original receipt/progress; let existing T5 recovery run. | Reupload, second Submission, or contributor-driven finalize. |
| Authority lost | Existing reads may be concealed; restore authority through normal owners or authorized management support. | Using the token to inspect an operation or bypass local revocation. |
| Governed revision later permitted | Prepare local corrected work and use a new attempt key; backend selects current revision lineage. | Client-selected predecessor/policy/compensation terms. |

Extend `SubmissionOperationReadService._public_failure` for the new content
mismatch code. Its current blanket exclusion of `cancelled` from new-key guidance
also needs a scoped correction: a cancelled request may return
`retry_new_key_after_terminal` only when the current TASK owner says a new intake
is permitted. Assignment invalidation must still prevent that guidance. This
keeps disconnect recovery concrete without creating a new lifecycle state.

“One use” is admission, not successful PRE or delivery of the HTTP response. A
client can spend a valid token by sending a bad/incomplete body; exact file
binding prevents acceptance of different bytes, not denial of service by the
credential holder. This is deliberate and keeps retries within existing custody.

## 7. Deployment, secrets and client execution

### Public upload destination

The MCP gateway's `WORKSTREAM_API_URL` may be a private origin (the inspected
hosted Compose file uses loopback). It is not a valid descriptor destination for
external clients. Add `WORKSTREAM_PUBLIC_API_URL` as a required, trusted public
**origin** for this tool: HTTPS, no username/password, query, fragment or path
other than an optional trailing slash. Canonicalize once at startup and append
the fixed `/api/v1/tasks/{uuid}/submissions` path. Explicit local test profiles
may allow loopback HTTP; hosted configuration must not.

Fail startup safely for missing/invalid public origin when the replacement tool
is shipped. Do not infer it from a client Host, request argument, exchanged token
claim or API response URL. Qualify that public origin against the same API
deployment/credential database; a wrong trusted configuration is an operational
error, not a reason to follow redirects. Verify TLS and reject 3xx without
forwarding the secret to any redirected origin.

### Timeouts, size and transport

Authorization is a small, ordinary JSON call with the existing normal MCP/API
timeout. The byte leg uses the API's independently qualified streaming profile.
At the inspected dependency, submission configuration uses a 300-second upload
total, 30-second upload idle and 300-second PRE hard envelope, with a 660-second
MCP submission timeout and 675-second MCP proxy allowance for the current
Base64 path. Verify effective settings again before cutover; these are observed
profile settings, not an unlimited-upload promise or new policy ceilings.

Direct-upload client and public API ingress deadlines must cover their actual
upload + PRE + bounded control/response budget. The ten-minute credential start
window is a different clock. Keep finite timeouts, API/project archive ceilings,
provider quotas, idle limits and cleanup charges. Qualify body streaming and
bounded memory at the largest supported archive and for slow/interrupted clients;
the new flow removes MCP Base64 overhead, not all system limits.

Remove submission-only MCP Base64 bounds and long upload timeout after tracing
consumers. Keep document read/upload and task-import bounds and timeout needs;
other tools still transport their own bounded content. Do not blindly shrink
the shared MCP request ceiling or remove every Base64 dependency. Public API
ingress must still pass the configured upload body and keep Authorization
redacted. No ZIP bytes should traverse MCP in the new integration trace.

### Secret handling

Return the scoped credential only in the successful API issuance response and
successful MCP structured descriptor. API/MCP responses, including errors, use
`Cache-Control: no-store`; no server response cache may store this secret.
Disable response-body/structured-result logging for this operation, redact all
Authorization headers and credential fields in logs/traces/errors, and retain
only non-secret identifiers, generations, decision IDs and outcomes in audit.
Do not put tokens in URLs, query strings, metrics labels, exception reprs,
prepared-input audit values, outbox events or checker inputs. Backend audit may
retain exact non-secret binding facts and their canonical digests.

Client examples should read the descriptor in memory and pass headers through an
HTTP library. Do not show the token in a command-line argument, environment dump,
shell history or verbose HTTP trace. A reference uploader should open the local
file, hash/measure it before authorization, keep that file descriptor stable,
recheck stat identity before sending, stream a bounded reader with exact length,
disable redirects/retries, bound the JSON response, and discard the credential
after the attempt. Backend hash verification still protects against same-length
file modification after the local check. Storing a recovery key does not require
storing the token. The existing CLI's file-stability behavior is a reference;
this feature does not require a new generic client SDK or CLI login path.

## 8. Implementation map

Paths in backticks below are proposed additions where stated. Existing owner
directories are linked; implementation may split cohesive files without changing
the responsibilities or introducing a parallel subsystem.

| Area | Files/symbols to change | Required outcome |
| --- | --- | --- |
| Route and dependency composition | `backend/app/api/routes/artifact_submissions.py`, `backend/app/api/submission_intake.py`, `backend/app/adapters/artifacts/__init__.py`; new route-local typed principal/issuance schemas | New small-JSON authorization route; mutually exclusive auth modes on canonical POST; exact headers and mode-specific recovery messages. |
| ART public command boundary | `backend/app/modules/artifacts/api/submission_intake.py`, `api/submission_command.py`; new `api/submission_upload_authorization.py` and cohesive issuance command | Explicit immutable file binding and principal variant through public ports; existing owner roots coordinate task/policy/credential issuance. |
| AUTH credential owner | `backend/app/modules/authorization/models.py`; new `api/submission_upload_credentials.py` and cohesive credential service/repository | Digest-only credential lifecycle, rotation, authoritative validation and narrow context construction, without storage/task policy ownership. |
| AUTH action/context/resource plumbing | `catalogue.py`, `action_definitions.py`, `domain/action_groups.py`, `runtime.py`, `kernel.py`, `prepared.py`, `domain/submission_intake.py`, `api/submission_intake.py`, `submission_intake.py`, resource digest/audit shape registries | New issue action mapped to existing permission; closed context dispatch; issuance/reserve/acceptance evidence includes exact credential lineage; normal contexts preserved. |
| Admission, bytes and recovery | `backend/app/modules/artifacts/intake/models.py`, `repository.py`, `foreground_command.py`, `foreground_admission.py`, `foreground_upload.py`, `streaming.py`, `acceptance.py`, `progress.py` | One atomic T1 credential redemption, operation/guard/capacity; expected count/hash checked before EOF; explicit credential-mode continuation/receipt evidence, uncertain path and current-authority recovery guidance. |
| TASK and project policy | Existing TASK intake custody/submission-context and PROJECT locked-policy public ports | Reuse current eligibility/revision/currentness checks and active guard; expose only missing typed facts, no new lifecycle states or credential table access. |
| SQL and migrations | New next-unused linear revision in `backend/alembic/versions/`, effective AUTH/T1/T4 closure functions and schema proof | Composite ownership, immutable binding/consumption and allow-event closure; preserve all retained existing rows and null Flow lineage. Do not assume a revision number from this design. |
| MCP tool/catalogue | `mcp_server/workstream_mcp/tools/task_execution.py`, `schemas.py`, `http_gateway.py`, `limits.py` | Metadata-only tool, fixed JSON route, strict response binding, safe structured descriptor; remove obsolete `submission_create` Base64 decoder/upload branch and its submission-only limits. |
| MCP contract packaging | Replace `contracts/submission_create.json` with `contracts/submission_upload_authorize.json`; update `mcp_server/pyproject.toml`, contract selection/hash/census tests | Review and package the new OpenAPI snapshot; remove the old snapshot rather than keep an alias. Tool count stays one-for-one unless unrelated source changes it. |
| Public address and deployment | `mcp_server/workstream_mcp/config.py`, `mcp_server/.env.example`, `deploy/hosted/compose.mcp.yml`, `release.env.example`, `preflight.py`, public ingress configuration/docs; `mcp_server/tests/test_config.py`, `scripts/test_hosted_release_config.py`, `scripts/test_hosted_mcp_container.py` | Trusted public HTTPS origin, correct direct-upload envelopes and secret redaction; independent JSON and binary legs; update exact fixture environments and startup validation together. |
| Current documentation | This spec, submission execution/client docs, AUTH specification/ADR boundary explanation, API examples, MCP README, hosted/public-access docs, roadmap/initiative | Declare implemented/exposed/deployed status accurately; document narrow model-visible credential exception and concrete recovery. |

The implementation must update the architecture dependency ledger only if a new
public owner edge is actually introduced. Reuse current ART→AUTH/TASK/PROJECT
edges and repository hashing/ID/error conventions. No generic capability broker,
alternate auth session system or new artifact provider is justified here.

## 9. Verification contract

These are **future runtime acceptance requirements**, not tests executed by this
design PR. Reuse existing production-valid fixtures and real owners; do not
disable SQL triggers, forge allowed audit events or stub all authority to reach
the interesting assertion. New test names below specify observable behavior;
they do not claim files/functions already exist.

| ID | Required observable behavior | Named proof and custody |
| --- | --- | --- |
| U01 | Valid Flow-authenticated exact Submitter gets a small issuance response; no operation, task guard, source, charge or PRE exists. | New `backend/tests/tasks/test_public_submission_upload_authorization.py::test_issue_has_no_intake_effects`; real PostgreSQL, public API and queried durable absence. |
| U02 | Foreign actor/task/assignment, manager-only caller, suspended actor, revoked link and missing/revoked Submitter grant cannot issue or disclose another binding. | Same module, `test_issue_authority_and_ownership`; independent persisted foreign resources and parametrized public denials. |
| U03 | Two identical authorized calls rotate one record; old secret fails, new secret works; lost-response retry and expired-unused replacement work. | New `backend/tests/authorization/test_submission_upload_credentials.py::test_unused_rotation_and_expiry`; DB-clock boundary and retained issuance audit events. |
| U04 | Different size/hash/feedback/task/assignment/link under one actor/key cannot mutate the original binding; existing ordinary or credential intake blocks issuance. | Same AUTH module, `test_binding_conflict_and_existing_operation`; real stored original binding and operation for every state class. |
| U05 | Malformed/oversized token, unknown ID, bad digest, wrong scheme, duplicate Authorization, stale/expired/spent generation and every selector substitution fail without provider/body/PRE work. | New public module, `test_credential_request_rejection`; real route dependency graph plus a body iterator/provider spy that fails if touched. |
| U06 | Credential cannot call actors/me, status read, claim, issuance, another task or any generic AUTH action; no fabricated human context can substitute. | New AUTH module, `test_submission_context_is_closed`; route composition tests and prepared-kernel negative cases for all action families, normal Flow positive controls. |
| U07 | Revocation/policy/assignment changes between issuance and upload prevent admission; revoked-then-regranted original grant does not revive old token. | New public module, `test_fresh_authority_at_redemption`; real mutations/owners and retained task/op absence. |
| U08 | Two concurrent redemptions create one operation/charge/allow/foreground owner; the loser cannot stream. | Extend `backend/tests/artifacts/test_submission_intake_admission.py::test_credential_concurrent_redemption`; independent PostgreSQL sessions with a controlled lock barrier and final state queries. |
| U09 | Rotation versus redemption, same actor/key across tasks, and different keys on one task preserve lock order and single ownership. | Same file, `test_credential_rotation_and_key_races`; independent transactions, both orderings, timeout/deadlock detection and exact winning records. |
| U10 | Failure after ART reservation, after reserve allow, and after credential update rolls back token use, operation, pointer, charges and allow together. | Same file, `test_credential_t1_rollback`; injected transaction-boundary faults and independent before/after DB reads. |
| U11 | T1 commit succeeds but acknowledgement is lost: no second body owner/lease, no new token, authenticated read resolves the one operation. | Extend `backend/tests/artifacts/test_submission_foreground_command.py::test_credential_unknown_admission`; commit-fault fixture with stored operation and public recovery. |
| U12 | Exact streamed bytes succeed; same-size wrong hash, short read, excess data and header length mismatch never seal source or run PRE. | Extend `backend/tests/artifacts/test_submission_intake_contracts.py::test_authorized_stream_binding` and public framing tests; real streamed byte chunks, EOF/PRE assertions, actual ingress framing qualification for excess bytes. |
| U13 | Interrupted/mismatched source keeps token spent and charge owned until existing cleanup settles; accepted versions remain protected. | Extend `backend/tests/artifacts/test_submission_source_cleanup.py::test_credential_failed_source_cleanup`; PostgreSQL + MinIO exact multipart/version and charge evidence. |
| U14 | PRE/T4 recheck authority without credential relocking/expiry extension; revocation before each boundary prevents acceptance and preserves cleanup; a new active grant never substitutes for the issued grant. | Extend `test_submission_foreground_command.py::test_credential_later_authority`; real AUTH/PG roots, unchanged credential row, retained denial and no T4 receipt; fail the test if credential continuation invokes public `authorize_read`. |
| U15 | PRE negative has bounded findings/no Submission; corrected new-key ZIP succeeds; unchanged key cannot obtain another token. | Extend `backend/tests/tasks/test_public_submission_intake.py::test_credential_pre_failure_and_correction`; public requests, exact task/assignment, real PRE qualification fixture and durable rows. |
| U16 | T4 response loss recovers the exact receipt; T5 retry creates one Submission/binding/POST graph, never another upload. | Extend existing intake progress/finalization proof with `test_credential_accepted_recovery`; PostgreSQL/MinIO and existing durable-worker fixture with source/operation/receipt identity. |
| U17 | Direct SQL cannot swap actor/link/assignment/project, issuance/reserve allow, generation, file binding or operation, clear lineage, reset spent state or insert missing evidence. | New AUTH test module, `test_credential_sql_closure`; bypass ORM validators, production guards enabled, one rejected transaction per independently invalid fact. |
| U18 | Migration preserves existing Flow operations, accepted receipts and pending T5 work; new schema/model/guard definitions agree. | Extend existing migration/acceptance fixtures with `test_upload_credential_migration`; real pre/post-upgrade PostgreSQL and owner-valid retained rows, no fake lineage backfill. |
| U19 | New MCP input accepts only metadata and exact feedback bounds; old tool/zip input absent; snapshot and installed wheel match public OpenAPI. | Update `mcp_server/tests/test_task_execution_contract_drift.py` and tool/gateway tests with `test_submission_upload_authorize_contract`; installed package and real OpenAPI census plus negative schemas. |
| U20 | Descriptor has correct trusted public origin/path/method/headers, echoed binding, false idempotence hint, one token copy and safe text; arbitrary backend URLs/headers cannot escape. | MCP tool/config tests, `test_upload_descriptor_is_closed`; malformed-response and private/public-origin substitution fixtures. |
| U21 | API/MCP/proxy logs, traces, exceptions, audit, queue/checker payloads and text content contain no token/general OAuth secret; no-store survives success and errors. | New focused transport privacy tests, `test_upload_credential_redaction`; sentinel credentials, captured sinks and deployed-header check. Do not mistake authorized structuredContent for a leak. |
| U22 | Real external client creates a ZIP above former 64 MiB bound, calls installed remote MCP for metadata only, then streams directly to public API and reads result via MCP. | Extend installed MCP/backend journey using separate processes and real local file/HTTP client; retain request-size/route trace, API response, PG operation, exact stored source and PRE result. No shared filesystem mount or mocked HTTP upload. |
| U23 | Largest advertised/project-limited ZIP, slow/interrupted client, expiry while waiting for locks and expiry after T1 obey measured memory/time/cleanup bounds. | Public ingress + PostgreSQL + qualified S3/MinIO profile; measured peak RSS and bytes, timing, source charges and cleanup evidence. Unsupported limits remain unadvertised. |
| U24 | Existing direct Flow ZIP upload/replay, document/import Base64 tools, initial and revision lifecycle, default review_pending and false-policy shared acceptance retain behavior. | Run affected existing public API/MCP suites and the scoped contributor journey; retain exact ContributionRecord/award facts for the automatic branch and guarded pending state for the default branch. |
| U25 | Credential continuation can observe its committed T4 receipt or settle its original expired lease, including revocation after commit; an unrelated operation/lease or later HTTP replay cannot use that evidence. Request cancellation recommends a new key only if current assignment authority permits it. | Extend `test_submission_foreground_command.py::test_credential_continuation_observation` and `test_submission_intake_progress.py::test_cancelled_request_recovery`; real committed acceptance, exact opaque observation evidence, negative operation/lease substitutions and current TASK eligibility. |

For U08–U11, tests must demonstrate the adversarial ordering/fault rather than
merely call methods sequentially. For U17, create valid issuance/redemption via
owners first, then mutate one fact with SQL so missing fixture prerequisites
cannot mask a weak closure. For U22, assert the actual MCP request contains only
small JSON and the ZIP source exists only in the external uploader environment.
Passing a mocked gateway test is not that proof. U23 qualifies operational
claims independently of pure schema acceptance.

## 10. Delivery sequence and completion

1. Implement AUTH model/context/action/SQL closure and the typed issuance owner,
   with exact authority, rotation, ownership and direct-SQL proof.
2. Integrate route-mode selection and T1 consumption into the existing command;
   add byte binding and recovery. Prove rollback, concurrency, unknown commits,
   fresh authority and later source lifecycle with normal Flow regression tests.
3. Replace the MCP Base64 submission tool, packaged contracts, docs and public
   origin configuration together; exercise an installed independent MCP client.
4. Qualify real public ingress, secrets, large/slow files and correction/recovery,
   then cut over the hosted MCP service against the matching API/schema release.

These are reviewable implementation increments, not parallel permanent product
flows. The API schema must exist before the replacement MCP release runs. The
old Base64 submission tool is removed in that release, with no alias. A deployment
failure should retain a known working release until the complete candidate is
qualified; it must not ship a fallback that silently routes large ZIPs through
MCP. Already-admitted canonical operations must remain readable/finalizable
across cutover. Do not downgrade away credential columns while retained operations
reference them; use forward repair and existing evidence-preservation rules.

Runtime completion requires U01–U25 at their claimed boundaries, resolved focused
security/architecture/reuse reviews, current contract/packaging checks, and a
documented supported public-client profile. Record implemented, public and
deployed status separately in the capability ledger. This design's completion
does not add a new release prerequisite to PR #708 or certify its outstanding
performance/hosted checks. It provides the next separately authorized MCP
implementation boundary.

### Protocol relationship

The ordinary MCP call remains authenticated JSON control traffic. The raw ZIP
travels over HTTPS outside that call. This is an application operation-credential
contract, not OAuth token passthrough or a claim that all MCP clients have binary
upload support. The official [MCP authorization security guidance](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations)
remains relevant to audience separation. The [experimental file-upload extension](https://github.com/modelcontextprotocol/experimental-ext-file-uploads/blob/main/specification/draft/file-uploads.md)
has a distinct draft workflow; this direct, mutating submission POST is not
advertised as implementing that extension.
