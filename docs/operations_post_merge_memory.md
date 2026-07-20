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
