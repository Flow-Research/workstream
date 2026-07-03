# Chunk 8: Submission Artifact And Policy Checkers

## Purpose

Chunk 8 expands the checker registry from the first structural runner into the first policy-aware submission artifact gate.

The goal is not to judge final work quality. The goal is to verify that required structural signals are present before Workstream can later move a locked submission toward human review.

Chunk 8 does not prove artifact content safety, confidentiality truth, absence of secrets, or hash/content equality. Those require later object-store reads, content scanning, and stronger checker adapters.

## Scope

- canonical checker names for evidence and policy checks
- submission artifact and evidence presence checks
- submission artifact and evidence integrity checks
- task acceptance-criteria checks
- required-file checks
- forbidden-file checks
- confidentiality attestation checks
- low-quality/generated-artifact warning checks
- worker-visible failure messages that do not leak internals
- Postgres-backed API tests through the existing checker-run endpoint
- documentation cleanup so checker policy templates and implementation use the same names

## Non-Scope

- automatic transition to `REVIEW_PENDING`
- automatic transition to user-facing `needs_revision`
- readiness certificate creation
- reviewer queue routing
- human review decisions
- contribution, payment, or reputation records
- external object-store content reads
- antivirus, secret-scanning engines, or external static-analysis adapters
- model-based reviewer simulation
- dedicated readiness-certificate evidence handoff, which needs the later readiness/pre-review record shape before it can be enforced correctly

## Naming Contract

Chunk 8 uses the architecture/template checker names as the canonical policy names.

Canonical Chunk 8 checker names:

- `check_evidence_present`
- `check_evidence_integrity`
- `check_acceptance_criteria_present`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

Chunk 8 performs a hard rename of Chunk 7's temporary public evidence-reference and artifact-manifest checker names to `check_evidence_present` and `check_evidence_integrity`.

The old names are not aliases. If a checker policy still references the old names after Chunk 8, durable checker execution must reject the policy as invalid instead of silently mapping it.

Internal helper function names may be implementation-specific, but API responses, persisted `checker_results.checker_name`, templates, docs, and project checker policies must use the canonical names. Tests must prove old public names are not emitted and are not accepted as registered policy names.

## Checker Behavior

### `check_evidence_present`

Fails when the task requires evidence and the locked submission has no evidence rows.

The checker reads:

- the locked project `PreSubmitCheckerPolicy` and effective project submission
  artifact policy
- `submission.evidence_items`

Worker-visible failure:

- explain that evidence required by the locked project pre-submit checker
  policy is missing
- tell the worker to attach evidence items before review

### `check_evidence_integrity`

Fails when submitted artifact/evidence references cannot be trusted structurally.

The checker validates:

- artifact manifest can be canonicalized
- artifact names are unique
- artifact hashes are present
- production artifact hashes use `sha256:<64 lowercase hex>`
- evidence items with local/R2/S3 object references include hashes
- evidence items with `type = external_reference` may omit `uri` and `hash` in Chunk 8

This checker does not download object-store content in Chunk 8. Content-addressed object verification remains an object-storage adapter concern for a later chunk.

Local test fixture hash token exception:

- production accepts `sha256:<64 lowercase hex>` only
- explicit local test fixtures may use deterministic `sha256:<non-empty-token>` placeholders
- placeholder tokens are not valid production submission proof

### `check_acceptance_criteria_present`

Fails when the task has no reviewable acceptance criteria.

The checker reads:

- `task.acceptance_criteria`

Project-manager operational message:

- tell the project manager to add reviewable acceptance criteria before review can continue

This is a locked task setup failure, not worker-fixable submission work. Worker-facing checker responses must not expose the internal `task_setup_blocked` route or the missing setup field names.

### `check_required_files`

Fails when required artifacts are not represented in the artifact manifest.

The checker reads:

- locked project `PreSubmitCheckerPolicy` required artifacts
- `submission.artifact_hash_manifest[*].artifact`

`task.required_files` is legacy/transitional storage. It is not the policy source of truth once `SubmissionArtifactPolicy` is implemented.

Matching is exact after path normalization. Chunk 8 does not implement glob matching.

Path normalization rules:

