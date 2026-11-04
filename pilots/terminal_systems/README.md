# Terminal Systems project setup

Start with [the contributor guide](guide.md) and [one illustrative task](task-example.md).
These are original project inputs for a fresh onboarding run. They are not a
checker implementation, an approved policy or a record of completed work.

## Files to use

- `guide.md`: upload the original Markdown bytes as the project document.
- `guide-request.json`: guide metadata and the illustrative task text in the
  existing public creation schema. Its document declaration does not upload bytes.
- `task-metadata.example.toml`: a copy of the shape example embedded in the
  guide, for authors to replace with their real values. It is not a working
  environment or a measured resource profile.
- `tasks/`: readable versions of the five initial briefs listed below. Their
  complete text is also carried in `tasks.json`.
- `tasks.json`: five authoring briefs in the existing task-import format, for
  import after the project is configured. They are work to assign, not completed
  submission packages or a checker allowlist.

The guide is self-contained when uploaded: its metadata table and example are
included in `guide.md`, without depending on a repository-relative attachment.
`task-example.md` is the queue-recovery brief, also embedded in the guide creation
request. Keep these copies synchronized when editing the inputs.

The guide does not repeat Workstream's platform upload limits. Setup leaves
project size overrides null unless the guide explicitly adds a restriction;
platform upload, archive-safety and storage-admission enforcement always applies.

## Initial work

| Brief | Main behavior the author develops into a solver task |
|---|---|
| [Queue recovery](tasks/queue-recovery.md) | Preserve completed effects and recover interrupted work without duplicating results. |
| [Snapshot restore](tasks/snapshot-restore.md) | Validate snapshot contents and publish a restored tree without damaging the prior destination on failure. |
| [Incremental build](tasks/incremental-build.md) | Rebuild affected dependencies and preserve correct output across failed steps. |
| [Database upgrade](tasks/schema-upgrade.md) | Convert retained records atomically and handle interruption, replay and unsupported versions. |
| [Event correlation](tasks/event-correlation.md) | Produce correct summaries despite duplicates, ties, timezone differences and shuffled records. |

These are original authoring assignments, not five finished benchmark packages.
Contributors must specify the exact interfaces and supply the starting code,
reference and verification. New subjects and identifiers can be added through
normal task creation; no runtime change or checker allowlist is implied.

## Onboard through the public product flow

1. The PM creates the project and guide with its illustrative task example,
   then uploads the declared original document through the public API or CLI.
   Committing the last document upload queues setup. The manager needs a role
   grant on this exact project for setup and proposal reads; project-creation
   authority alone is insufficient.
2. Setup receives the assigned guide documents and task examples, along with
   trusted system instructions. It reads the originals and proposes source-cited,
   structured PRE and POST checks for PM review. Each suggestion has a stage,
   classification rationale, inputs, ordered steps, pass conditions, work
   failure findings, positive and negative examples, implementation needs and
   conditions where evaluation cannot establish a work verdict. The artifact
   policy records source-supported packaging rules. The proposal names no
   checker image, registry entry, model profile or runtime configuration.
   PRE checks run before immutable Submission creation; POST checks evaluate
   submitted work afterward. A task example illustrates possible work and
   does not make its subject or identifiers mandatory for every assignment.
3. The PM reviews the whole proposal against the original guide and tasks.
   If it needs correction, an authorized PM requests a successor with written
   feedback. The correction model receives the original guide and examples
   plus that explicit feedback only. Earlier proposals remain immutable; they
   are not handed back to the model as instructions or selected implementations.
   A finalized attempt cannot be rerun, and a terminal invalid attempt cannot
   be reopened through same-operation replay.
4. Engineering implements and tests project checks in external images, using
   the source-backed suggestions as an advisory handoff. Project logic belongs
   in those images, not in project-named branches of Workstream or its shared
   runner. Use the [image command](../../docs/engineering/checker-images.md)
   for each project-owned implementation. Its default ECR destination names
   are `workstream-checker-pre-terminal-systems` and
   `workstream-checker-post-terminal-systems` in `eu-north-1`, once the operator
   has created the selected repositories. A name here does not prove an image
   exists. An authorized Operator registers exact immutable image/configuration
   entries; the execution host needs the matching digest and cache entry.
   Publication or registration does not change a saved proposal, require fresh
   inference, approve a policy or activate a guide.
5. The PM selects review and revision policies separately. For PRE approval,
   the PM supplies explicit `pre_submit_attachments` and
   `post_submit_attachments` lists with the chosen registered image identities
   and non-secret configuration. These are human phase choices, independent of
   `suggestion_id`; no one-to-one mapping or image membership in the proposal
   is required. Both lists are required, and explicit empty lists are valid.
   Workstream then derives the selected POST policy. The PM reads and approves
   that POST policy in a separate operation. Finance supplies the published
   contribution policy. Activate only after the exact approvals and public
   readiness checks pass. The default ReviewPolicy requires human review;
   disabling it is an explicit PM choice and retains the shared authorized
   acceptance operation.
