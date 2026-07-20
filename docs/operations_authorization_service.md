# Authorization Service Operations

## Purpose

This runbook assigns ownership and stop conditions for the staged WS-AUTH-001
authorization rollout. The verified-token configuration and evidence commands
are executable contracts. Canonical actor resolution, actor-self authorization,
one-time bootstrap, and administrative grant APIs are active through AUTH-08;
later actor lifecycle and project-grant sections remain staged until their
owning implementation chunks.

## Ownership

| Area | Primary owner | Required evidence |
|---|---|---|
| Issuer/audience/algorithm configuration | Platform security | Approved non-secret configuration inventory and verifier tests. |
| JWKS endpoint, cache, and rotation | Platform security/on-call | Rotation drill, cache bounds, outage behavior, alerts. |
| Introspection/revocation policy | Platform security | Approved mode, endpoint trust policy, timeout/failure proof. |
| First Access Administrator bootstrap | Restricted deployment operator | Dry-run, target verification, one-time result, authority event. |
| Legacy actor classification | Data migration owner plus security reviewer | Versioned manifest, live-row digest, checksum, dry-run report. |
| Actor/grant administration | Access Administrator | Supported API/command, reason, idempotency, evidence. |
| Project contributor grants | Covered Project Manager | Exact-project target and privacy-bounded candidate lookup. |
| Recovery operations | Operator or covered Project Manager as specified | Matched permission, reason, resource scope, immutable evidence. |
| Rollout and rollback | Release owner | Migration round trip, compatibility inventory, rollback stop conditions. |
| Live authorization proof | Release owner plus security/QA | API-visible drill with redacted committed evidence. |

## Required Configuration

Platform security owns the following inventory. Production, staging, and
preview fail closed when a required value is absent or outside its bound.

| Variable | Accepted value | Default/requirement |
|---|---|---|
| `WORKSTREAM_TOKEN_ISSUER` | Canonical HTTPS URL, at most 200 characters; no userinfo, query, or fragment | Required |
| `WORKSTREAM_TOKEN_AUDIENCE` | Non-empty string | `workstream` |
| `WORKSTREAM_TOKEN_JWKS_URL` | Canonical HTTPS URL; no userinfo, query, or fragment | Required |
| `WORKSTREAM_TOKEN_ALGORITHMS` | One-family subset of `RS256,RS384,RS512,ES256,ES384,ES512,EdDSA` | Required; no symmetric algorithms |
| `WORKSTREAM_REQUIRED_HUMAN_SCOPE` | One scope token | `workstream:access` |
| `WORKSTREAM_REQUIRED_SERVICE_SCOPE` | One scope token | `workstream:service` |
| `WORKSTREAM_TOKEN_CLOCK_SKEW_SECONDS` | Integer `0..300` | `30` |
| `WORKSTREAM_TOKEN_MAX_BYTES` | Integer `512..32768` | `16384` |
| `WORKSTREAM_TOKEN_HEADER_MAX_BYTES` | Integer `128..8192`, not above token max | `4096` |
| `WORKSTREAM_TOKEN_PAYLOAD_MAX_BYTES` | Integer `256..24576`, not above token max | `12288` |
| `WORKSTREAM_TOKEN_JWKS_CACHE_TTL_SECONDS` | Integer `30..3600` | `300` |
| `WORKSTREAM_TOKEN_JWKS_MAX_RESPONSE_BYTES` | Integer `1024..1048576` | `262144` |
| `WORKSTREAM_TOKEN_JWKS_MAX_KEYS` | Integer `1..100` | `20` |
| `WORKSTREAM_TOKEN_UNKNOWN_KID_CACHE_TTL_SECONDS` | Integer `1..300` | `30` |
| `WORKSTREAM_TOKEN_UNKNOWN_KID_CACHE_MAX_ENTRIES` | Integer `1..1000` | `100` |
| `WORKSTREAM_TOKEN_JWKS_CONNECT_TIMEOUT_SECONDS` | Float `0.1..10` | `2` |
| `WORKSTREAM_TOKEN_JWKS_READ_TIMEOUT_SECONDS` | Float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_JWKS_WRITE_TIMEOUT_SECONDS` | Float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_JWKS_POOL_TIMEOUT_SECONDS` | Float `0.1..10` | `1` |
| `WORKSTREAM_TOKEN_JWKS_TOTAL_TIMEOUT_SECONDS` | Float `0.5..15` | `5` |
| `WORKSTREAM_TOKEN_INTROSPECTION_MODE` | `disabled` or `required` | Required |
| `WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON` | Issuer-policy evidence reference | Required in `disabled` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_URL` | Canonical HTTPS URL | Required in `required` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_ID` | Non-empty secret-backed identifier | Required in `required` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_SECRET` | Non-empty secret value | Required in `required` mode |
| `WORKSTREAM_TOKEN_INTROSPECTION_MAX_RESPONSE_BYTES` | Integer `256..262144` | `65536` |
| `WORKSTREAM_TOKEN_INTROSPECTION_CONNECT_TIMEOUT_SECONDS` | Float `0.1..10` | `2` |
| `WORKSTREAM_TOKEN_INTROSPECTION_READ_TIMEOUT_SECONDS` | Float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_INTROSPECTION_WRITE_TIMEOUT_SECONDS` | Float `0.1..10` | `3` |
| `WORKSTREAM_TOKEN_INTROSPECTION_POOL_TIMEOUT_SECONDS` | Float `0.1..10` | `1` |
| `WORKSTREAM_TOKEN_INTROSPECTION_TOTAL_TIMEOUT_SECONDS` | Float `0.5..15` | `5` |
| `WORKSTREAM_API_RATE_LIMIT_KEY_SECRET` | Canonical padded RFC 4648 Base64 decoding to `32..64` bytes | Required |
| `WORKSTREAM_API_FIRST_ACCESS_RATE_LIMIT` | Integer `1..10000` | `10` |
| `WORKSTREAM_API_FIRST_ACCESS_RATE_WINDOW_SECONDS` | Integer `1..3600` | `60` |
| `WORKSTREAM_API_ADMIN_MUTATION_RATE_LIMIT` | Integer `1..10000` | `30` |
| `WORKSTREAM_API_ADMIN_MUTATION_RATE_WINDOW_SECONDS` | Integer `1..3600` | `60` |

