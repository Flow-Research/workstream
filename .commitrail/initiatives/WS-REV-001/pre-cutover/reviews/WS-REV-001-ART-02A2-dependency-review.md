# Dependency Review: Merged ART-02A2

## Scope

Read-only review of ART-02A2 from prior trusted main
`aa0fdcd6912e66609e39a2fbd7b65f67be6c62f3` through merged trusted main
`9a04434e2f23c5dec8939dadb943bba4d85110c0` and its impact on the WS-REV plan.
ART implementation remains owned by WS-ART.

## Exact Merge Evidence

- Pull request: #129
- Merge commit: `9a04434e2f23c5dec8939dadb943bba4d85110c0`
- Final branch head: `32aab89262a3944f305e9e5dc4c65a2d31e2e144`
- Merged at: `2026-07-16T10:07:03Z`
- ART internal reviewed code SHA: `ae70bc2f10334f649c1af7f210e58ee378695a2b`
- Integrated evidence-bound head: `4ca80deede70b9b88f4cff01f01939f1309a20f6`
- Final GitHub Backend: run `29487194049`, success
- Final GitHub Agent Gates: runs `29487194116` and `29487194180`, success
- CodeRabbit: success

ART's internal evidence records 154 focused tests at 94.40 percent scoped
coverage, 38 isolated artifact PostgreSQL tests, 207 isolated
AUTH/authentication/Alembic tests, 71 agent-gate tests, and 94.8 percent
repository docstring coverage.

## Confirmed Boundary

- ART-02A2 adds inactive provider-neutral `PreparedArtifact` and
  `CommittedArtifactSource` types whose server commitment remains inseparable
  from the exact second-pass bytes.
- `ArtifactScratchManager` owns bounded private ephemeral processing scratch
  with aggregate quota, file/concurrency limits, free-space admission,
  deadlines, crash cleanup, no-follow/private-file checks, and a cross-process
  ledger. The ledger is not PostgreSQL, Redis, artifact storage, or durable
  product state.
- The shared bounded file-lock/cancellation primitives and LocalStorage private
  helpers preserve custody through timeout, cancellation, close, cleanup, and
  retry.
- Active ArtifactStore v1, provider selection, schema, product routes, and
  artifact lifecycle behavior remain unchanged.
- The chunk adds no actor, action, permission, resource context, grant, or
  service-principal authority.
- No S3 SDK, MinIO, AWS S3, R2, Flow Node, admission, verification/publication,
  reviewer packet read, evidence intake, checker cutover, recovery activation,
  or live proof is included.

## REV Disposition

ART-02A2 is compatible with REV as an ART-owned future intake foundation only.
REV never imports `ArtifactScratchManager`, `PreparedArtifact`, or
`CommittedArtifactSource`; persists scratch paths, ledger reservations, source
descriptors, or anonymous read handles; or constructs another preparation or
cleanup path. Review services consume only later typed ART capabilities through
composition-root registration.

This merge resolves the final planning-publication dependency, not the runtime
ART gates. ART-02A3, 02B1, 02C1-02C3, 02D, 03, 04A/04B, 05, 06A/06B, and 07
remain dependency-owned gates where their v2, S3, admission,
verification/publication, operator recovery, guide/upload/submission/checker,
reviewer read/intake/retention/projection, and live-proof contracts are needed.

## Snapshot Evidence

Merged-ART pre-external-review non-review initiative snapshot digest:
`a9b37925682a06e7d7871b7b060bf53efd23f8f67535ecb417f5259a1b5f7055`.

The digest hashes sorted `sha256sum` output for initiative files excluding
`reviews/**`; it binds the merged-ART dependency refresh before later external
review repairs and their separate exact-SHA evidence binding.

```text
git show --check 9a04434e2f23c5dec8939dadb943bba4d85110c0
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_loop_memory_state.py
python3 scripts/test_agent_gates.py
```

## Current Refresh Reviewer Status

| Tracks | Agent | Result | Residual |
|---|---|---|---|
| Senior engineering, architecture, reuse/dedup | `/root/final_art_senior_review` | PASS WITH LOW RISKS | Reviewer-specific ART read/intake port ownership remains a future fail-closed gate. |
| QA/test, product/ops | `/root/final_art_qa_review` | PASS | None. |
| Security/auth, docs, CI integrity | `/root/final_art_security_review` | PASS AFTER FIXES | Provider activation overclaim corrected. |

These reviewers covered the full planning PR plus the merged ART-02A2 refresh.
Final publication evidence binds reviewed code SHA
`cce3884033a187d40b9a8ae67af8163098e19318` after external review repairs.
