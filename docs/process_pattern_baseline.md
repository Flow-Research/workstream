# Process Pattern Baseline

## Scope

This file records reusable process patterns observed at metadata level across existing task-operation projects. It does not copy task content, private data, client material, or project-specific deliverables.

The baseline is used only to judge whether Workstream captures the operating model common to serious task evaluation and contribution systems.

## Observed Reusable Pattern

Across projects, the same control structure appears with different names:

```text
Project Guide
-> Queue / Lane Status
-> Task Workspace Record
-> Preflight / Checker Scripts
-> Review Guard
-> Submission Packet
-> Review Packet
-> Evidence / Verification Log
-> Needs Revision Replay
-> Accepted / Rejected
-> Contribution Record
-> Conditional Compensation Award / Fulfillment Status
-> Workflow Lessons
```

## Common Artifacts

### Project Guide

Defines:

- project purpose
- task fit
- quality bar
- required materials
- submission format
- review expectations
- common failure modes

### Queue Status

Tracks:

- draft or screening work
- ready work
- active work
- submitted work
- needs revision
- accepted
- rejected
- compensation fulfillment state

Some projects also use explicit lane capacity rules, such as keeping only one live execution active while preparing future tasks in a ready lane.

### Review Guard

Defines:

- blockers
- major risks
- minor risks
- decision labels
- adversarial review questions
- human-writing quality checks
- returned-feedback replay rules

### Checker Scripts

Common script roles:

- start task
- preflight task
- package submission
- run ready gate
- update queue status
- summarize queue
- validate rubric or review packet
- audit workflow state

### Submission And Review Packets

Packets preserve:

- final deliverable
- required metadata
- evidence
- checker answers
- review notes
- revision history
- packaging status

### Evidence And Lessons

Repeated strong projects keep:

- verification logs
- review-readiness evidence
- workflow lessons
- status histories
- review rounds

This is how local memory becomes reusable process.

## Workstream Implications

Workstream must support:

- versioned project guides
- queue lanes derived from status
- project-specific review guards
- automated checker policies
- review-readiness evidence before review
- submission and review packet records
- revision replay tied to prior findings
- reviewer contribution records created from every valid human review
- submitter contribution records created from accepted evidence-backed work
- lessons learned promoted into guides, checkers, or templates
- compensation fulfillment status separate from task status

## Non-Goals

Workstream does not import or depend on project-specific task content.

The transferable asset is the operating model, not the data.