Secrets, private keys, bearer tokens, full claims, and raw JWKS documents must
not appear in committed configuration or evidence.

Verified issuer and `sub` identity anchors are each limited to 200 characters
across the verifier, canonical registry, compatibility storage, audit, and
checker provenance. Development issuer and subject settings use the same bound.
Oversized values fail verification or configuration before actor persistence.

Verification evidence:

```bash
tmp_venv="$(mktemp -d)"
python3 -m venv "$tmp_venv"
"$tmp_venv/bin/python" -m pip install -e ./backend
"$tmp_venv/bin/python" -c 'import jwt, cryptography, httpx'
"$tmp_venv/bin/python" -m pip check
rm -rf "$tmp_venv"

cd backend
.venv/bin/python -m pytest -q tests/test_auth.py tests/test_config.py
.venv/bin/python -m ruff check app tests scripts
: "${WORKSTREAM_TEST_DATABASE_URL:?set a disposable migrated test database URL}"
WORKSTREAM_DATABASE_URL="$WORKSTREAM_TEST_DATABASE_URL" \
  WORKSTREAM_TEST_DATABASE_URL="$WORKSTREAM_TEST_DATABASE_URL" \
  .venv/bin/python -m pytest -q
: "${WORKSTREAM_TEST_ADMIN_DATABASE_URL:?set a local Postgres admin URL}"
metadata_dir="$(mktemp -d)"
trap 'rm -rf "$metadata_dir"' EXIT
.venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "$metadata_dir/result.json" \
  --timeout-seconds 3600 -- \
  .venv/bin/python scripts/api_contract_e2e.py
cd ..
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
git diff --check
```

During the compatibility period, `/api/v1/auth/me` uses only the verified
issuer/subject plus bounded legacy roles. It does not copy issuer email or
display name into actor storage or responses, so both response fields remain
`null`. Consumers must not treat token identity metadata or legacy workflow
eligibility as profile or authorization truth. Human-owned display data is
written only through `PATCH /api/v1/actors/me`.

## Request And Error Context

Clients may send one `X-Request-ID` and one `X-Correlation-ID`. Each supplied
value must be a canonical lowercase, hyphenated, non-nil RFC 9562 UUID using the
RFC variant and version 1 through 8. A missing request ID is generated as
UUIDv4; a missing correlation ID reuses the effective request ID. Duplicate,
comma-joined, malformed, non-ASCII, nil, or unsupported-version values stop
before route/dependency execution with HTTP 400 `invalid_request`. That response
uses one newly generated UUIDv4 for both safe headers and never reflects the
rejected bytes.

Every success and error response returns the effective IDs in
`X-Request-ID` and `X-Correlation-ID`. Application-supplied response values for
those headers are overwritten. Status, content length, duplicate unrelated
headers, `WWW-Authenticate`, `Retry-After`, streaming chunks, and background
work remain unchanged.

Errors add this canonical object while retaining the existing top-level
`detail` or domain `code/details` compatibility fields:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Request validation failed",
    "details": {},
    "correlation_id": "00000000-0000-4000-8000-000000000001",
    "retryable": false
  }
}
```

The authentication boundary uses `missing_token`, `invalid_token`,
`identity_verification_unavailable`, and `unsupported_subject_kind` for their
exact branches. Verification/registry unavailability is retryable; invalid
credentials, unsupported kinds, validation, permission, not-found, conflict,
and internal application errors are not. The canonical nested validation
summary is capped at 20 errors with type/location evidence only. Existing
sanitized validator messages remain solely in the bounded compatibility
`detail` list.

Use the correlation ID to join operator evidence. Never add bearer tokens,
claims, subjects, emails, SQL, provider bodies, exception text, or secrets to
responses or logs. AUTH-04A does not activate rate controls, grant APIs, or new
product authority; those remain owned by later separately reviewed chunks.

## Canonical Actor Resolution

Every protected human request resolves the exact verified `(issuer, subject)`
through one `ActorIdentityLink` to one local `ActorProfile`. The first valid
human access consumes the PostgreSQL first-access rate control, then creates the
profile, identity link, `ActorProfileProvisioned`, and `ActorIdentityLinked`
evidence in one transaction. Concurrent allowed first-access requests cannot
leave duplicate profiles, links, or evidence. Rate-limited requests may still
receive HTTP 429 before identity serialization.

`GET /api/v1/actors/me` returns the caller's privacy-bounded Contributor-domain
profile plus sorted active administrative role names as a non-authoritative
self projection; project grants remain empty until AUTH-10. `PATCH /api/v1/actors/me` accepts
only `display_name` and `contact_email`; token roles, issuer metadata, actor
kind, status, grants, and lifecycle fields are not writable there. Suspended
profiles remain readable for support, but suspended or deactivated profiles
cannot be mutated or use legacy product routes.

Unknown services require later manual provisioning and are denied without a
write. Agent and Space subjects are denied without a write. Operators must not
convert token roles, email shape, subject shape, or old typed profiles into
actor kind or authority.

A provisioned service ActorProfile is the stable Workstream principal, similar
to a Kubernetes ServiceAccount. Its immutable `service_identity` is one of the
closed registered internal services; its identity link separately stores the
configured issuer and opaque subject used to verify credentials. Display name,
email, subject syntax, token role, and adapter provenance are never service
identity evidence.

Service authority is a reviewed static service-to-ActionId matrix, not a grant
or database assignment table. A service receives no Contributor,
AdminRoleGrant, or ProjectRoleGrant authority. Every matrix action remains
unavailable until merged feature behavior exists and the dedicated AUTH
activation custodian integrates its evaluator and changes only that action's
availability.

### Existing Service Identity Mapping Custody

This procedure applies only when service ActorProfiles already exist before
migration `0023`. The data-migration owner prepares a private draft containing
the exact existing ActorProfile ID, issuer, opaque subject, and proposed fixed
service identity for every row. A security reviewer verifies each choice from
authoritative ownership records. Neither the tool nor an operator may infer a
value from subject syntax, email, display name, token role, or adapter
provenance.

Run the supported tool against the exact target database. Draft and envelope
files must be regular, non-symlink, owner-only mode `0600` files in a controlled
directory outside the checkout, every linked worktree, and shared Git metadata.
Zero existing service rows require no file; otherwise the envelope must cover
the complete locked service projection and select unique values from the seven
closed identities.

```bash
chmod 600 /secure/workstream/service-identity-draft-v1.json
.venv/bin/python scripts/service_actor_identity_mapping.py validate \
  --draft /secure/workstream/service-identity-draft-v1.json
