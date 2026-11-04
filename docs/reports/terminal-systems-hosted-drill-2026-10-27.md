# Terminal Systems hosted first-journey drill — 2026-10-27

**November 4: the small hosted task reached automatic acceptance and a publicly readable submitter contribution. Final replay/recovery reconciliation and PR verification remain in progress.**

## Retained guide 27 deployment and model failure

The preceding committed deployment retained backend source
`466faca5e0e7e4c640c2f94e4472562618f1da71` and schema
`0066_guide_check_specification`, at release
`sha256:6ec9fb8dc7ab96103ab227a0e875c4bbb4b39cc1da0209a4784a18ad7e4b3856`;
active-marker SHA-256 is
`6d8b6b844fe6a51db0c532106794159b46b32445cbb967f17e6fe802b6b900c2`.
POST image `sha256:526599603d1429f08b6fc6d5f9ad1dcf27c2cc801dc0f5650e28e2335ec45e69`
was built from `6af3c7ee` and qualified on `adcf35a5`. The unchanged native binary
now runs as PID `2633053`. Trial profile version 2 permits 100,000 entries while
the original 64 MiB archive limit and runtime identity remain unchanged.

Eight new immutable registrations passed public publication, GET and exact replay;
two cache files were sealed and service-read verified. The resulting 82 registry
rows, 30 authority contexts and 13 cache entries preserve all predecessors.
Canonical AWS proof, five-service health and the retained-data cutoff passed
before commit, with no migration or row reset. Two earlier commit checks held
while timer proof was running; both remain retained, and commit passed only after
the proof settled. No guard was bypassed and no paid inference occurred during
this repair/deployment. Guide 27 subsequently completed setup, separate approvals,
activation, task creation/screening/release and claim. Claim immediately returned
`in_progress`. Negative PRE and replay created no Submission; positive PRE,
S3 verification and exact Submission replay passed for Submission
`01a1a523-827d-74de-ac81-bc4917a912e0`.

Automatic POST run `01a1a523-86de-7a15-ae40-d213fba1db57` reached
`infrastructure_failed / implementation_unavailable`. Verified private ART
response evidence identifies a known incomplete materials-check model response:
all 8,192 output tokens were reasoning, with no final answer. This is not
contributor failure. Public Operator recovery authorized one child attempt and
successor run `01a1a530-69ab-7624-8f7f-bc88d4abb1ba`, generation 2; the successor
also failed with an incomplete model response. Both failures remain retained;
neither is evidence of contributor failure or acceptance.

Exact source `a4afa8d75` hosted Backend run `41776758402` passed. Independent
artifact reconciliation found 11,533 unique completed tests, matching collection
and the full manifest, with zero skips/deselections and completed cleanup. The
tested merge tree equals the PR tree; this evidence does not cover later edits.
The timing target was not met. No complete hosted journey pass is claimed.

## Current MVP scope — incident summary task

The user narrowed the demonstration to a small realistic task rather than a
complete benchmark-authoring evaluator. The [incident summary pilot](../../pilots/terminal_systems/mvp/README.md)
keeps the real guide, public APIs, S3 custody, durable workers, external checker
execution and governed outcomes. Its PRE checks required-file shape; its POST
independently counts a fixed event log and rejects incorrect reports. POST uses
no model and executes no submitted code. This does not prove general benchmark
quality evaluation.

Guide 28 completed real source-only setup with two PRE suggestions and one POST
suggestion. The manager selected one implementation per phase; suggestions do
not determine image identities. Both immutable registrations passed read/replay.
The image built from `4e481e5f5` passed six packaged tests, including actual
wrong/correct counts, changed input and malformed/missing PRE files. A first
packaged test run exposed a read-only copied fixture; `0d60241ce` repairs only
the fixture copy and adds the malformed-input proof. The checker image is
unchanged.

The supplemental runtime used for the accepted task was committed at release
`sha256:ee22e22e8236d5990418a43a856388a395458ed40fc497f4dd6dcdcac223f940`,
marker `1e0dc836cc94f2e9d97dc8cf093269828ba3bcdb8faf718accd1746801da3423`.
Backend source and schema remain unchanged. Canonical AWS proof, application
health and retained-data checks passed. Image
`sha256:4e5b9c71e5772f3b195ce36115eb1077c98c67932d92c0fe45ede31d764beebb`
runs the external PRE and POST checks without model access.

Public task `01a1a544-7a9b-7393-8ba0-666859e1e805` was created, screened,
released and claimed. Claim immediately returned `in_progress`. A missing-summary
ZIP failed PRE with 422, including replay, and created no Submission. A
structurally valid but incorrect report passed PRE and S3 verification, creating
Submission v1 `01a1a552-6e0b-7332-b956-bf271e84abd7`. Exact submission replay
returned the same identity. Automatic external POST completed with one blocking
`incident_summary_counts` finding at `summary.json`; the Submission became
`needs_revision` with a ready public revision context. Public history uses
sanitized status text, check identity and file location; it does not expose the
checker's arbitrary message text.

The correction recounts the unchanged source events. Its verified archive is
`sha256:ea08202a67100ac5b574d73df5e3d7430511bd28bd8eb8cf8c7a1f7fdf4f023c`.
Public intake created Submission v2 `01a1a55b-867f-715d-ae36-563cb64877dd`,
linked to v1 and the retained feedback. Exact replay preserved its submission,
admission and evaluation-request identities. Automatic POST completed with no
blocking findings. The task became `accepted` at `2026-11-04T07:01:51.970834Z`.
FinalAcceptance `01a1a55d-36b2-7d82-8bc2-9633f55332e0` records
`task_post_submit_route`, immutable AUTH evidence and routing manifest
`01a1a55d-36a1-7894-8f34-ced6e0d2544e`. ContributionRecord
`01a1a55d-36fb-73d5-b078-d6c165db95b5` binds that acceptance, v2, the exact
archive hash, assignment and locked ContributionPolicy version.

Independent public contributor and manager exports returned identical records.
A read-only consistent database snapshot confirmed one acceptance, one submitter
contribution, no Review and no reviewer contribution for this task. The locked
policy is unpaid: no compensation award applies, and none was created. This
exercise does not prove a paid award or payment delivery. Project model spend
remains $8.917426660 settled and $0 reserved, within the additional $10 cap;
the incident-summary POST made no model call.

Guide 27's model-based POST and its single authorized retry both exhausted their
8,192-token output allowance without an answer. Both are retained infrastructure
failures, not contributor failures. Exact POST retry replay returned the same
generation 2. Recreating its already-dispatched paid child returned the intended
409 superseded-parent conflict; no additional child was created. No further retry
of that locked profile is planned.

## Final-data restore diagnostic — November 4

A snapshot-consistent custom backup of the actual pilot database retained all
134 public tables, including accepted v2 and its contribution. The ordinary
isolated restore failed: existing CHECK validators depended on the caller's
search path. The observed sequence exposed the canonical JSON helper, the
outbox outcome validator, and two project-role reference validators. This is a
restore defect, not loss of or a change to the live accepted outcome.

Using the same retained backup, an isolated diagnostic bound those four
functions to their existing owners before loading data. All 134 table row counts
and digests then matched the source snapshot, including the exact acceptance and
contribution linkage. No validator was disabled; each temporary container used
no network and was removed. The diagnostic is **not** an ordinary restore pass.
The diagnostic did not modify the live database. Forward migration
`0067_canonical_json_restore_path` subsequently passed on the drill database;
the migration comparison preserved every business row. A fresh 8,071,378-byte
snapshot-consistent backup then passed ordinary `pg_restore --exit-on-error`
into a network-isolated PostgreSQL container, without special SQL patches or
disabled guards. All 134 table counts and digests matched, including the exact
FinalAcceptance and ContributionRecord linkage. The temporary container was
removed. Private proof fingerprint:
`sha256:5e8f730d381f4e83738e4d381c880a7bdee0a9f454b7aa98eee2db18f74c10af`.
This proves database restoration; it does not replace S3 custody or the remaining
worker-interruption proofs.

The repaired backend was deployed from `1b947dfe2819ad9d66d265e9aa1383900eb0dbbd`
at release `sha256:26591f3e5021b2c3a7f1a8af77688d8384a4a140e57ab7f1732576e116ccfb6b`.
The API and durable workers drained before the migration. All retained business
rows matched through the pre-resumption cutoff; the three exact pending notices
were preserved, not deleted or marked delivered. Canonical AWS proof passed,
all five application services returned healthy, and scheduled work resumed.
The native checker process and external image remained unchanged. After restart,
public contributor and manager exports still matched the original accepted
record exactly; Submission and checker history reads returned 200. Public-read
proof fingerprint:
`sha256:7670a58982c863cca4156105e96cccbb758bc499a900371b8973910aad19abb4`.
This is a controlled drain/restart proof, not an abrupt-worker-loss proof.

## Retained guide 26 checkpoint and repair qualification — November 4

Guide 26 ran with backend source `466faca5e0e7e4c640c2f94e4472562618f1da71`,
schema `0066_guide_check_specification`, release
`sha256:0f46f3ea112a3e510a318fbb67af5ff9e3979a5314ef0437fc3e54c198fe8c21`;
active-marker SHA-256 is
`4dbaf553b80b753994257f73ef02d227629ca2bf2d4b8a4c2edf3ea8bf812129`.
That additive image rollout passed all 13 phases, including canonical AWS proof,
the retained-data cutoff, five-service health and controlled Beat resumption.
It retained the native binary and restarted it as PID `2298844`; schema and backend
remained unchanged. No migration, database reset or retained-data rewrite occurred.
Seventy-four registrations, 27 authority bindings and 12 cache entries preserve
predecessors. POST image
`sha256:4d8de652b72418fbb98bc0e4580b6ea8c1edc12c113287b0480625cb2d665c2c`
was built and qualified from source `24b974b3de46a50ba7eafbe4854b166d58050c87`,
distinct from backend source `466faca5`. Controlled native qualification passed
two isolated trials, four controlled model effects, no additional provider call
on replay and owned-service cleanup. Its earlier capacity failure remains
retained; this controlled pass is separate from the real-project outcome below.

Guide `01a1a465-0329-76ce-85ef-03094ae6d626` completed normal setup with
three PRE/six POST advisory suggestions and zero warnings. Independently verified
ART evidence binds the actual outbound request to the unchanged original guide
and task example, with input keys exactly `material` and `task_examples`.
The PM independently selected two PRE/eight POST attachments; separate approvals,
activation generation 2 and exact replays passed. Task
`01a1a46b-1f50-733c-b31d-9795cf026444` passed create/screen/release/claim
and replays; claim immediately starts work as `in_progress`. The selected-PRE
negative returned missing-`instruction.md` feedback without a Submission and
passed replay. A later package reached verified S3 admission
`01a1a46e-8951-7d51-abca-ea2ea76abb0f`, immutable Submission v1
`01a1a470-08a1-7afc-a7ff-55ffabdc2a19` and exact replay.

Automatic POST run `01a1a470-0cc2-78c4-8343-cf197d843ef9` ended
`infrastructure_failed / invalid_output` at 02:49:38 UTC after nine paid model
calls costing US$0.133162800. Two distinct trial receipts exist, but the actual
builder exit code was zero with export `capacity_exceeded`/`disk_exceeded`, no
candidate image/archive digest, and all 17 dependent test steps skipped. Those
receipts do not prove completed work tests or a contributor work failure. The
Submission remains `evaluation_pending`, with no work verdict, Revision,
FinalAcceptance or ContributionRecord.

The node's candidate archive limit is 64 MiB; the selected trial profile permits
20,000 entries and 2 GiB disk. Read-only immutable Python-base analysis establishes
a lower bound of 36,596 charged path components, not the actual candidate archive
or a direct observation of the original failing branch. The controlled capacity
probe below resolves the required limits for that retained package/plan; no host
free-space cause is claimed for the live project trial. The repair now deployed above raises the
default maximum-entry limit to 100,000. Only a build with exit code zero, no signal,
`export_outcome=capacity_exceeded` and both candidate image/archive digests null
is classified as infrastructure capacity before assessment. Task-disk-limit and
step-export-capacity results remain assessable. This changes no native contract
and does not establish a live work verdict.
Guide 25's earlier infrastructure failure remains immutable.

A separate controlled negative-package capacity probe passed on retry2 in
191.87 seconds. With the original 64 MiB node archive limit and 2 GiB trial disk
unchanged, raising only plan/profile entries from 20,000 to 100,000 exported a
45,435,904-byte archive whose hash matched the native receipt. Ten of 17 steps
ran; seven dependency skips trace through the canonical state graph to the
nonzero `reference_verify_3` work result. There were no resource failures or
unexplained skips. Two controlled model-ledger effects were retained, replay added
zero effects, no paid inference ran, and native cleanup was confirmed. Semantic
assessment was deliberately disabled; the probe's outer infrastructure outcome
is not a live work verdict, acceptance or full positive image qualification.

Both preceding probe tests remain failed and retained. The first exposed a
fixture's fixed two-trial custody assumption for this one-requirement case;
source `e6935430` makes that count follow the selected requirements. Retry1
exported the same-size archive under 256 MiB but its assertion incorrectly counted
seven grounded work-dependency skips as resource failures. The repaired graph
check rejects unexplained/resource-caused skips; retry2 passed with the original
64 MiB limit. No 256 MiB deployment or production runtime-identity change is
required by this bounded capacity result. A new immutable 100,000-entry profile
and prospective image approval still remain necessary.

Repair source `6af3c7ee80f3463140a850767bfee5477955f661` passed 125 focused
tests and built image
`sha256:526599603d1429f08b6fc6d5f9ad1dcf27c2cc801dc0f5650e28e2335ec45e69`.
The probe used fixture source `e69354301b8353135e991147244f837b2b9dbc31`;
`adcf35a5e80f0685091fa6a81d1bfdc6e1b5f36d` additionally aligns the canonical
positive fixture profile with 100,000 entries. The separate standard canonical
positive qualification on that exact `adcf35a5` source now passed: one test in
173.08 seconds, exit zero, two isolated trials and four controlled model effects,
with no paid inference. Its `evidence-result.json` SHA-256 is
`9819e2f33bd78e35c8b76277cd4460547f47274540c51daccd40c32319022cbc`.
The final fixture receipt confirms zero additional replay calls and removed owned
runtime resources; the captured PostgreSQL/MinIO cleanup receipt confirms removal
of only the owned containers. Both qualification and cleanup are complete. This
is controlled qualification, separate from the later deployment recorded above
and unproven live semantic acceptance. None of these sources is certified by the
earlier `942aa11a` CI aggregate. Guide 26's locked image/profile, Submission,
failure and timestamped account below remain unchanged. Private retry2 summary SHA-256:
`3f28de15e4f92f2a9aa2e7fc4a1335eaf217ad060d645a31c96a9ba1c303dfe1`.

