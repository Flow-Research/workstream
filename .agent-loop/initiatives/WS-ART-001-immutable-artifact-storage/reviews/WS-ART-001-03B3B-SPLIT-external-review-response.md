# WS-ART-001-03B3B Split — External Review Response

## CodeRabbit review on 2026-07-30

All 11 findings against PR #228 were verified and accepted.

- Replaced range shorthand with every canonical chunk identifier and made the
  dependency graph branch after 03B3B1 before joining at 03B4.
- Bound dependency approval to independent protected GitHub review/merge
  history by a maintainer other than the PR author. Repository evidence is
  audit-only; CI must reject self-authored/forged, stale-head, missing, or
  digest-drifted approval.
- Made 03B3B1 a hard predecessor for PDF, OOXML, and image packages/imports.
- Added architecture/isolation where required and established 90% subsystem
  plus 78% repository coverage commands to every parser contract.
- Defined the OOXML member/rejection policy and inherited exact D42 resource
  limits before adapter dispatch.
- Made DOCX traversal, PPTX slide/notes ordering and 300/301 boundary, and XLSX
  formula/shared-string/merged-cell semantics plus 100/101 boundary explicit.
- Restricted image output to a fixed structural allowlist, discarded all
  ancillary metadata, and required inherited resource/termination tests.

Validation after the repair is recorded in the PR and its exact-head hosted
checks. No runtime or package change is part of this planning PR.