.venv/bin/python scripts/service_actor_identity_mapping.py bind \
  --draft /secure/workstream/service-identity-draft-v1.json \
  --output /secure/workstream/service-identity-envelope-v1.json
chmod 600 /secure/workstream/service-identity-envelope-v1.json
.venv/bin/python scripts/service_actor_identity_mapping.py verify \
  --envelope /secure/workstream/service-identity-envelope-v1.json
```

`validate` and `verify` never modify PostgreSQL. `bind` refuses an existing
output path. The tool prints only stable codes, bounded counts, and non-secret
digests. Inject `WORKSTREAM_SERVICE_ACTOR_IDENTITY_MAPPING_FILE` only into the
migration process immediately before `alembic upgrade head`; never commit or
log the path or confidential contents.

Migration `0023` consumes the packaged versioned contract, locks the complete
actor/link source projection, and refuses missing, extra, stale, duplicate, or
ambiguous mappings atomically. It retains only bounded counts and non-secret
source, manifest, envelope, and database-binding digests. After database
verification and the approved rollback window, securely delete the draft and
envelope. If any row cannot truthfully map, remain on `0022` and open a reviewed
data-remediation decision; never guess, delete history, or use manual SQL.

The [approved AUTH-06 chunk contract](../.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/chunks/WS-AUTH-001-06-canonical-actor-profile.md)
records the exact deprecated compatibility identifier. That temporary,
enumerated intake route writes only `LegacyWorkflowEligibility` and cannot
create a grant or change a canonical profile. Its direct compatibility
consumers are assigned-submitter claim, assigned-submitter start, and submission
intake. Operator start override does not use the bridge. AUTH-13 removes the
claim and start consumers; AUTH-14 removes the final submission consumer,
compatibility route, and adapter.

## Contributor Attribution Migration And Runtime Guard

Migration `0027_contributor_foundation` clean-cuts the retired assignment and
submission human-owner columns to `contributor_id`. Before any DDL, it locks
`actor_profiles`, `task_assignments`, and `submissions` and independently
classifies every old value as malformed UUID, missing ActorProfile, or service
ActorProfile. Failure reports only bounded row/profile ID pairs and counts. It
redacts malformed source values completely while retaining safe row IDs and
well-formed missing/service profile IDs. It does not inspect issuer, subject,
email, token claims, current assignment, or another table to infer a
replacement.

Remediate a refusal only from authoritative canonical-actor evidence. Create or
repair the canonical human ActorProfile through its owning reviewed process,
or correct a demonstrably wrong attribution through a separately reviewed data
repair. Do not map by email or display name, select a latest profile, convert a
service identity, fabricate an ActorProfile, or edit immutable audit history.
Rerun from exact head `0026_actor_profile_lifecycle` and retain the bounded
preflight result with the deployment evidence.

The reusable primitive is
`public.require_human_actor_profile_reference()`. Exact triggers
`task_assignments_contributor_human` and `submissions_contributor_human` enforce
human lineage. Exact foreign keys
`fk_task_assignments_contributor_id_actor_profiles` and
`fk_submissions_contributor_id_actor_profiles` enforce existence, while renamed
indexes `ix_task_assignments_contributor_id` and
`ix_submissions_contributor_id` preserve lookup behavior.

After upgrade, both columns are non-null `varchar(36)` foreign keys. PostgreSQL
rejects a missing profile with SQLSTATE `23503` and a service profile with
`23514`. Suspended and deactivated human profiles remain valid historical
references. Downgrade first locks the same tables and refuses before DDL when
any non-owned dependency uses the shared lineage function; remove or migrate
that dependent schema through its owning release before retrying.

Claim and submission also revalidate current identity inside their mutation
transaction in lock order ActorProfile, exact issuer/subject identity link,
task, active assignment. An inactive or non-human identity returns HTTP 403
`active_contributor_required`. Missing, mismatched, database-unavailable, or
lock-failed canonical identity state rolls back and returns retryable HTTP 503
`contributor_identity_unavailable`. These responses are identity eligibility,
not permission decisions; grant and resource authorization remain separate.

## PostgreSQL Rate Controls

First human access now uses the AUTH-04B PostgreSQL control. Future
authority-management mutations attach their separately configured control in
their owning chunks. Every replica must use the same secret and settings.
Missing secret or database access fails first access closed with retryable HTTP
503; an exhausted window returns retryable HTTP 429 with an integer
`Retry-After`. Existing exact identity links do not consume first-access
capacity.

Generate the secret outside the repository and store it in the deployment
secret manager:

```bash
python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

Counters store only the server-owned scope and an HMAC-SHA256 digest of the
verified issuer/subject. They do not store raw identity, actor, token, claim,
role, email, or network values. Consumption uses database time and commits in
an independent session before the protected mutation may continue or return
429, so downstream rollback does not restore allowance.

Secret rotation intentionally creates a new digest space. Before rotating:

1. Quiesce every protected write for at least the largest effective
   pre-rotation window configured on any replica.
2. Rotate every replica while writes remain quiesced; mixed-secret replicas
   must not serve protected writes.
3. Delete only rows expired by PostgreSQL time:

```sql
DELETE FROM api_rate_control_counters
WHERE window_expires_at <= statement_timestamp();
```

4. Confirm all replicas use the new secret, then resume protected writes.

