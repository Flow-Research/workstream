# Decisions: WS-POL-001 - Submission Artifact Policy Foundation

## Accepted

- `ProjectGuide` remains human-facing instruction.
- `SubmissionArtifactPolicy` is the machine-readable intake contract.
- Workstream default submission artifact rules are non-bypassable.
- `EffectiveSubmissionArtifactPolicy` is default plus project policy.
- `PreSubmitCheckerPolicy` is generated from effective policy.
- Pre-submit checks block before submission creation.
- Post-submit/internal checks remain separate from pre-submit checks.
- Worker-facing task outcomes remain simple; internal routes stay internal.
- Stored review decision values remain exactly `accept`, `needs_revision`, and
  `reject`. Display wording must not create new persisted tokens.

## Pending Human Decisions

- Exact default Workstream submission artifact policy fields.
- Whether generated pre-submit policy is persisted or derived on demand.
- Exact names for locked submission artifact policy version/hash fields.
- Compatibility plan for `ProjectGuide.evidence_policy`.
- Compatibility plan for task `required_files` and `required_evidence`.