- trim leading and trailing whitespace
- convert backslashes to `/`
- collapse duplicate `/`
- strip a leading `./`
- reject empty paths
- reject absolute paths beginning with `/`
- reject `.` or `..` path segments
- keep matching case-sensitive

### `check_forbidden_files`

Fails when artifact names or evidence object references include known forbidden path patterns.

Workstream default forbidden patterns:

- `.env`
- `.pem`
- `.key`
- `id_rsa`
- `private_key`
- `secret`
- `token`
- `credential`
- `node_modules/`
- `.git/`

The failure message must not echo secrets, signed URLs, private credentials, or full internal paths.

Forbidden pattern matching rules:

- normalize paths with the same path normalization rules used by `check_required_files`
- compare normalized paths in lowercase
- `.env`, `id_rsa`, `private_key`, `secret`, `token`, and `credential` match exact path segments only
- `.pem` and `.key` match filename suffixes only
- `node_modules/` and `.git/` match path segments only
- substrings inside otherwise valid filenames do not fail by themselves, so `my-token-report.md` does not fail only because it contains `token`

### `check_confidentiality_attestation`

Fails when the worker attestation is missing or does not satisfy the deterministic Chunk 8 confidentiality boundary.

The normalized attestation must:

- be at least 40 characters
- not equal generic acknowledgements such as `ok`, `done`, `yes`, `i agree`, or `confirmed`
- include at least one confidentiality term: `confidential`, `private`, `client data`, or `proprietary`
- include at least one credential term: `credential`, `secret`, `token`, `password`, or `api key`
- include at least one source/platform term: `source material`, `source code`, `platform artifact`, `copied artifact`, or `copied platform`

This checker does not prove the claim is true. It only ensures the worker made the required attestation before review.

### `check_low_quality_generated_artifacts`

Warns when summary, artifact names, artifact notes, or evidence labels contain obvious placeholder/generated-output signals.

Default warning patterns:

- `todo`
- `placeholder`
- `lorem ipsum`
- `sample output`
- `dummy`
- `generated by chatgpt`
- `as an ai language model`

This checker is warning-grade and non-blocking in Chunk 8. It always emits `status = warning` when it finds a signal, and the current blocking model only blocks failed checker results.

If a future project needs generated-artifact signals to block review, that must be implemented as a separate failed-result checker or a deliberate blocking-model change.

## Pre-Submit Versus Durable Runs

Pre-submit feedback executes the task's locked project `PreSubmitCheckerPolicy`, which was compiled from the effective project submission artifact policy at project setup time. These checks run before Workstream creates a submission row:

