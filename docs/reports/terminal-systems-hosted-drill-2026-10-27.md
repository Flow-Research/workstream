# Terminal Systems hosted first-journey drill — 2026-10-27

**Current rehearsal: IN PROGRESS. No real-project release pass is claimed.** This report implements the evidence structure for [#555](https://github.com/Flow-Research/workstream/issues/555) and the [bounded rehearsal record](../../.commitrail/changes/terminal-systems-repaired-recovery-trial.md#authorized-hosted-drill-and-reporting). Bootstrap deployment used source `ac637495f`; the separately sealed repair release now runs source `0659c749`. Live setup recovery is in progress; no Submission or final contribution outcome is claimed.

The target is original project guide -> approved locked policies -> released task -> claim/start -> ZIP intake feedback or immutable Submission -> durable POST -> governed outcome -> exact contribution evidence. Use explicitly PM-approved `human_review_required=false`. Preserve default-true handoff guards; live human review, payment delivery, reputation, frontend and claim expiry/skip remain deferred. #496 is excluded.

## Release and project provenance

| Required binding | Current-run value |
|---|---|
| Executed source commit and exact review/CI evidence | `0659c749`; focused implementation reviews passed. Canonical image verification, fresh AWS proof, preflight and five-service health passed. The current PR also repairs instruction guidance and POST requirement identity; those new repairs still need image/runtime qualification, fresh full CI and the complete journey. |
| Backend API, Celery worker/Beat, parser and proxy image digests and fixture derivatives | All five use verified agents derivative `sha256:feeaf0935bc283f29e898821acddcb12de904cf4a4880f75b9743ef9f48ee96c`; public fixture CA is the only derivative change. OmniCore image construction also verified, but this run uses the OpenAI Agents SDK. |
| Native service, Smol, guest and configured cache/archive/config digests | Smol 1.31.4; service `sha256:5e5760b898017453feb821a24066dc78201249ce39a1eb2f3eb27fffef100ba0`; exact four cache entries and three trial bindings pass preflight. No live task trial yet. |
| Migration head; non-secret release/configuration fingerprints; Celery worker topology | `0064_checker_trial_evidence`; one prefork worker with concurrency 2 and one Beat; native config `sha256:de1ea6de41d14887c600ed938f8757ffbfb110056089459bd20384983af15e8d`. |
| Identity qualification; issuer/key configuration digest, without subject/token | Authorized simulated HTTPS/JWKS issuer through the actual verifier; six distinct admitted actors. JWKS digest `sha256:70718dcfcb5c4052d01764b05a73e1eada122d945f88f4342395f27e23be1ded`. No production Flow issuer certification. |
| AWS candidate activation/freshness and non-secret proof fingerprint | Exact release readiness, runtime immutability and negative-access probes passed; namespace `sha256:cf487c3b9b8ae93579939f80cb245ca79c25a5641fb3d5ce461abc16f0f4bad7`. Refresh timer active; evidence freshness is time-bounded. |
| Original guide/task-example/import/positive/negative package SHA-256 values | Public guide exact-byte proof and three local ZIP fingerprints recorded below. Task import not yet executed. |
| Project/guide/setup/correction/result IDs and requirement mapping | Project `01a17c77-eb01-7945-8b6d-0fe92c2d4be7`; guide `01a17caa-6fd9-761e-a3b6-4a0cd1623f9f`; setup `01a17caa-7014-7415-a67f-895a1cb54a1f`. No compilation result. |
| Registry/config/model-profile IDs/digests and exact approved bindings | Nine entries registered/read/replayed; full receipt manifest `sha256:23651b6f563d3415404427958b43f33c3bbc87ab60dcd277e6fdd4b3194984d9`. Project policy approval remains pending. |
| PRE/POST approvals; ReviewPolicy, revision and ContributionPolicy versions; activation/LIVE identities | NOT RUN |
| Task/assignment/Submission/checker/routing/acceptance/contribution/award IDs | NOT RUN |
| Private evidence manifest fingerprint, observation interval and cleanup inventory | Deployment snapshot at 10:06 UTC: `sha256:0dea8330260de284fb7e8fbc3916e7e62c260649d2491a1f342bfa5e6a663578`, binding 31 evidence files. Final journey/cleanup manifest pending; retained product data untouched. |

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

### Current observations

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

### Original queue package: local qualification

The genuinely authored `queue-recovery` package has a functioning buggy starter,
a general reference repair and independent expected results. Independent review
caught malformed-record and ordered-recovery defects in its initial reference;
those were repaired and their failed-before/passed-after evidence retained.
This is authoring-package correction, separate from Workstream product repair.

The current v2 package passed 23 expected native controls, including three
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

Every result below starts at `NOT RUN`; this denotes missing current-run evidence, not an absent implementation. Replace a status only with an observed outcome and bounded evidence reference. Use `PASS`, `FAIL`, `BLOCKED`, `IN PROGRESS` or `NOT RUN`; a blocker must identify its unavailable prerequisite. Retain failed observations and exact candidate attribution.

| Capability and concrete scenario | Required observable outcome | Result | Evidence / remaining limit |
|---|---|---|---|
| Identity/admission: admit distinct PM, Finance, Operator and contributor humans through the verifier | Identity alone supplies no project authority; explicit grants control actions | PASS | Six distinct fixture actors admitted; canonical grants issued through public APIs. Unrelated contributor denied the guide reads below. Simulated issuer only. |
| Authorization: unrelated actor/project/resource, revoked grant/link and stale replay | Deny without unauthorized effects or private disclosure; replay checks current authority | NOT RUN | — |
| Guide custody: create/upload unchanged original and download through public reads | Exact digest/size/bytes and unrelated-actor denial; duplicate upload retains original custody | PASS | Manager detail, original download and setup read returned 200; each corresponding unrelated-contributor read returned concealed 404. Same-key upload returned 202, replayed=true, identical document/hash/byte count. |
| Async setup: actual assigned originals/example reach durable worker and parser | Source-backed PRE/POST proposal, sufficiency and explicit gaps; no injected result | FAIL | The repaired SDK completed seven paid calls, but final setup output was schema-invalid. No compilation/proposal was accepted. Diagnosis in progress before another paid attempt. |
| PM correction and agreement: inspect current proposal against guide and packages | Supported successor preserves predecessor; required uncovered checks block approval/activation | NOT RUN | — |
| Registry and model configuration: register/read/replay exact configured capabilities | Immutable image/config/profile identities and fresh Operator authority; registration alone does not activate | PASS | Nine public registry registrations, reads and same-key replays retain exact identities. Profiles published against the one project budget. Actual project bindings remain unapproved. |
| Policy/activation: separate PRE/POST approval, review/revision configuration and Finance publication | Exact complete locked context before activation/READY; false policy explicitly approved | NOT RUN | — |
| Task creation/import/screen/release: import original briefs and exercise manager operations | Exact task/source/batch receipts; locks preserved; replay creates no duplicates | NOT RUN | — |
| Contributor workspace: discover/read task, claim/start and obtain locked guide/context | Exact grant and assignment authority; downloaded original is verified; other assignees deny | NOT RUN | — |
| Default ZIP intake: unsafe ZIP/secret/unchanged-work negative plus warning-only inputs | Blocking feedback creates no Submission and preserves valid working assignment; warnings do not block | NOT RUN | — |
| Project PRE: genuine layout/metadata negatives and corrected package | Actionable intended findings before Submission; exact ready admission only after complete pass | NOT RUN | — |
| Successful preparation/replay and immutable Submission | Same bytes/hash/size/manifest and locked lineage; replay reuses IDs without rerunning effects | NOT RUN | — |
| Durable POST: real positive and substantive negative package | Exactly one current result with intended findings; automatic dispatch uses selected image/material | NOT RUN | — |
| Model/trial/material custody: approved profile, real assessment and isolated reference/verifier execution | Correct exact material roles, verified trial receipts and private ART call evidence; no passing substitutes | NOT RUN | — |
| Model replay/recovery: duplicate delivery or permitted successor uses retained effect | No second paid create; immutable slots and once-only settlement; ambiguous effect remains held | NOT RUN | — |
| False-policy success: governed acceptance and applicable conditional awards | One shared FinalAcceptance, exact submitter ContributionRecord and frozen award set atomically; no Review/reviewer contribution | NOT RUN | — |
| True-policy guard/handoff regression | Eligible passing evidence reaches review_pending without acceptance/contribution/award effects; human runtime stays deferred | NOT RUN | — |
| Work failure and corrected replacement ZIP | Exact cause routes needs_revision when allowed; successor preserves predecessor/history and locked rules | NOT RUN | — |
| Revision limits/windows: zero/positive caps, final failure, setup pause/repair and timeout/reclaim | Correct assignment rounds/database-clock window; final failure or timeout retains evidence and returns ready; no artificial renewal | NOT RUN | — |
| Coverage-incomplete routing | No false auto-acceptance; false returns needs_revision without spent round, true retains review_pending | NOT RUN | — |
| Known infrastructure failure: discover and reason-bound Operator retry | Original Submission retained, no contributor revision spent; fresh authority and stable replay | NOT RUN | — |
| UNKNOWN request interruption | Source-specific inspection classifies committed/no-effect/unresolved; only proven-safe recovery invokes existing owner | NOT RUN | — |
| UNKNOWN completion interruption | Committed outcome verified without repeated effects; unresolved source/UNKNOWN child remains held | NOT RUN | — |
| Acceptance commit/ack loss and duplicate broker delivery | Exact acceptance/contribution/award set unchanged; retained original attempts immutable | NOT RUN | — |
| Public contribution JSON/CSV and task audit reads | Exact source/award facts, current self/export/audit authority and complete bounded traversal; no external-payment claim | NOT RUN | — |
| Artifact diagnosis/verification retry on AWS | Supported bounded Operator reads/retry preserve original custody and do not disclose private coordinates | NOT RUN | — |
| AWS failure/isolation/retention | Intended access only; denied/uncertain writes/reads and interrupted verification remain recoverable; retained facts survive | NOT RUN | — |
| Native deployment and representative limits | Exact Smol/images, read-only verified material, measured CPU/memory/PID/disk/output/time and bounded admission | NOT RUN | — |
| Missing runtime/cache, cancellation and service recovery | Correct infrastructure classification, no false completion, owned scratch/VM/cgroup cleanup and capacity reuse | NOT RUN | — |
| Secured diagnostics and collector outage | API/job correlation without documents/tokens/model bodies; collector outage preserves product correctness | NOT RUN | — |
| Drain/restart and forward recovery | Producers and Celery workers drain in supported order; immutable facts survive; no protected migration downgrade | NOT RUN | — |
| Final-data backup/ordinary isolated restore | Guide/Submission bytes, audit, policies, task history, effects and contribution/award facts remain intact | NOT RUN | — |

CLI, MCP and TUI surfaces are implemented separately. Record any exercised client and binary/source identity explicitly; backend scenarios do not certify every client surface. Optional interfaces are not additional first-journey prerequisites.

## Paid accounting and evidence privacy

| Account boundary | Required treatment | Current rehearsal result |
|---|---|---|
| Original Terminal Systems rehearsal | Earlier uncertain setup spend remains retained separately; do not reset it or mark it free | Unresolved historical spend; no new dispatch against this allowance |
| Separately authorized model-only qualification | Preserve its existing project/account and US$0.016527 settled ledger. A model-plus-trial continuation reuses that account/headroom; no automatic new allowance or transfer to a fresh real-project account | NOT RUN |
| New complete-project drill | User explicitly authorized an additional US$10 total on 2026-10-27, across setup, POST and retries; one new account, immutable 10,000,000,000-nanodollar ceiling | Account provisioned through public API; at 10:06 UTC seven completed effects settled US$0.7242128 total, reserved US$0, remaining ceiling US$9.2757872 |
| New current-run dispatch | Record pricing provenance, exact account/effect IDs, starting/ending settled and reserved totals and remaining authorized headroom. Stop paid dispatch on ambiguity or exhaustion | Original pre-effect failure retained. Same-attempt recovery settled seven effects and ended schema-invalid; no automatic new paid attempt or budget reset. |

Pinned-rate ledger settlement is not provider-invoice reconciliation. An unresolved paid effect is a held effect, not a free retry. See [shared accounting](../../.commitrail/changes/checker-model-runtime.md) and [the later separate qualification authority](../../.commitrail/changes/hosted-smol-project-execution.md#live-model-qualification-authority).

Keep keys, JWTs, subjects, request headers, credentials, connection/provider coordinates, raw private artifacts and model request/response bodies outside public reports and Git. Retain private evidence under access control; publish only safe IDs/hashes and bounded outcomes. Preserve earlier failed attempts and product evidence. Cleanup is limited to explicitly owned disposable resources; record owned process/resource absence and retained data separately.

## Release and issue reconciliation

| Gate | Current-run disposition |
|---|---|
| #576: actual PM agreement, fresh proposal and independently checked packages/material | NOT RUN |
| #581: terminal retry and full request/completion/acceptance interruption matrix | NOT RUN |
| #582: candidate AWS activation, public exact-byte custody, failure recovery and final-data restore | NOT RUN |
| #583: exact native deployment, limits, readiness/cleanup, diagnostics/outage and operations | NOT RUN |
| #555: connected real-project public/durable journey and exact final facts | NOT RUN |
| Exact candidate's required CI, focused defect regressions and applicable internal reviews | NOT RUN |
| Stale wording/Markdown links, affected roadmap reconciliation and local sheet constraints if exports exist | NOT RUN |

No issue is closed by this draft or by a child implementation merge. Complete release reporting requires every applicable outcome above to have current evidence, no unresolved journey blocker, and documented operating/recovery limits. Unimplemented/deferred human review, payment fulfillment and reputation must remain clearly identified; they are not silently certified by the automated contribution path.
