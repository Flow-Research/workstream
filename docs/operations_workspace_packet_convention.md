# Workspace And Packet Convention

## Purpose

Each project needs a predictable structure for work, evidence, review, and final submission. This prevents missing files, scattered feedback, and unclear readiness.

Workstream does not need to own the execution workspace, but it must define what a valid task packet looks like.

## Project-Level Convention

Every project has a guide-version policy bundle derived by Workstream from
open-ended project material:

```text
GuideSourceSnapshot
GuideSufficiencyReport
SubmissionArtifactPolicy
EffectiveProjectSubmissionArtifactPolicy
```

Every task then locks the project intake context:

```text
GuideSourceSnapshot
EffectiveProjectSubmissionArtifactPolicy
PreSubmitCheckerPolicy
required_artifacts
required_evidence
allowed_artifact_types
forbidden_artifact_types
artifact_hash_manifest_format
storage_reference_format
paste_ready_or_upload_ready_format
review_packet_format
revision_packet_format
```

## Recommended Task Packet Shape

```text
task/
  task.md
  acceptance_criteria.md
  submission/
    summary.md
    artifacts/
    evidence/
    checker_results/
  review/
    review_packet.md
    findings.md
  revision/
    prior_feedback_checklist.md
    revision_replay.md
  contribution/
    contribution_record.md
  status.md
```

This is a convention, not a required filesystem layout for every project. The product supports the same concepts even when files are uploaded through the UI.

## Packet Readiness

A packet is not ready unless:

- task requirements are present
- acceptance criteria are present
- required output artifacts are attached
- evidence is attached
- artifact hashes are present
- evidence references bind to artifact hashes
- pre-submit checks from the locked project pre-submit checker policy pass before submission creation
- prior feedback is linked when resubmitting
- status is current

## Paste-Ready Or Upload-Ready Standard

Some projects need final work in a paste-ready form. Others need a zip, artifact bundle, markdown packet, or review file.

The project guide explains the canonical form to humans. The approved `SubmissionArtifactPolicy` and persisted `PreSubmitCheckerPolicy` enforce the artifact, evidence, hash, and packaging rules. Project owners do not author or approve this machine policy schema directly.

## Why This Matters

The repeated failure mode across task programs is not only bad work. It is missing packaging, missing evidence, stale feedback, unclear status, and mismatched final artifacts.

The convention makes readiness inspectable.
