# Systems Architecture Review

Review scope: markdown docs in `<repo-root>`.

Reviewer role: Systems Architecture Reviewer.

## Findings

### High: Compensation fulfillment state was mixed into task lifecycle

Task lifecycle initially included a compensation fulfillment state as a terminal
task state. That risks the same reporting confusion seen in task platforms
where accepted work and fulfilled awards are separate dimensions.

Suggested change: keep task status and compensation fulfillment status
separate. Task terminal states should be accepted, rejected, or cancelled,
while fulfillment status advances independently under its own adapter-owned
contract.

Status: fixed in `docs/roadmap_30_day_master_plan.md`, `docs/architecture_lifecycle_state_machine.md`, and `docs/operations_payment_reputation.md`.

### High: Roles and permissions needed a first-version matrix

The plan mentioned roles, but did not define who can review, override, or
administer compensation fulfillment. That creates risk of self-review, unsafe
overrides, and fulfillment changes without authority.

Suggested change: add a permission matrix and separation rules.

Status: fixed in `docs/operations_roles_permissions.md`.

### Medium: Guide and policy versioning needed to attach to system records

Tasks recorded guide version, but the locked task contract and downstream system records also need policy versions so later guide edits do not make old decisions ambiguous.

Suggested change: add server-stamped locked guide and policy version fields to
the task contract, submissions, checker runs, reviews, ContributionRecords, and
CompensationAwards. Submitters submit against the task id without restating policy
versions.

Status: fixed in `docs/architecture_data_model.md`.

### Medium: Artifact immutability needed to be explicit

The evidence model had hashes but did not clearly say when artifacts become immutable.

Suggested change: artifacts should be hash-locked when checker execution begins; changes require a new submission version.

Status: fixed in `docs/architecture_system_architecture.md` and `docs/architecture_data_model.md`.

### Low: Duplicate older docs are not part of the canonical package

The canonical package now lives in the flat `docs/` directory and the root `README.md` links to those files.

Suggested change: keep future markdown docs in `docs/` with clear prefixes.

Status: resolved by flattening markdown documentation into `docs/`.

### Low: README had duplicate roles/permissions links

README linked both `docs/roles_permissions.md` and `docs/operations_roles_permissions.md`.

Suggested change: keep the operations document as canonical because it has the permission matrix.

Status: fixed in `README.md`.

## Baseline Scope Update

Baseline scanned at metadata/process level only under `local reference workspace`, covering several reference projects. The scan looked at guide names/headings, queue/status structures, review guards, checker/preflight scripts, review packet/evidence/status patterns, and submission package/provenance structures. No task content or confidential details were copied.

### Medium: Packaged submission provenance should be first-class

Baseline pattern: submission packages commonly carry hashes, provenance metadata, checker logs, validation logs, and status records. Workstream already had artifact hashes, but needed a named readiness/provenance concept that ties a submission packet to the exact checker run that cleared it for review.

Suggested change: add readiness certificate and submission provenance fields.

Status: fixed in `docs/architecture_data_model.md`, `docs/architecture_checker_framework.md`, and `docs/template_submission_packet.md`.

### Medium: Lessons learned should be a data object, not only prose

Baseline pattern: repeated workflow misses become guide updates, review-guard updates, checker updates, or workflow lessons. Workstream mentioned lessons learned, but did not model them as a durable object.

Suggested change: add `ProjectLesson` with status and recommended change.

Status: fixed in `docs/architecture_data_model.md` and `docs/operations_operator_workflow.md`.

### Low: Workstream captures the reusable operating model

Baseline pattern: project guide, queue/status, checker/preflight, review guard,
review packet, evidence, status ledger, needs-revision replay, and independent
contribution/compensation fulfillment tracking.

Assessment: Workstream captures this reusable model through the canonical docs linked in `README.md`. Remaining duplicate older docs should be cleaned later, but they do not block the planning package.
