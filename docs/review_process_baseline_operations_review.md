# Process Baseline Operations Review

Reviewer role: Operations and Review Workflow Reviewer.

Scope:

- markdown docs in `<repo-root>`
- metadata-level process patterns under `local reference workspace`
- no task content, private data, or confidential project details copied

## Findings

### High: Workstream needed a documented process-pattern baseline

Finding:

The plan described the reusable lifecycle, but did not explicitly record the cross-project baseline: project guides, queue/status files, review guards, checker scripts, submission packets, evidence logs, revision replay, and workflow lessons.

Suggested change:

Add a baseline document that captures metadata-level reusable patterns and makes clear that Workstream transfers operating model only, not project data.

Status: fixed in `docs/process_pattern_baseline.md`.

### High: Ready work needed a screening gate before contributors see it

Finding:

The reference evaluation projects often have review guards, simulation gates, or screening lanes before work is treated as ready. Workstream would break in daily use if weak tasks went straight from draft to ready.

Suggested change:

Keep `SCREENING` as a real lifecycle state and require a ready gate before `READY`.

Status: fixed in `docs/architecture_lifecycle_state_machine.md`, `docs/operations_project_operating_manual.md`, and `docs/operations_queue_policy.md`.

### High: Preflight evidence needed to be first-class

Finding:

Existing projects repeatedly preserve preflight/checker evidence. Workstream had evidence generally, but needed a specific preflight record that reviewers can trust before review.

Suggested change:

Add a preflight evidence template and later checker support after the readiness/pre-review record shape is locked.

Status: fixed in `docs/template_preflight_evidence.md` and `docs/architecture_checker_framework.md`.

### Medium: Lane capacity rules needed to be explicit

Finding:

Queue health is not just status count. A lane can look organized while review
pending, active work, or authorized but unfulfilled awards quietly pile up.

Suggested change:

Define lane capacity defaults and daily queue review metrics.

Status: fixed in `docs/operations_queue_policy.md`.

### Medium: Reviewer simulation should exist before first-of-kind tasks are released

Finding:

Reference review-guard-heavy workflows show the value of pretending to reject the task before release. Workstream needed this as an operational gate.

Suggested change:

Add reviewer simulation gate for high-value and first-of-kind tasks.

Status: fixed in `docs/operations_project_operating_manual.md`, `docs/operations_subagent_review_protocol.md`, and `docs/roadmap_implementation_backlog.md`.

### Medium: Lessons learned needed action ownership

Finding:

Workflow lessons are useful only if they become guide, checker, template, or policy updates.

Suggested change:

Require each lesson to have an owner and target action.

Status: fixed in `docs/operations_project_operating_manual.md`.