Runtime consumption opportunistically deletes at most 100 expired other rows.
On idle systems, operators may run the same expired-only SQL cleanup. Never
delete active rows to recover capacity, and never downgrade migration `0017`
while the table is nonempty; the guarded downgrade takes an exclusive table
lock, refuses, and rolls back. Quiesce every protected write before attempting
the downgrade so waiting writers cannot resume against a removed table.

## JWKS Rotation And Outage

Rotation procedure:

1. Confirm the new key is published by the configured issuer over trusted
   HTTPS.
2. Verify algorithm and key-use constraints.
3. Exercise unknown-key refresh once; do not create refresh loops.
4. Verify both old and new unexpired tokens only during the issuer's approved
   overlap.
5. Confirm cache, refresh-success, and refresh-failure metrics use bounded
   labels.
6. Remove the retired key according to issuer policy and repeat denial tests.

During an outage, cached keys may be used only inside the configured safe
window. Once verification cannot be established, protected requests fail
closed. Operators must not switch to an unpinned algorithm, shared production
HMAC secret, development verifier, unsigned token, or unverified claim parsing.

## Introspection And Revocation Mode

Production must select an explicit mode:

- disabled only with documented issuer revocation/short-lifetime evidence;
- required bearer-token introspection only to a separately configured HTTPS
  endpoint with OAuth client-secret Basic authentication, no redirects or
  environment proxies, and strict time/response bounds.

Required introspection responses contain `active=true`, `iss`, `sub`, `aud`,
and `jti`; every identity value must match the already signature-verified
token. Introspection cannot provide or replace identity, kind, scope, roles, or
grants. Identifier-only introspection is not supported in this chunk. Platform
security owns the client ID/secret, rotation, and revocation procedure.

JWKS and introspection use separate clients and policies. Bearer tokens never
reach JWKS endpoints, redirect targets, logs, traces, errors, or audit events.
An introspection outage fails according to the approved mode; it cannot silently
degrade to token-role authority.

## Bootstrap Custody

Bootstrap is a restricted local management operation.

Before execution:

- verify the target is the intended active human profile and identity link;
- verify the environment and database;
- capture a redacted dry-run result;
- confirm the one-time bootstrap has not already completed;
- confirm the deployment operator has restricted environment access;
- confirm audit and database-time behavior are available.

Run the supported command from the backend with the target's canonical UUID:

```bash
WORKSTREAM_DATABASE_URL='<target async Postgres URL>' \
  .venv/bin/python -m scripts.bootstrap_access_administrator \
  --actor-profile-id '<canonical actor UUID>' --dry-run

WORKSTREAM_DATABASE_URL='<target async Postgres URL>' \
  .venv/bin/python -m scripts.bootstrap_access_administrator \
  --actor-profile-id '<canonical actor UUID>' --execute
```

Dry-run is read-only and does not promise later success. Execution locks
`AuthorityControl(id = 1) FOR UPDATE`, revalidates the active human target,
then commits exactly one initial grant, completed control transition, and
success event. Exit code `0` is eligible/success, `2` is invalid or ineligible,
`3` is already bootstrapped/concurrent loser, and `1` is infrastructure
failure. Preserve the bounded JSON result and correlated authority evidence;
never add issuer, subject, email, display name, token, or database URL.

If execution returns `1`, leave bootstrap custody with the deployment operator,
verify transaction rollback and database availability, and retry the same
supported command. Later or concurrent attempts return the stable audited
conflict and must not be repaired by editing the control or grant tables.

Never bootstrap through public HTTP, direct SQL, a shared secret, or a
fabricated human/system role.

## Legacy Actor Classification

Non-empty legacy registries require the supported classification tool and a
versioned JSON manifest. Each entry binds the exact legacy actor ID, issuer,
opaque subject, and subject kind.

Platform security owns the manifest and envelope. Both files contain
confidential identity-linking evidence even though the command report is
redacted. Store them in an environment-specific owner-only directory outside
the repository, every linked worktree, and the Git common directory. Do not
attach either file to tickets, CI logs, PRs, or engineering-loop evidence.

Manifest schema version 1 has exactly this shape:

```json
{
  "schema_version": 1,
  "classifications": [
    {
      "actor_id": "00000000-0000-5000-8000-000000000000",
      "issuer": "https://issuer.example.invalid",
      "subject": "opaque-subject-from-the-legacy-row",
      "subject_kind": "human"
    }
  ]
}
```

`subject_kind` is only `human` or `service`. The actor ID must be the canonical
UUIDv5 derived by the existing registry from the byte-exact HTTPS issuer and
case-sensitive opaque subject. Operators must classify from authoritative
issuer records; email, subject syntax, token roles, profile rows, and manual SQL
are not classification evidence.

The tool must:

- support dry-run;
- reject unknown fields/kinds, duplicates, missing rows, extra rows, stale
  rows, mismatched issuer/subject, invalid UUIDs, and ambiguous classification;
- compute a complete live-row digest and manifest checksum;
- bind evidence to a non-secret database/environment identifier;
- write no grants;
- emit a bounded remediation report.

Prepare a restricted directory and validate without writing an envelope:

```bash
cd backend
WORKSTREAM_DATABASE_URL='<target async Postgres URL>' \
  .venv/bin/python scripts/legacy_actor_classification.py \
  --manifest /secure/workstream/prod/legacy-actor-manifest-v1.json
```

Dry-run is the default. An empty registry needs no manifest and returns an
explicit empty proof. A non-empty registry without a manifest fails closed. The
JSON report contains only row count, mode, empty status, checksums, and the
non-secret database binding; stderr uses stable error codes and does not render
identity values, paths, database names, or connection URLs.

After the dry-run report is reviewed, export one write-once envelope:

```bash
cd backend
WORKSTREAM_DATABASE_URL='<target async Postgres URL>' \
  .venv/bin/python scripts/legacy_actor_classification.py \
  --manifest /secure/workstream/prod/legacy-actor-manifest-v1.json \
  --output /secure/workstream/prod/legacy-actor-classification-v1.json \
  --generated-at 2026-07-13T12:30:00Z
```

