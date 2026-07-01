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
- `evidence_policy`, `required_files`, and `required_evidence` are transitional
  fields to replace, not compatibility contracts to preserve.

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
- Final confirmation that Chunk 1 implements records/contracts/activation guard
  only, while full async agent execution comes later.
