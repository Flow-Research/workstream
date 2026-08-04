# Chunk Contract: WS-ART-001-04A3 — Semantic Manifest And Change Gate

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Started by human after plan review

## Goal

Derive one canonical semantic manifest from the same server-inspected outer-ZIP
bytes accepted by 04A2, and provide a typed, side-effect-free change gate that
rejects exact or semantically unchanged work before checker or provider I/O.

04A3 installs the process-local identity and comparison capability. It does not
activate a route or persist a manifest. `04C2` will persist this exact manifest
with the verified ready admission; `05A` will bind that admission and manifest
to an immutable `Submission`. Until those chunks exist, no runtime code may
claim a durable canonical predecessor manifest.

## Canonical Authority And Predecessor Boundary

- Archive digest and byte count come only from the server-owned
  `PreparedArtifact.commitment` over the uploaded scratch bytes.
- Manifest entries come only from fully read member bytes after the complete
  04A2 safety validation. ZIP-declared sizes alone are never authoritative.
- Legacy caller-owned `Submission.package_uri`, `Submission.package_hash`, and
  `Submission.artifact_hash_manifest` are never read by this capability and
  never become archive identity, manifest identity, checker input, predecessor
  evidence, or admission evidence.
- A first submission has no predecessor and proceeds through the gate.
- A later comparison accepts only typed ART-owned predecessor facts containing
  the immutable Submission id/version and its persisted archive and semantic-
  manifest identities. An existing Submission without those canonical facts
  fails closed as `submission_canonical_predecessor_unavailable`; there is no
  legacy fallback or fabricated backfill.
- The eventual orchestration locks the task and reloads the immediate
  predecessor before comparison. The process-local result binds the observed
  predecessor id/version and identities. `04C2` and `05A` must revalidate that
  selector under their transaction locks before durable publication or
  consumption. Concurrent preparations may inspect concurrently; predecessor
  advancement makes an older selector stale rather than allowing it to bind.

## Canonical Manifest Contract

The closed manifest body is:

```json
{
  "schema_version": "workstream.submission_bundle_manifest.v1",
  "entries": [
    {"normalized_path": "dir", "entry_type": "directory"},
    {
      "normalized_path": "dir/run.sh",
      "entry_type": "file",
      "sha256": "sha256:<64 lowercase hex characters>",
      "byte_count": 1,
      "executable": true
    }
  ]
}
```

- Entries are ordered by normalized NFC POSIX path after 04A2's case-folded
  collision checks. No other keys are permitted.
- Explicit and synthetic parent directories produce the same entry. A distinct
  empty directory remains semantic. Directory entries contain neither digest,
  byte count, nor executable fields.
- The manifest digest is `app.core.hashing.canonical_json_hash(body)`, using the
  existing sorted-key, compact UTF-8 JSON encoding and `sha256:` prefix.
- Entry order in the ZIP, compression method/level, timestamps, comments, extra
  fields, ownership, group, read/write bits, setuid/setgid/sticky bits, and
  other packaging metadata are excluded.
- A regular file is executable only when `ZipInfo.create_system == 3`, the Unix
  file type is regular or unspecified, and any Unix execute bit is present.
  Non-Unix or invalid/missing Unix metadata defaults to false. Directories have
  no executable value. Symlinks and special entries remain rejected by 04A2.
- The flag expresses semantic intent only and never authorizes execution.
  Later projections must use fixed startup-validated modes: `0400` for regular
  files, `0500` for executable files, and `0500` for directories. They must
  never restore arbitrary archive permissions. 04A3 does not create a file-tree
  projection; 04B owns the first sealed projection through
  `ArtifactScratchManager` and must verify every projected file against this
  manifest.

## Typed Process-Local Result And Gate

04A3 returns immutable typed values for:

- archive SHA-256 and byte count;
- closed manifest body, schema version, and semantic-manifest digest;
- normalized typed entries and aggregate counts;
- comparison outcome (`first_submission` or `changed`);
- the nullable canonical predecessor selector used for comparison.