`--generated-at` is an explicit UTC RFC3339 second so the same reviewed inputs
produce byte-identical evidence. Export writes mode `0600` through a
crash-safe, atomic no-overwrite publish. Repeating the exact command is
idempotent only when the existing regular file has identical bytes and private
permissions. A different existing file, symlink, relative path, repository
path, or Git-directory path fails closed.

The envelope contains schema version, sorted classifications, live source-row
digest, canonical manifest digest, generated-at, database binding, and a digest
over the complete envelope. The binding hashes PostgreSQL database name and
database OID. It is a non-secret same-cluster wrong-database guard, not a
globally unique deployment identity. A clone, restore, or database recreation
requires a fresh dry run and envelope even when the human environment label is
unchanged.

The canonical actor-schema migration locates this envelope only through:

```bash
export WORKSTREAM_LEGACY_ACTOR_CLASSIFICATION_FILE=/secure/workstream/prod/legacy-actor-classification-v1.json
```

Set the variable only on the reviewed AUTH-06 migration runner. The migration
loads the strict envelope, recomputes the complete live row-set digest and
database binding inside its transaction, and aborts on checksum, TOCTOU,
missing/extra row, identity, or binding mismatch. The envelope never creates
grants and is not a supported ad hoc migration path.

On validation failure, correct the authoritative manifest or target database,
rerun dry-run, and export to a new secure path when the evidence bytes change.
Never edit an envelope or bypass the failure with SQL.

Deploy AUTH-06 only in a quiesced maintenance window after the dry-run report
and envelope have been reviewed:

1. Drain in-flight API requests and jobs.
2. Stop every old-version API replica and asynchronous writer.
3. Run the migration from the reviewed AUTH-06 release artifact.
4. Start only replicas and jobs containing the matching AUTH-06 code.
5. Complete the checks below before resuming traffic.

```bash
cd backend
export WORKSTREAM_LEGACY_ACTOR_CLASSIFICATION_FILE=/secure/workstream/prod/legacy-actor-classification-v1.json
.venv/bin/alembic upgrade 0020_canonical_actor_profile
```

Verify one durable migration-state row before serving traffic. Record only the
schema version, classified count, and checksums; do not export identity rows:

```sql
select schema_version, classified_count, source_row_set_sha256,
       manifest_sha256, envelope_sha256, migrated_at
from actor_profile_migration_state where id = 1;

select
  (select count(*) from actor_profiles) as profile_count,
  (select count(*) from actor_identity_links) as identity_link_count,
  not exists (
    select 1 from actor_profiles p
    full join actor_identity_links l on l.actor_profile_id = p.id
    where p.id is null or l.id is null
  ) as exact_one_link_per_profile,
  to_regclass('public.admin_role_grants') is null as no_admin_grant_table,
  to_regclass('public.project_role_grants') is null as no_project_grant_table;
```

Confirm every canonical profile has exactly one identity link, the classified
count matches the reviewed report, and no grants were created by the migration.
Retain the manifest and envelope only through verification and the approved
rollback window. Then delete both identity-bearing files from operator storage
and retain only the bounded report and durable checksum record.

Rollback to `0019_authority_idempotency` uses the same quiescence sequence: drain
requests and jobs, stop all AUTH-06 writers, run the downgrade, deploy only the
matching pre-AUTH-06 code, verify, and then resume traffic. The downgrade is
envelope-independent because its required state is in PostgreSQL. It refuses
while any profile is suspended or any identity link is revoked; those states
may be repaired only through their reviewed lifecycle operations, never direct
SQL. Deactivation is terminal: if any actor is deactivated, downgrade is
unavailable and operators must recover forward on AUTH-06. A non-empty registry
restored to 0019 cannot be upgraded again from deleted evidence: run the
classification tool against the exact restored rows and obtain a newly reviewed
envelope. The migration never guesses a subject kind or bypasses this
fresh-evidence requirement.

Run the exact rollback only after those checks pass:

```bash
cd backend
.venv/bin/alembic downgrade 0019_authority_idempotency
```

Rollback restores every canonical identity to legacy identity storage and
copies the current canonical `display_name` and `contact_email`, including
`null`, into the restored row. This prevents a cleared canonical contact email
from being resurrected by pre-AUTH-06 code. Because canonical migration does
not import legacy display fields, rollback intentionally scrubs retained legacy
display data unless it was set through `PATCH /api/v1/actors/me` after AUTH-06.

## Staged Rollout

For each chunk:

1. Confirm allowed files and stop conditions.
2. Run focused tests plus the full backend suite/API drill required by the
   contract.
3. Run migration upgrade, downgrade-one, and re-upgrade where applicable.
4. Confirm the obsolete-path allowlist only shrinks and no compatibility path
   was added or restored.
5. Run required internal reviewers and repair valid findings.
6. Publish one chunk-sized PR and stop for human merge approval.
7. Update post-merge memory before activating the next chunk.

Do not cut over a resource family until its local actor, grant, permission,
resource loader, lifecycle guards, negative tests, and evidence path exist.

### Catalogue And Action-Evidence Staging

The catalogue contains exactly 74 PermissionIds and 65 ActionIds after
AUTH-09D-B. The two AUTH-07B actor-self actions, seven AUTH-08 administrative
actions, `actor.service.provision`, `actor.profile.read`,
`actor.identity_link.read`, the three profile lifecycle actions, and the two
identity-link lifecycle actions are active; the other 48 entries remain planned
and non-executable. The target post-custody
invariant is that planned runtime entries contain only action, permission, exact
AUTH activation owner, and availability. Until the availability-neutral custody
transfers merge, the 25 ART and 19 REV rows retain their historical feature
owner values as an explicitly blocked exception.
Their owning feature must publish the approved principal/resource/guard/surface/
transaction contract before registration or activation, but those foreign facts
do not become free-form catalogue fields. Startup validation failure is a release
blocker, not a reason to relax catalogue checks.

PR #139 requires availability-neutral transfer of all 25 ART and 19 REV owner
rows to exact AUTH chunks before feature activation. Counts and mappings remain
unchanged. Catalogue totals are derived from the trusted entry head: four later
REV registrations add exactly four planned and zero active actions, while the
review-evidence binding registration adds exactly one planned and zero active
action, in either order. Neither addition is operational until its complete
feature contract and separate reviewed AUTH registration exist.

