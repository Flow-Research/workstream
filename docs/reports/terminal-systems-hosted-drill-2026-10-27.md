# Terminal Systems hosted first-journey drill — 2026-10-27

**Current rehearsal: IN PROGRESS. No real-project release pass is claimed.** This report implements the evidence structure for [#555](https://github.com/Flow-Research/workstream/issues/555) and the [bounded rehearsal record](../../.commitrail/changes/terminal-systems-repaired-recovery-trial.md#authorized-hosted-drill-and-reporting). On November 1, deployed source `a3fc1f196` completed guide activation, task import and claim that immediately starts work, PRE-negative rejection/recovery, and verified immutable Submission creation/replay. Automatic POST ended as an infrastructure failure before a work verdict. The Submission remains pending; no acceptance or contribution is claimed. The native repair at `4ec4cbb58` is now deployed: authorized retry/replay retained the original paid response and exposed its actual `invalid_output` without a second charge. Guide6 generation 2 persisted corrected dependencies, but semantic finding-code discrepancies kept approval on hold. Generation 3 remains provider-uncertain with one prepared effect retained. Three Luna profiles and nine new registry versions are published; their runtime rollout is complete. Guide7 setup returned a known invalid result; its six Luna calls settled US$0.0872514. The safe-candidate correction repair is now deployed and verified in guide8. Its final result failed different configuration and PRE-specification rules; the clearer instruction/example is implemented but its live qualification remains.

The target is original project guide -> approved locked policies -> released task -> claim (starts work) -> ZIP intake feedback or immutable Submission -> durable POST -> governed outcome -> exact contribution evidence. Use explicitly PM-approved `human_review_required=false`. Preserve default-true handoff guards; live human review, payment delivery, reputation, frontend and claim expiry/skip remain deferred. #496 is excluded.

## Release and project provenance

| Required binding | Current-run value |
|---|---|
| Executed source commit and exact review/CI evidence | `1e32931b` for setup/approvals; `a3fc1f196` for the November 1 activation/claim/Submission checkpoint. Its required CI passed after one unchanged-head schema-lane rerun. Native recovery ran at `4ec4cbb58`; guide8 ran the adapter correction at `e8d6980ac`. Required CI for `dc15dc828` passed all 11,595 selected nodes across 17 lanes, with zero skips/deselections and complete cleanup. Head `b5d21c4db` subsequently failed two stale correction-format test assertions; all other lanes passed. The bounded test repair passes focused checks but awaits fresh hosted verification. Live contribution qualification remains incomplete. |
| Backend API, Celery worker/Beat, parser and proxy image digests and fixture derivatives | Current `e8d6980ac` agents derivative `sha256:1474b7c0b5447f1aff019a0889e7dc9eb29fcc8193f2d103753110600c5f143b` for all five; public fixture CA is the only derivative change. Both SDK image inventories verified; this run uses the OpenAI Agents SDK. |
| Native service, Smol, guest and configured cache/archive/config digests | Smol 1.31.4; service `sha256:34be988c12481b575467ea4db6eb337711ec3732f8e16121f0485fb86a72c43d`; native-only retry reused the retained model response; no Trial yet. The completed Luna rollout preserves six retained cache entries and extends six existing authority contexts to nine; substantive Trial qualification remains pending. |
| Migration head; non-secret release/configuration fingerprints; Celery worker topology | `0065_claim_starts_work`; one prefork Celery worker with concurrency 2 and one Beat; native-only checkpoint config `sha256:72babee2dcc2773f2968a1f9dbd3c5829385918e278c126bd319d479daf3c208`; active Luna config `sha256:570f17c44fccfdb8f413e41ad85fc0e9a72637379ed45777d07d8896e7e937fe`. |
| Identity qualification; issuer/key configuration digest, without subject/token | Authorized simulated HTTPS/JWKS issuer through the actual verifier; six distinct admitted actors. JWKS digest `sha256:70718dcfcb5c4052d01764b05a73e1eada122d945f88f4342395f27e23be1ded`. No production Flow issuer certification. |
| AWS candidate activation/freshness and non-secret proof fingerprint | Native-recovery release `sha256:2e85ec00cfa905f13bfb11a89d8d196e0c71a17d2b3d549e7389aa9dce43af8b` passed canonical readiness, runtime immutability and negative-access probes. Subsequent candidate `sha256:964222c127cea848d8c35571a4592b5f7d7202bb7acb8d22c8d9267c506f260f` completed after the retained transient one-off inspection failure was resolved; exact application container health and canonical proof receipts were verified. The backend correction subsequently activated release `sha256:e5b931283a34965f2dc8ff9b380750d98007b22321889d0e9ed6c45e222c907e` with fresh canonical proof and retained-data verification before Beat resumed. Namespace remains `sha256:cf487c3b9b8ae93579939f80cb245ca79c25a5641fb3d5ce461abc16f0f4bad7`; freshness is time-bounded. |
| Original guide/task-example/import/positive/negative package SHA-256 values | Guide/ZIP fingerprints below. Public task import consumed 14,710 verified bytes, SHA-256 `a719390aebd455d64e3f519c5a3c5fe110f147135623247844dd846041179849`, creating five tasks. |
| Project/guide/setup/correction/result IDs and requirement mapping | Project `01a17c77-eb01-7945-8b6d-0fe92c2d4be7`; current guide `01a17d0a-cec1-786f-bf90-594f9dec5c82`; corrected compilation `01a17d13-d490-7ec8-b403-dfb17d3c3f3e`. Earlier failed guide remains retained. |
| Registry/config/model-profile IDs/digests and exact approved bindings | Original PRE and eight updated POST entries registered/read/replayed; updated receipt manifest `sha256:c99e833020d68f6f5e7a142afe9014b634a311fa3324e7e01a1cab6e5f9c2a9b`. Those bindings belong to the approved original guide. Nine new `drill-4ec4b` registry versions carry actual emitted finding-code descriptions and exact Luna model selectors; they are published/read/replayed, not approved project bindings. |
| PRE/POST approvals; ReviewPolicy, revision and ContributionPolicy versions; activation/LIVE identities | Guide activation `01a196fa-6693-7fd4-ab90-59a59b7b440d`; unpaid ContributionPolicy version `01a196f9-8924-7c6a-ab78-6aefa0eeb1e6`. Existing AUTH-gated Operator tool committed shadow generation 1, then live generation 2. |
| Task/assignment/Submission/checker/routing/acceptance/contribution/award IDs | Task `01a196fd-4957-751a-b0c2-dd70e71ffe7a`; assignment `01a196fe-6a94-7490-a624-9959109b54fa`; Submission `01a19703-0398-7d55-a33d-58658c9b0a50`; failed POST run `01a19703-07d0-7cc9-8cec-1e1da215c121`. Retry successor `01a19736-93a2-71b5-8cf0-913cbd25aec1`; no routing, acceptance, contribution or award row at the bounded snapshots below. |
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
US$0.6535634; independent custody and later public reads confirmed success. The
account total is US$2.6751144 settled, zero reserved, and US$7.3248856 remaining.
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
completed and settled US$0.0872514; the account now holds US$4.5760968 settled,
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
US$0.09226014 in pinned-rate settlement. The unchanged account now holds
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
probe. The repair is not yet deployed or live-qualified; validation and existing
correction, source, execution and spending bounds remain unchanged. No further paid
attempt has been invoked at this checkpoint.

Hosted CI for `b5d21c4db` completed sixteen lanes successfully; shared foundations A
failed two old assertions that rejected values could never appear anywhere in a
correction prompt. The new contract permits safe candidates as explicit untrusted
data while keeping diagnostics value-free. Test-only repair `7a3e1386f` asserts
both boundaries and complete revalidation; focused execution and QA/test-delta
review passed. This is not a fresh full-suite pass.

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
| Durable POST: real positive and substantive negative package | Exactly one current result with intended findings; automatic dispatch uses selected image/material | BLOCKED | Automatic POST ran but first resource ended as infrastructure failure. Native recovery exposes the retained invalid plan correctly. Guide6 corrections remain unapproved; Luna setup returned an invalid result; correction-loop repair and exact governed image/model selection remain before substantive qualification. |
| Model/trial/material custody: approved profile, real assessment and isolated reference/verifier execution | Correct exact material roles, verified trial receipts and private ART call evidence; no passing substitutes | IN PROGRESS | First model effect completed with retained request/response and charge. No Trial or final assessment was created; required nested execution remains unproven. |
| Model replay/recovery: duplicate delivery or permitted successor uses retained effect | No second paid create; immutable slots and once-only settlement; ambiguous effect remains held | IN PROGRESS | Native-only checker retry reattached the original completed effect without another charge; unresolved/known-no-effect recovery variants remain. |
| False-policy success: governed acceptance and applicable conditional awards | One shared FinalAcceptance, exact submitter ContributionRecord and frozen award set atomically; no Review/reviewer contribution | NOT RUN | — |
| True-policy guard/handoff regression | Eligible passing evidence reaches review_pending without acceptance/contribution/award effects; human runtime stays deferred | NOT RUN | — |
| Work failure and corrected replacement ZIP | Exact cause routes needs_revision when allowed; successor preserves predecessor/history and locked rules | NOT RUN | — |
| Revision limits/windows: zero/positive caps, final failure, setup pause/repair and timeout/reclaim | Correct assignment rounds/database-clock window; final failure or timeout retains evidence and returns ready; no artificial renewal | NOT RUN | — |
| Coverage-incomplete routing | No false auto-acceptance; false returns needs_revision without spent round, true retains review_pending | NOT RUN | — |
| Known infrastructure failure: discover and reason-bound Operator retry | Original Submission retained, no contributor revision spent; fresh authority and stable replay | IN PROGRESS | Submission/assignment retained, no revision or acceptance effects; public Operator retry discovery passed. Subsequent public retry/replay completed with the original paid effect and no revision penalty; wider failure/recovery variants remain. |
| UNKNOWN request interruption | Source-specific inspection classifies committed/no-effect/unresolved; only proven-safe recovery invokes existing owner | NOT RUN | — |
| UNKNOWN completion interruption | Committed outcome verified without repeated effects; unresolved source/UNKNOWN child remains held | NOT RUN | — |
| Acceptance commit/ack loss and duplicate broker delivery | Exact acceptance/contribution/award set unchanged; retained original attempts immutable | NOT RUN | — |
| Public contribution JSON/CSV and task audit reads | Exact source/award facts, current self/export/audit authority and complete bounded traversal; no external-payment claim | NOT RUN | — |
| Artifact diagnosis/verification retry on AWS | Supported bounded Operator reads/retry preserve original custody and do not disclose private coordinates | NOT RUN | — |
| AWS failure/isolation/retention | Intended access only; denied/uncertain writes/reads and interrupted verification remain recoverable; retained facts survive | IN PROGRESS | Exact-release canonical readiness/runtime-immutability/negative-access probes passed; submission bytes reached verified artifact custody. Wider interruption/retention matrix remains. |
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
| New complete-project drill | User explicitly authorized an additional US$10 total on 2026-10-27, across setup, POST and retries; one new account, immutable 10,000,000,000-nanodollar ceiling | November 1: US$2.021551 after native retry, then US$2.6751144 after guide6 generation 1. After guide8: US$4.66835694 settled, zero reserved, US$5.33164306 remaining against the unchanged cap |
| New current-run dispatch | Record pricing provenance, exact account/effect IDs, starting/ending settled and reserved totals and remaining authorized headroom. Stop paid dispatch on ambiguity or exhaustion | Earlier failure retained. Setup/correction and one POST model effect completed in the same account; POST added US$0.043729. Native retry reused that effect without another charge. Guide6 generation 1 completed with four model calls and added US$0.6535634; its intermediate unresolved read preceded successful persistence. Generation 2 then persisted a correction, while generation 3 remains provider-uncertain with five completed effects and one prepared effect. Guide7 used six Luna calls costing US$0.0872514 and ended known-invalid. After the reviewed correction repair, guide8 used six calls adding US$0.09226014 and exposed different known-invalid fields. No budget reset or blind retry occurred. |

Pinned-rate ledger settlement is not provider-invoice reconciliation. An unresolved paid effect is a held effect, not a free retry. See [shared accounting](../../.commitrail/changes/checker-model-runtime.md) and [the later separate qualification authority](../../.commitrail/changes/hosted-smol-project-execution.md#live-model-qualification-authority).

Keep keys, JWTs, subjects, request headers, credentials, connection/provider coordinates, raw private artifacts and model request/response bodies outside public reports and Git. Retain private evidence under access control; publish only safe IDs/hashes and bounded outcomes. Preserve earlier failed attempts and product evidence. Cleanup is limited to explicitly owned disposable resources; record owned process/resource absence and retained data separately.

## Release and issue reconciliation

| Gate | Current-run disposition |
|---|---|
| #576: actual PM agreement, fresh proposal and independently checked packages/material | IN PROGRESS — original guide agreement/activation completed; guide6 semantic discrepancies held approval and generation 3 remains unresolved. Guide8 proves safe-candidate correction; selected-binding/specification guidance, approved selection and complete native package qualification remain. |
| #581: terminal retry and full request/completion/acceptance interruption matrix | IN PROGRESS — claim/Submission replay and lost PRE-response recovery passed; governed POST retry/replay reused completed evidence; later interruption cases remain. |
| #582: candidate AWS activation, public exact-byte custody, failure recovery and final-data restore | IN PROGRESS — current release probes and verified immutable Submission passed; wider failure/restore matrix remains. |
| #583: exact native deployment, limits, readiness/cleanup, diagnostics/outage and operations | IN PROGRESS — native EOF repair passed live retry; Luna rollout completed after preserving and diagnosing two private-helper failures. Representative Trial, limits and operations qualification remain. |
| #555: connected real-project public/durable journey and exact final facts | BLOCKED — first POST ended as infrastructure failure; no final contribution outcome. |
| Exact candidate's required CI, focused defect regressions and applicable internal reviews | IN PROGRESS — dc15dc828 required CI passed: 17 lanes, 11,595 exact completions, zero skips/deselections and complete cleanup. Native recovery has live proof; the subsequent b5 suite failed two stale correction-format assertions. Their focused repair passes; fresh full-suite verification and the revised model/image journey remain pending. |
| Stale wording/Markdown links, affected roadmap reconciliation and local sheet constraints if exports exist | NOT RUN |

No issue is closed by this draft or by a child implementation merge. Complete release reporting requires every applicable outcome above to have current evidence, no unresolved journey blocker, and documented operating/recovery limits. Unimplemented/deferred human review, payment fulfillment and reputation must remain clearly identified; they are not silently certified by the automated contribution path.