At **02:52:03 UTC on November 4**, read-only accounting records the unchanged
US$10 ceiling with **US$8.757024460 settled, zero reserved and US$1.242975540
remaining** (8,757,024,460 / 0 / 1,242,975,540 nanodollars). This is a timestamped
ledger observation, not provider-invoice reconciliation or new spending authority.

Exact source `942aa11a6db1859da52646362120e9a6504dd808` passed backend CI
[41753798837](https://github.com/Flow-Research/workstream/actions/runs/41753798837):
11,528 unique tests across 17 lanes, zero skips/deselections and complete cleanup,
independently reconciled to its tested merge tree. This pass does not cover the
later checker/fixture sources described above; fresh aggregate verification and
live guide 27 approval/execution remain required; current `a4afa8d75` CI is pending.

Private bounded receipts: guide 26 activation/task/intake/Submission journals and
`after-post-budget.private.json`; accounting
`independent-evidence-verification.json` (SHA-256
`06ff34fce44c015053baf9d28d18ab360559f26c7b02cfc3da69eb8f3c772415`);
and diagnostic `offline-repro-24b974b3/FROZEN-MANIFEST.json` (SHA-256
`d28af5b4ec3fd5bf71413568fab45f416b7f8f5d8f0af6fb33144d4a22f19d6d`).
Raw model documents and provider material remain private.

## Retained guide 24–25 checkpoints

The following observations retain their original deployment, accounting and
failure cutoffs; the guide 26 section above supplies the current selection.

Guide 24 `01a1a337-4ca2-71bc-b0c3-d7067c8d159d` uses the same original guide
bytes and task example. Generation 1 produced a `draft_ready` proposal with
three PRE and five POST suggestions. Explicit PM corrections produced generation
2 with two PRE and five POST suggestions, then a final source-agreed generation
3 with two PRE and six POST advisory suggestions. Generation 3 result is
`sha256:7c4b6e69ca3f758435f4a18fa30c4f800ef5d66ccc6476d4bbe6887ae441a8c7`;
its `forbidden_artifacts` list is empty. The PM's content-filename objection is
resolved in that final proposal. Setup did not choose images or require one image
per suggestion.

Actual ART-verified request evidence confirms initial setup's user input keys
were exactly `material` and `task_examples`; explicit corrections added only
`manager_feedback`. The original document identity, hash, bytes and example
were unchanged, with fresh scoped document handles per attempt. Trusted system
instructions supplied exact `agent_version=v1`. No image, registry or
prior-proposal metadata reached the model. This live guide 24 result verifies
the strict output-version repair after guide 23's terminal failure.

The authorized PM independently selected two PRE and eight POST image
attachments. Separate PRE and POST approvals and their exact replays passed.
Activation operation `01a1a355-9c94-7127-ad6e-246606a7ee9f` selected the
approved policies at generation 2 and passed replay. New task
`01a1a357-3d30-78d7-8c50-0abc1f8a763e` and assignment
`01a1a358-2c7c-7885-99f9-b2bdbc7d47b9` were claimed into `in_progress`
with exact replay. Public reads prove the older task retains guide 19 while
this new task locks guide 24.

A PRE-negative package returned 422 because root `instruction.md` was absent;
exact replay returned the same feedback. The complete PM project collection
showed zero Submissions for the task before valid intake. A valid structural ZIP
then passed selected PRE and S3 verification, yielding ready admission
`01a1a360-4c79-72f0-9000-3e01ed5f3c2f`. It created immutable Submission v1
`01a1a366-7d06-7b7c-b5cc-cf2d9cfbeb9a` and evaluation request
`01a1a366-80b8-73c9-ac28-8f28125cd06f`. Exact Submission replay returned
201 with the same identities. Automatic POST run
`01a1a366-815c-7e5e-b013-2a6013cbaa66` was created at 21:52:45 UTC and ended
`infrastructure_failed`. The Submission remains `evaluation_pending`, with
zero work findings and no Revision. Offline inspection of the retained checker
plans found invalid `source_quote` indices 1, 2 and 3. One correction named only
the first; the next plan fixed that quote but left indices 2 and 3 invalid, so
the strict validator rejected index 2. Replacing only those invalid quotes with
unique verbatim source command lines lets both otherwise unchanged plans pass
the same validator. No trial ran and no work failure was found. The two completed
model calls cost US$0.0156745. The repaired checker now reports all independent
citation failures in its single bounded correction; strict source validation
and the two-call limit remain. All 119 external-checker model tests pass,
including a three-error regression.

The repaired image
`sha256:e1408460fe3d6ec329123570d216b3dd6ad959d3463b31310f315bc67550ef40`
was built from `e19084276416a5d9305104fe5979ed46ab7c7792` and passed
controlled image qualification. An initial physical qualification failed during
collection because its fixture imported removed setup catalogue contracts;
that failed evidence is retained. The repaired fixture separates advisory
specifications from explicit human attachments, and existing backend preflight
now collects both canonical native fixtures. Actual native qualification on
`a05c962fc25a2b398ddcd52f74c494305096de16` then passed with two isolated
trials, four controlled model effects, zero additional provider calls on replay
and complete owned runtime, PostgreSQL and MinIO cleanup. That controlled
qualification made no paid provider calls and establishes no complete project journey.

Eight new immutable `real-e1908427` POST registrations passed public POST,
GET and exact replay. The image entered deployment through additive release
`sha256:bb6afea7062b8312403b716baa848131de2a5c6f5025e1217648a8dcffbd24f9`
and stayed selected through the later backend-only release `79e84fa5`;
the current `24b974b3` image selection is recorded above. Predecessor images,
registrations and guide 24's locked policies and failed run remain intact.
Backend source `466faca5` is distinct from POST image source `e1908427` and
native-qualification source `a05c962f`.

Fresh guide 25 `01a1a3b4-7b5c-744f-86cc-f35a7c5c4f23` completed normal
setup and one explicit PM-feedback correction. Its corrected `draft_ready`
proposal contains two PRE and seven POST advisory suggestions, result
`sha256:90bbbe1a46e40617cbb103384f73759d907a3ba82193d59c6ef8108c4cbf40a9`.
Read-only inspection verified the actual retained outbound S3 request bytes:
initial user input keys are exactly `material` and `task_examples`; correction
adds only `manager_feedback`. Original document identities, hashes, bytes and
examples match, while run-scoped handles and manifests bind distinct attempts.
No registry or image metadata entered either input. The explicit feedback
already distinguishes objective PRE intake from qualitative/model POST work
evaluation. The subsequent `466faca5` deployment includes the general prompt
clarification; no new setup inference is credited to that deployment.

The PM independently selected two unchanged PRE and eight new POST attachments;
POST policy readback matches the exact qualified `e1408460` image entries. Separate approvals
and replays passed. Activation `01a1a3c6-706c-7cb6-9841-4d2ef2d845fa`
selected generation 2. Task `01a1a3c6-9038-7324-91d3-af56e0a9dcaa`
passed creation, screening, release and claim, including exact replays;
assignment `01a1a3c6-fa27-7b43-b2d4-05eb38846af6` is `active`, and the task is `in_progress`.
Claim starts work atomically; there is no separate Start operation.

Guide 25's first unsafe-traversal control originally stopped before intake POST:
strict public work-context JSON found omitted required nullable fields, and its
write journal remained empty. Earlier private-reader normalization was an
observer accommodation, not proof that the advertised TASK wire contract was
valid. The deployed repair preserves required-nullable output in four reads and
manager commands, with a closed public claim projection and unchanged internal
replay custody. A fresh raw public context now passes strict JSON validation and
identifies the same task/assignment; at that pre-intake read the complete PM
project collection confirmed zero Submissions for the task.

All five default-negative cases and exact same-key replays then passed: unsafe
traversal, secret canary, symlink, malformed ZIP and compression ratio. The ten
requests returned the intended 422 feedback between 00:35:02 and 00:42:09 UTC on
November 4, retaining the original working assignment. No admission, Submission,
POST evaluation or model dispatch resulted. The `size-limit` case proves compression-ratio
enforcement only, not the maximum uploaded-byte limit. The aggregate
`default-intake-live-proof.json` binds the exact deployed source/release and ten
receipt hashes. Selected project-PRE negative and same-key outcome replay also
passed: both responses returned 422 `pre_submission_checker_failed`, with
`layout_missing_required_file` at `instruction.md` and `eligible=false`. Four
Workstream baseline checks and the first external check passed; the second
external layout check failed as intended. Error outcome/details match across
replay; request correlation IDs differ normally. At that negative cutoff, the
complete PM Submission collection had no target row and `next_cursor=null`.
Public reads and a read-only
SQL snapshot at 00:49:21 UTC confirm the same active assignment/task in progress,
zero admissions, Submissions, dispatches, POST runs and model effects. The detailed
`project-pre-proof-v2.private.json` retains this bounded proof.
The subsequent intended POST-negative package passed preparation: the first
202 response was `stored_pending_verification`; explicit same-key replay returned
202 `ready`, with admission `01a1a409-3569-73cc-8fff-666e12d06429`.
Submission creation and exact 201 replay passed with immutable v1
`01a1a409-a2b1-7ce9-af68-57dcc19d72bb` and evaluation request
`01a1a409-a6b2-7530-9dd1-8b34b20be532`. Initial public feedback showed
`evaluation_pending` and checker `queued`. The subsequent bounded read-only SQL
observation found run `01a1a409-a755-7869-bab5-b4f8072c8cb5` ended
`infrastructure_failed / invalid_output` at 00:52:36 UTC. No work verdict or
Revision resulted. Offline replay of the ART-verified retained output identifies
a mixed validation failure: the first plan omitted `schema_version` and contained
two non-verbatim source quotes. Early structural rejection hid the citation
indices from the single correction request; its response fixed the schema but
not the quotes. No trial ran. The source repair shares one citation checker
between strict validation and bounded diagnostics, so independently checkable
quote failures reach correction even when another field is invalid. It preserves
closed-plan rejection and the two-call limit. Synthetic regressions pass, and
removing diagnostic enrichment makes the mixed-error regression fail; replay of
both historical responses still rejects them. At that cutoff the repair was not image-qualified or deployed. Its subsequent
`24b974b3` qualification/deployment and fresh guide 26 are recorded above; guide 25's locked Submission and failure remain unchanged. No retry
or successor is claimed. Submission creation supersedes the zero-Submission snapshot at 00:49:21,
but this infrastructure failure does not establish the intended negative work
result. Substantive POST, governed correction, acceptance and exact
ContributionRecord evidence remain pending.

At the **before-publication read-only cutoff**, the unchanged US$10 account had
**US$8.45712428 settled, zero reserved and US$1.54287572 remaining**
(8,457,124,280 / 0 / 1,542,875,720 nanodollars). The publisher verified those
balances unchanged after registration. No allowance was reset. These historical
figures follow guide 24's failed POST and precede guide 25 setup; they are not
the current balance. A later settled observation is recorded separately below.

At **00:50:01 UTC on November 4**, a fresh read-only observation before POST
records the unchanged US$10 cap with **US$8.55824392 settled, zero
reserved and US$1.44175608 remaining** (8,558,243,920 / 0 / 1,441,756,080
nanodollars), unchanged from the settled post-correction receipt at 00:06:02 UTC.
This is the pre-POST cutoff, not a later settlement claim. These account
observations are not provider-invoice reconciliation. At **00:52:46 UTC**, after
the failed POST, read-only SQL records **US$8.57363932 settled and zero reserved**,
leaving **US$1.42636068** under the unchanged cap (8,573,639,320 / 0 /
1,426,360,680 nanodollars). The later guide 26 settlement is recorded above.

Exact source `a05c962f` is distinct from the retained deployed backend source.
CI run
[41732508593](https://github.com/Flow-Research/workstream/actions/runs/41732508593)
passed 11,520 unique tests across 17 lanes, with zero skips/deselections and
complete cleanup. Independent reconciliation verified the artifact and lane
hashes against the identical tested merge tree. This is parent-source evidence,
not a passing aggregate for the deployed repair or current PR head. Earlier
source `e822a022c4440914e3aa627eaab0dbc2e687df28` has the same backend/application
trees as deployed `466faca5`; QA/test-delta review passed on `e822a022`, and
security/architecture review passed on `466faca5`. Its backend CI
[41746851816](https://github.com/Flow-Research/workstream/actions/runs/41746851816)
exposed three remaining test callers that expected nullable fields to be omitted:
draft task creation, historical contributor/manager work context, and the
unrelated-contributor assignment-outcome projection. Their assertions now require
explicit nulls while retaining history, privacy and policy checks. That run is superseded
and records those failures; it is not passing evidence. The later exact `942aa11a`
aggregate is recorded above and excludes the pending project-checker repair. Earlier `04437e76`/`97ad` failures or cancellations
are not credited as passes. Earlier runs
[41720437277](https://github.com/Flow-Research/workstream/actions/runs/41720437277)
and [41723295868](https://github.com/Flow-Research/workstream/actions/runs/41723295868)
were canceled after supersession and remain historical. The corrected real API
contract drill passed through authorized claim on isolated PostgreSQL and MinIO
with complete cleanup; guide 24 reached an actual immutable Submission.

Current public recovery cannot reopen a terminal setup attempt: same-operation
replay retains that outcome, and correction requires a finalized current
proposal. Fresh guide 26 does not reopen guide 25's locked Submission or failed
POST; guide 23's failed attempt and all prior evidence remain immutable. The remaining connected proof is durable POST,
genuine work failure/correction, recovery/replay and exact shared acceptance
and contribution evidence. [#555](https://github.com/Flow-Research/workstream/issues/555)
and related release scopes remain open.

The target is original project guide -> approved locked policies -> released
task -> claim (starts work) -> ZIP intake feedback or immutable Submission ->
durable POST -> governed outcome -> exact contribution evidence. Use explicitly
PM-approved `human_review_required=false`. Preserve default-true review
handoff guards; live human review, payment delivery, reputation, frontend and
claim expiry/skip remain deferred. #496 is excluded.

## Release and project provenance

### Historical guide 23 terminal setup — November 3

Guide 23 generation 1 produced two PRE and six POST suggestions under the
proposal-only setup contract. Its explicit PM correction ended
`compilation_invalid_terminal / schema_invalid`: both final model responses
used an output `agent_version` different from trusted `v1`. The model prompt
had demanded the trusted version without supplying its value. The strict
validator correctly rejected the output; no retained response was rewritten.
The shared instruction and bounded diagnostic repair was subsequently verified
by guide 24. Guide 23 has no checker approval, activation, task or contribution
outcome. Its terminal attempt cannot be reopened through same-operation replay.

### Historical guide 22 generation 1 checkpoint — November 3, before setup separation

| Required binding | Actual retained evidence |
|---|---|
| Backend source and CI | `e2b926288899bcd9b05e1a560ec19b6bca8cfcfc`, tree `0225f3ab4deed84cc9377f978fc6666fb9ff3375`; tested merge `71e735f7b631dbf1e66e1f8822e1678a4bc98faf` has the same tree. [Verified Backend aggregate](https://github.com/Flow-Research/workstream/actions/runs/41649582058): 11,702 unique completions across 17 lanes, zero skips/deselections and complete cleanup. Slowest lane 1,399.838 seconds; timing target not met. CodeRabbit skipped substantive review. CI does not establish a live journey outcome. |
| Actual deployment | Release `sha256:a6d626a56f0d29c6afb0ae1481554a5bdd6c023e7d3ebc5822d5e1b612b7abaf`; marker SHA-256 `b66cc37d6c05d1827c038f47b159439e85a9b61de6cb2b2606d9241fd96d2486`. Agents image `sha256:cc8e9f24af440682f153291b8e1d498c0495acc60eb282b6f3f6b3111a18f7a2`, Omni image `sha256:805431224490bdbba306491f3c85d96bbc057b77bdf04cb201c3530245a3d40b`. The backend-only rollout retained native process 717609, real-e49 POST, cache/authority/registry and existing data; no migration, reset or registration replacement. |
| Generation 1 proposal | Guide `01a1a1c7-3688-78f1-8196-61565a7483ab`, compilation `01a1a1cf-56d7-744c-969e-8b1f216bfa69`. Original guide/examples and setup profile v12 are unchanged. The persisted `draft_ready` proposal has ten requirements, two PRE/eight real-e49 POST bindings and no warnings. Retained package SHA-256 `3b9b16726917350491137c7bcca018af2b75f632deba85166e5ebc97448d505c`; target `sha256:906aefc58368e40eb54d6b247d38aeb7f547b352e3b7d0b6a3391bdac46c830a`. |
| PM correction and cutoff | Correction `01a1a1e2-5db6-7c2b-a53b-497e65e21c80`, successor setup `01a1a1e2-5db7-7e4a-b1c4-b69bddb9f874`; create/exact replay/read passed and generation 2 reached `compilation_reserved`. Requested edits remove the fixed Dockerfile-path restriction, require solver evaluation evidence with provenance, and select qualified PRE `drill-4ec4b` instead of `v1`. No corrected result, checker approval or activation is inferred. |
| Pre-correction accounting | Generation 1 added 211,890,440 nanodollars. Before generation 2 dispatch: 7,915,994,420 settled, zero reserved, 2,084,005,580 remaining under the unchanged 10,000,000,000 cap. Generation 2 settlement/reservations are pending and are not represented by that earlier zero-reserved observation. |
| Retained proof limits | Earlier d01 public artifact reads and aborted ART fault cleanup remain scoped evidence; normal generation-1 verification is not recovery. Guide 19's failed POST remains historical. Guide 22 has no checker approval, activation, fresh work task, POST verdict, acceptance or ContributionRecord at this cutoff. |

### Historical guide 21 checkpoint — November 3, terminal setup failure

The following table records that earlier cutoff; its pending-deployment statements are historical.

| Required binding | Actual retained evidence |
|---|---|
| Backend source and CI | `d01fc8e5a09379ab5162b7662fa4eecc54c3c876`, tree `625f3633f7f344b9bdefb938c460e021ef16c678`; tested merge `af771bbbe7569711b13d966cf7e25508d8bcefe3` has the same tree. [Verified Backend aggregate](https://github.com/Flow-Research/workstream/actions/runs/41631361979): 11,659 unique completions across 17 lanes, zero skips/deselections and complete cleanup. Slowest lane 1,460.364 seconds; timing target not met. CodeRabbit skipped substantive review. Focused internal reviews passed; CI does not establish a live journey outcome. |
| Actual deployment | Release `sha256:37ab3113140ee3e48c0e4d1d540f4e936f958f5bd27000151f468e02fa8d82dc`; marker SHA-256 `8368472f23a7e6e103db2757a31cc75c7a64a57820d397f334939d1d6d74cf4c`. Agents image `sha256:2be387f7a67caf0297c86867aad76b3b84253d405dc36b0534f7e119327c3611` and Omni image `sha256:c691d7e50bf5fdd1699d449aa6971bc74a43e7cebf810667398ac744cf2a68d3` were built from that source. Canonical AWS proof, retained-data checks and five healthy application containers passed. POST stays `real-e49dfcea`; native process 717609 was preserved. No migration, database reset or registration replacement occurred. |
| Fresh guide and upload | Guide `01a1a163-96e0-7107-bf08-6348afc8677d`, setup `01a1a163-9718-72fc-959e-7a27bd92b156`, attempt `01a1a166-a6aa-712d-8727-dcbc70c3b78c`. Create/replay, manager review/revision-policy choices/replays, original upload and exact replay passed. Original guide/examples and OpenRouter `openai/gpt-5.6-luna` setup profile v12 remain unchanged. These manager choices are not checker approvals. |
| Terminal setup and diagnosis | Twelve retained request/response objects were hash/size/owner verified. Exact context `sha256:23888b3d1922e482abf905b32c9b630077d174bad8d5d452b098221721fcc431` and native-parser replay confirm five POST bindings copied the trial-profile UUID alongside the semantic-profile version/digest. Exact correction schemas were present in the real requests. A detached diagnostic changing only those five IDs passes the unchanged full validator; reverting one rejects. The final selection contains two PRE and eight intended `real-e49dfcea` POST bindings with valid aggregate budgets. No retained output was modified or accepted. |
| Public access observations | Six public GETs on the preceding deployment proved an existing revoked Submitter receives concealed task denial while authorized control reads succeed; relevant owners are unchanged. On d01, 29 public artifact GETs passed: Operator reads and paired contributor denials across binding, content, replica, verification receipt, job and timeline surfaces, with exact DTO privacy/lineage checks. A private reader normalized omitted nullable Task fields before this successful run; that observer change did not establish the advertised public TASK wire contract, whose strict guide 25 failure is recorded above. These reads do not prove verification retry or final-data recovery. |
| Evidence cutoff and accounting | No finalized proposal, checker approval, activation, task or new POST resulted from guide 21. Six completed setup calls added 215,140,380 nanodollars. Account total: 7,704,103,980 settled, zero reserved and 2,295,896,020 remaining under the unchanged 10,000,000,000 cap. The source private registry-selection repair still requires deployment and live qualification; earlier attempts stay immutable. |

### Historical guide 20 checkpoint — November 3

| Required binding | Actual retained evidence |
|---|---|
| POST source and CI | `e49dfcea1fff63dea4ec03d35322085ac869acab`, tree `33f71bab03a4d5d1a6050835c48a3a8040fe6c27`; tested merge `75ae528c5c189ef486c6c7a169b3d0f6ebf225b1` has the same tree. [Verified Backend aggregate](https://github.com/Flow-Research/workstream/actions/runs/41617101238): 11,642 unique completions, 17 lanes, zero skipped/deselected tests and complete cleanup. Slowest lane 1,206.477 seconds; timing target not met. CodeRabbit was skipped. Source reviews passed; these checks do not establish a live journey outcome. |
| POST qualification and publication | Image `sha256:d78b777a57a5bd4675454cf0e0237c4ca963e46ea2eea61fde5c87d81d076bcf`, immutable version `real-e49dfcea`. Controlled image/physical qualification and eight immutable registration/read/exact-replay operations passed. The prompt requires strict integer citations and scopes runtime-only condition 11 to the runtime rubric; validators/correction limits remain unchanged. Controlled qualification supplies no fresh project work verdict. |
| Actual config deployment | Release `sha256:edd0f2185cd8cbe5f94da8a554f79d3a5bc3987e36b7a034469d83c025ef2513`; marker SHA-256 `7e7c7f0813016cc2c5a04d645a27d090a81fe503922820a18dc0ee46035ac9f8`. Backend source `357b9a55d91ccb285030b3f336eb890b25ae1735` and image `sha256:90df91272f857260a77714207ed28201163749ef86ba6980e8f44ea7ce7658e2` are retained, with genuine build provenance. The native binary is unchanged and restarted as PID 717609. Ten cache entries, 21 authority contexts and 58 registrations preserve all predecessors; canonical proof, retained-data checks and five healthy application containers passed. |
| Fresh guide and upload | Guide `01a1a11f-67b4-7e20-b8b4-566b39513ef6`, setup `01a1a11f-67f1-7d45-997b-2eb6cfe479d8`. Create/replay, explicit manager review/revision-policy choices/replays, original upload and exact replay passed. The original guide/examples and setup profile v12 are unchanged. Review policy `01a1a11f-d616-7960-82cd-e6270ef35379` and revision policy `01a1a120-3c2f-7ab6-8110-1085bcdcf1bd` are manager choices, not checker approvals. |
| Terminal setup and diagnosis | Setup ended `compilation_invalid_terminal / schema_invalid` at 11:25:04 UTC after six completed calls: two draft and four correction calls. Twelve retained request/response objects were verified. Exact-owner replay against reconstructed context `sha256:fbdef5b8fb6a16461ab5fdbbfbcfa54ab7283669b64fc511c25bb54cc1a44525` confirms the final candidate passes structural/Pydantic parsing, but four bindings combine trial-profile v10 IDs with semantic-profile v9 version/digest fields. Strict registered-configuration validation correctly rejects those mixed tuples. A private four-ID-only counterfactual then exposes a second rejection: nine selected POST bindings cost 3,600,000 ms against the unchanged 3,400,000 ms budget, including a duplicated checker. It still selects old real-e0b502f9 entries, not the new image. No retained output was rewritten or accepted. |
| Evidence cutoff and accounting | No finalized proposal, checker approval, activation, task or new POST outcome resulted from guide 20. The source correction-feedback repair passes focused tests; deployment and live qualification remain pending. It never fills in rejected values or changes selected versions, acceptance validation, correction limits or budgets. After terminal setup: 7,488,963,600 settled nanodollars, zero reserved and 2,511,036,400 remaining under the unchanged 10,000,000,000 cap. Guide 19 and all earlier records remain immutable. |

### Historical guide 19 checkpoint — November 2–3

| Required binding | Actual retained evidence |
|---|---|
| Source and CI | `357b9a55d91ccb285030b3f336eb890b25ae1735`, tree `ecd422cdfe36cd337e4c55fba4218ee03f38cb49`; tested merge `7ff714e8e25a68beebafd52ebcd86ce5c3595c33`. [Backend aggregate](https://github.com/Flow-Research/workstream/actions/runs/41422662161) completed 11,642 unique tests across 17 lanes, zero skips/deselections and complete cleanup. The slowest lane took 1,433.5 seconds; the timing target was not met. Exact-source internal reviews passed. CI does not establish a live journey outcome. |
| Actual deployment | Release `sha256:a6a43df436557494521562cf0e15d0cd50d3022329040b324e037fc24d0da631`; marker SHA-256 `0d061e9b4d6eaaf4508cfb37abb937aa5b9ef348add5f187a4a79dc931f0f683`. Backend image `sha256:90df91272f857260a77714207ed28201163749ef86ba6980e8f44ea7ce7658e2`. The rollout retained the native binary/process, nine cache entries, 18 authority contexts, 50 registrations and previous data/configuration evidence. POST remains image `sha256:b53763590e5a17b8776ae931498b5e07a0da496cf8d23e21574575607f2bd5cf`, version `real-e0b502f9`; no new POST-image qualification is implied by this backend-only repair. |
| Guide and exact manager correction | Guide `01a19c08-132a-7e6d-aa65-83446709f846`. Generation 1 compiled but selected older POST versions. One explicit manager correction produced generation 2 with four completed model calls. Semantic comparison found exactly eight capability-version changes to `real-e0b502f9`, unchanged requirements and other fields, and no warnings. Proposal target `sha256:f41cc3e236e016a4c70def5f132d2d77cbf388c0a89d62445308f109a4e49d1a`. Original guide/examples and setup profile v12 remain unchanged. |
| Approvals and activation | PRE approval `01a19c20-85e8-782c-b050-b893e83346c9`, POST approval `01a19c21-88a1-7c5b-989d-1d0e4a335293`, POST policy `01a19c20-8eef-794b-a84a-27619ba8f7fb`; exact replays passed. Activation `01a19c22-7ecb-7c1e-8c56-e0a2d8b83bed` selected generation 2 and passed replay/read-back. Explicit false human review, revision policy and the retained unpaid ContributionPolicy remain locked choices. |
| Task and immediate claim | Task `01a19c23-2f1b-7928-90ed-0a319cb1d7ac`, assignment `01a19c23-bee3-79dc-804f-c1a159c4108c`. Create/screen/release and immediate replay passed. Claim/replay retained one assignment, one command receipt/event, two distinct authorization decisions and equal assignment/start timestamps, without a separate Start operation. |
| Intake, immutable Submission and failed POST | Unsafe-traversal, secret-canary and project-PRE negatives returned intended feedback; project-PRE replay and warnings-only intake passed. After the interruption, the stored POST-negative v3 ZIP reached ready admission. Submission v1 `01a1a0ce-7415-7d5f-8e06-070ac760a11f` and evaluation request `01a1a0ce-77a5-7f3a-9761-bdc941fd924c` were created and exactly replayed. Run `01a1a0ce-7844-734f-a14f-197b92557b87` ended `infrastructure_failed / invalid_output`. Read-only observation at November 3 09:55:22 UTC found no persisted results or findings; no work verdict, governed revision, acceptance or contribution outcome is claimed. |
| Resumption and accounting cutoff | November 3 resumption retained the original instance, volume, source and project evidence; operator transport access was restored without resetting the drill. Pre-POST observation was 7,194,713,820 settled nanodollars and zero reserved. After the failed POST: 7,265,861,820 settled, zero reserved and 2,734,138,180 remaining under the unchanged 10,000,000,000 cap. Recovery, genuine work failure/correction, governed acceptance/contribution and final-data restore remain incomplete. |

Scoped guide 19 retrieval verified eight model request/response objects and the
checker request/result against their stored hashes. Both assessment responses
used string-valued recovery spans; the correction also quoted finding line
numbers. The later e49 repair clarified integer output and moved runtime-only
instructions out of the author rubric, preserving strict validation and the
correction limit. Its subsequent qualification/deployment is recorded above;
no retained response or historical work outcome was rewritten.

### Historical e0b / guide 18 checkpoint — November 2

| Required binding | Actual retained evidence |
|---|---|
| Source and CI | `e0b502f9bd4ec988c5320e223548e84fba82f573`; tested merge `4479bc826e57c316d012310e97f8f86f7188175f`. [Backend attempt 2](https://github.com/Flow-Research/workstream/actions/runs/41412570920) completed 11,631 unique tests, zero skips/deselections and all cleanup checks. The schema lane first exceeded 1,500 seconds, then passed in 1,458.935 seconds without changing its selection or cap. This evidence does not certify the subsequent diagnostic repair. |
| Qualified POST and publication | Image `sha256:b53763590e5a17b8776ae931498b5e07a0da496cf8d23e21574575607f2bd5cf`, immutable version `real-e0b502f9`; eight registration/read/replay receipts. Controlled physical proof retained four model effects, two 17-step trials and no additional replay calls, with owned cleanup. It is not guide 18's live POST outcome. |
| Actual deployment | Release `sha256:e8a4a24fbcb12973f692ebf1717ba83c2b3f0e32f85bed879ecdc3debe3c00c3`; marker SHA-256 `13bd48dfd8e2eb1bbd3c6901b5ff44770398c65e55e72d8fc8ff039e85156198`. Both SDK images were built from the exact source; unchanged backend content retained the Agents digest `sha256:9c0e8c35e083992f1fe468fd5f3ffe744cc1d45e938066cc6150a6724ec0da8d`. All five application containers passed health and canonical AWS proof. Nine cache entries, 18 authority contexts and 50 runtime registrations preserve their predecessors. Native binary `sha256:34be988c12481b575467ea4db6eb337711ec3732f8e16121f0485fb86a72c43d` restarted as PID 2351869. |
| Original guide and setup | Guide `01a19b81-238c-78ed-b57a-4cb8665b689f`; setup `01a19b81-23cb-7660-9cab-c61d47531672`; attempt `01a19b82-60d1-761d-840d-0b01acee4db3`. Create/upload and exact replays passed with unchanged original bytes/examples. Review=false and revision policies were explicitly selected and replayed; neither is a checker approval. Setup ended schema-invalid at 09:14:20 UTC, without a finalized compilation. |
| Failure diagnosis | Fourteen canonical AWS request/response evidence objects were hash/size/owner verified without reinference. Reconstructed context `sha256:e6a4848c5cf2a75d25420b5e64cc5702dd40f958bb373fe6776cd663a2fe98f4` matches every stored attempt identity and actual prompt. Slot 4 contains two registry-constant violations plus the 180/120-second mismatch; slot 6 repairs constants but still violates the deadline. Its historical checker selections also fail the intended new-image agreement. No retained response was edited. |
| Accounting and remaining proof | 6,916,744,120 settled nanodollars, zero reserved under the existing 10,000,000,000 cap. New guide agreement, genuine POST findings/correction, ART and delivery recovery, shared acceptance/contribution and final-data restore remain incomplete. Simulated Flow identity is not production Flow certification. |

### Historical guide 17 checkpoint

The following exact facts belong to the preceding deployment and remain retained.

| Required binding | Historical guide 17 checkpoint |
|---|---|
| Deployed source and exact CI | `c96216540e19f888ef482a57779da4d656561895`; tested merge `de8d485165c4d3a35737e51dedafca468ea93838` has the same tree. All five workflows, 17 lanes and 11,631 exact completions passed, with zero skips/deselections and complete cleanup. [Backend receipt](https://github.com/Flow-Research/workstream/actions/runs/41399356431). This does not certify the subsequent working source-quote diff or a live journey pass. |
| Backend release and image | Release `sha256:61e164252356c5545fb477f139ad508c279ccb3e539535679ee0429b82948336`; Agents fixture `sha256:9c0e8c35e083992f1fe468fd5f3ffe744cc1d45e938066cc6150a6724ec0da8d`. Five application containers passed health, canonical AWS proof and retained-data preservation before Beat resumed. Marker SHA-256 `6cf7c11164c8fb33a049b1ad7094cb400446fd46084e85a3cb6c3ec799313710`; selector SHA-256 `dbe358b2f2437a8ba1f562acae78f757d46f60c34382c49fa39d225836092885`. |
| Native runtime and queue boundary | Native service `sha256:34be988c12481b575467ea4db6eb337711ec3732f8e16121f0485fb86a72c43d`, PID 1999130, unchanged by the c962 cutover. Eight cache entries, 15 authority contexts and 42 registrations remain retained. Prefork delivery uses `workstream.outbox`; the pending scanner uses `celery`. Healthy runtime and earlier controlled qualification do not prove guide 17's substantive trials. |
| Identity and original material | The simulated HTTPS/JWKS issuer remains a fixture, not production Flow certification. Original guide: 12,110 bytes, SHA-256 `13d789d4b8df5d6b310d844c622336f265d53d2ddc38e8aa101b67765f9f7183`. POST-negative v3: 22,599 bytes, SHA-256 `a95a287599a61be6ba3b4bb8e7a3d42f80350ac34889e4bf32abd04614a90617`. |
| Project, guide and compilation | Project `01a17c77-eb01-7945-8b6d-0fe92c2d4be7`; guide `01a19afb-dd0a-75c3-9f95-2444e1b47f00`; generation-2 setup `01a19b0a-0d0b-741b-864b-2e2c2ce7d36d`; compilation `01a19b0f-5e68-7859-a908-a04fdc928b9d`; proposal target `sha256:103302204383053696d3f08f229fd41f1e8bd412093f5633d0221563be9e5a37`. |
| Approved checker bindings | Two PRE bindings retain `drill-4ec4b`; all eight POST bindings select `real-26d5977e`, image `sha256:53d0a828914a690b0a365f6d6783dace7bb80d3b655e7ef16b48ad5d9283b617`. Immutable semantic v9, trial-assessment v10 and setup v12 profiles retain their exact selected tuples. The working source-quote change is not part of that image. |
| Approvals and activation | PRE approval `01a19b12-c439-702f-976f-07625523a493`; POST approval `01a19b13-ea4e-7efb-9a10-01c8f727d0c2`; POST policy `01a19b12-ced7-7912-8acb-ff3c35ee9b6f`. Exact replays passed. Activation operation `01a19b14-cd46-79b4-9022-7d935cbff7e2` selected generation 2, explicit false human review and the retained unpaid ContributionPolicy version `01a196f9-8924-7c6a-ab78-6aefa0eeb1e6`. |
| Task, assignment and immutable Submission | Task `01a19b15-73f9-733a-bd00-d7ecdcc54e27`; assignment `01a19b15-f9b4-7053-b72b-e6ec060d862d`; admission `01a19b34-3d4a-7b58-a392-14f6823649d3`; Submission v1 `01a19b35-d73d-79fb-b158-b694ca118819`; evaluation request `01a19b35-daf9-772d-ac00-ae9bb79cea1d`; run `01a19b35-dba6-74f5-845f-fb273c79a149`. Creation and exact replay retain the same identities. Task/Submission remain `evaluation_pending`; run is `infrastructure_failed / invalid_output`, with no findings or acceptance/contribution evidence. |
| Warnings verification and ART fault | Warnings-only verification job `01a19b32-5b26-737c-87a0-37aeb305f2d2` completed generation 1/attempt 1, with receipt `01a19b32-d08a-74f5-9db2-80c13adf128a` and admission `01a19b32-d0a3-7560-a042-13f7a1ffb6f7`. Query-proof mismatch aborted the fault before cancellation; the original two queues were restored. No recovered generation or failure/retry pass is claimed. |
| Paid accounting and evidence cutoff | 6,713,600,840 settled nanodollars, zero reserved, unchanged 10,000,000,000-nanodollar cap. Two completed author-evidence effects settled 10,997,000 nanodollars, included in that total. Four canonical S3 request/response evidence objects were byte/hash verified with no new provider calls or product writes; manifest SHA-256 `915007d9e1dd24213469ca49231a8d42fc57685fa2844961b9fe34aa416b83f2`. No payloads or private storage paths are published here. Final journey/recovery/cleanup evidence remains incomplete. |

### Historical provenance through guide 12

The following bindings describe earlier checkpoints only. Their relative words,
account balances, pending checks and deployment selections are historical; the
opening section supplies the current checkpoint. No retained row or receipt
was replaced to advance the drill.

| Required binding | Historical value through guide 12 |
|---|---|
| Executed source commit and exact review/CI evidence | `1e32931b` for original setup/approvals; `a3fc1f196` for original activation/claim/Submission; `4ec4cbb58` for native recovery; `e8d6980ac` for guide8 correction; `321486686` for guides9–11; deployed `4e0d4035c` for guide12 and its corrected generation. Then-pushed source `97681138c` passed all five substantive workflows, 17 lanes and 11,620 exact unique completions, with zero skips/deselections and complete cleanup. That test-only successor has the same application tree as deployed 4e; its full CI does not certify pushed `0040a7b28`, whose fresh CI was still running at that checkpoint, or the unfinished live journey. |
| Backend API, Celery worker/Beat, parser and proxy image digests and fixture derivatives | Guide 12 source `4e0d4035c`, release `sha256:eca4560e56317ab9e05f0a0d63eb1d2b80e8c23e9a466d57e6241d740a6f3a7d`, agents fixture image ID `sha256:a94a29bb5a01921644c0b41f89324d871d041a64e790e0b03c605aec07433e7a`. Guide12 bootstrap bound the five exact healthy marker containers and actual source/image pins. This run uses the OpenAI Agents SDK; no current Omni deployment is claimed. |
| Native service, Smol, guest and configured cache/archive/config digests | Smol 1.31.4; service `sha256:34be988c12481b575467ea4db6eb337711ec3732f8e16121f0485fb86a72c43d`; native-only retry reused the retained model response; no Trial yet. The completed Luna rollout preserves six retained cache entries and extends six existing authority contexts to nine; substantive Trial qualification remains pending. |
| Migration head; non-secret release/configuration fingerprints; Celery worker topology | `0065_claim_starts_work`; one prefork Celery worker with concurrency 2 and one Beat; native-only checkpoint config `sha256:72babee2dcc2773f2968a1f9dbd3c5829385918e278c126bd319d479daf3c208`; active Luna config `sha256:570f17c44fccfdb8f413e41ad85fc0e9a72637379ed45777d07d8896e7e937fe`. |
| Identity qualification; issuer/key configuration digest, without subject/token | Authorized simulated HTTPS/JWKS issuer through the actual verifier; six distinct admitted actors. JWKS digest `sha256:70718dcfcb5c4052d01764b05a73e1eada122d945f88f4342395f27e23be1ded`. No production Flow issuer certification. |
| AWS candidate activation/freshness and non-secret proof fingerprint | Native-recovery release `sha256:2e85ec00cfa905f13bfb11a89d8d196e0c71a17d2b3d549e7389aa9dce43af8b` passed canonical readiness, runtime immutability and negative-access probes. Subsequent candidate `sha256:964222c127cea848d8c35571a4592b5f7d7202bb7acb8d22c8d9267c506f260f` completed after the retained transient one-off inspection failure was resolved; exact application container health and canonical proof receipts were verified. The backend correction subsequently activated release `sha256:e5b931283a34965f2dc8ff9b380750d98007b22321889d0e9ed6c45e222c907e` with fresh canonical proof and retained-data verification before Beat resumed. The subsequent instruction release `sha256:7fe931ffa814aff305f521c9cac9e2c18c72245e445f9d01b1d852ac32fab7c4` ran source `321486686`; guide12 release `sha256:eca4560e56317ab9e05f0a0d63eb1d2b80e8c23e9a466d57e6241d740a6f3a7d` deploys `4e0d4035c` with the same native binary. Each rollout retains its own time-bounded proof receipts. Namespace remains `sha256:cf487c3b9b8ae93579939f80cb245ca79c25a5641fb3d5ce461abc16f0f4bad7`; freshness is time-bounded. |
| Original guide/task-example/import/positive/negative package SHA-256 values | Guide/ZIP fingerprints below. Public task import consumed 14,710 verified bytes, SHA-256 `a719390aebd455d64e3f519c5a3c5fe110f147135623247844dd846041179849`, creating five tasks. |
| Project/guide/setup/correction/result IDs and requirement mapping | Project `01a17c77-eb01-7945-8b6d-0fe92c2d4be7`; original approved guide `01a17d0a-cec1-786f-bf90-594f9dec5c82` and compilation `01a17d13-d490-7ec8-b403-dfb17d3c3f3e` remain retained. Guide12 `01a19956-5074-71dd-81bc-992008ca021d`; generation-2 setup `01a1996b-59d7-726e-89d8-ce25ab1eeb1b`; compilation `01a1996f-99d2-73fc-8fcb-0e17ac923ac0`; proposal target `sha256:68e3854e3b0c286a775e6c9eaed911a3db10740cc842628aa3d44fc2ee4bd852`. |
| Registry/config/model-profile IDs/digests and exact approved bindings | Original PRE and eight updated POST entries registered/read/replayed; updated receipt manifest `sha256:c99e833020d68f6f5e7a142afe9014b634a311fa3324e7e01a1cab6e5f9c2a9b`. Those bindings belong to the approved original guide. Nine new `drill-4ec4b` registry versions carry actual emitted finding-code descriptions and exact Luna model selectors; they were initially published/read/replayed without approval, then selected through guide12 generation-2 approvals. Later immutable Luna setup profiles 7 and 8 selected high reasoning and distinct output bounds; guide12 used version 8. They did not alter old locked policies. |
| PRE/POST approvals; ReviewPolicy, revision and ContributionPolicy versions; activation/LIVE identities | Original activation `01a196fa-6693-7fd4-ab90-59a59b7b440d` and unpaid ContributionPolicy version `01a196f9-8924-7c6a-ab78-6aefa0eeb1e6` remain retained. Guide12 PRE approval `01a19974-4e60-761a-956a-3a09dbe16c1e` and POST approval `01a19975-8557-71ce-9f1b-1f09b767e77e` each replayed exactly; POST policy `01a19974-564b-7a87-8efc-ed80329f703f`. Activation `01a19979-156b-7593-b883-e00b8efb991f` selected generation 2, explicit false human review, two revision rounds/48 hours and the existing unpaid Finance version. Operator shadow/live transitions remain retained. |
| Task/assignment/Submission/checker/routing/acceptance/contribution/award IDs | Original task `01a196fd-4957-751a-b0c2-dd70e71ffe7a`, assignment `01a196fe-6a94-7490-a624-9959109b54fa`, Submission `01a19703-0398-7d55-a33d-58658c9b0a50`, failed run `01a19703-07d0-7cc9-8cec-1e1da215c121` and retry `01a19736-93a2-71b5-8cf0-913cbd25aec1` remain retained. Queue12 task `01a19979-6d78-759f-8836-119de2bc845a`, assignment `01a1997b-5978-7cb5-bd70-e2ec3de8190a`, admission `01a19992-4508-73d0-a299-1b3a8aefe4f1`, Submission `01a19992-eafe-725b-8e3c-bd97e2ceeb37`, evaluation request `01a19992-eec0-7857-93c8-466fe0562b43` and automatic run `01a19992-ef6b-7cb7-a0bc-7d42bce61ef2` are retained. The task is `evaluation_pending`; its POST is `infrastructure_failed / invalid_output`. No revision, acceptance, contribution or award is claimed. |
| Private evidence manifest fingerprint, observation interval and cleanup inventory | November 1 progress manifest `sha256:341717bb2e746475ea083034078f77d54f406b5d3acc9c55cfe29ecd5d1c0c1d` binds 60 local operation logs; server journals and later independent observations are retained separately. Final journey/cleanup manifest remains pending. |

Record actual immutable identifiers and bounded evidence references, not private storage locations, connection URLs, raw subjects or payloads. Source files or healthy services do not substitute for these bindings.

## Prior scoped evidence — not this rehearsal's results

| Existing evidence | What it establishes | Limit |
|---|---|---|
| [Public connected local proof](../../.commitrail/changes/public-guide-to-contribution-proof.md) | Public guide inputs, recorded inference, durable local journey, both policy outcomes and focused failure proof | Local identity/MinIO and recorded inference; not this hosted project |
| [Terminal Systems setup](../../.commitrail/changes/terminal-systems-live-setup.md) | Real setup and explicit corrections produced a reviewed historical handoff | Pre-narrowing schema, unapproved/unactivated; needs supported fresh correction |
| [Project checkers](../../.commitrail/changes/terminal-systems-project-checkers.md) | Implemented POST/model/trial/material capabilities and bounded native qualifications | Not proof of this project's approved bindings or contribution outcome |
| [Hosted Smol qualification](../../.commitrail/changes/hosted-smol-project-execution.md) | Synthetic public AWS/native baseline and one live OpenRouter POST; same-effect replay and US$0.016527 pinned-rate settlement | Simulated identity, synthetic single rubric; no real-project setup or grading-quality claim |
| [Identity fixture](../../.commitrail/changes/hosted-drill-identity.md) | Actual HTTPS/JWKS verification through unchanged Flow adapter and AUTH | Simulated Flow-compatible issuer; no external Flow certification or revocation/introspection proof |

Some issue/onboarding prose retains historical gVisor or unavailable-POST descriptions. Current merged owners and the [capability ledger](../roadmap_status.md) select native Smol and implement those POST capabilities. Implementation and scoped qualification remain distinct from this project's agreement, approved bindings, activation and exercised proof.

## Prior connected capability scenarios

### Guide 17, exact c962 deployment and remaining POST gate — November 2

The backend-only c962 cutover retained the native binary and process, existing
POST image, locked history and account. Its canonical image, AWS and preservation
checks passed; the exact-source CI aggregate subsequently completed all 11,631
nodes. That source repaired phase-local setup correction budgets and bounded
registered-constant diagnostics. It does not contain the working procedure
source-quote change.

Guide 17's public manager correction persisted generation 2, separate PRE/POST
approvals and exact replays, followed by activation generation 2. Claim returned
`in_progress`; independent custody matched one assignment, one claim receipt/event,
equal assignment/start timestamps and fresh replay authorization. No separate
Start operation occurred. Unsafe-ZIP, secret-canary and project-PRE controls
returned blocking feedback and passed absence checks before Submission. The
project-PRE negative also passed exact replay; unsafe-ZIP and secret-canary
replays were not performed in this continuation.
Warnings-only intake returned 202 and normal durable verification created exactly
one generation-1 receipt and ready admission. It created no Submission.

The ART fault observer rejected its query-shape proof before cancellation. Its
bounded holder was released and the original `celery` and `workstream.outbox`
consumers restored. The warning archive then verified normally; that is not an
ART failure/recovery pass. Source-derived query-prefix, Celery worker and socket custody
preparation does not turn an unexecuted fault into hosted evidence.

The distinct POST-negative archive reached ready admission, immutable Submission
v1 and exact replay. Automatic POST completed two paid `author_evidence_accurate`
model effects, then ended `infrastructure_failed / invalid_output`. The corrected
proposal still cited source line 103's closing code fence instead of line 102's
command. Both model effects and their exact private evidence remain retained;
no hosted trial, substantive finding or `needs_revision` work verdict resulted.
The task remains `evaluation_pending`; this infrastructure outcome imposes no
contributor penalty and supplies no acceptance or contribution.

The subsequent e0b change replaced procedure line-number proposals with one
private `source_quote` format: an exact unique full-line source window, bounded
to 16,384 UTF-8 bytes, from which the checker derives procedure bounds. Existing
command/argument, source, state, material and capsule authority checks remain;
coverage-gap and recovery-applicability citations retain their own validation.
See the [checker contract](../../pilots/terminal_systems/checkers/README.md#post-prerequisites).
All 115 model unit tests passed locally and in the qualified image. The e0b
publication/deployment above contains this repair; its fresh guide 18 failed
setup before it could select the new image for work. Guide 17 rules and paid
effects remain immutable. No unchanged-image resampling or budget change occurred.

Remaining proof is genuine POST/trial work outcomes, actual feedback-governed
correction and unchanged-ZIP guards, applicable ART and UNKNOWN recovery/replay
with no extra effects, then the shared authorized FinalAcceptance and exact
submitter ContributionRecord/applicable award set. Preserve the default-true
review handoff; passing false-policy checks must use that same acceptance owner
without fabricating a Review or reviewer contribution. The complete public API/durable-worker
journey and the release scopes below remain open.

## Historical checkpoints — earlier sources, policies and balances

All observations below retain their original dates and scope. References to
"current", "latest", pending checks or balances inside these historical records
mean that checkpoint, not the current opening checkpoint above.

### Initial hosted checkpoint — November 1

TLS renewal of the separate drill issuer preserved its six identities, signing
material and exact public JWKS. Four original actors authenticated through the
public verifier afterward. Migration 0065 preserved retained data; during the
subsequent transport update all 132 non-probe table fingerprints stayed identical.
The three canonical AWS probe rows and one activation added by each successful
proof group were reconciled separately; excluding only the recorded group
reconstructed both original probe-table hashes. No database reset or restore was
used to advance the journey.

Finance published the unpaid contribution policy through public APIs. Manager
activation selected the exact approved guide/policies. Five original tasks were
imported; only queue recovery has progressed through screening, release and
claim. Claim returned `in_progress`; same-key replay returned the identical
assignment. Independent read-only verification found one assignment, one durable
claim receipt, one `TaskClaimed` event and two fresh authorization decisions.
Database `assigned_at` and `started_at` were equal; no Start operation or event
occurred, and all locked activation identities matched.

The PRE-negative upload produced preparation
`01a196ff-d255-760f-96e6-06c020d208e5`, with no durable storage intent, admission or
Submission. A 30-second client timeout lost the first response; public discovery
found `checks_failed`, and explicit same-key replay recovered the expected 422
`pre_submission_checker_failed`. The other package passed PRE, then artifact
verification produced admission `01a19701-f0a1-7b94-bcb2-c79ea470e899` from
preparation `01a19701-99de-7b5d-a422-ceaa3fb2e9c6`. Both Submission-create responses
were 201 with the same IDs and body hash
`23f1d160e8f3bc6d79cef56e50ea73dcc71d84dee9dbd256928ce78859411f6c`.

At 12:21:37 UTC, independent read-only custody verification matched the
Submission, consumed admission, verified/available/valid replica and receipt to
the exact 20,470-byte archive/hash. The task/attempt remained `evaluation_pending`
and its assignment active. Automatic durable POST ended
`infrastructure_failed` / `implementation_unavailable`, with routing
`not_evaluated`; its outbox delivery completed with `invocation_unknown=false`.
There were no acceptance, contribution, Review, award, routing, revision or retry
rows. Operator discovery exposed an eligible exact retry source and no UNKNOWN
delivery. Finance was denied contributor work-context and Submission-history
reads with concealed 404 responses.

The first author-evidence model call completed and settled US$0.043729. Its
retained plan quoted six real commands with incorrect source line numbers; an
offline diagnostic changing only those spans passed strict validation, but that
copy is not model evidence. Separately, an offline native socket reproduction
showed clean EOF after a non-exhausting completed reply being classified as
failure, which can mask the image's own outcome. Original guest stdout was not
retained separately, so the observed normalization is not presented as recovered
guest output. Repair `4ec4cbb58` distinguishes clean frame-boundary closure from
truncation/cancellation, and supplies explicitly numbered source text to the
project model. Original evidence and strict citation validation remain intact.
Focused tests and internal reviews pass; the native recovery checkpoint below qualifies the EOF repair. Revised image selection and substantive Trial/work evaluation remain.

The private task driver initially used the administrative grant route for a
submitter and omitted the release reason; both requests were rejected. Correct
project-manager role issuance and a reasoned release subsequently succeeded.
These are retained operator-driver errors, not product authorization bypasses.

No substantive POST work verdict, corrected successor, final acceptance or
ContributionRecord is yet proven. The unpaid policy permits proof of the exact
empty applicable award set only, not positive compensation or fulfillment.

### Native recovery checkpoint — November 1, 13:08 UTC

The native-only rollout installed the reviewed binary at exact source
`4ec4cbb58`, retained the existing backend images with a fresh canonical inventory
proof, and restored all five healthy services. The original config, trial authority,
checker pins and application rows remained unchanged; only exact recorded AWS
proof/activation receipts were appended. An executable-mode error in the private
rollout helper stopped progress before any AWS proof call; explicit mode handling
was corrected and checked under the restrictive umask. The failed observation is
retained. No migration, data reset or rollback restore occurred.

The public Operator retry and exact same-key replay returned receipt
`01a19736-93ad-7abd-9aec-c79dcf3bdc4b` and generation-2 run
`01a19736-93a2-71b5-8cf0-913cbd25aec1`. Both 201 responses had SHA-256
`65743df2c9a5fe890af1016632a2a8d76f664725ed55d537c37260c11fb8e152`.
At 13:07:59 UTC, independent read-only verification confirmed exact ancestry,
unchanged locked policies, one retry receipt and acknowledged delivery with no
UNKNOWN invocation. The successor completed `infrastructure_failed / invalid_output`:
the original invalid model plan remained invalid, now without the native EOF error
masking it. One recovery attachment reused the original completed call-0 effect;
no second effect or charge was created. Submission/assignment custody remained
intact and no acceptance, contribution, Review, award, routing or revision effect
was created.

Before another setup dispatch, the 13:08:42 UTC account observation still showed
US$2.021551 settled, zero reserved and US$7.978449 available under the same cap.
The new numbered-source project image passed 43 packaged tests and controlled
socket smoke without a provider call, then eight new registry versions were
published, read and exactly replayed through Operator APIs. They do not replace
old task bindings. New guide `01a19738-de01-7d91-96a7-9929d411d877` received the
unchanged original bytes through public upload and started setup under the same
project account. A 13:09:37 UTC read displayed `provider_outcome_unresolved` while inference was
still running; it was not a terminal failure. By 13:10:32 UTC compilation
`01a1973b-ab5c-7a38-8760-24c0edba48fc` was persisted and setup was
`policy_draft_ready`, without retry or resume. Four completed model calls cost
US$0.6535634; independent custody and later public reads confirmed success. At that checkpoint the
account held US$2.6751144 settled, zero reserved, and US$7.3248856 remaining.
Approval, additive runtime binding and the substantive journey remain pending.

### Further correction and Luna preparation — November 1

Guide6 generation 2 completed public manager correction and persisted compilation
`01a19746-cdda-760d-93b9-7e5119e71ed8`. Its dependencies were corrected, but
comparison with the project image found semantic finding-code discrepancies;
approval was withheld. A further public correction created generation 3, whose
attempt remains `compilation_provider_uncertain`: five model effects completed
and one effect remains prepared. No compilation or approval is claimed for that
generation, and the retained effect has not been blindly redispatched.

Before Luna dispatch, the account recorded US$4.4888454 settled, zero reserved and US$5.5111546
remaining under the unchanged US$10 cap. The Terra profile's next maximum
reservation is US$5.544912, exceeding this remaining allowance. That comparison
establishes the current reservation limit; it does not establish the sole cause
of the initial provider-uncertain transition.

Three actual OpenRouter `openai/gpt-5.6-luna` profiles were published, read and
replayed: semantic version 4 (`01a19765-4b3e-7d3b-89b8-2798362ce041`), trial
assessment version 5 (`01a19765-ba30-7c2b-94d9-f09ef6d87d88`) and setup version 6
(`01a19765-bb85-7f8f-a66e-8fa856684bef`). Nine new `drill-4ec4b` registry versions
publish the actual project finding-code descriptions and pin the exact model
selectors. Registration does not approve a guide, replace an old locked binding
or demonstrate Luna grading quality.

The additive runtime candidate retains the backend/native pins and all six cache
entries, preserving the six existing authority contexts while adding three Luna
contexts. During rollout, database reconstruction matched the original retained
rows after accounting for the exact canonical AWS probe/activation groups and
eight ordinary scheduled scanner authorization audit appends. These were
identified append-only facts, not ignored tables or rewritten history. The final
commit then failed during Docker inspection of a transient one-off container,
after Beat had resumed. Finalization then verified the five exact retained
application containers instead of enumerating temporary proof containers. Release
`sha256:964222c127cea848d8c35571a4592b5f7d7202bb7acb8d22c8d9267c506f260f`
completed at 14:39 UTC with native PID 450912 and all five services healthy. Its
receipt binds the successful preservation check before scheduler resumption;
it does not claim later ordinary audit appends were in that earlier snapshot.
No database baseline, historical row, budget or original evidence was reset.

Guide7 `01a1978d-7a9b-7c72-bef5-26fb64f45c94` then received the same 12,110 guide
bytes and task example. Setup attempt `01a1978d-cc63-79c2-bcb1-02234a27edb7`
ended `compilation_invalid_terminal / schema_invalid`. All six model effects
completed and settled US$0.0872514; at that checkpoint the account held US$4.5760968 settled,
zero reserved and US$5.4239032 remaining. No proposal or approval was created.

Forensic reads through the configured ArtifactStore and canonical ART ancestry
checks recovered all twelve retained request/response objects and verified their
exact hashes and lengths. Offline replay used the actual request schemas and
256,000-byte limit. The three final replies were complete, not truncated: the
first claimed blocked status without blocking evidence; the second omitted an
isolation dependency; the third reused a requirement ID. The correction prompts
supplied generic error codes without the prior candidate, so indexed errors did
not identify a proposal available in the new conversation. The same-PR repair
keeps a bounded rejected candidate as untrusted correction data and supplies
closed, trusted diagnostics; canonical validation and all attempt/budget bounds
remain required. At the guide7 checkpoint, repair and live qualification were still pending; the next section records the deployed correction.
The existing public correction operation requires a finalized proposal target.
A known-invalid setup has no such target, and its replay cannot invoke again under
changed runtime code. The next qualification uses an explicit fresh draft guide
with the original bytes; guide7 and its terminal evidence remain retained. A
same-guide retry for this terminal state is not claimed as an available API.
No substantive POST verdict, acceptance or contribution is claimed.

### Deployed correction and guide8 diagnosis — November 1

The reviewed adapter repair at `e8d6980ac` was deployed after both SDK image
inventories passed. The native process, six cache entries, nine authority contexts,
locked records and schema `0065_claim_starts_work` remain unchanged. A fresh
retained-data snapshot was verified before Beat resumed. The first final-marker
attempt waited for an in-progress canonical AWS proof; it made no marker write.
After the proof settled, explicit finalization completed normally. No new model
call was made by deployment.

Fresh guide8 `01a197c1-b59d-7970-a7d6-d6726c127294` received the unchanged original
guide bytes and task examples. Attempt `01a197c2-273d-793d-9b3d-666c772e7a64`
ended `compilation_invalid_terminal / schema_invalid`, confirmed through the
public setup read and retained records. All six Luna effects completed, adding
US$0.09226014 in pinned-rate settlement. At the guide8 checkpoint the account held
US$4.66835694 settled, zero reserved and US$5.33164306 remaining. Separate manager
review/revision policy selections were saved; no proposal approval or activation
occurred.

All twelve request/response objects passed ART ancestry, byte-count and hash
verification. Offline comparison proves each correction carried exactly the prior
rejected candidate. The model corrected its empty blocked result and then its
missing isolation dependencies. Every final reply followed a fresh complete
source read and finished without truncation or refusal.

The last reply still selected a model-profile ID from another catalog entry in
two POST configurations. Replacing only each ID with its own selected entry's
constant in memory makes those configuration checks pass. The next unchanged
owner rejects two missing PRE specifications. These counterfactuals diagnose the
errors; they neither edit retained output nor produce an approvable proposal.
The instruction/example repair clarifies complete PRE specifications and exact
configuration tuples from the selected registry entry. Its complete synthetic
result passes the canonical owners; wrong-entry selectors and omitted PRE
specifications reject. Focused checks passed, including a schema-guard removal
probe. At the guide8 checkpoint this instruction/example repair was not yet deployed;
the next section records its deployment and later failed qualifications. Validation
and existing correction, source, execution and spending bounds remain enforced.

Hosted CI for `b5d21c4db` completed sixteen lanes successfully; shared foundations A
failed two old assertions that rejected values could never appear anywhere in a
correction prompt. The new contract permits safe candidates as explicit untrusted
data while keeping diagnostics value-free. Test-only repair `7a3e1386f` asserts
both boundaries and complete revalidation; focused execution and QA/test-delta
review passed. This is not a fresh full-suite pass.

### Deployed instructions and guides9–11 — November 1

Source `321486686` was deployed for guides9–11 under release
`sha256:7fe931ffa814aff305f521c9cac9e2c18c72245e445f9d01b1d852ac32fab7c4`.
The five exact application containers were healthy, the native binary/cache and
schema remained unchanged, and retained-data verification preceded scheduler
resumption. Each later guide bootstrap rechecked the actual source, release,
container image IDs and health. No product code changed during those three attempts; they
exercised existing setup operations and immutable model profiles. The later
source-4e deployment and guide12 checkpoint follow below.

| Attempt | Profile and observed outcome | Completed effects / additional settlement |
|---|---|---|
| Guide9 | Luna setup v6. Complete replies failed `warning_evidence`; separate inspection found dangling POST requirement references and two wrong-entry model-profile constants. Source/context delivery and exact rejected-candidate custody were correct. | 6 / US$0.07918008 |
| Guide10 | Setup-only Luna v7 selected high reasoning with 16,384 output tokens per call. All three final replies ended `length` and failed JSON parsing; canonical/context validation was not reached. Malformed candidates were correctly omitted from correction data. | 7 / US$0.13829728 |
| Guide11 | Setup-only Luna v8 retained high reasoning and increased output limits to 32,768 per call and 131,072 aggregate. All final candidates ended `stop`, with 42,691 aggregate output tokens. They still failed `unsafe_text`, dependency-availability rules and finally `warning_evidence`; the last reply also had eight missing POST requirement references. | 8 / US$0.14840234 |

All three attempts ended `compilation_invalid_terminal`; none created a valid
proposal, approval, activation, new task or contribution. The diagnoses verified
12, 14 and 16 retained ART request/response objects respectively. Guide11's unsafe
candidate was omitted, while its safe rejected candidate was retained hash-exact
in later requests. The final source read covered the complete original. No
syntactic repair or semantic inference was attempted on guide10's incomplete JSON.
In-memory status-only counterfactuals for guides9/11 exposed binding-reference
failures, not an approvable proposal. Full replay context excluded runtime/storage
metadata absent from provider requests; these diagnostic limits remain explicit.
Private frozen diagnoses retain the exact object/source fingerprints; retained
output was not edited or submitted as a replacement.

The source-321 hosted run completed all 17 lanes and 11,616 exact unique nodes,
with zero skips/deselections and complete cleanup; canonical evidence validation,
real API e2e and the other recorded required workflows passed. This supersedes the
earlier b5 assertion failure for that tested source, not the missing live outcome.
Application validation correctly rejected the observed noncompliant outputs.

Offline reproduction then found two correction-diagnostic gaps: the trusted
unsafe-text and dependency-availability failures both appeared as generic
`canonical_constraint`. The shared parser now maps those exact causes to closed
codes at their existing bounded field paths. Unsafe candidates remain omitted;
no rejected values or exception text are exposed. Both SDK correction paths are
covered. This diagnostic repair preserves validation. Source `4e0d4035c` subsequently
deployed it; guide12 below records the observed proposal and manager correction.

At the guide11 checkpoint, the unchanged account held **US$5.03423664 settled, zero reserved
and US$4.96576336 remaining**. Among the profiles examined, only Luna was verified
affordable within this remainder. The proposed Terra dispatch bound of US$5.839824
and Sol minimum dispatch bound of US$11.48304 exceed it; neither dispatch began.
These are reservation feasibility checks, not predictions of model quality or
new spending authority. No account reset, increased cap or blind replay occurred.
The complete first contribution journey and applicable recovery proofs remain
unproven; no new runtime, tool, same-guide terminal retry or TUI workflow is claimed.

### Deployed diagnostic repair and guide12 agreement — November 1–2

Source `4e0d4035c` deployed under release
`sha256:eca4560e56317ab9e05f0a0d63eb1d2b80e8c23e9a466d57e6241d740a6f3a7d`,
with the native binary and schema unchanged. Guide12 bootstrap validated the
five exact healthy marker containers and actual source/image pins before public
creation, upload and policy writes. The pushed `0040a7b28` project-checker repair
is not part of this deployed source or its live evidence; its fresh CI is running.

Guide12 generation 1 persisted a warning-free draft with ten requirements,
two PRE specifications and eight POST bindings after seven completed Luna v8
effects costing US$0.1632804. Independent PM semantic review still found an
incorrect fixed environment/Dockerfile rule and difficulty-evidence classification;
approval was withheld. A public same-guide correction was created, read and
replayed, then dispatched and replayed through the existing operation. Its one
generation-2 attempt persisted compilation `01a1996f-99d2-73fc-8fcb-0e17ac923ac0`
after four completed effects costing US$0.105595. Earlier candidates and effects
remain retained; no terminal-invalid replay, edited output or new workflow was used.

Separate manager PRE and POST approvals each replayed their exact receipt.
The POST policy was deterministically derived from the approved proposal, then
separately approved and read back as current. Activation generation 2 selected
the explicit false-human-review policy, two revision rounds with a 48-hour
deadline and the existing unpaid Finance policy. The new queue-recovery task
was created, screened, released and claimed directly into `in_progress`.

At 23:52:00 UTC, bounded live claim verification found one assignment, one claim
receipt, one `TaskClaimed` event, two claim responses and two exact authorization
decisions; no separate Start event or Submission existed. The original/replay
authorizations were selected by their exact prepared context, not a count of all
project claim decisions. This establishes claim/replay for the new locked guide,
not ZIP intake, a substantive POST outcome, acceptance or contribution.

The first current-task negative-intake driver stopped before upload because it
expected an empty-history 200; the canonical no-history response is 404. The
private harness now handles that response correctly, without fabricating a 200
or changing the product. Live controls then produced these bounded observations:

| Current queue12 control | Observed blocking result | Durable boundary |
|---|---|---|
| Unsafe traversal archive, 00:02:58 UTC | 422 `submission_archive_unsafe_entry` | No matching preparation |
| Secret-canary archive, 00:03:20 UTC | 422 `high_confidence_secret_detected` | One failed preparation `01a19991-4988-7bab-8f04-2475cdfac150` |
| Project PRE negative, 00:03:42 UTC | Defaults passed; selected PRE prefix returned 422 `metadata_invalid_argument_array` | One failed preparation `01a19991-91c4-756a-a740-aa3cdad990dc` |

Each snapshot found zero task-wide admissions and Submissions, retained the
working assignment and dispatched no model POST. These are intake controls,
not post-submit task failure or acceptance. The later POST-negative preparation and Submission outcomes follow below;
these earlier zero-effect snapshots remain scoped to their individual controls. Earlier original-task PRE rejection
and immutable Submission proof remain scoped to their original locked policies.

The 22,599-byte POST-negative ZIP, SHA-256
`a95a287599a61be6ba3b4bb8e7a3d42f80350ac34889e4bf32abd04614a90617`,
passed PRE. Public preparation returned 202 `stored_pending_verification`; the
durable worker then produced ready admission `01a19992-4508-73d0-a299-1b3a8aefe4f1`.
Same-key preparation replay read `ready`. Public Submission creation and exact
replay retained Submission `01a19992-eafe-725b-8e3c-bd97e2ceeb37` and evaluation
request `01a19992-eec0-7857-93c8-466fe0562b43`.

Automatic run `01a19992-ef6b-7cb7-a0bc-7d42bce61ef2` ended
`infrastructure_failed / invalid_output`, with the task still `evaluation_pending`
and no revision or acceptance. One real author-evidence model effect completed;
its response contained duplicate JSON, omitted required schema information and
bad citations. Strict validation rejected it rather than supplying a substantive
work verdict. Read-only ArtifactStore inspection verified the retained 27,315-byte
request and 2,718-byte response against their exact custody hashes, with no
reinference. The response and original failure evidence remain unchanged.

Public Operator inspection found the exact run eligible for retry and zero
unresolved model candidates. The unchanged image was not retried. A bounded
project-image correction is in progress and unqualified; neither that working
diff nor source 0040 CI establishes a repaired deployed outcome.

The initial workspace/isolation helper stopped before HTTP because its required
foreign project did not exist; that harness failure remains retained. After the
separate fixture was prepared, the bounded source-4e workspace proof passed at
00:47:29–00:47:33 UTC on November 2: contributor work context, exact original
content and manager locked context returned 200; two other-actor reads and one
foreign-project manager read returned concealed 404. The download matched all
12,110 bytes and SHA-256
`13d789d4b8df5d6b310d844c622336f265d53d2ddc38e8aa101b67765f9f7183`.
That first other-actor case followed recorded revocation and did not prove
same-role assignment isolation.

A separate live same-role proof passed at 01:01:30–01:01:37 UTC. Grant
`01a199c5-69b5-7785-9fe6-95dd939ee232` remained active at version 1 before,
through and after the six reads. The assigned contributor's work context and
original document, plus manager locked context, returned 200/200/200; the other
same-project Submitter's work-context/document reads and foreign-project manager
read returned concealed 404/404/404. Exact original bytes/hash and immutable
lineage were preserved. The new grant was then explicitly revoked through the
public API with 200/version 2; exact replay retained revoked/version 2. These
bounded reads and grant cleanup made no paid model or task-lifecycle call.

Separately, source `54ccc01fa` passed all 106 packaged model-image tests. Its
first controlled smoke stopped on a fixture permission defect under umask 077;
that failure remains retained. Source `906d04d92` repaired fixture permissions
and projection selection, and the actual Docker smoke under umask 077 passed.
The separate controlled POST supplement also passed with receipt SHA-256
`a4eb6a52af491cff4a1f4860a42faf2e44eebf9215294d29b432efa9e62738fa`,
zero provider calls and original state preserved. The source-906 native build
passed without changing the retained deployed binaries or runtime/configuration.

Physical source-906 composition reached four completed controlled model effects,
two authenticated trials with 17 step outcomes each, and replay without another
provider call. It then **failed** exact VM-directory inventory because the engine
had created its cache-lock sentinel; database and MinIO cleanup completed. The
failed run remains failed. A later read-only probe found the sentinel regular,
0600, UID/GID 1000, zero bytes, one link and unlocked, with no matching HOME
process or retained cgroup. Source `8e42648a2` applies strict sentinel validation;
eleven focused helper tests, mutation probes and independent QA passed. The actual
source-8e offline native build passed with networking disabled and all retained
native binary hashes unchanged.

Fresh physical source-8e composition then **passed** with canonical result
`test_exit_code=0` and exact verified artifact/node-configuration hashes. It used
a controlled local provider, retained four completed model effects and two
authenticated nested trials with 17 step outcomes each, and exact replay added
zero provider calls. Owned runtime resources were removed; database and MinIO
cleanup completed. Result SHA-256 is
`344ac05b1ac4b2260246a6756be6b23f8759d56323003691a83b82f105e7e5b1`;
fixture-summary SHA-256 is
`532f46ae67c0b34240fddd0f10e512521ad4844f6408fd5dbea6edfa726bef88`.
This qualifies that controlled physical KVM composition, not a new paid POST or
real-project acceptance: the evidence explicitly records
`guide_to_contribution_proven=false` and `predecessor_material_exercised=false`.
The source-906 failure remains retained, the deployed backend remains source 4e,
and the final ContributionRecord remains pending.

Immutable Luna profiles semantic v9, trial-assessment v10 and setup v11 were
actually published. Publication does not replace the active guide/task's locked
bindings or prove a paid inference outcome. No further model cost was incurred;
settled spend remains US$5.30734734 under the unchanged US$10 cap.

At the guide 12 checkpoint, the account observation was **US$5.30734734 settled, zero reserved and
US$4.69265266 remaining** under the unchanged US$10 cap. The author-evidence call
added US$0.0042353. No Terra/Sol dispatch, budget increase or final contribution
is claimed.

Source `97681138c`, a test-only successor with the same application tree as 4e,
passed all five substantive workflows and 17 lanes: 11,620 exact unique nodes,
zero skips/deselections and complete database/MinIO cleanup. It repairs the stale
unsafe-output assertion that failed the source-4e CI lane; that superseded run
was not a full-suite pass. The 976 result does not certify pushed `0040a7b28` or
complete the live project journey.

### Bootstrap observations (October 27)

- EC2 is running with approximately 39 GiB free on its root disk. SSH was
  initially unreachable because the operator's network address changed; adding
  an exact current-address rule restored authenticated access. Existing services
  and retained databases were left unchanged.
- Candidate `ac637495f` and the previously built `5ab96251` have identical backend
  tree `49ab013bede9defca61b62c90c24b4ae8d3d2ba6`. This permits image provenance
  reuse; it does not prove the new deployment or journey has run.
- Independent inspection found the Terminal Systems recovery trial starts from
  the deliberately buggy starter rather than the repaired reference. A
  focused probe also found a failed restart-verification receipt can escape the
  deterministic contradiction guard. These are project-checker defects; a
  bounded repair is verified locally in PR #697 before genuine positive POST qualification. The setup declaration repair, live adapter repair and drill report are included in that same PR.
- The new isolated runtime now has the real pinned Python offline base: four
  verified layers, 49,063,540 total cache bytes. Cache inventory is
  `sha256:c90cfa89676434e9d0aa53509e26442dd296750fac3faa002a7d3a5241885e84`.
  This prepares the dependency; native build/execution remains unproven.
- Bootstrap release `sha256:d1ad90ecc93070f7cb6663bceebd12ed50ef25b8025240f8dc3f99730d7673ef`
  passed migrations, fresh AWS proof, native/proxy health and canonical preflight;
  API, durable workers and parser started. The subsequent combined repair and trial authority deployment is recorded below. Existing retained deployments remain untouched.
- Six distinct human fixture actors were admitted through the public verifier.
  The canonical one-time access-administrator bootstrap was used; subsequent
  service provisioning, project creation and role grants used public APIs.
  Temporary global manager creation authority was revoked after exact project
  authority was granted. This does not yet prove all negative authorization cases.
- Project `01a17c77-eb01-7945-8b6d-0fe92c2d4be7` has its public US$10 lifetime
  budget and published semantic, trial-assessment and setup model profiles.
  The account began with zero reserved and settled spend. Current live-model observations are recorded below; those initial counters are not the current balance.
- One PRE and eight POST entries were published through the public Operator
  registry endpoint with exact image and profile pins. Actual receipt identities
  are retained for trial authority and later policy approval. All nine public reads and explicit same-key HTTP replays returned the exact
  original entries. Complete approved-binding proof remains outstanding;
  publication grants no project acceptance authority.

### First actual guide execution

The combined repaired runtime was deployed under release
`sha256:382a4215c0ce9a4f82ecc3b6860d74fcf0027bdae890e87c652597a10b036540`,
with canonical trial authority
`sha256:9d91c86b76941068ac40b634170056a3ea5dfeef61cb7da8df1766848cb63117`.
Fresh AWS verification, native/proxy catalog agreement, canonical preflight and
all five application services passed. The native cache contains the real PRE,
repaired POST, trusted intake and builder entries. Original bootstrap snapshots
and business data were preserved.

Public guide creation returned `awaiting_documents`. Upload then stored the
unchanged 12,110-byte guide; the authorized public download matched every byte
and SHA-256 `13d789d4b8df5d6b310d844c622336f265d53d2ddc38e8aa101b67765f9f7183`.
The automatic durable setup delivery created attempt
`01a17caa-e435-7105-a56e-9d0c1ed29468`, initially observed as provider-unresolved
without a compilation result. Its subsequent metered recovery ended
`compilation_invalid_terminal`, as recorded below. The retained setup row's queued fields alone are not the
execution outcome: the public read correctly projects the compilation attempt.

Read-only accounting observed no setup effects and zero reserved/settled charge.
The actual native OpenAI SDK request omits OpenRouter's required usage-reporting
field; the trusted handler rejects it before preparing a paid effect. A pure
probe with the actual published profile and subject confirms that rejection and
that adding only the missing field passes. Prompt bounds, profile/tool agreement
and socket custody independently passed. The original exception stack was not
retained by sanitized runtime logging, so these discriminating boundary proofs
are distinct from a captured live stack. The following repair preserves that
failed evidence; no direct row reset or blind paid retry occurred.

### SDK repair deployment and metered recovery

Source `0659c749` adds the required OpenRouter usage field in the existing SDK
adapter. The real SDK serialization regression fails on the old adapter and
passes with the repair; the Responses control and missing-usage rejection remain
protected. The 153 affected local tests pass. Focused security, architecture,
QA/test-delta and CI-integrity reviews passed that exact source; the subsequent
`1ee11d2be` documentation-only correction received its own documentation review.

Release `sha256:75aed987966bdfe587543604ae9ba2e8e951e0643af5b9f703a4ee98dd302aaf`
passed canonical image verification, a fresh AWS proof, preflight and five-service
health. The native process and exact trial authority were preserved. Before
redelivery, a fresh read of the exact original attempt found no model slots or
effects and zero budget counters. The existing durable setup task was explicitly
redelivered with its original IDs. This was an operator delivery action, not a
claim of public manager recovery. An initial operator invocation omitted the
container entrypoint and failed to load broker configuration before publication;
it was corrected without changing product code or retrying a paid effect.

At 10:03 UTC the first actual OpenRouter call completed and settled
US$0.080238. A second call was dispatching; its US$5.544912 reservation represents
maximum permitted usage, not an incurred charge. Both calls use the existing
setup profile and the same US$10 lifetime account. By 10:06 UTC the bounded
run completed seven metered effects, settling US$0.7242128 with no remaining
reservation. Final output failed schema validation; public status is now
`compilation_invalid_terminal` with `schema_invalid`. No compilation was
accepted. Current CI independently found that the setup instruction example
fails its strict schema contract. All three actual final JSON outputs pass that
structural schema, so the example defect is distinct. The retained final output
fails four canonical dependency checks: two checker-tool dependencies name the
runner instead of the checker implementation, and two isolated-execution
dependencies name the trial proxy instead of the runner. Correcting only those
values in a private diagnostic copy reveals two missing nested-trial
dependencies. Adding only those dependencies makes the copy pass all three
validation layers against the actual guide context. The original remains
unchanged; the edited copy is not a proposal or approval. Explicit guidance is
being repaired; no new paid attempt has been started.

### Configured rubric versus policy requirement identity

Offline inspection of the unchanged retained output found all ten intended
configured checks and exact registered configurations. Seven POST requirement
names differ from their configured rubric selectors. The published request
contract permits this, but the project image incorrectly rejects those names.
This is a separate project-checker integration defect, not a reason to rename the
model's retained output or weaken Workstream validation. The bounded repair
keeps the configured rubric and local finding identifiers fixed while validating
the policy requirement identifier independently. It needs a new qualified POST
image and registrations; PRE production remains unchanged. No real POST run or
policy approval is claimed from this inspection.

### Corrected setup and manager agreement

Release `sha256:4ba75415370a84bda3c02f097eae53418942bcdddfc023385df9dbe890a649a8`
qualified the instruction and POST requirement-identity repairs at `1e32931b`.
The new POST image is
`sha256:bff40d104b6a3debe1308bd59f00fedfd7be61f83e39c4dcc1fcdf585ee8f9ee`;
eight new immutable registrations retain the original PRE registrations.

Guide `01a17d0a-cec1-786f-bf90-594f9dec5c82` stored the unchanged original
and completed real OpenRouter inference through the OpenAI Agents SDK using
`openai/gpt-5.6-terra`. The initial proposal selected older POST registrations.
A public manager correction requested the exact new registrations and missing
model/prepared-context dependencies. Its pending identifiers were rediscovered
through the public read before dispatch, rather than supplied from the creation
response. The predecessor and earlier failed attempt remain retained.

Corrected compilation `01a17d13-d490-7ec8-b403-dfb17d3c3f3e` has target digest
`sha256:25e8463dcd738c19ac0730ce43714f5dcf9a9a9266786aff51733ee47754c291`.
Independent inspection confirmed two PRE and eight POST checks against the
original guide, exact registrations, configuration, dependencies and citations.
A foreign contributor's approval request returned concealed 404 with unchanged
proposal reads. Manager PRE approval succeeded, the durable worker derived the
POST policy, and a separate manager POST approval succeeded.

- PRE policy: `01a17d16-90da-7306-b6cb-3472c9b2ccf1`.
- POST policy: `01a17d16-937f-7499-a32f-05e8490a736a`.
- Review policy: `01a17d18-46d4-708a-a4f7-ec07da0f30e2`, generation 1,
  explicitly `human_review_required=false`.
- Revision policy: `01a17d18-47b9-72ce-a0cc-8a8cba7acfaf`, generation 1,
  two rounds and a 48-hour revision window.

Public management reads confirmed both selections. At the setup checkpoint,
Finance publication and guide activation had not run. The first November 1
read-only ledger observation found the corrected compilation persisted, all four
correction effects completed, US$1.977822 settled and zero reserved. The latest
hosted checkpoint above records the subsequent activation and POST attempt; the
accounting table below records its additional charge. No budget was reset.

### Original queue package: local qualification

The genuinely authored `queue-recovery` package has a functioning buggy starter,
a general reference repair and independent expected results. Independent review
caught malformed-record and ordered-recovery defects in its initial reference;
those were repaired and their failed-before/passed-after evidence retained.
This is authoring-package correction, separate from Workstream product repair.

At this historical v2 checkpoint, the package passed 23 local controls, including three
independently staged twelve-test reference runs. The buggy starter, plausible
wrong repair, removed output and fabricated output fail their intended checks.
The actual PRE functions accept the positive and POST-negative package and
reject the PRE-negative for its missing root `instruction.md`. These are local
package/function results, not public API or native Smol results.

| Historical v2 ZIP | Bytes | SHA-256 |
|---|---:|---|
| Positive | 20,347 | `9d5b213c28b0473404bd0b2f13363b95380ecff6f74d5baecbf324757cfe47cd` |
| PRE-negative | 17,908 | `7e8030f51874e7f31c1f8d9763237e6987fe6877fd826cc7155449b96b84eaab` |
| POST-negative | 20,470 | `404ec9d61ad0eec515aa1f0aa32571fe688bf3d5eecfc741d4afcb2bb078e8b1` |

The solver-visible documented command executes without protected material.
The seventeen-step trial plan requires 470,000 ms of total/CPU allowance;
hosted build, aggregate disk/memory and measured deadline sufficiency remain
unproven. Earlier packages and observations are retained as superseded evidence.

## Current scenario matrix — November 4

Earlier scoped passes remain explicitly attributed below; they do not replace
missing current-project outcomes.

`NOT RUN` denotes missing current-run evidence, not an absent implementation. Each changed status requires an observed outcome and bounded evidence reference. Use `PASS`, `FAIL`, `BLOCKED`, `IN PROGRESS` or `NOT RUN`; a blocker must identify its unavailable prerequisite. Retain failed observations and exact candidate attribution.

| Capability and concrete scenario | Required observable outcome | Result | Evidence / remaining limit |
|---|---|---|---|
| Identity/admission: admit distinct PM, Finance, Operator and contributor humans through the verifier | Identity alone supplies no project authority; explicit grants control actions | PASS | Six distinct fixture actors admitted; canonical grants issued through public APIs. Unrelated contributor denied the guide reads below. Simulated issuer only. |
| Authorization: unrelated actor/project/resource, revoked grant/link and stale replay | Deny without unauthorized effects or private disclosure; replay checks current authority | IN PROGRESS | Finance task-context and Submission-history requests returned concealed 404. Six further public GETs proved an existing revoked Submitter receives concealed task denial with authorized controls; active same-role substitution, identity-link revocation and stale mutation replay remain. |
| Guide custody: create/upload unchanged original and download through public reads | Exact digest/size/bytes and unrelated-actor denial; duplicate upload retains original custody | PASS | Manager detail, original download and setup read returned 200; each corresponding unrelated-contributor read returned concealed 404. Same-key upload returned 202, replayed=true, identical document/hash/byte count. |
| Async setup: actual assigned originals/example reach durable worker and parser | Source-backed advisory PRE/POST specifications and sufficiency; no injected result or image selection | PASS | Guide 26 normal setup produced three PRE/six POST suggestions and zero warnings; actual ART-verified request keys are exactly material/task_examples. Guide 25 explicit PM-feedback correction proof remains retained. |
| PM correction and agreement: inspect current proposal against guide and packages | Supported successor preserves earlier evidence; PM resolves source disagreements before approval | PASS | Guide 25 corrected proposal has two PRE/seven POST suggestions; the independent human choice has two PRE/eight POST attachments. Exact image-policy match, separate approvals and replays passed. |
| Registry and model configuration: register/read/replay exact configured capabilities | Immutable image/config/profile identities and fresh Operator authority; registration alone does not activate | PASS | Eight new immutable POST registrations for the exact qualified `24b974b3` image `4d8de652` passed public publication/read/replay; predecessor registrations remain retained. Human phase attachments are independently approved; setup does not choose images. |
| Policy/activation: separate PRE/POST approval, review/revision configuration and Finance publication | Exact complete locked context before activation/READY; false policy explicitly approved | PASS | The current guide's human-selected PRE/POST policies were separately approved and activated with exact replay. Earlier guide 19 approvals remain historical. |
| Task creation/import/screen/release: import original briefs and exercise manager operations | Exact task/source/batch receipts; locks preserved; replay creates no duplicates | IN PROGRESS | Guide 26 fresh task create/screen/release/claim and exact replays passed. Earlier five-task import remains historical; wider current batch scenarios remain separate. |
| Contributor workspace: discover/read task, claim and obtain locked guide/context | Exact grant and assignment authority; downloaded original is verified; other assignees deny | IN PROGRESS | Guide 26 claim/replay immediately reached in_progress under the deployed strict public task contract. Wider isolation and revocation scenarios remain. |
| Default ZIP intake: unsafe ZIP/secret/unchanged-work negative plus warning-only inputs | Blocking feedback creates no Submission and preserves valid working assignment; warnings do not block | IN PROGRESS | Guide 25 traversal, secret-canary, symlink, malformed-ZIP and compression-ratio negatives plus exact replays passed (ten intended 422 responses), with no admission/Submission/POST/model dispatch and the same working assignment. The size case proves ratio only. Current unchanged-work/warning-only proof remains separate. |
| Project PRE: genuine layout/metadata negatives and corrected package | Actionable intended findings before Submission; exact ready admission only after complete pass | IN PROGRESS | Guide 26 missing-instruction negative and replay created no Submission; a later package passed selected PRE/S3 verification into ready admission and immutable Submission. Guide 25 detailed negative/zero-effect snapshots remain retained. Wider metadata/failure controls remain. |
| Successful preparation/replay and immutable Submission | Same bytes/hash/size/manifest and locked lineage; replay reuses IDs without rerunning effects | PASS | Guide 26 verified S3 admission and immutable Submission `01a1a470-08a1-7afc-a7ff-55ffabdc2a19` v1/exact replay passed. Subsequent infrastructure failure supplies no work verdict; guide 25 receipts remain historical. |
| Durable POST: real positive and substantive negative package | Exactly one current result with intended findings; automatic dispatch uses selected image/material | PASS | Guide 28 v1 completed with a blocking incident_summary_counts finding; corrected v2 completed without findings. Both ran the actual external image over verified S3 material; no model or injected result. |
| Model/trial/material custody: approved profile, real assessment and isolated reference/verifier execution | Correct exact material roles, verified trial receipts and private ART call evidence; no passing substitutes | IN PROGRESS | Predecessor `24b974b3` image `4d8de652` retains its controlled qualification. Guide 26 live POST had export capacity failure/all 17 steps skipped. Separately, image `52659960` retry2 capacity probe passed with 100,000 entries/original 64 MiB: ten executed steps, seven grounded work skips, no resource failures, controlled replay/cleanup. The negative probe disabled semantic assessment. Separate standard positive qualification on `adcf35a5` passed in 173.08 seconds with two trials/four controlled effects/no paid calls; zero additional replay calls and complete owned runtime/PostgreSQL/MinIO cleanup. Live work verification remains pending. |
| Model replay/recovery: duplicate delivery or permitted successor uses retained effect | No second paid create; immutable slots and once-only settlement; ambiguous effect remains held | IN PROGRESS | Native-only checker retry reattached the original completed effect without another charge; unresolved/known-no-effect recovery variants remain. |
| False-policy success: governed acceptance and applicable conditional awards | One shared FinalAcceptance, exact submitter ContributionRecord and frozen award set atomically; no Review/reviewer contribution | PASS | Guide 28 v2 reached one FinalAcceptance and submitter ContributionRecord, with no Review/reviewer contribution. Public contributor/manager exports match exact artifact, policy and assignment. The unpaid policy correctly creates no award; paid awards are not proved here. |
| True-policy guard/handoff regression | Eligible passing evidence reaches review_pending without acceptance/contribution/award effects; human runtime stays deferred | NOT RUN | — |
| Work failure and corrected replacement ZIP | Exact cause routes needs_revision when allowed; successor preserves predecessor/history and locked rules | PASS | Guide 28 v1 needs_revision and ready revision context were read publicly. A genuinely recounted ZIP preserved source bytes and linked v2 to v1 and actual feedback; v2 was accepted. |
| Revision limits/windows: zero/positive caps, final failure, setup pause/repair and timeout/reclaim | Correct assignment rounds/database-clock window; final failure or timeout retains evidence and returns ready; no artificial renewal | NOT RUN | — |
| Coverage-incomplete routing | No false auto-acceptance; false returns needs_revision without spent round, true retains review_pending | NOT RUN | — |
| Known infrastructure failure: discover and reason-bound Operator retry | Original Submission retained, no contributor revision spent; fresh authority and stable replay | IN PROGRESS | Earlier public retry/replay reused the original completed paid effect without revision penalty. Guide 17 and guide 19 retain separate invalid-output runs without a work verdict; guide 24's failed run also remains immutable. No guide 19 or guide 24 retry or model resampling is claimed. Wider failure/recovery variants remain. |
| ART verification failure and same-job recovery | Bound one actual interruption before terminal commit, then normal retry yields the same job and exact receipt/admission lineage | NOT RUN | Guide 17's observer aborted on query-proof mismatch. The later guide 19 task's observer rejected PostgreSQL's full-mask address representation before cancellation. Independent observation confirmed the holder was gone and both original queues restored; its job verified normally at generation 1/attempt 1 with one receipt and admission. Neither abort proves recovery. |
| UNKNOWN request interruption | Source-specific inspection classifies committed/no-effect/unresolved; only proven-safe recovery invokes existing owner | NOT RUN | — |
| UNKNOWN completion interruption | Committed outcome verified without repeated effects; unresolved source/UNKNOWN child remains held | NOT RUN | — |
| Acceptance commit/ack loss and duplicate broker delivery | Exact acceptance/contribution/award set unchanged; retained original attempts immutable | IN PROGRESS | Exact public submission replay before and after acceptance returns the same admission, Submission v2 and evaluation request. Explicit lost-ack/broker-redelivery injection is not claimed. |
| Public contribution JSON/CSV and task audit reads | Exact source/award facts, current self/export/audit authority and complete bounded traversal; no external-payment claim | PASS | Contributor and manager JSON exports agree exactly for accepted v2, including FinalAcceptance/routing, artifact hash, assignment and locked policy. Public Submission/checker history remains readable after acceptance; active work-context correctly closes with concealed 404. Contributor/manager CSV exports also agree exactly with the JSON identities and hashes. A dedicated project Audit Authority grant exposed all six task events; before grant, foreign contributor and after revocation returned concealed 404. The owned temporary grant was revoked. |
| Artifact diagnosis/verification retry on AWS | Supported bounded Operator reads/retry preserve original custody and do not disclose private coordinates | IN PROGRESS | On d01, 29 public reads passed, including exact Operator DTOs and paired contributor denials for binding/content/replica/receipt/job/timeline surfaces. Actual verification interruption and same-job recovery remain NOT RUN. |
| AWS failure/isolation/retention | Intended access only; denied/uncertain writes/reads and interrupted verification remain recoverable; retained facts survive | IN PROGRESS | Exact-release canonical readiness/runtime-immutability/negative-access probes passed; submission bytes reached verified artifact custody. Wider interruption/retention matrix remains. |
| Native deployment and representative limits | Exact Smol/images, read-only verified material, measured CPU/memory/PID/disk/output/time and bounded admission | IN PROGRESS | Current release `26591f3e` runs backend `1b947dfe`/schema `0067` and runs the unchanged native binary as PID `2781660`; supplemental image `4e5b9c71` passed the real small-task PRE/POST path. Retry2 controlled proof exported 45,435,904 bytes below original 64 MiB with 100,000 entries and unchanged 2 GiB disk; no 256 MiB deployment is needed. Separate standard positive qualification and owned-service cleanup passed; immutable profile v2/image `52659960` runtime adoption is committed; guide 27 ran POST and one retry, both infrastructure failed. Guide 28 subsequently reached the accepted small-project outcome. |
| Missing runtime/cache, cancellation and service recovery | Correct infrastructure classification, no false completion, owned scratch/VM/cgroup cleanup and capacity reuse | NOT RUN | — |
| Secured diagnostics and collector outage | API/job correlation without documents/tokens/model bodies; enabled-export outage preserves product correctness | NOT RUN | Recorded release configuration disables OTLP export; absence is not outage proof. Current-service privacy/correlation remains unexercised. Optional collector deployment is not a first-journey prerequisite; exporter failure tests remain source-level evidence. |
| Controlled drain/restart and forward migration | Producers and Celery workers drain in supported order; immutable facts survive; no protected migration downgrade | PASS | The final accepted journey survived migration 0067 and restart of all five application services. Full retained-row comparison passed before Beat resumption; exact public contribution and history reads passed afterward. Abrupt interruption/recovery remains separately unproven. |
| Final-data backup/ordinary isolated restore | Database metadata, audit, policies, task history, effects and contribution/award facts remain intact; object bytes retain separate S3 custody | PASS | After forward migration 0067, a fresh snapshot-consistent backup restored normally without SQL patches or disabled guards. All 134 table counts/digests and exact accepted contribution lineage matched; isolated container cleanup passed. See the November 4 restore evidence above. |

CLI, MCP and TUI surfaces are implemented separately. Record any exercised client and binary/source identity explicitly; backend scenarios do not certify every client surface. Optional interfaces are not additional first-journey prerequisites.

## Paid accounting and evidence privacy

| Account boundary | Required treatment | Current rehearsal result |
|---|---|---|
| Original Terminal Systems rehearsal | Earlier uncertain setup spend remains retained separately; do not reset it or mark it free | Unresolved historical spend; no new dispatch against this allowance |
| Separately authorized model-only qualification | Preserve its existing project/account and US$0.016527 settled ledger. A model-plus-trial continuation reuses that account/headroom; no automatic new allowance or transfer to a fresh real-project account | NOT RUN |
| New complete-project drill | User explicitly authorized an additional US$10 total on 2026-10-27, across setup, POST and retries; one new account, immutable 10,000,000,000-nanodollar ceiling | Historical guide 24/25 cutoffs remain above. At 02:52:03 UTC November 4 after guide 26 POST: 8,757,024,460 settled nanodollars, zero reserved, 1,242,975,540 remaining under the unchanged 10,000,000,000 cap. |
| New current-run dispatch | Record pricing provenance, exact account/effect IDs, starting/ending settled and reserved totals and remaining authorized headroom. Stop paid dispatch on ambiguity or exhaustion | Guide 26 setup settled US$0.050222340; its nine POST calls settled US$0.133162800 and ended infrastructure_failed/invalid_output. Native qualification used a controlled provider. No reset, free retry or completed work verdict is inferred. |

Pinned-rate ledger settlement is not provider-invoice reconciliation. An unresolved paid effect is a held effect, not a free retry. See [shared accounting](../../.commitrail/changes/checker-model-runtime.md) and [the later separate qualification authority](../../.commitrail/changes/hosted-smol-project-execution.md#live-model-qualification-authority).

Keep keys, JWTs, subjects, request headers, credentials, connection/provider coordinates, raw private artifacts and model request/response bodies outside public reports and Git. Retain private evidence under access control; publish only safe IDs/hashes and bounded outcomes. Preserve earlier failed attempts and product evidence. Cleanup is limited to explicitly owned disposable resources; record owned process/resource absence and retained data separately.

## Release and issue reconciliation

| Gate | Current-run disposition |
|---|---|
| #576: actual PM agreement, fresh proposal and independently checked packages/material | PASS for the small project — guide 28 source-only setup, human image attachments and separate approvals/activation passed; real wrong/correct packages produced expected POST outcomes. Earlier complex-project/correction evidence remains retained. |
| #581: terminal retry and full request/completion/acceptance interruption matrix | IN PROGRESS — claim/Submission replay and earlier governed retry evidence remain retained. The guide 17 ART fault aborted before cancellation with successful queue cleanup; its recovery is NOT RUN. Actual UNKNOWN request/completion/acceptance and applicable failure/retry proof remain. |
| #582: candidate AWS activation, public exact-byte custody, failure recovery and final-data restore | IN PROGRESS — current additive rollout preserved retained data/AWS custody. Guide 26 verified ready admission, immutable Submission v1 and exact replay passed. Artifact interruption/recovery, wider isolation/final-data restore remain. |
| #583: exact native deployment, limits, readiness/cleanup, diagnostics/outage and operations | IN PROGRESS — current release ee22e22e retains backend466/schema0066 and adds incident-summary image4e5b9c71. AWS/health/retention proofs passed; guide 28 ran real PRE/POST to acceptance. Earlier image52659960 qualification remains retained. Remaining operating/recovery scenarios are not certified. |
| #555: connected real-project public/durable journey and exact final facts | PASS for the incident-summary path — guide 28 setup/activation/claim, PRE rejection/noSubmission, v1 POST failure, genuine corrected v2, shared FinalAcceptance and exact public JSON/CSV contribution evidence passed. No fabricated Review; unpaid/no awards. Wider release/recovery checks remain under their own rows. |
| Exact candidate's required CI, focused defect regressions and applicable internal reviews | IN PROGRESS — exact a4afa8d75 passed 11,533 unique tests with zero skips/deselections and completed cleanup. Later MVP changes have six passing local/packaged tests and focused review; fresh final-head CI is required. Earlier evidence does not certify this candidate. CodeRabbit substantive review is not inferred. |
| Stale wording/Markdown links, affected roadmap reconciliation and local sheet constraints if exports exist | Current documentation checks passed; affected roadmap claims reconciled. No local sheet exports are present. Recheck after further changes. |

No issue is closed by this draft or by a child implementation merge. Complete release reporting requires every applicable outcome above to have current evidence, no unresolved journey blocker, and documented operating/recovery limits. Unimplemented/deferred human review, payment fulfillment and reputation must remain clearly identified; they are not silently certified by the automated contribution path.
