# Post-Merge Memory Operations

## Purpose

Managers review and approve each implementation PR once. Workstream then
records merge state automatically without a second bookkeeping PR or repeated
reviewer fanout.

## Trust Boundary

`.github/workflows/loop-memory.yml` runs only after a push to protected `main`
or an explicit operator replay. It executes the updater already present on
`main`; it never checks out pull-request-head code with write credentials. Its
only write target is `automation/loop-memory`. The branch blocks deletion and
non-fast-forward updates. Because organization policy disables deploy keys, the
workflow also signs all canonical generated files with an Actions-only Ed25519
private key. The reviewed public key on `main` lets operators reject any branch
write that did not come from trusted automation, while an expected protected-
`main` SHA rejects replay of an older valid signed snapshot. Invalid branch
state is discarded and deterministically rebuilt from the immutable bootstrap.

The generated branch is a closed tree containing:

- `.agent-loop/STATE.json` - canonical live state
- `.agent-loop/LOOP_STATE.md` - generated human view
- `.agent-loop/MERGE_LOG.jsonl` - append-only merge history
- `.agent-loop/WORK_QUEUE.md` - latest merge-derived gate per initiative
- `.agent-loop/INITIATIVE_STATE/<initiative-id>.md` - compact per-initiative
  merge/start projection
- `.agent-loop/MANIFEST.json` - ordered payload paths and SHA-256 digests
- `.agent-loop/STATE.sig` - signature over manifest bytes and every ordered
  `(path, bytes)` payload

Exact-tree validation rejects missing, extra, symlinked, or substituted paths.
Projection timestamps come from authenticated merge events, never render time.
Before signed start events exist, queue and initiative views intentionally show
the latest completed/stopped/next gate and cannot attest chat-only or unmerged
starts.

## Merge Intent

Every PR adds exactly one immutable file at
`.agent-loop/merge-intents/<chunk-id>.json`:

```json
{
  "schema_version": 2,
  "initiative_id": "WS-AUTH-001",
  "chunk_id": "WS-AUTH-001-06",
  "chunk_title": "Canonical Actor Profile And Identity Link",
  "next_chunk_id": "WS-AUTH-001-07",
  "next_chunk_title": "Authorization Kernel And Permission Registry",
  "next_requires_explicit_start": true
}
```

Agent Gates rejects missing, modified, duplicate, malformed, unknown-key,
mismatched path/chunk, or incomplete next-chunk metadata before merge. A
non-null next chunk must belong to the same initiative and resolve to exactly
one chunk contract whose heading has the same ID and title. A null value means
the initiative declares no successor; it never selects another initiative.
The post-merge updater fetches this exact added file and the referenced
successor contract from the reviewed final head. PR-body edits cannot
substitute lifecycle authority.

The protected `main` branch requires `agent-gates` and Backend `test`, and it
dismisses stale approvals after a new push. A changed intent therefore needs
fresh checks and human review before merge.

## Normal Operation

1. The manager reviews and merges the normal PR.
2. `Loop Memory` resolves the current protected-main SHA before reading or
   clearing generated state. The immutable `WS-ENG-001-03` schema-v2 merge
   intent anchors the replacement ledger; later runs start from its canonical
   tail. A queued push may reconcile forward only when its event SHA is an
   ancestor of current protected `main`. A replay must name current protected
   `main` exactly.
3. The updater validates the committed merge intent and records observed
   Backend, Agent Gates, and CodeRabbit conclusions from each final PR head.
4. The workflow renders into an empty output directory, builds an exact Git tree
   through an empty temporary index, commits a normal child of the prior state
   tip, and pushes it fast-forward to `automation/loop-memory`.
5. Work stops. A next chunk starts only under the generated explicit gate.

## Read Current State

```bash
git fetch origin automation/loop-memory
git show origin/automation/loop-memory:.agent-loop/STATE.json
git show origin/automation/loop-memory:.agent-loop/LOOP_STATE.md
git show origin/automation/loop-memory:.agent-loop/WORK_QUEUE.md
git show origin/automation/loop-memory:.agent-loop/MANIFEST.json
python3 scripts/update_post_merge_memory.py verify-state \
  --state-root <checked-out-state-branch> \
  --public-key .agent-loop/keys/loop-memory-signing-public.pem \
  --expected-main-sha "$(git rev-parse origin/main)"
```

## Recovery

If the workflow fails because of repository permissions or a transient GitHub
error, replay trusted default-branch automation with:

```bash
gh api --method POST repos/Flow-Research/workstream/dispatches \
  -f event_type=loop-memory-replay \
  -F client_payload[target_sha]="$(git rev-parse origin/main)"
```

`repository_dispatch` always selects the workflow from the default branch;
callers cannot choose feature-branch workflow code for the write token. Stale
replay SHAs fail closed before generated state is inspected. Replays are
idempotent and reconcile skipped intermediate commits. An unexpected tracked
path is recovered by the same replay: retained canonical inputs are
authenticated, output is rebuilt in an empty directory, and a normal
fast-forward child replaces the tree. The workflow never recursively deletes
the legacy checkout, edits generated files by hand, or force-pushes. Schema-v1
generated state and signatures remain rejected; no schema-v1 intent is parsed
or normalized. Invalid immutable schema-v2 intent requires an explicit corrective
engineering PR; generated files must not be edited by hand.

If the automation branch is absent, the same trusted workflow creates a signed
generated root commit. Existing branches always retain their prior tip as the
new commit's parent and update by fast-forward only.

## Review Policy