Migration `0021` preserves historical audit rows with null `action_id`. Inspect
non-null action evidence only by bounded ActionId, request/correlation IDs, and
resource references; do not export event payloads or actor identity-link data
for routine diagnosis. Every action must carry its catalogue-mapped PermissionId,
and every permission added after migration `0018` must carry one of its mapped
actions. Planned actions can record bounded denial evidence but cannot record an
allowed decision through the typed writer.

The historical permission set remains exactly 49 values. The post-`0020` set
contains exactly 25 values, including `review.queue.override`; do not derive
historical status from identifier prefixes. All submission/review rows remain
planned. Initial and revision submission share `submission.create`, and no
revision-specific permission or preparation action exists.

Review reads consume the request-scoped public
`AuthorizationService.require(action_id, typed_resource_context)` boundary.
The service's bound caller-owned `AsyncSession` is the only transaction source;
the method accepts no session or `uow` argument. Review code must not query
grants, import AUTH persistence, select raw
PermissionIds, or implement permission unions. Artifact recovery remains the
ART-owned `artifact.verification_job.retry` action through
`ArtifactOperatorRecoveryPort`; shared outbox dispatch/retry remains outside
REV ownership.

Review and other sensitive mutations must wait for `WS-AUTH-001-PREP`. That
protocol locks `AuthorityControl(id=1)` first when final-admin safety applies,
orders multiple principals by ActorProfile ID, then locks each human profile,
exact link, and exact matched grant or each service profile and exact link.
Service identity, static matrix membership, and action availability are
code-owned validations, not database lock targets. Only then does AUTH create an
internal, non-Pydantic `PreparedAuthorizationHandle` bound to the exact session,
ActionId, actor reference kind, actor reference, idempotency key, and canonical
request digest. It is never a route schema or caller input. Consumption matches
every binding before the feature locks rows and recomposes final facts, then AUTH
evaluates and stages evidence once before one route/service-command commit.
Crossed tests must cover link revoke, actor suspend/deactivate, exact grant
revoke, final-admin mutation, and same-session/action cross-actor or
cross-request substitution. Never serialize or reuse the handle, let dependency
teardown commit it, or commit AUTH evidence separately from feature state. The
existing `AuthorityClaimHandle` is a separate idempotency-reservation contract,
not this prepared authorization handle.

Downgrade is allowed only while every action ID remains null and no permission
outside migration `0018`'s historical 49-value set exists in the decision,
target-reference, or invalidation-reference fields. The migration takes an
exclusive audit-table lock before these checks and keeps it through destructive
DDL. If any forward evidence exists, stop and recover forward rather than
discarding it.

Canonical actor self-read/self-update, the seven AUTH-08 administrative
actions, AUTH-09B controlled service provisioning, and the two AUTH-09C
actor-registry reads are active. Project capability context waits for AUTH-10
exact-project grants and canonical project composition.

AUTH-10 is a clean cut to independent `submitter`, `reviewer`, and
`adjudicator` grants. Before rollout, scan current typed schemas, audit facts,
idempotency records, and PostgreSQL validators for `both`, replacement fields,
replacement events, and replacement reasons. Migration `0027` must stop on any
incompatible evidence; operators must remediate through a separately approved
data decision, never an automatic conversion. A safe downgrade also refuses
rather than deleting adjudicator or new exact-role evidence.

Project-role revocation is routed by exact role. Submitter invalidation may
reach task assignment; reviewer invalidation reaches only REV; adjudicator
invalidation remains dormant until that lifecycle exists. Verify grant ID,
actor, project, role, and cause event before a consumer changes product state.
Revoking one role must leave the other project roles and all AdminRoleGrants
unchanged.

The first fixed-service set remains seven artifact identities and eleven matrix
memberships from AUTH-09A. Missing provisioned rows deny without stopping the
application. New REV/CON service identities require an exact owning-feature
manifest followed by AUTH-owned enum/constraint/matrix, provisioning, admission,
and cross-service denial proof. Do not create a shared review service or a
database service-grant table.

Fixed-service admission is request-local. Resolve only the verified issuer and
opaque subject through the exact stored link and active service profile; never
accept a service identity, action, permission, or matrix row from request or
token claims. An unknown or absent provisioned row returns bounded
`service_actor_not_provisioned` and does not block startup or Access
Administrator provisioning. Static catalogue/matrix mismatch is instead a
code invariant and may fail startup.

For an admitted service, AUTH selects its exact static `ActionId` row before
availability. Cross-service actions deny without human grant lookup, including
actions sharing a `PermissionId`; own rows remain unavailable while planned.
Revoked links and suspended or deactivated profiles deny from current database
state. Failed admission creates no first-access row, invokes no human rate
control, and advances no timestamp. If exact active resolution staged
observation timestamps before a later denial, cancellation, or evidence
failure, the request transaction rolls them back before secret-free denial
evidence is restaged from a clean transaction.

Diagnose fixed-service denials only through request/correlation ID, local actor
reference, exact ActionId, and bounded denial facts. Never log or export issuer,
opaque subject, bearer material, claims, scopes, provider payloads, mapping-file
contents, or service credentials. Lifecycle or immutable-identity drift during
the profile-then-link lock/revalidation step is a denial, not a fallback to
human grants.

## Actor Self Decision Operations

`GET /api/v1/actors/me` declares `actor.profile.read_self`; it permits an
active identity link with an active or suspended human actor. Both self routes
lock the exact actor profile first and its exact identity link second and
recheck current state before deciding. GET then advances verification timestamps
and commits bounded read-decision evidence. `PATCH /api/v1/actors/me` declares
`actor.profile.update_self`; it additionally mutates only `display_name` or
`contact_email` and commits mutation plus allow evidence once. The authorization
kernel never commits or rolls back.

