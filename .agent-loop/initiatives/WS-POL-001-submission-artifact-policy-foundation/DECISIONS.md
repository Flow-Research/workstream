# Decisions: WS-POL-001 - Submission Artifact Policy Foundation

## Accepted

- `ProjectGuide` remains human-facing instruction.
- `ProjectGuide` is open-ended project material. It may be markdown, imported
  documentation, URL-backed docs, examples, rubrics, repository docs, or any
  project-specific material.
- `SubmissionArtifactPolicy` is the machine-readable intake contract.
- Project owners provide open-ended project material and business terms;
  they do not author or approve Workstream internal policy schema directly.
- `ProjectGuideSufficiencyAgent` evaluates whether the guide is sufficient for
  submitters, reviewers, and Workstream quality control.
- `GuideSufficiencyReport.status` values are `passed`, `blocked`, and
  `passed_with_warnings`.
- Guide sufficiency finding severities are `blocking_gap`, `warning`, and
  `info`.
- `SubmissionArtifactPolicyDerivationAgent` derives
  `SubmissionArtifactPolicy` after guide sufficiency passes or passes with
  warnings.
- `SubmissionArtifactPolicyDerivationAgent` produces constrained project
  policy, not unrestricted executable checker code.
- Workstream derives `SubmissionArtifactPolicy` from project material,
  with internal agent assistance allowed, then requires approval by `admin` or
  `project_manager` after any sufficiency warnings are acknowledged and before
  guide activation.
- Workstream default submission artifact rules are non-bypassable.
- `EffectiveProjectSubmissionArtifactPolicy` is default plus project policy.
- Workstream's trusted checker compiler builds and validates the constrained
  checker specification, then turns it into deterministic project-scoped
  `PreSubmitCheckerPolicy`.
- Tasks lock the applicable guide snapshot, effective project submission artifact policy hash,
  and pre-submit checker bundle hash. Tasks do not rerun derivation or compile
  unique checker bundles by default.
- Pre-submit checks block before submission creation.
- Preflight feedback is `PreSubmitCheckResponse`; blocked submission-create
  attempts return `pre_submission_checker_failed` with structured
  pass/fail/warning details. Neither is `accept`, `needs_revision`, or `reject`.
- Post-submit/internal checks remain separate from pre-submit checks.
- Worker-facing task outcomes remain simple; internal routes stay internal.
- Stored review decision values remain exactly `accept`, `needs_revision`, and
  `reject`. Display wording must not create new persisted tokens.
- `evidence_policy`, task-owned `required_files`, task-owned
  `required_evidence`, and generic checker-policy version locks are discarded
  construction-state fields. They are not compatibility contracts and must not
  be restored in current v0.1 APIs or migrations.
- Guide/source capture starts automatic project setup through Celery. The
  pipeline runs guide sufficiency first, stops on blocking sufficiency, and
  creates only a draft `SubmissionArtifactPolicy` after sufficiency passes or
  passes with warnings.
- Project setup automation must be visible through Workstream APIs. Operators
  should not inspect Postgres directly to learn whether sufficiency analysis,
  policy derivation, policy approval, effective policy merge, or checker
  compilation happened.
- `ProjectSetupRun` is a non-authoritative orchestration ledger. It can expose
  queue status, Celery task id, current setup step, bounded errors, and output
  ids, but it does not replace the actual guide sufficiency, submission
  artifact policy, effective policy, or pre-submit checker policy records.
- Project setup and project policy visibility APIs require project setup
  operator access. In v0.1, that means verified `admin` or `project_manager`
  token roles.
- Worker-facing task context APIs must read already-stamped locked context from
  the task. They must not recompute policy from the current active guide, and
  they must omit compiler internals, raw compiled bundles, private source refs,
  and internal policy authority fields.
- The Terminal Benchmark live API drill must be repeatable without direct DB
  reads. Any state needed to continue the drill must be exposed through an
  authorized API response.
- Submission finalization is the public operation that locks a submitted packet
  and starts the pre-review gate. The external requester authorizes the action;
  Workstream records system-owned pre-review gate execution through an internal
  system actor so audit trails distinguish human/operator requests from
  automated checker execution.
- In v0.1, submission finalization is an `admin` or `project_manager`
  operation. The internal pre-review gate system actor cannot authorize HTTP
  requests; it is only used for automated checker execution audit attribution.
- Public API wording should prefer `finalize` for submission handoff into the
  pre-review gate. `lock` can remain an internal persistence concept such as
  `locked_at`, but should not remain the public endpoint name once the finalize
  API replaces it.

## Accepted Defaults

- Workstream default pre-submit checks include packet shape, artifact manifest
  presence, artifact hash validation, storage reference safety, forbidden
  artifact blocking, required artifact presence, required evidence presence,
  worker attestation validation, and low-quality/generated artifact warnings.
- Workstream default hard rules require production hashes shaped as
  `sha256:<64 lowercase hex>` with `sha256` as the platform-locked artifact
  hash algorithm, safe relative artifact paths, no absolute paths,
  no traversal paths, no raw signed URLs, no query-string storage refs, no local
  filesystem paths, no credential/token-bearing refs, and no default-forbidden
  artifacts such as `.env`, `.git`, private keys, secrets, tokens, and
  `node_modules`.

## Remaining Human Review Focus

- Final review of persisted provenance field names for guide sufficiency
  reports, project submission artifact policies, effective project submission artifact policy hashes, and
  generated project pre-submit checker compiled bundle hashes.
- Confirm the next chunk contract before resuming the real Terminal Benchmark
  drill through the automatic Celery setup path.
- Confirm the visibility/finalize API contract before rerunning the Terminal
  Benchmark drill without DB inspection.