Implementation, specification, generator, workflow, policy, and hand-edited
memory changes retain all normal review requirements. Only deterministic output
committed by `Loop Memory` to `automation/loop-memory` skips the second review
and PR cycle.

## Explicit Start And Cancel Operations

`Loop Memory Explicit Event` is the only authority for starting reviewed work
or cancelling its active state. A start may select the declared successor or a
unique reviewed contract in a stopped initiative when all signed initiatives
are idle and that chunk identity has never been completed in signed history.
Dispatch it from `main` with the exact current-main SHA, initiative
ID, chunk ID, planning or implementation phase, action, and a bounded
single-line reason. For `start`, GitHub must report that the dispatcher
currently has `write`/`push`, `maintain`, or `admin` repository permission, matching
the closed permission policy in
`.agent-loop/policies/loop-memory-start-authorities.json` on trusted `main`.
That authenticated dispatch is the single approval checkpoint. For `cancel`, a
reviewer other than the dispatcher must approve the `loop-memory-start`
environment deployment.

Configure that environment with required reviewers, self-review disabled,
administrator bypass disabled, and deployment restricted to protected `main`.
The job reuses the existing repository-managed `LOOP_MEMORY_SIGNING_KEY` used
by trusted merge memory. Do not create, transfer, or paste a second private key.
The protected environment authorizes cancellation only; it does not redefine
the existing key's repository scope.

Every signed event records the dispatcher, immutable run ID and creation time,
current-main SHA, prior state-branch tip, reason, initiative, and chunk. Starts
also bind the current GitHub repository permission, selection mode, lifecycle
phase, canonical contract path and
heading title, and exact trusted-main Git blob. They record the versioned
dispatcher authorization; cancellations record the
protected-environment approvers. The workflow catches signed state up through
main before applying the event and rechecks main immediately before signing and
publication.

Dispatch and audit with:

```bash
main_sha=$(git rev-parse origin/main)
gh workflow run loop-memory-start.yml --ref main \
  -f action=start -f initiative_id=WS-ENG-001 \
  -f phase=implementation \
  -f chunk_id=WS-ENG-001-04B -f reason='Approved implementation' \
  -f expected_main_sha="${main_sha}"
gh run view <run-id> --log
# Cancellation audit only:
gh api repos/Flow-Research/workstream/actions/runs/<run-id>/approvals
```

Verify deployment configuration before enabling it:

```bash
gh api repos/Flow-Research/workstream/environments/loop-memory-start
```

Do not rerun a failed job. Inspect the signed automation branch first. If no
event was published, dispatch a fresh run; if it was published, its event ID and
active projection are authoritative. A push race leaves the branch unchanged.
Recover branch corruption with authenticated replay, never force-push or hand
edits.

Planning placeholders must start with `phase=planning`; their signed output is a
reviewed executable amendment, not implementation. Writer-directed contracts
declare this phase in `## Start phase`; automation derives the trusted phase and
rejects a mismatched dispatcher input. A new authenticated writer
dispatch may restart or reprioritize after a completed cancellation, but it
does not alter the cancellation record or approval evidence.

Failure handling is closed: stale main/tip, missing, ambiguous, symlinked,
foreign, malformed, or blob-mismatched contract; globally active work; missing or
dispatcher without an allowed repository permission, missing or same-dispatcher cancellation
approval, rerun, collision, active conflict, and moved branch all require
inspection followed by a fresh dispatch. Invalid signature/tree or
branch corruption requires disabling writes and authenticated recovery. A push
race publishes nothing and also requires inspection before redispatch.

The cutover inventory is fixed in
`.agent-loop/policies/loop-memory-legacy-start-exemptions.json`. Each exact entry
can close once without a signed start and is then consumed. No new exemption may
be added after merge. Signing-key rotation is not supported by this chunk:
start/cancel evidence cannot be reconstructed from main, so replacing the key
would break audit continuity. Suspected compromise is a blocking incident:
disable both workflows, preserve the branch and audit logs, and require a new
reviewed key-continuity design before any rotation or replay.

## WS-ENG-003 One-Use Recovery

PR #166 introduced single-checkpoint starts but necessarily began before that
mechanism existed, so its merge had no predecessor signed start. The reviewed
WS-ENG-003 recovery certificate binds exact merge
`6445ce6276a85c4ddef29d0f5e93cdbffe5d45bc` (PR #166) and activates only when
the resolved protected-main target is the `WS-ENG-003-01` recovery merge.

Before reducing any missing merge, the workflow requires the plan to contain
exactly PR #166 followed by the recovery target, derives the recovery PR number
from GitHub's unique merge evidence, and rejects collisions with signed state.
Each reducer receives only its matching authorization out of band; recovery
entries are never written to canonical state or ledger history. Both exact
exemptions must be consumed before signing or publication, while unrelated
legacy exemptions remain intact. A successful replay has an empty plan and does
not recreate recovery entries. This is not a general operator bypass and must
not be extended to later chunks.

## WS-ENG-004 Exact Bootstrap

The successor-only start rule could not authorize the repair that makes a
stopped, null-successor initiative resumable. The version-two recovery
certificate therefore activates only when the reconciliation plan is exactly
the merged `WS-ENG-004-01` target and that target's first parent is the signed
current-main SHA. Its initiative, chunk, and PR identity come from trusted
GitHub merge evidence.

The one target exemption exists only in ephemeral runner input, is consumed
before its merge record is appended, and is forbidden from final state, ledger,
projections, or manifest. An empty replay is inert; extra, missing, reordered,
later, or unrelated targets fail closed. This bridge does not authorize any
ordinary start. After reconciliation, writer-directed starts use only the
signed explicit-event path described above.
