# Process Pattern Baseline Review

Review scope: metadata-level inspection only under `/home/abiorh/snorkel`. No task content copied.

Projects inspected: Sequoia, Geranium, Excalibur, Marlin, Termius.

## Baseline Patterns Observed

- Project-level guides are the operating law.
- Queues and status files separate intake, active work, ready work, review, and completed states.
- Review guards exist independently of submission checklists.
- Submission checklists appear before "ready" decisions.
- Task workspace conventions define required files and paste-ready or submission-ready structure.
- Evidence folders, platform reviews, checker logs, review packets, and status files repeat per task.
- Reviewer-side work has review packets, prior feedback checklists, status files, and sometimes second-pass reviews.
- Some projects include explicit reviewer simulation or adversarial gates before final readiness.
- Lessons and failure-mode documents are used to update workflow after repeated misses.

## Findings

### High: Workstream needs an explicit Workspace/Packet Convention module

Workstream has submission packet templates, but the baseline shows each project needs a directory or packet convention before work starts. This prevents inconsistent evidence placement and missing ready artifacts.

Suggested change: add an operations doc for project workspace conventions and add it to the roadmap/templates.

### High: Workstream needs a pre-review simulation gate

Geranium and Sequoia patterns show review guard plus adversarial/reviewer simulation before calling work ready. Workstream has subagent review protocol but not a productized gate in the lifecycle.

Suggested change: add `pre_review_gate` as an optional checker phase before `REVIEW_PENDING`, and add reviewer simulation to checker policy/project templates.

Update: Workstream now has a `SCREENING` lifecycle state before `READY` and a post-submission `pre_review_gate` checker phase that runs while the persisted task status is `AUTO_CHECKING`. This captures the same reusable pattern without adding another post-submission task state.

### Medium: Lessons learned should be first-class

The baseline has workflow lessons, failure modes, and writing risk signals. Workstream mentions lessons learned but lacks a concrete record type or cadence.

Suggested change: add `LessonRecord` or project lessons log to the domain model and operator workflow.

### Medium: Status dashboard should include queue lanes, not only task statuses

Baseline queues distinguish intake, active, ready, screening, done, and review. Workstream statuses are good, but queue lanes should be configurable per project for operator views.

Suggested change: add queue lane policy to project configuration and dashboard requirements.

Update: Queue policy now includes `SCREENING`, and the task status template makes a human-readable snapshot standard.

### Low: Templates should include prior-feedback checklist

Reviewer-side work repeatedly uses prior feedback checklists. Workstream has revision replay but should also provide a template for prior feedback before starting a revision.

Suggested change: add `prior_feedback_checklist_template.md`.

Update: This template exists and is linked from the README.

### Medium: Preflight evidence should remain separate from final submission evidence

Finding: Baseline projects often preserve preflight evidence separately from final artifacts. This avoids confusing "we checked readiness" with "the submitted work passed final verification."

Suggested change: keep `PreflightEvidence` as a separate record type or artifact class, and show it on task/review pages separately from final submission evidence.

Update: `preflight_evidence_template.md` exists. Implementation should preserve this distinction in the data model/UI.
