# WS-ART-001-03B3B2 PR Trust Bundle

## Chunk

`WS-ART-001-03B3B2` — PDF Extractor (L1).

## Goal and human-approved intent

Install only the dependency approved in merged 03B3B1 and add bounded PDF text
extraction inside the existing hidden, isolated guide-extraction framework.
Guide uploads remain independent from contributor ZIP submissions. This chunk
does not activate AUTH, invoke sufficiency, or begin OOXML/image work.

## What changed and why

- Added the exact hash-bound `pypdf==6.14.2` wheel to runtime dependencies and
  the lockfile.
- Added a PDF-only adapter that rejects encrypted, malformed, interactive,
  attached, embedded, external, and active PDFs; enforces 500 pages; and emits
  deterministic compact JSON with explicit page boundaries.
- Loads the trusted adapter only for PDF after process resource limits, then
  installs seccomp before reading or parsing untrusted bytes.
- Added PDF policy v2 so pre-support v1 `unsupported` attempts cannot replay.
  Exact-lineage retry custody resets once to the new policy and preserves the
  old immutable evidence.
- Assigned the new focused test to the existing `shared_foundations` lane and
  updated the artifact specification and initiative status.

## Design chosen

The existing `GuideExtractionRunner` and child protocol remain authoritative.
The parent sees only the server-derived `pdf` classification and bounded result.
There is no second parser runtime, direct provider access, raw agent input, or
new authorization path. Canonical output is `{"pages":[...]}`.

Rejected alternatives were parsing during upload, loading `pypdf` for every
format, retaining PDF as policy-v1 unsupported, accepting partial extraction,
or allowing arbitrary PDF actions.

## Scope control and product behavior

All changed files are in the corrected chunk contract. The only contract
additions are the existing persistence service, its policy replay test, and the
canonical lane inventory required to make the original acceptance criteria
executable. No provider, AUTH, Celery, submission, review, compensation,
reputation, OCR, OOXML, image, route, or agent-assembly behavior changes.

PDF failures remain internal bounded extraction outcomes and never become guide
insufficiency decisions. Only successful current-policy canonical content can
later enter sufficiency.

## Acceptance criteria proof

- Exact 500/501 page boundary is tested.
- Malformed and encrypted documents are rejected.
- Forms, XFA, attachments, embedded/file-spec objects, open/additional actions,
  JavaScript, named/launch/submit/import/external actions, URI links, widgets,
  and rich media are rejected with bounded codes.
- Import graph and execution-order tests confine the parser to the PDF child:
  limits, trusted import, seccomp, then untrusted parsing.
- Workspace cleanup, child failure, timeout, cancellation, input/output limits,
  and protocol validation reuse and exercise the existing framework proofs.
- The isolated PostgreSQL regression proves v1 unsupported evidence is not
  replayed after PDF policy v2 and that v2 success becomes the replay target.

## Tests and checks

- `uv run python scripts/check_guide_extractor_dependencies.py` — pass.
- `uv lock --check` — pass; wheel URL/hash matches the approved manifest.
- `uv run ruff check app tests scripts` — pass.
- Focused PDF/extraction/architecture suite — 77 passed before the final added
  order/action cases; targeted final repair suite — 31 passed.
- New PDF module coverage — 94.81 percent (above 90 percent).
- Isolated PostgreSQL policy replay test — 1 passed.
- CI lane inventory tests — pass; `test_guide_pdf.py` is in
  `shared_foundations`.
- Stale-contract scan, Markdown links, and `git diff --check` — pass.
- Repository-wide 78 percent coverage and hosted semantic lanes remain for the
  GitHub Backend gate; no local full-suite run was used.

## Test delta and CI integrity

No test or assertion was removed, skipped, or weakened. New adversarial cases
cover actual action annotations rather than only synthetic root keys. No
workflow, lane count, coverage threshold, or failure behavior changed. Hosted
installation remains protected by the exact direct wheel URL/hash and the
dependency checker; the lockfile records the same bytes.

## Reviewer results

- Architecture: initial High findings repaired; re-review pass with one Low
  import-style proof hardening item, also repaired.
- Security/auth: pass.
- QA: initial action-dictionary High repaired; re-review pass.
- Product/ops: pass.
- Senior engineering: initial verification/DB seed/scope findings repaired;
  final re-review pass.
- CI integrity: pass with informational hosted-install notes.
- Docs: pass.
- Reuse/dedup: pass with Low future shared-normalizer advice.
- Test delta: initial missing-case and branch-proof findings repaired; final
  re-review pass.

## External review

CodeRabbit and hosted GitHub gates have not run yet. Their findings remain
external merge evidence and must be checked after the draft PR opens.

## Remaining risks and follow-up

`pypdf` is an untrusted-format parser, so OS termination remains an essential
control. The trusted dependency import intentionally precedes descriptor-only
seccomp because Python import needs filesystem reads; resource limits are
already installed and no untrusted bytes are read until after seccomp.

03B3B3A (OOXML security) and 03B3B4 (image metadata) remain separate chunks.
03B4 sufficiency continuation cannot start until all required format chunks
merge.

## Human review focus and merge ownership

Review the exact wheel/hash, active-content deny semantics, 500-page boundary,
trusted-import/seccomp ordering, PDF policy-v2 replay reset, and deterministic
page JSON. A human owns merge approval; the agent will not merge this PR.
