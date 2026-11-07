# Managed MCP and CLI hosted qualification

The normal EC2 deployment now runs the shipped private MCP Compose service.
The API, durable workers and external Rust password-login issuer remained active
during the client drill. This extends the earlier
[temporary client proof](demo-identity-clients-2026-11-07.md); it does not replace
that report's historical scope.

## Qualified deployment

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
