# Managed MCP and CLI hosted qualification

The normal EC2 deployment now runs the shipped private MCP Compose service.
The API, durable workers and external Rust password-login issuer remained active
during the client drill. This extends the earlier
[temporary client proof](demo-identity-clients-2026-11-07.md); it does not replace
that report's historical scope.

The [resource-sizing qualification below](#sealed-size-resource-qualification-and-fresh-hosted-journey)
records the latest deployed backend and a separate new contribution. Earlier
identities and evidence remain attributed to their original deployment.

## Earlier qualified deployment

- MCP source: `8f46a920c9524f017d48a9d0b1aad06e8edd7f1f`.
- MCP OCI manifest: `sha256:e034a1eba0906744a471602411ac95396a68372144a16209821fb688cd7335db`.
- Backend source: `d8daf19f6a3ae74b32bad75f28aa40452766d633`.
- Active release: `sha256:06a493c1f692178ff286df07c8b22529c73beeb9f5ea5aa6d2ade7610a5085ee`.
- Tested CLI SHA-256: `a9672343b86d95fa4c4ac18215c20f1a1fb56d0bb46b464a9d781c0edc5665f6`.

Canonical release and AWS storage qualification passed before activation. The
periodic AWS proof remained active and successful. MCP shares the API's current
network namespace, exposes only host loopback port 8080, and mounts no credentials.
The SDK client used pinned SSH forwarding and protocol `2026-07-28`; discovery
returned 132 tools. The compiled Go CLI used the normal API through its separate
private tunnel.

## Live client and identity evidence

Real Rust account login supplied each caller's short-lived bearer. The proof
covered administrator/participant identity separation, missing and malformed
credentials, natural token expiry, authorized and denied project reads, and
same-value profile editing. Issuer account creation did not supply Workstream
project authority: the administrator explicitly issued a Project Manager grant,
and that manager explicitly issued the new contributor's Submitter grant.

Both clients read project/guide context, queues and task facts. MCP created a
draft task; exact CLI/MCP replay returned the same receipt and changed-body
replay failed. Screening and release locked the existing Garden guide and
policies; contributor claim immediately produced `in_progress` and its active
assignment. There was no separate start call.

Restarting only MCP preserved the API and Celery worker container identities. A fresh
SDK connection rediscovered its catalogue; both clients replayed the current
claim with the exact original receipt. Replaying the earlier draft creation
after task advancement correctly returned 409. Restart does not override
lifecycle-sensitive replay rules.

## Intake and host capacity

The first intake attempt returned infrastructure unavailable before creating a
preparation or Submission. The host had 2.5 GB free, below intake's 3 GiB physical
reservation. Its health handshake still worked. Removing identified superseded
backend image tags unused by any container restored 9.5 GB free; active and
previous deployment images, registry contents, all volumes and retained evidence
were preserved. The same request then reached the real checker. This was a host
capacity refusal, not a contributor-quality failure.

A malformed `proof.json` produced an actionable external PRE finding through
both clients, including exact replay. Its preparation retained the failed result
and no admission; the contributor's Submission history remained empty. The
valid Garden proof passed Workstream defaults and the project-owned PRE image.
Storage first returned pending verification and object-confirmed states; callers
retained the same key, bytes and packet while waiting for verified admission.

## Completed Garden contribution

The new documentation work on [Garden PR #287](https://github.com/Flow-Research/garden/pull/287)
used head `ed37cbb63966c5560a79e2daa6b47b049e62d5ab`, bound by its exact
Workstream task trailer. Its [actual CI run](https://github.com/Flow-Research/garden/actions/runs/42355493268)
passed. The ZIP contained one regular root `proof.json` with the project's five
required fields; its 291 bytes hashed to
`sha256:6b63f9445ac10c0e7e53a7381ddf808d91401685f200ca326c33f79f278ff5fa`.

The CLI created immutable Submission v1 only after verified admission. Durable
workers ran `garden_task_proof` successfully and routed the result under locked
`human_review_required=false` rules. Contributor and manager APIs both returned
accepted work. Exact MCP submission replay retained the original Submission and
evaluation request. Complete contribution exports before and after replay
contained the same single contribution and single earned award for this Submission:

| Durable fact | Identity |
| --- | --- |
| Task | `01a1b516-229c-7d9e-a337-a8e4bbd0befb` |
| Submission | `01a1b531-4276-73d1-93c0-2f56af11c245` |
| Current completed checker run | `01a1b531-4430-7984-adbf-c836d59b3e2d` |
| FinalAcceptance | `01a1b532-dd0d-71e1-ab44-42f8bdfc88b6` |
| ContributionRecord | `01a1b532-dd56-7abb-96f3-8e8b39729936` |
| Earned 100 FLOW project-points award | `01a1b532-dd60-7763-ab5a-d609caf6a911` |

Assertions bound the archive hash/size, exact assignment and contributor, locked
policy identities, current checker/result IDs and `task_post_submit_route`
acceptance provenance. Review and review-lease references remained null. Points
are an earned award, not cash settlement or fulfillment. Garden's PR remained
open and unmerged; its configured checker required no independent GitHub review.
The operator controlled the demo account and GitHub work; this does not establish
an independently verified mapping between GitHub authors and issuer subjects.

The private public-response evidence packet hashes to
`sha256:4678d9533f91a3425b365dab11875c574119e29032ae74ad0eb22ae857017fa9`.
It contains no bearer credentials and remains outside the repository.

After verification, the manager revoked the temporary Submitter grant and the
administrator revoked the temporary Project Manager grant. Self authentication
remained valid, while both clients denied manager task reads and exact creation
replay. Bounded API, MCP, Celery and issuer log captures contained none of
the known caller bearers. Owned SSH tunnels and temporary bearer files were
removed; accounts, accepted work, contribution/award records and audit history
remain intact. This known-token scan is not a claim about every historical secret.

## Sealed-size resource qualification and fresh hosted journey

The resource correction was deployed as release
`sha256:4a0001cac9c21714f06a0dbb9dcc963289ba8d3a6f235cdf6879cbb46cc496a1`,
using backend source `b637b33f7136ac2d81ef8d56ab71d704a8fd474a` and image
`sha256:c5df6dbb0641239d6cadb062fe89753785b5d9f3983ad049f1b4ecd53044e8e5`.
The unchanged MCP image above remained in use, attached to the replacement API
container's actual namespace. The tested Linux CLI hashed to
`65e36e36d8a8b69a05c10a2cc6305d73c5a84b6b91a9abcb6350bf475fa04306`.

Scratch reservations now grow before writes from counted upload bytes plus
bounded buffer headroom. New submission ZIPs are capped at 500 MiB; smaller
project/deployment limits still apply. Guide and retained-artifact limits remain
distinct, as does MCP's 64 MiB transport ceiling. The sealed ZIP length then
bounds inspection expansion and VM allocation. The original operation deadline
covers upload and subsequent inspection; it is not restarted at sealing.

| Qualified input | Data disk | Separate root overlay | Result |
| --- | --- | --- | --- |
| Tiny PRE and POST fixtures | 1 GiB | 1 GiB | Passed inspection/export and cleanup |
| Exactly 500 MiB new ZIP | 2 GiB | 1 GiB | Passed canonical preparation/native inspection |
| Retained 512 MiB artifact | 2 GiB | 1 GiB | Passed the separate internal read contract |
| New ZIP above 500 MiB | None | None | Rejected before VM allocation |

The pinned envelope also passed maximum expanded-content, 2,000-entry,
1,024-byte path, depth-32 and directory-stress cases. Qualified overhead is
769,622,016 bytes; minimum observed free inodes were 45,482. Cancellation,
abandoned upload, capacity refusal, lease expiry and slot reuse left no owned
VMs, cgroups or leases. Native automatic image seeding was disabled by the
command owner so it cannot allocate an unaccounted extra VM.

The intake/native components were qualified from `18a9e7c06ca73874be99c596eb3381bb0f0880fe`.
Their exact image/runtime pins remain independently bound; all 72 observed
intake import files and native/guest sources are unchanged by the backend's
later orchestration repairs. Those repairs have separate real-scratch,
PostgreSQL and mutation proof. The complete numeric receipt hashes to
`sha256:df328a8cc9a1e03134f1985101879bbfe6f5cf64475e3d7e21ce57f55107058a`.
These measured synthetic limits are not a 500 MiB public project submission or
an arbitrary-image capacity guarantee. The Garden guide allows only a 128 KiB ZIP.

The previous deployed configuration requested a fixed 3 GiB data disk and did
not separately charge its root overlay. The corrected small-input charge is
1 GiB data plus 1 GiB overlay; its supported maximum is 2 GiB plus 1 GiB.
Logical reservation, disk capacity and actual physical usage are different
measurements. No comparison with unmeasured previous upload latency is claimed.
The tiny native fixture sealed at 0.023 seconds, was VM-ready at 8.704 seconds
and acknowledged cleanup at 10.402 seconds, measured cumulatively inside the
canonical-owner fixture rather than through the public API.

Deployment drained the existing Celery workers, verified retained database contents,
installed the pinned assets and passed real AWS storage qualification. A native
socket-readiness race in the private deployment harness was resolved by checking
the already-running exact process and continuing with canonical preflight;
completed starts were not repeated. A proof-script argument error was corrected
against the MCP tool's empty input schema. Preservation evidence ends at the
actual pre-read cutoff: later legitimate actor/AUTH audit writes are retained,
not erased or misrepresented as an unchanged database. Fresh real issuer/API/MCP
observations then bound the active containers, native process and release.

A separate fresh task used [Garden PR #287](https://github.com/Flow-Research/garden/pull/287)
head `4e61e1d70d04a81681b775cde7c36acd76161ed8`, its exact task trailer and
[successful current-head CI](https://github.com/Flow-Research/garden/actions/runs/42371374488).
The new documentation work explains PRE/POST failures and safe replay. This
was not a relabeling of an earlier accepted task. The PR remained open and unmerged.

Fresh Rust logins supplied the CLI and SDK client. Forty read/authentication
checks and fourteen task-creation/replay checks passed before screening, release
and immediate claim. Malformed proof returned actionable PRE findings through
both clients, created no Submission and preserved `in_progress` and assignment
ownership. The first malformed preparation took 17.3 seconds; its MCP replay
took 11.1 seconds. The valid 292-byte ZIP first returned pending verification in
19.7 seconds, with MCP replay taking 12.4 seconds. These are client-observed
elapsed times, not isolated VM startup or complete acceptance latency.

The storage job verified the original put attempt on its first execution.
Unchanged replay progressed through `stored_pending_verification`,
`object_confirmed` and `ready`; only verified admission permitted Submission v1.
The evaluation event was delivered once, external Garden POST passed, and locked
`human_review_required=false` routing invoked shared acceptance. Contributor and
manager reads agreed on these durable facts:

| Durable fact | Identity |
| --- | --- |
| Task | `01a1b5ea-30cf-7c14-9f75-0b04256817ed` |
| Submission | `01a1b5f6-04b9-7298-8229-6bbc29ba5bf5` |
| Completed checker run | `01a1b5f6-066e-75fc-8bc0-066621bfa3fe` |
| FinalAcceptance | `01a1b5f7-d2e9-7796-9485-9e15e5e9d7f6` |
| ContributionRecord | `01a1b5f7-d33a-7b5f-928d-b7c1930b6e33` |
| Single 100 FLOW points award | `01a1b5f7-d345-75e0-96e1-5ffb804353d1` |

Exact MCP Submission replay retained the same Submission/evaluation identities,
completed checker run, contribution and award. Assertions bind assignment,
contributor, locked policies and the exact ZIP hash
`sha256:9fc1c8b0ae78ffe48ce705be9612c847f57bb5af2dc51a6d5248494a5bbaf99e`.
Review and review-lease references remain null; no reviewer contribution is
fabricated. The response evidence packet hashes to `sha256:a89a3015a4c9cfa5695e6470e9c23790b6e69039125744434afb05fc3b66f487`.
Read-only snapshots after failed PRE and after acceptance found zero owned native
leases, VMs, guardians, cgroups, scratch reservations and workspaces. Services
remained running; these snapshots did not delete or recover resources.

Both temporary project grants were revoked. Ten post-revocation checks confirmed
that live authority is required for manager reads and creation replay. Final
bounded service-log scans contained none of the known caller bearers; this run's
three bearer files and private bearer inventory were removed. Owned SSH tunnels
closed; issuer accounts, keys, accepted work and evidence remain retained.

[Exact backend CI](https://github.com/Flow-Research/workstream/actions/runs/42367582804)
passed all 27 jobs, including CLI contracts, MCP packaging and real-API contracts.
The package-only MCP run's six integration skips are not integration evidence;
the separate real-API job supplies that proof. This deployed journey still does
not establish live human review, public DNS/TLS, a native Garden/Codex connector
or publication of CLI binaries.

## Coverage and distribution limits

This is representative live workflow evidence, not execution of all 132 tools.
Catalogue/contract tests and real-container fixture tests cover additional
surfaces, including stale API namespace detection and coupled MCP replacement.
An SDK connection does not prove a native ChatGPT/Codex connector, OAuth discovery
or public MCP ingress. Public `identity.flowresearch.tech` DNS/TLS participant
access remains unqualified.

The four-platform CLI release preview passed on Linux amd64, macOS amd64/arm64
and Windows amd64. It proves packaging and controlled native client behavior;
the hosted calls above used the Linux binary. No binary release was published.
Publication needs a fresh unused tag after human merge, the protected release
approval, and verification of downloaded public assets. The existing
`cli-v0.1.0` tag targets older code and must not be moved or approved as this build.