6. Import the five briefs, screen them against the activated guide, and release
   eligible tasks. A contributor claims a task, which starts work immediately,
   then submits real work through public ZIP intake.
7. Observe the connected journey: default and selected PRE feedback before
   Submission, durable POST evaluation after Submission, and the governed
   outcome. Include genuine failure, recovery and replay. Record exact source,
   guide, policy, image, Submission and contribution facts without editing
   product rows or fabricating evidence.

## Current boundary

The [current hosted drill report](../../docs/reports/terminal-systems-hosted-drill-2026-10-27.md)
records the exact deployment, guide versions, retained evidence and remaining
gates. Setup's source-backed PRE and POST suggestions are advisory. They do not
select implementations, approve policies or establish a work outcome. The PM
and engineering must check that any proposed attachment implements the intended
project rules before the authorized approval locks it.

For this drill, [checker qualification](checkers/README.md#post-prerequisites)
must exercise realistic valid, invalid and edge-case examples through the actual
Workstream intake and post-submission execution paths. Retain each exact image
digest/configuration hash, expected and observed outcomes, and bounded evidence
in the [drill report](../../docs/reports/terminal-systems-hosted-drill-2026-10-27.md).
Infrastructure failure never establishes a work verdict. The PM judges whether
the rules express the intended project standard; engineering proves observed
checker behavior on those examples. That evidence is bounded, not a universal
correctness guarantee. This is required drill practice; activation does not
automatically enforce this example suite.

The project-owned [checker implementation](checkers/README.md) has qualified
PRE and POST images. At the November 4 checkpoint, additive release `0f46f3ea`
selects POST image `4d8de652` built and physically qualified from `24b974b3`,
with backend `466faca5`/schema `0066` unchanged and native PID `2298844`.
Controlled native qualification passed two isolated trials, four controlled model
effects, no additional provider call on replay and owned-service cleanup.

Guide 26 normal setup produced three PRE/six POST advisory suggestions and zero
warnings; actual ART request evidence proves input keys exactly `material` and
`task_examples`. Independent human two PRE/eight POST attachments, separate
approvals, activation and immediate claim into work passed with replay. Selected-PRE
missing-instruction feedback created no Submission and passed replay. A later
package reached verified S3 admission, immutable Submission v1 and exact replay.
POST ended `infrastructure_failed / invalid_output` after nine paid model calls.
Two trial receipts exist, but build export capacity failed and all 17 dependent
work-test steps were skipped. No work verdict, Revision, FinalAcceptance or
ContributionRecord resulted. The pending repair raises the default maximum-entry
limit to 100,000. Only a build with exit code zero, no signal,
`export_outcome=capacity_exceeded` and both candidate image/archive digests null
is classified as infrastructure capacity before assessment. Task-disk-limit and
step-export-capacity results remain assessable. This changes no native contract
and is not deployed or live-proven.

A separate image `52659960` negative capacity probe passed with only plan/profile entries
raised to 100,000: the original 64 MiB archive limit and 2 GiB disk were unchanged.
Its 45,435,904-byte archive matched native custody; ten steps ran and seven skips
were grounded in failed reference verification, with no resource failures. Two
controlled model effects, no extra effects on replay, no paid inference and cleanup
were verified. The first two probe tests remain failed after bounded fixture
custody-count and dependency-skip assertion repairs. Semantic assessment was
disabled: this is neither a live work verdict nor full positive qualification.
Image `52659960` was built from `6af3c7ee` with 125 focused tests; later `e6935430`/`adcf35a5`
fixture repairs remain separately attributed. Separate standard canonical positive
qualification on exact `adcf35a5` passed in 173.08 seconds: two isolated trials,
four controlled model effects, exit zero, no paid inference and zero additional
replay calls. Owned runtime resources and isolated PostgreSQL/MinIO containers
were removed. Fresh immutable profile/image approval and live semantic
acceptance remain unproven; no 256 MiB deployment or production runtime-identity
change is needed for the demonstrated capacity.

Guide 24/25 failures and guide 25's explicit PM-feedback correction remain
immutable. Earlier five default-negative/replay controls created no admission or
Submission; the size case proves compression ratio only. Exact source `942aa11a`
passed CI with 11,528 tests, excluding the pending repair. Live work verdicts,
recovery and exact contribution evidence remain pending. This input package and
its controlled image qualification do not claim a complete hosted journey; use
the linked report for source pins, timestamped accounting and historical scope.

The inference runtime derives suggestions from this original guide and its
example. The separate [manager-authored rules runtime](../../docs/operations_project_operating_manual.md#manager-authored-guide-rules)
accepts a PM-supplied rules document without inference; these inputs do not
provide one. The PM still chooses compensation, review mode, revision limits
and timing through their separate governed operations. The input version label
alone does not publish or replace a live guide.

The work remains tracked by [project preparation #576](https://github.com/Flow-Research/workstream/issues/576)
and [the connected journey #555](https://github.com/Flow-Research/workstream/issues/555).
