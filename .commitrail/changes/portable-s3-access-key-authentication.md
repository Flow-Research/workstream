# Portable S3 access-key authentication

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: A hosted deployment can access AWS S3 from any host using explicit private access-key credentials without certificate infrastructure, while preserving isolated storage authority and verification.

## Intent

The operator approved replacing the current deployment's manual certificate dependency with dedicated restricted access keys. Do not introduce an online CA or require EC2 hosting. Preserve product records, bucket objects and enforced storage protections; remove obsolete proof-only records with their tables.

## Current behavior

Native AWS configuration rejects static credentials. Runtime and proof evidence bind three distinct role ARNs and exact policies. MinIO static credentials are local-only. Hosted startup currently binds certificate files and Roles Anywhere checks.

## Bounded change

### Allowed

- ART provider interfaces, S3 and local adapters, backend and Celery startup,
  ART storage orchestration, and artifact readiness reporting.
- The proof-only models, operator commands, deployment scheduling and focused
  tests, plus one forward migration dropping only the two proof tables.
- Release-image workflow selections and their contract tests, native backend
  configuration example, and app-only hosted deployment integration.
- Direct IAM-user credential loading and isolated AWS authentication, IAM
  policy generation, live deployment verification, and affected operator docs.

### Not allowed

- Ambient credential fallback, provisioning credentials in runtime,
  credentials in tools/checker guests, deletion of product records or bytes,
  and weakened bucket immutability or authorization.
- New certificate services, new general-purpose credential frameworks, unrelated product work.

## Design and decisions

The user explicitly requires removing the expiring database-proof system, not
retaining an alternate activation path. Remove proof/activation models and
runtime gates, periodic jobs, proof-only configuration, obsolete tests and
current documentation. Drop proof-only tables through an explicit forward
migration after checking references. Do not rewrite old migration history.
Project/assignment/submission records, artifact metadata and stored bytes are
not part of this deletion.

Use one dedicated IAM user with direct access to the configured S3 bucket and
artifact prefix, through one isolated private credential file. No certificate
infrastructure, AssumeRole hop or three-user verification workflow. Preserve
AWS authentication, conditional writes, full-byte readback, exact namespace,
Workstream authorization, retry/recovery and terminal transaction safeguards.
Deployment qualification checks actual storage behavior without persisting an
expiring permission-to-use-storage record or running a privileged scheduler.

## Acceptance criteria

- Explicit private-file credentials authenticate on a non-EC2 host with metadata/ambient lookup disabled.
- Incorrect, disabled or missing credentials fail closed without secret-bearing errors.
- The dedicated key cannot administer IAM, change bucket protections, delete retained artifacts, or access other prefixes; deployment operator credentials are absent from application containers.
- Exact-byte upload/read, immutable-write denials, namespace custody and authorization remain enforced. Replace the expiring role-proof dependency deliberately; do not silently skip guards or invent activation receipts.
- Key replacement is verified before retiring the previous key; certificate trust is retired only after successful direct-key storage qualification.
- Operator receives exact restricted IAM configuration and private secret-file instructions; real AWS proof precedes deployment readiness claims.

## Risk and review routing

- Risk class: L1.
- Reviewers: security, architecture, QA/test delta, documentation.
- Human review focus: long-lived secret trade-off, preserved principal isolation, migration/rotation and rollback.

## Evidence

Source trace establishes certificate coupling and isolated proof-only database references. Backend and policy implementation and live dedicated-user storage qualification passed the focused checks recorded below. Deployment cutover and full CI remain pending.

## Review focus

Review removal of transient activation plumbing without removing product
namespace, authorization, exact-byte, retry or terminal transaction safeguards.
The user explicitly authorized removal of proof-only tables. There are no
product foreign keys into them; the forward migration must not use CASCADE.

## Reconciliation

The operator requires one delivery PR for the identity and hosting work. Integrate app-only deployment with dedicated S3 credentials in that same change, preserving both boundaries. Certificate renewal is superseded for the replacement deployment.

## Dependency trace and scope correction

Activation UUIDs are transient runtime evidence only. No product artifact put,
replica, operation, observation, verification or recovery record stores them.
Foreign keys are confined to the proof/activation tables. Removal therefore
requires a forward cleanup migration for proof-only storage, not rewriting
artifact lineage. Preserve product data and file bytes.

The old 15-minute proof validity detected configuration drift. Removing it
removes that bounded drift-detection claim; it does not remove per-operation
AWS authorization, conditional writes, hash verification or product authority.
Update current specifications accordingly. AWS administrators remain trusted.

No new proof table, timer or receipt is allowed. Candidate review follows the
focused implementation evidence below.

## Implementation verification

- Backend credential/startup checks: 333 initial targeted tests, followed by
  120 focused tests after the prefork startup-budget correction.
- Real MinIO: 42 adapter/conformance cases passed.
- PostgreSQL 16: 13 migration/terminal/recovery/assigned-document cases passed,
  including preservation of an existing product artifact row after dropping
  the two proof-only tables.
- Hosted configuration and image checks: 97 tests passed.
- Policy generation: eight tests and focused security inspection passed.
- Complete backend collection: 11,551 cases collected; full hosted execution
  remains pending and is not inferred from focused passes.
- Ruff, whitespace and changed Markdown link checks passed.
- Live AWS qualification with the dedicated user passed conditional create,
  exact readback, missing HEAD 404, replay precondition, and denied overwrite,
  delete, wrong-prefix put and anonymous read. This used a synthetic 66-byte
  object and the generated bucket policy; it does not claim the migrated
  application journey has passed.
- New host is provisioned with pinned unchanged Identity/MCP/PostgreSQL/Redis
  images. Backend release build, integrated deployment and public cutover are
  still pending. Old host and Elastic IP remain unchanged.

Obsolete tests exercised the removed certificate/activation mechanism. Mixed
terminal/recovery tests retain their independent product assertions under the
new storage path; no CI skip or coverage threshold was introduced.

## Integration repair evidence

The release-image workflow still selected removed activation-era tests. Replace
those selectors with the current AWS settings rejection cases and the complete
direct-user credential module; retain the image build/verification gates. A
workflow contract checks that every explicitly selected backend test exists.
The stale activation argument in the retained stale-put observation test is
removed without changing its fencing assertions. The native backend example
now documents only the dedicated credential file for this deployment path.

App-only deployment integration retains direct-key mounts for API, worker and
enabled model proxy while excluding them from Beat, MCP, parser and checker
guests. Native checker custody stays exclusive to the single-host overlay.
