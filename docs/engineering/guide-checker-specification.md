# Guide setup: PRE and POST specification contract

Setup translates the assigned guide documents and task examples into check
specifications. The initial model prompt contains only that project material,
apart from trusted system instructions. Registry inventory, image choices,
runtime availability and lifecycle policy are not model inputs.
It does not recommend review mode, revision caps or windows, deadlines, assignments,
compensation or routing. The PM configures those through the existing policy paths.
Administrative guide clauses are outside the checker inventory.

## Inputs and authority

| Input | Meaning |
| --- | --- |
| Document manifest | Exact authorized originals, opaque read handles and evidence identities. The agent must actually read them. |
| Task examples | Illustrations of the project, never a task allowlist or completed submission. |
| Instructions | Snapshotted scope, format, complete synthetic output example and constraints. |

Only assigned originals are accessible. Same-run structured-output repair may
receive bounded validation errors; it cannot add project configuration sources.
Missing implementation does not block a source-sufficient proposal.
Missing PM policy choices do not block specification. A guide with no additional
checkable work obligations does not need fabricated requirements; source coverage
and guide sufficiency still require validation.

## PRE and POST

PRE is intake work before Submission creation. POST is background evaluation
of an immutable Submission; model judgments always belong here. Split file
presence from semantic content,
and documentary assessment from actual execution. A model reading a claimed run
cannot prove that the run happened. Describe needed inputs and implementation
without claiming any available registry image, profile or runner.

The Workstream default remains independent: ZIP safety, verified bytes/manifest,
high-confidence secrets and unchanged-work detection. Unspecified project upload
limits stay null; the platform ceilings still apply. Summary and attestation remain
warning-only. The agent cannot change those defaults.

## Exact output

One JSON object, with no surrounding prose or Markdown, duplicate keys, unknown
fields, nonfinite numbers or omitted schema-required members. Optional setup
notes remain bounded prose; they cannot carry executable selections.

| Field | Purpose |
| --- | --- |
| `status`, `findings` | Whether the guide is sufficient to specify checks; source-linked blockers or warnings. |
| `submission_artifact_policy` | Guide-derived artifact requirements and explicit size overrides, or null for a blocked guide. |
| `requirements` | Source-cited PRE/POST suggestions with stable proposal-local `suggestion_id`, reason and complete specification. |
| `setup_notes` | Brief operator-facing facts about deriving checks; no executable choices. |
| `agent_name`, `agent_version`, `schema_version` | Exact protocol and supplied runtime identity. |

A check specification states its proposed method in plain language, inputs,
ordered steps, observable pass/fail conditions, work findings, positive and
negative implementation examples and natural-language implementation needs.
It distinguishes inability to evaluate from failed contributor work. The
`suggestion_id` identifies a proposal member; it is not a registered image or
the human-execution `requirement_id` used by the external checker protocol.
Missing implementation alone does not create a guide blocker or warning.

The complete [synthetic example](../../backend/app/core/project_guide_instructions.py)
contains a report-file PRE suggestion and a POST assessment of whether report
conclusions follow its observations. It names no registered implementation.
Its identities and suggestions must never be copied into a real project. Tests
validate the example against the exact provider schema and canonical checks;
the serialized example is part of the instruction snapshot/hash.

## Engineering and approval handoff

PM and engineering decide which suggestions require implementation. Engineering
implements, tests, pushes to ECR and registers exact external checker images.
An authorized Project Manager attaches explicit `pre_submit_attachments` and
`post_submit_attachments` lists with exact registered images and non-secret
configuration during policy approval. Empty lists express valid human intent.
Attachments are phase choices, not a one-to-one mapping from suggestions: an
image may cover several suggestions and a phase may use several images. The
Workstream PRE default stays separate. Approval retains the exact lists, binds
them to authorization and replay, and locks image digests and configuration.
Registration after the proposal does not change its hash or require a new setup
run. POST projection consumes the approved locked POST policy. Registry
publication alone grants no project execution authority. Both phase attachment
lists must be present; explicit empty lists are valid and suggestions impose no
image-membership requirement.

## Rejection and correction

Both private drafting and independent source review enforce the restricted schema
and canonical/context rules. Known invalid completed output receives bounded paths
and closed error codes and may be corrected at most twice in each drafting or source-review phase, within
the original shared attempt budget.
The agent returns a complete replacement, not a patch. No rejected values or raw
exception messages are put in feedback. Unknown provider failures are not replayed
as format errors. Corrections do not reset time, turn/tool budgets, source access,
circuit admission or cleanup. Exhaustion returns invalid output without a proposal.

The successful review phase must independently reopen the assigned originals.
Schema validity cannot prove that every natural-language assertion is correct;
source review and PM review remain necessary. Historical stored proposals are not
rewritten. Manager-authored input follows the same specification-only result
contract without inference. Optional or configurable automatic setup is deferred.
