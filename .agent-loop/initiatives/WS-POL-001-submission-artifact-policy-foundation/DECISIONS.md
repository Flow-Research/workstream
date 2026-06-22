# Decisions: WS-POL-001 - Submission Artifact Policy Foundation

## Accepted

- `ProjectGuide` remains human-facing instruction.
- `SubmissionArtifactPolicy` is the machine-readable intake contract.
- Project owners provide project setup material in plain language;
  they do not author `SubmissionArtifactPolicy` directly.
- Workstream derives `ProjectSubmissionArtifactPolicy` from project material,
  with internal agent assistance allowed, then requires approval by `admin` or
  `project_manager` before guide activation.
- Workstream default submission artifact rules are non-bypassable.
- `EffectiveSubmissionArtifactPolicy` is default plus project policy.
- `PreSubmitCheckerPolicy` is generated from effective policy.
- Pre-submit checks block before submission creation.
- Blocking pre-submit feedback is `pre_submission_checker_failed` with
  structured pass/fail/warning details; it is not `accept`, `needs_revision`,
  or `reject`.
- Post-submit/internal checks remain separate from pre-submit checks.
- Worker-facing task outcomes remain simple; internal routes stay internal.
- Stored review decision values remain exactly `accept`, `needs_revision`, and
  `reject`. Display wording must not create new persisted tokens.

## Pending Human Decisions

- Exact default Workstream submission artifact policy fields.
- Exact v0.1 project-owner intake checklist for deriving project policy.
- Whether generated pre-submit policy is persisted or derived on demand.
- Exact names for locked submission artifact policy version/hash fields.
- Compatibility plan for `ProjectGuide.evidence_policy`.
- Compatibility plan for task `required_files` and `required_evidence`.