Exact archive equality rejects as `submission_archive_unchanged`. Different
archive bytes with equal semantic-manifest identity reject as
`submission_manifest_unchanged`. Rejection is contributor-safe and causes no
Submission, CheckerRun, Review, admission, put attempt, outbox event, provider
I/O, contribution, compensation, reputation, reviewer-contribution, task-state,
or assignment-state effect. Scratch cleanup remains owned by the surrounding
`PreparedArtifact` lifecycle. This ART gate is context-neutral: later checker-
remediation and human-review revision obligations remain XINT/CHK/REV concerns
and do not change semantic equality.

## Allowed Files

- `backend/app/modules/artifacts/submission_archive.py`
- `backend/app/modules/artifacts/submission_manifest.py` (new)
- `backend/app/interfaces/artifact_operations.py` only for the typed process-
  local manifest/predecessor/result contracts required by later ART chunks
- `backend/tests/test_submission_archive.py`
- `backend/tests/test_submission_manifest.py` (new)
- `backend/tests/test_submission_change_gate.py` (new)
- `backend/scripts/run_test_lanes.py` only to inventory each new test once in
  the existing `shared_foundations` lane
- `backend/tests/test_ci_test_lanes.py` only when an explicit inventory
  assertion is needed
- `.github/workflows/backend.yml` only if the existing ART 90-percent coverage
  step does not already cover the new module; no other workflow behavior may
  change
- this chunk contract plus the ART plan/spec/status/review/trust-bundle files
  when needed to keep the canonical contract and evidence aligned

No migration, ORM model, TASK repository/service, route, or schema change is
allowed in 04A3.

## Not Allowed Changes

Project checker execution, provider I/O, durable admission or manifest
persistence, Submission/review lifecycle mutation, arbitrary permission
preservation, file execution, generic download authority, AUTH activation,
scratch-path exposure/persistence, a second scratch manager, or direct reads of
legacy caller-owned package/manifest fields.

No CI weakening is allowed: no skipped/xfail/importorskip replacement, lane
removal/rename, timeout reduction, `continue-on-error`, `|| true`, lower
coverage floor, coverage exclusion, or non-blocking lint/type/test gate.

## Acceptance Criteria

- Equivalent safe ZIPs differing only in packaging produce the same semantic
  body and digest; archive digests may differ.
- File bytes, normalized path, entry type, byte count, distinct empty
  directory, or normalized executable intent changes semantic identity.
- Explicit and synthetic parents are identical; nested ZIPs remain opaque file
  bytes.
- Unix execute bits collapse to one boolean; non-execute permission changes do
  not affect identity; Windows/non-Unix metadata defaults false.
- File digests and sizes are computed during the full validated member read.
- The gate implements first, exact-unchanged, semantic-unchanged, changed,
  canonical-predecessor-unavailable, and stale-selector behavior with stable
  typed outcomes/errors.
- Legacy caller values cannot influence any result, and all rejection paths are
  proven to precede checker/provider/durable effects.
- Concurrent preparation semantics are explicit: comparison binds one locked
  predecessor selector; later predecessor advancement invalidates that selector
  during 04C2/05A revalidation rather than silently changing its meaning.

## Verification Commands

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_submission_archive.py tests/test_submission_manifest.py tests/test_submission_change_gate.py tests/test_ci_test_lanes.py)
(cd backend && .venv/bin/python -m pytest -q tests/test_submission_archive.py tests/test_submission_manifest.py tests/test_submission_change_gate.py --cov=app.modules.artifacts.submission_archive --cov=app.modules.artifacts.submission_manifest --cov-report=term-missing --cov-fail-under=90)
(cd backend && .venv/bin/python -m ruff check app tests scripts)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

The exact PR head must pass hosted `Backend / test`, including the unchanged
repository-wide `coverage report --precision=2 --fail-under=78`, and
`Agent Gates / agent-gates`. Each new test module must be collected exactly
once by the semantic lane inventory.

## Required Reviewers

Architecture, security, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

Stop if any implementation trusts caller manifest/package fields, persists
scratch identity before verified admission, weakens ZIP safety, makes packaging
metadata semantic, permits arbitrary modes/execution, or cannot prove unchanged
rejection precedes protected side effects.