Self routes return explicit 403 errors because the caller owns the target:
`identity_link_revoked`, then `actor_deactivated`, then `actor_suspended` for an
update. A correction to lifecycle state takes effect on the next request; no
decision cache survives a request. Token role changes do not affect either
self action. Unknown and planned actions appear publicly only as
`permission_not_granted`.

For diagnosis, query authority-domain `authorization_decision` rows by bounded
request/correlation ID and exact ActionId. Confirm the mapped PermissionId,
actor-profile resource reference, `allowed` fact, and denial code. Do not log or
export issuer subjects, bearer tokens, display names, contact emails, or token
roles. If a denied PATCH occurs, the route transaction is rolled back and the
same frozen denial is committed from a clean transaction; a changed decision
ID or concurrent display-field mutation is an incident signal.

## Administrative Authority Operations

AUTH-08 activates permission and administrative-role definition reads, scoped
administrative-grant collection and actor-history reads, and administrative
grant issue/revoke. Access Administrator is the only role that can issue or
revoke. Audit Authority is read-only and sees only the system or exact-project
scope covered by its current grant; filtering occurs before totals and cursors.
Requested target role/scope is mutation data, never caller authority.

AUTH-09C adds `GET /api/v1/actors/{actor_profile_id}` and `GET
/api/v1/actors/{actor_profile_id}/identity-links`. Both require an effective
system-scoped Access Administrator or Audit Authority grant; a project-scoped
Audit Authority grant never covers the global actor registry. The link route
returns the one v0.1 link object, not a collection. Suspended/deactivated target
actors and revoked target links remain readable for lifecycle diagnosis.

The profile response includes only canonical lifecycle state, timestamps,
display name, provisioning method, and the closed local `service_identity` for
a service actor (`null` for a human). The link response includes only its local
IDs, subject kind, lifecycle state, and timestamps. Neither response includes
issuer, subject, contact email, reason, lifecycle actor, token/claim, grant,
assignment, or service-action-matrix data.

The kernel locks and revalidates the human caller profile, exact link, and
matched system grant before target lookup and holds those locks through
disclosure and commit. It does not acquire `AuthorityControl` or lock a distinct
target. Unauthorized callers are denied before lookup. Missing actor and link
targets both roll back the staged allow and return the same
`actor_resource_not_found` 404; they do not advance caller timestamps or leave
allow evidence. SQL/evidence/touch/commit failure rolls back and returns the
retryable `service_unavailable` 503.

Each protected route owns one caller-session transaction. A successful read,
exact replay, issue, or revoke commits its decision evidence and advances the
caller's `ActorProfile.last_seen_at` and `ActorIdentityLink.last_verified_at`
using database time. Issue/revoke additionally commit business state,
idempotency completion, success evidence, and linked invalidation together.
Success, invalidation, mismatch, and post-allow conflict evidence derive their
request/correlation IDs from the exact authorization decision; feature callers
cannot override them.
The decision resource-context digest binds role, scope, target, and existing
idempotency-record disposition. Issue/revoke recomputes the reason digest before
any state or evidence write.
The shared authorization dependency never commits an open feature transaction;
it rolls back anything the route forgot to commit.

### Controlled Service Provisioning

`POST /api/v1/service-actors` accepts only a fixed `service_identity`, opaque
subject with no leading or trailing whitespace, bounded reason, and UUID
`Idempotency-Key`. Accepted subject bytes are preserved without normalization.
The issuer comes from the configured provider-neutral verifier; operators
cannot submit or override it.
Only an effective system Access Administrator may call the route. A successful
request creates one active service ActorProfile and exact identity link plus the
allowed decision, `ServiceActorProvisioned`, linked invalidation, and committed
idempotency result in one transaction. It creates no role, grant, assignment,
or service admission.

Treat `service_identity_already_provisioned` and
`identity_subject_already_linked` as final 409 occupancy conflicts. Treat
`idempotency_mismatch` as client request drift. Retry `service_unavailable` with
the same key and exact body. Do not inspect or export issuer, subject, bearer
token, email, or raw reason when diagnosing a failure; use bounded
request/correlation IDs and ActionId `actor.service.provision`.

Provisioning is not token verification. The new service profile's
`last_seen_at` and link's `last_verified_at` stay null, including on replay.
Only the human caller timestamps advance on a committed create or replay.
Provisioned service tokens enter only the central AUTH typed-service path;
legacy dependencies continue to reject them. Unprovisioned service tokens deny
without actor first-access, timestamp observation, or rate-control activity.

If route-owned persistence or decision evidence fails, roll back the entire
unit and return the bounded retryable `503 service_unavailable` envelope. Do
not report a mutation as successful, retain a pending idempotency result, or
advance verification timestamps. A retry uses the same idempotency key. Exact
replays reauthorize current caller authority and canonical resource state before
returning the stored response. A deactivated service profile or revoked service
link makes replay unavailable; mismatches commit only bounded denial evidence
from a clean transaction.

## Rollback

Rollback stops rather than bypasses authorization. A deployment may roll back
only to the preceding reviewed chunk state and compatible schema revision.

Stop rollout when:

- issuer behavior would require trusting a token role/unverified claim;
- classification requires guessing subject kind;
- a second canonical actor/verifier/authorization path appears necessary;
- authority state and evidence cannot commit atomically;
- final-administrator safety depends on an unlocked count;
- an intermediate release cannot execute the established intake lifecycle;
- tests, CI, privacy, or auth defaults would need weakening.

Do not restore deleted authority through direct SQL or re-enable any obsolete
token-role path.

## Recovery Permission Inventory

| Operation | Authority | Required controls |
|---|---|---|
| Normal covered task/setup repair | Covered Project Manager `project.task.manage` | Exact project, lifecycle guard, reason/evidence where mutation is corrective. |
| Start override | Operator `operations.task.start_override` | Recovery-only path, exact task/project, reason, matched grant/permission, audit. |
| Submission gate repair | Operator `operations.submission_gate.repair` | No submission/review rewrite; reason, matched authority, immutable checker evidence. |
| Checker retry | Operator `operations.checker.retry` | New attempt/supersession evidence; no prior result deletion. |
| Review lease force release | Operator `review.lease.force_release` under WS-REV-001 | Review-owned lease guards and evidence; no review decision. |

