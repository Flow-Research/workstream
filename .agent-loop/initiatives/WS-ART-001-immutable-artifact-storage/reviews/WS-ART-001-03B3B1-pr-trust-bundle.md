# WS-ART-001-03B3B1 PR Trust Bundle

## Chunk

`WS-ART-001-03B3B1` — Parser Dependency Approval.

## Goal

Approve and enforce the smallest exact PDF, OOXML-safety, and image-metadata
dependency set without installing packages or changing runtime behavior.

## Human-approved intent

The merged 03B3B split contract requires dependency approval before any PDF,
OOXML, or image parser implementation. The human owner explicitly started this
chunk after PR #228 merged.

## What changed

- Added a canonical allowlist for `pypdf==6.14.2`, `defusedxml==0.7.1`, and
  `Pillow==12.3.0`, including exact approved wheel URLs and SHA-256 hashes.
- Added a deterministic checker for manifest shape, wheel identity/platform,
  hash-bound future declarations, prohibited packages, format-scoped imports,
  and independent exact-head GitHub approval.
- Added focused failure tests and wired the gate before backend installation.
- Registered the focused test module in the canonical `shared_foundations`
  semantic lane after hosted inventory validation exposed the missing entry.
- Updated the ART specification, chunk command, status, and review evidence.

## Why it changed

Untrusted document parsers are a supply-chain boundary. A package name or
version alone cannot prove which bytes will later be installed, and a
repository-authored approval file cannot independently authorize itself.

## Design chosen

- PDF: pure-Python `pypdf`.
- OOXML safety: pure-Python `defusedxml` plus later ART-owned bounded container
  and format adapters.
- Image metadata: native `Pillow`, restricted to two named Python 3.11/3.12
  manylinux x86_64 wheels.
- Future runtime declarations must use the exact approved wheel URL with its
  SHA-256 fragment. Optional/dependency-group parser declarations are denied.
- Allowlist changes require a current approving GitHub review from an
  independent human owner/member/collaborator on the exact PR head.

## Alternatives rejected

- `python-docx`, `python-pptx`, `openpyxl`, `lxml`, and `XlsxWriter`: larger,
  unnecessary graphs for the bounded v0.1 OOXML extraction design.
- Version-only pins: do not bind installed artifact bytes.
- Repository-local approval as authority: forgeable by the proposing PR.
- `pull_request_target`: an unnecessary privileged workflow boundary.

## Scope control

No `pyproject.toml`, lockfile, dependency install, application import, parser
adapter, AUTH, Celery, submission, or product lifecycle change is included.

## Product behavior

None. Project Manager guide-source handling remains distinct from contributor
one-ZIP submission handling. All parser behavior remains unimplemented.

## Acceptance criteria proof

- Canonical schema covers version, license, maintenance, advisories,
  transitive graph, native-code, malformed-input, network, cancellation,
  import, format, source, wheel URL, and hash facts.
- Three closed scopes are present exactly once.
- Plain pins, wrong hashes/URLs/wheels/tags/scopes, prohibited packages,
  optional-group bypasses, cross-format imports, self/bot/stale/dismissed
  approvals, and GitHub API failure all reject in focused tests.

## Tests/checks run

- Manifest checker: pass.
- Focused pytest: 34 pass; checker coverage 92.94 percent.
- Ruff lint and format: pass.
- Compile, markdown links, stale artifact/wording, lightweight agent gates,
  and `git diff --check`: pass.

## Test delta

One new focused test module; no tests removed, skipped, or weakened.

## CI integrity

The gate runs before package installation. Existing backend tests, semantic
lanes, provider proof, and 78/90 percent coverage floors are unchanged. Token
permissions remain read-only: `contents: read` and `pull-requests: read`.

## Reviewer results

Architecture, security, QA, product/ops, senior engineering, CI integrity,
reuse/dedup, and test delta pass after valid findings were repaired. Docs
review is rerun on the staged evidence.

## External review

CodeRabbit's later substantive review produced three valid repaired findings
and one workflow-checkout finding rejected by direct hosted evidence. The first approval-authorized
Backend run found one missing semantic-lane inventory entry, now repaired.
Exact repaired-head hosted results remain required external evidence.

## Remaining risks

- Live GitHub review-event/check semantics require hosted proof.
- Review submitted/dismissed events rerun the full Backend job; this is an
  accepted low operational cost for the v0.1 fail-closed required check.
- `defusedxml` is a stable, slow-release security utility; its isolation and
  bounded OOXML use remain mandatory in later chunks.

## Follow-up work

After this chunk merges, `WS-ART-001-03B3B2` may install only the approved PDF
wheel and implement bounded PDF extraction. Later OOXML and image chunks remain
separate and require explicit starts.

## Human review focus

Confirm the three-package minimum, wheel URL/hash selection, native Pillow
platform bounds, prohibited package set, and independent exact-head approval
semantics.

## Human merge ownership

Only the human owner may approve and merge this PR. The PR must receive an
independent qualifying GitHub approval on its exact final head; this agent will
not merge it.