- `check_submission_packet`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`

The project pre-submit checker policy is generated from:

```text
WorkstreamDefaultSubmissionArtifactPolicy
+ SubmissionArtifactPolicy
```

Workstream defaults are non-bypassable. Project policy can add required artifacts, evidence requirements, stricter forbidden patterns, and packaging rules, but it cannot remove hash requirements, allow unsafe storage references, require forbidden files, or downgrade blocking defaults.

Blocking pre-submit failures prevent submission creation. Preflight failures
return `PreSubmitCheckResponse(status="failed", eligible_to_submit=false,
results=[...])`. Blocked submission-create attempts return
`DomainError(code="pre_submission_checker_failed")` with structured
pass/fail/warning details, create no submission row, no submission version, no
task transition to `submitted`, and no submission-created audit event. They do
not return review decision values: `accept`, `needs_revision`, or `reject`.

Durable post-submit checker runs execute the complete `execution_checkers` list
from the submission-stamped locked `PostSubmitCheckerPolicy` body. That locked
body includes Workstream default durable checkers, project required checkers,
warning checkers, and blocking severities. The durable run records the locked
post-submit checker policy id, version, hash, and internal policy body stamped
on the submission. Worker-facing responses do not expose those provenance
fields.

- `check_submission_packet`
- `check_policy_context_present`
- `check_evidence_present`
- `check_evidence_integrity`
- `check_required_files`
- `check_forbidden_files`
- `check_confidentiality_attestation`
- `check_low_quality_generated_artifacts`
- additional locked `required_checkers`
- additional locked `warning_checkers`

`check_acceptance_criteria_present` is registered in Chunk 8, but it is a
locked task setup checker. It is not part of the default durable
submission-quality list. If a locked `PostSubmitCheckerPolicy` requires it and
it fails, the run must use task setup routing, not worker revision routing.

## Routing Boundary

Chunk 8 still records checker results only.

If worker-fixable submission checks fail, the durable checker run records:

- `status = completed`
- `routing_recommendation = needs_revision`
- `outcome_source = auto_checker`

Worker-fixable submission checks include missing evidence, missing required files, malformed artifact/evidence hash references, forbidden file patterns, and missing/invalid confidentiality attestation.

If task setup checks fail, the durable checker run records:

- `status = completed`
- `routing_recommendation = task_setup_blocked`
- `outcome_source = auto_checker`

Project setup checks include missing acceptance criteria or missing locked project/policy context. These are not worker revision outcomes.

Routing priority is deterministic:

1. `checker_retry` for checker/platform execution failures
2. `task_setup_blocked` for locked task setup defects
3. `needs_revision` for worker-fixable submission failures
4. `allow_review` when there are no blocking failures

When one checker run contains both task setup failures and worker-fixable submission failures, `task_setup_blocked` wins because the project manager must fix the task contract before the worker can receive a meaningful revision request.

Chunk 8 documents `task_setup_blocked` in its schema and implements the routing contract, but normal API flows are expected to prevent task setup defects before submission. For example, current task screening requires acceptance criteria before a task can be released. Chunk 8 tests must verify the enum/source-of-truth contract and may verify task setup routing through controlled service/repository setup if no normal FastAPI path can produce a locked submission with that defect. A later admin repair workflow can add a real API path for this route.

Chunk 9 owns applying the lifecycle transition.

If Chunk 8 checks pass or only warning-grade checks fire, the durable checker run records:

- `status = completed`
- `routing_recommendation = allow_review`
- `outcome_source = none`

`allow_review` still means ready for human review, not accepted.

## Worker Visibility

Workers may see:

- checker name
- status
- severity
- safe worker message
- safe suggested fix
- safe evidence references

Workers must not see:

- raw metadata
- stack traces
- signed URLs
- credentials
- private object paths
- hidden detection patterns beyond safe category names
- reviewer-only policy notes

Safe evidence references mean opaque Workstream evidence ids, sanitized labels, or public-safe references only. Worker-visible evidence references must not include raw object URIs, bucket names, object keys, local filesystem paths, signed URLs, query strings, credential-bearing references, or private storage paths.

## Conditions Of Satisfaction

- canonical Chunk 8 checker names are registered
- stale Chunk 7 temporary checker names are removed from public docs/templates/tests
- pre-submit feedback executes the task's locked project `PreSubmitCheckerPolicy` and runs without durable checker records
- preflight failures return `PreSubmitCheckResponse(status="failed", eligible_to_submit=false, results=[...])`
- blocked submission-create attempts return `DomainError(code="pre_submission_checker_failed")`, include structured pass/fail/warning details, create no submission row, no submission version, no task transition to `submitted`, and no submission-created audit event
- Workstream default submission artifact rules cannot be weakened by project policy
- durable checker runs persist Chunk 8 checker results
- missing required evidence blocks review routing
- missing required files block review routing
- malformed artifact/evidence hash references block review routing
- forbidden file patterns block review routing without leaking sensitive details
- missing or generic confidentiality attestation blocks review routing
- low-quality generated artifact patterns persist warning results by default
- clean submissions keep `routing_recommendation = allow_review`
- worker-fixable submission failures keep `routing_recommendation = needs_revision` and `outcome_source = auto_checker`
- task setup failures keep `routing_recommendation = task_setup_blocked` and do not create worker revision outcomes
- worker-facing checker-run responses omit `routing_recommendation`,
  `outcome_source`, and internal route tokens such as `allow_review`,
  `checker_retry`, and `task_setup_blocked`
- tests use real FastAPI calls and Postgres-backed persistence, not monkeypatch-only unit tests
- senior engineering, QA/test, security/auth, and product/ops reviewer tracks pass before PR completion

## Verification

Run from `backend/` against local async Postgres:

```bash
WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_checkers.py -q
```