Conceptual historical “admin override” statements are not operations. No
recovery permission may erase checker evidence, create a review decision,
alter an immutable submission, create/alter a contribution record, or bypass
contribution policy.

## Monitoring And Alerts

Required bounded-cardinality metrics cover:

- `workstream_auth_verification_total{result}`;
- `workstream_auth_jwks_cache_total{result}`;
- `workstream_auth_jwks_refresh_total{result}`;
- `workstream_auth_introspection_total{mode,result}`;
- actor first access/conflict and actor/link state;
- authorization allow/deny code and registered permission;
- administrative/project grant state;
- invalidation backlog and reconciliation retry;
- bootstrap attempt/result.

Alerts require an owner, diagnosis steps, safe recovery, escalation path, and
evidence-retention period. Alert on sustained verification failure, unusable
JWKS cache, repeated bootstrap/final-administrator denial, unusual grant
mutation rate, invalidation backlog, and abnormal first-access conflicts.

Platform security/on-call alerts when verification or refresh failures exceed
5% for five minutes, when all JWKS refreshes fail for two consecutive cache
windows, or when required introspection is unavailable for two minutes.
Diagnosis checks the approved issuer configuration, HTTPS reachability, key
rotation window, cache age, and introspection health without printing response
bodies or credentials. Recovery restores the approved issuer endpoint/policy;
it never enables HMAC, development auth, redirects, or an unpinned algorithm.
Escalate to the release owner and security lead and retain redacted incident
metrics/configuration evidence for the normal security incident period.

Never use token, subject, email, `jti`, raw URL, key material, or unbounded
resource IDs as metric labels.

## Authority Mutation Idempotency

AUTH-09D-A and AUTH-09D-B expose:

```text
POST /api/v1/actors/{actor_profile_id}/suspend
POST /api/v1/actors/{actor_profile_id}/reactivate
POST /api/v1/actors/{actor_profile_id}/deactivate
POST /api/v1/actor-identity-links/{identity_link_id}/revoke
POST /api/v1/actor-identity-links/{identity_link_id}/reactivate
```

Each route requires an effective system Access Administrator, the administrative
mutation limiter, a UUID `Idempotency-Key`, and exactly one normalized bounded
`reason`. Conflicts do not consume the key. Deactivation is terminal, and a
profile reactivation does not restore a revoked identity link, grant, or fixed
service admission. Link revoke/reactivate preserves the immutable issuer and
subject binding, permits repair while its owner is suspended, refuses terminal
owners, and never restores a grant or fixed-service admission. An administrator
cannot revoke their own identity link.

Service-actor creation, administrative/project grant issue or revocation,
actor suspension/reactivation/deactivation, and identity-link
revocation/reactivation require a canonical UUID idempotency key. The namespace
is actor-kind, opaque actor reference, closed operation, and key. Reusing that
namespace with a different canonical request produces `idempotency_mismatch`
without exposing the stored digest, record, or response.

Reservation must be the first database write. Business state, one concrete
success event, one linked invalidation event, and the typed replay reference
commit in the same caller-owned transaction. The authorization repository and
service never commit, roll back, open a second session, expire a pending row, or
steal a claim. On mismatch the caller rolls back the reservation transaction,
starts a clean transaction on the same injected session, commits exactly one
privacy-bounded denial event, and then translates the conflict.

A replay reference is internal only. Active administrative routes load the
canonical resource and evaluate current authority again before responding;
later route owners must preserve the same rule. There is currently no
invalidation consumer or backlog processor; the durable event is foundation
evidence for the owning later chunk.

## Authority Audit Custody

Authority decisions and invalidation requests use the shared `audit_events`
ledger. Database triggers reject normal `UPDATE`, `DELETE`, and `TRUNCATE` for
both lifecycle and authority rows. There is no runtime flag, session setting,
or application-user bypass. Authority timestamps come from the database, and
the application writer joins the caller's transaction so evidence cannot
commit separately from the authority mutation it explains.

Production must run Workstream with a dedicated non-owner database role that
has no DDL, trigger-management, table-owner, superuser, or bypass privileges.
Release verification must fail if the application credential owns
`audit_events` or can disable its triggers. Schema migration credentials are
separate and unavailable to the running service.

Owner-level maintenance is exceptional and requires an approved change record,
an outage or writer drain, and an explicit list of rows and purpose. The
database owner must:

1. begin one transaction and take `ACCESS EXCLUSIVE` lock on `audit_events`;
2. record the pre-change row count and trigger state without exporting private data;
3. disable only the named mutation trigger needed for the approved operation;
4. perform only the listed maintenance statements and verify affected IDs/counts;
5. re-enable the trigger before commit and prove all three audit triggers enabled;
6. retain redacted change evidence and return credentials to controlled storage.

Do not use owner maintenance to revise authority history, erase a denial, or
fabricate evidence. Normal migration downgrade refuses while authority rows
exist; destructive cleanup requires a separately reviewed retention or legal
procedure and is not an application operation.

## Incident Response

For suspected authority misuse:

1. Preserve request/correlation IDs and append-only authority evidence.
2. Suspend/revoke through supported operations when current authority permits.
3. Confirm same-token denial on the next request.
4. Inspect exact matched grant, permission, project, and resource guards.
5. Reconcile affected assignments without rewriting submitted/review history.
6. Escalate final-administrator risk before any state mutation.
7. Record corrective action and retained evidence without secrets or private
   artifact content.

## Live Proof Responsibility

The final release owner coordinates a supported API/command drill proving:

- first human access;
- one-time bootstrap and concurrent conflict;
- scoped administrative grants;
- exact-project submitter/reviewer/adjudicator grants;
- admin/contributor separation and self-action denial;
- same-unexpired-token revocation;
- suspension/reactivation and link revocation;
- service subject handling;
- cross-project concealment;
- final-administrator concurrency safety;
- authorized audit export and absence of direct database authority edits.

Committed proof uses approved redacted placeholders and never production
tokens, private keys, raw claims, private actor/source IDs, or local paths.
