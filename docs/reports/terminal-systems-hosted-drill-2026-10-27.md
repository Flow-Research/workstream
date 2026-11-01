# Terminal Systems hosted first-journey drill — 2026-10-27

**Current rehearsal: IN PROGRESS. No real-project release pass is claimed.** This report implements the evidence structure for [#555](https://github.com/Flow-Research/workstream/issues/555) and the [bounded rehearsal record](../../.commitrail/changes/terminal-systems-repaired-recovery-trial.md#authorized-hosted-drill-and-reporting). On November 1, deployed source `a3fc1f196` completed guide activation, task import and claim that immediately starts work, PRE-negative rejection/recovery, and verified immutable Submission creation/replay. Automatic POST ended as an infrastructure failure before a work verdict. The Submission remains pending; no acceptance or contribution is claimed. Repairs at `4ec4cbb58` have focused review and tests, but are not yet deployed or qualified by this live journey.

The target is original project guide -> approved locked policies -> released task -> claim (starts work) -> ZIP intake feedback or immutable Submission -> durable POST -> governed outcome -> exact contribution evidence. Use explicitly PM-approved `human_review_required=false`. Preserve default-true handoff guards; live human review, payment delivery, reputation, frontend and claim expiry/skip remain deferred. #496 is excluded.

## Release and project provenance

| Required binding | Current-run value |
|---|---|
| Executed source commit and exact review/CI evidence | `1e32931b` for setup/approvals; `a3fc1f196` for the November 1 activation/claim/Submission checkpoint. Its required CI passed after one unchanged-head schema-lane rerun. Native/prompt repair `4ec4cbb58` still needs deployment and final-head CI. |
| Backend API, Celery worker/Beat, parser and proxy image digests and fixture derivatives | November 1 agents derivative `sha256:f72d1f1aa559ef33f6c4a90451b68337e7f87b3131f698321a5789c55803a951` for all five; public fixture CA is the only derivative change. Both SDK image inventories verified; this run uses the OpenAI Agents SDK. |
| Native service, Smol, guest and configured cache/archive/config digests | Smol 1.31.4; service `sha256:5e5760b898017453feb821a24066dc78201249ce39a1eb2f3eb27fffef100ba0`; five cache entries and three trial bindings passed preflight. First live POST invoked the model but created no Trial; repaired native service remains unqualified. |
| Migration head; non-secret release/configuration fingerprints; Celery worker topology | `0065_claim_starts_work`; one prefork Celery worker with concurrency 2 and one Beat; native config `sha256:72babee2dcc2773f2968a1f9dbd3c5829385918e278c126bd319d479daf3c208`. |
| Identity qualification; issuer/key configuration digest, without subject/token | Authorized simulated HTTPS/JWKS issuer through the actual verifier; six distinct admitted actors. JWKS digest `sha256:70718dcfcb5c4052d01764b05a73e1eada122d945f88f4342395f27e23be1ded`. No production Flow issuer certification. |
| AWS candidate activation/freshness and non-secret proof fingerprint | Release `sha256:9b5a8ed2fb998539ac850adc7f95eb6b444a2ab80ee65390bdee5983b22a559c` passed canonical readiness, runtime immutability and negative-access probes. Namespace remains `sha256:cf487c3b9b8ae93579939f80cb245ca79c25a5641fb3d5ce461abc16f0f4bad7`; freshness is time-bounded. |
| Original guide/task-example/import/positive/negative package SHA-256 values | Guide/ZIP fingerprints below. Public task import consumed 14,710 verified bytes, SHA-256 `a719390aebd455d64e3f519c5a3c5fe110f147135623247844dd846041179849`, creating five tasks. |
| Project/guide/setup/correction/result IDs and requirement mapping | Project `01a17c77-eb01-7945-8b6d-0fe92c2d4be7`; current guide `01a17d0a-cec1-786f-bf90-594f9dec5c82`; corrected compilation `01a17d13-d490-7ec8-b403-dfb17d3c3f3e`. Earlier failed guide remains retained. |
| Registry/config/model-profile IDs/digests and exact approved bindings | Original PRE and eight updated POST entries registered/read/replayed; updated receipt manifest `sha256:c99e833020d68f6f5e7a142afe9014b634a311fa3324e7e01a1cab6e5f9c2a9b`. Corrected proposal bindings independently inspected and approved. |
| PRE/POST approvals; ReviewPolicy, revision and ContributionPolicy versions; activation/LIVE identities | Guide activation `01a196fa-6693-7fd4-ab90-59a59b7b440d`; unpaid ContributionPolicy version `01a196f9-8924-7c6a-ab78-6aefa0eeb1e6`. Existing AUTH-gated Operator tool committed shadow generation 1, then live generation 2. |
| Task/assignment/Submission/checker/routing/acceptance/contribution/award IDs | Task `01a196fd-4957-751a-b0c2-dd70e71ffe7a`; assignment `01a196fe-6a94-7490-a624-9959109b54fa`; Submission `01a19703-0398-7d55-a33d-58658c9b0a50`; failed POST run `01a19703-07d0-7cc9-8cec-1e1da215c121`. No routing, acceptance, contribution or award row at the bounded snapshot below. |
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

## Current capability scenarios

### Latest hosted checkpoint — November 1

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
`pre_submission_checker_failed`. The other package passed PRE, then worker
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
Focused tests and internal reviews pass; live repair qualification remains.

The private task driver initially used the administrative grant route for a
submitter and omitted the release reason; both requests were rejected. Correct
project-manager role issuance and a reasoned release subsequently succeeded.
These are retained operator-driver errors, not product authorization bypasses.

No substantive POST work verdict, corrected successor, final acceptance or
ContributionRecord is yet proven. The unpaid policy permits proof of the exact
empty applicable award set only, not positive compensation or fulfillment.

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

The current v2 package passed 23 local controls, including three
independently staged twelve-test reference runs. The buggy starter, plausible
wrong repair, removed output and fabricated output fail their intended checks.
The actual PRE functions accept the positive and POST-negative package and
reject the PRE-negative for its missing root `instruction.md`. These are local
package/function results, not public API or native Smol results.

| Current ZIP | Bytes | SHA-256 |
|---|---:|---|
| Positive | 20,347 | `9d5b213c28b0473404bd0b2f13363b95380ecff6f74d5baecbf324757cfe47cd` |
| PRE-negative | 17,908 | `7e8030f51874e7f31c1f8d9763237e6987fe6877fd826cc7155449b96b84eaab` |
| POST-negative | 20,470 | `404ec9d61ad0eec515aa1f0aa32571fe688bf3d5eecfc741d4afcb2bb078e8b1` |

The solver-visible documented command executes without protected material.
The seventeen-step trial plan requires 470,000 ms of total/CPU allowance;
hosted build, aggregate disk/memory and measured deadline sufficiency remain
unproven. Earlier packages and observations are retained as superseded evidence.

`NOT RUN` denotes missing current-run evidence, not an absent implementation. Each changed status requires an observed outcome and bounded evidence reference. Use `PASS`, `FAIL`, `BLOCKED`, `IN PROGRESS` or `NOT RUN`; a blocker must identify its unavailable prerequisite. Retain failed observations and exact candidate attribution.

| Capability and concrete scenario | Required observable outcome | Result | Evidence / remaining limit |
|---|---|---|---|
| Identity/admission: admit distinct PM, Finance, Operator and contributor humans through the verifier | Identity alone supplies no project authority; explicit grants control actions | PASS | Six distinct fixture actors admitted; canonical grants issued through public APIs. Unrelated contributor denied the guide reads below. Simulated issuer only. |
| Authorization: unrelated actor/project/resource, revoked grant/link and stale replay | Deny without unauthorized effects or private disclosure; replay checks current authority | IN PROGRESS | Finance task-context and Submission-history requests returned concealed 404; revoked/foreign-project and stale-authority cases remain. |
| Guide custody: create/upload unchanged original and download through public reads | Exact digest/size/bytes and unrelated-actor denial; duplicate upload retains original custody | PASS | Manager detail, original download and setup read returned 200; each corresponding unrelated-contributor read returned concealed 404. Same-key upload returned 202, replayed=true, identical document/hash/byte count. |
| Async setup: actual assigned originals/example reach durable worker and parser | Source-backed PRE/POST proposal, sufficiency and explicit gaps; no injected result | PASS | Earlier schema-invalid attempt retained; fresh guide setup and explicit manager correction produced the persisted, independently inspected compilation above. |
| PM correction and agreement: inspect current proposal against guide and packages | Supported successor preserves predecessor; required uncovered checks block approval/activation | PASS | Public correction, read-discovered dispatch and exact source/registration inspection completed; predecessor retained. |
| Registry and model configuration: register/read/replay exact configured capabilities | Immutable image/config/profile identities and fresh Operator authority; registration alone does not activate | PASS | Nine public registry registrations, reads and same-key replays retain exact identities. Profiles published against the one project budget. Corrected project bindings received separate PRE/POST approval. |
| Policy/activation: separate PRE/POST approval, review/revision configuration and Finance publication | Exact complete locked context before activation/READY; false policy explicitly approved | PASS | Public approvals, false review/revision selections, unpaid Finance publication, readiness and exact guide activation/readback passed on a3fc1f196. |
| Task creation/import/screen/release: import original briefs and exercise manager operations | Exact task/source/batch receipts; locks preserved; replay creates no duplicates | IN PROGRESS | Five tasks imported from verified original bytes; queue recovery screened/released with exact locked context. Import/release replay remains unexercised. |
| Contributor workspace: discover/read task, claim and obtain locked guide/context | Exact grant and assignment authority; downloaded original is verified; other assignees deny | IN PROGRESS | Public claim/context and exact replay passed; independent DB proof confirms one assignment/event and equal assignment/start time. Full contributor document-download/isolation matrix remains. |
| Default ZIP intake: unsafe ZIP/secret/unchanged-work negative plus warning-only inputs | Blocking feedback creates no Submission and preserves valid working assignment; warnings do not block | NOT RUN | — |
| Project PRE: genuine layout/metadata negatives and corrected package | Actionable intended findings before Submission; exact ready admission only after complete pass | IN PROGRESS | Missing-instruction ZIP rejected without admission/Submission; public discovery and same-key replay recovered a lost response. POST-negative ZIP passed PRE. Other negatives remain. |
| Successful preparation/replay and immutable Submission | Same bytes/hash/size/manifest and locked lineage; replay reuses IDs without rerunning effects | PASS | Public preparation/discovery/replay and Submission/replay passed. Independent exact admission/replica/hash/size/lineage snapshot corroborated the durable worker verification; no separate reviewer object fetch claimed. |
| Durable POST: real positive and substantive negative package | Exactly one current result with intended findings; automatic dispatch uses selected image/material | BLOCKED | Automatic POST ran but first resource ended as infrastructure failure. Native relay and numbered-source repairs require live qualification before a work verdict. |
| Model/trial/material custody: approved profile, real assessment and isolated reference/verifier execution | Correct exact material roles, verified trial receipts and private ART call evidence; no passing substitutes | IN PROGRESS | First model effect completed with retained request/response and charge. No Trial or final assessment was created; required nested execution remains unproven. |
| Model replay/recovery: duplicate delivery or permitted successor uses retained effect | No second paid create; immutable slots and once-only settlement; ambiguous effect remains held | NOT RUN | — |
| False-policy success: governed acceptance and applicable conditional awards | One shared FinalAcceptance, exact submitter ContributionRecord and frozen award set atomically; no Review/reviewer contribution | NOT RUN | — |
| True-policy guard/handoff regression | Eligible passing evidence reaches review_pending without acceptance/contribution/award effects; human runtime stays deferred | NOT RUN | — |
| Work failure and corrected replacement ZIP | Exact cause routes needs_revision when allowed; successor preserves predecessor/history and locked rules | NOT RUN | — |
| Revision limits/windows: zero/positive caps, final failure, setup pause/repair and timeout/reclaim | Correct assignment rounds/database-clock window; final failure or timeout retains evidence and returns ready; no artificial renewal | NOT RUN | — |
| Coverage-incomplete routing | No false auto-acceptance; false returns needs_revision without spent round, true retains review_pending | NOT RUN | — |
| Known infrastructure failure: discover and reason-bound Operator retry | Original Submission retained, no contributor revision spent; fresh authority and stable replay | IN PROGRESS | Submission/assignment retained, no revision or acceptance effects; public Operator retry discovery passed. No retry dispatched at this checkpoint. |
| UNKNOWN request interruption | Source-specific inspection classifies committed/no-effect/unresolved; only proven-safe recovery invokes existing owner | NOT RUN | — |
| UNKNOWN completion interruption | Committed outcome verified without repeated effects; unresolved source/UNKNOWN child remains held | NOT RUN | — |
| Acceptance commit/ack loss and duplicate broker delivery | Exact acceptance/contribution/award set unchanged; retained original attempts immutable | NOT RUN | — |
| Public contribution JSON/CSV and task audit reads | Exact source/award facts, current self/export/audit authority and complete bounded traversal; no external-payment claim | NOT RUN | — |
| Artifact diagnosis/verification retry on AWS | Supported bounded Operator reads/retry preserve original custody and do not disclose private coordinates | NOT RUN | — |
| AWS failure/isolation/retention | Intended access only; denied/uncertain writes/reads and interrupted verification remain recoverable; retained facts survive | IN PROGRESS | Exact-release canonical readiness/runtime-immutability/negative-access probes passed; submission bytes reached worker-verified custody. Wider interruption/retention matrix remains. |
| Native deployment and representative limits | Exact Smol/images, read-only verified material, measured CPU/memory/PID/disk/output/time and bounded admission | IN PROGRESS | Pinned Smol/cache/authority and preflight passed; actual model-backed POST ran. Real nested trial and representative measured resource limits remain unproven. |
| Missing runtime/cache, cancellation and service recovery | Correct infrastructure classification, no false completion, owned scratch/VM/cgroup cleanup and capacity reuse | NOT RUN | — |
| Secured diagnostics and collector outage | API/job correlation without documents/tokens/model bodies; collector outage preserves product correctness | NOT RUN | — |
| Drain/restart and forward recovery | Producers and Celery workers drain in supported order; immutable facts survive; no protected migration downgrade | IN PROGRESS | November 1 controlled migration/transport rollouts preserved retained rows and restored all five roles. Full final-journey drain/recovery remains. |
| Final-data backup/ordinary isolated restore | Guide/Submission bytes, audit, policies, task history, effects and contribution/award facts remain intact | NOT RUN | — |

CLI, MCP and TUI surfaces are implemented separately. Record any exercised client and binary/source identity explicitly; backend scenarios do not certify every client surface. Optional interfaces are not additional first-journey prerequisites.

## Paid accounting and evidence privacy

| Account boundary | Required treatment | Current rehearsal result |
|---|---|---|
| Original Terminal Systems rehearsal | Earlier uncertain setup spend remains retained separately; do not reset it or mark it free | Unresolved historical spend; no new dispatch against this allowance |
| Separately authorized model-only qualification | Preserve its existing project/account and US$0.016527 settled ledger. A model-plus-trial continuation reuses that account/headroom; no automatic new allowance or transfer to a fresh real-project account | NOT RUN |
| New complete-project drill | User explicitly authorized an additional US$10 total on 2026-10-27, across setup, POST and retries; one new account, immutable 10,000,000,000-nanodollar ceiling | November 1 observation after first POST call: US$2.021551 settled, US$0 reserved, US$7.978449 remaining against the unchanged cap |
| New current-run dispatch | Record pricing provenance, exact account/effect IDs, starting/ending settled and reserved totals and remaining authorized headroom. Stop paid dispatch on ambiguity or exhaustion | Earlier failure retained. Setup/correction and one POST model effect completed in the same account; POST added US$0.043729. No retry or budget reset at this checkpoint. |

Pinned-rate ledger settlement is not provider-invoice reconciliation. An unresolved paid effect is a held effect, not a free retry. See [shared accounting](../../.commitrail/changes/checker-model-runtime.md) and [the later separate qualification authority](../../.commitrail/changes/hosted-smol-project-execution.md#live-model-qualification-authority).

Keep keys, JWTs, subjects, request headers, credentials, connection/provider coordinates, raw private artifacts and model request/response bodies outside public reports and Git. Retain private evidence under access control; publish only safe IDs/hashes and bounded outcomes. Preserve earlier failed attempts and product evidence. Cleanup is limited to explicitly owned disposable resources; record owned process/resource absence and retained data separately.

## Release and issue reconciliation

| Gate | Current-run disposition |
|---|---|
| #576: actual PM agreement, fresh proposal and independently checked packages/material | IN PROGRESS — original guide agreement/activation completed; repaired checker selection and complete native package qualification remain. |
| #581: terminal retry and full request/completion/acceptance interruption matrix | IN PROGRESS — claim/Submission replay and lost PRE-response recovery passed; governed POST retry and later interruption cases remain. |
| #582: candidate AWS activation, public exact-byte custody, failure recovery and final-data restore | IN PROGRESS — current release probes and verified immutable Submission passed; wider failure/restore matrix remains. |
| #583: exact native deployment, limits, readiness/cleanup, diagnostics/outage and operations | BLOCKED — native EOF repair and representative Trial/operations qualification remain. |
| #555: connected real-project public/durable journey and exact final facts | BLOCKED — first POST ended as infrastructure failure; no final contribution outcome. |
| Exact candidate's required CI, focused defect regressions and applicable internal reviews | IN PROGRESS — a3fc1f196 required CI passed; 4ec4cbb58 repair has focused tests/reviews, final-head CI and live qualification pending. |
| Stale wording/Markdown links, affected roadmap reconciliation and local sheet constraints if exports exist | NOT RUN |

No issue is closed by this draft or by a child implementation merge. Complete release reporting requires every applicable outcome above to have current evidence, no unresolved journey blocker, and documented operating/recovery limits. Unimplemented/deferred human review, payment fulfillment and reputation must remain clearly identified; they are not silently certified by the automated contribution path.
