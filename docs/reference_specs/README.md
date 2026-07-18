# Workstream Reference Specifications

The checksum-listed WS-ARCH/WS-AUTH/WS-CON/WS-IMP inputs were supplied on
2026-07-11. The canonical WS-REV Markdown/PDF pair was replaced by the revised
supplied pair on 2026-07-15 after duplicate `(2)` filenames were corrected.
The table below contains the eight inputs governed by the central
`SHA256SUMS` manifest.

| File | Status | SHA-256 |
|---|---|---|
| `WS-ARCH-001-workstream-v0.1-architecture-baseline.pdf` | archival input | `547176dcedf41895ed896d5262a6ab8c6c029d71dac50bd17ed9da65f692b9b3` |
| `WS-AUTH-001-actor-profile-role-and-authorization-service-specification.md` | archival input | `464a7afb032e950b83e8fdb8c04fafe0b9ebddf549c4475dca684946740869a9` |
| `WS-AUTH-001-actor-profile-role-and-authorization-service-specification.pdf` | archival input | `69670ed59006b29cb7f60d12101cedf250c82a3488497f07d6c27e140aef1d2e` |
| `WS-CON-001-contribution-record-and-compensation-boundary-specification.pdf` | archival input | `34c4337f27e42a5b0ed5e153fe8ccd492ecede202c2764506a930d109aef66c1` |
| `WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md` | archival input | `e2116bce55fda1cce46a93e64bedcb47133d3898c1d4a51863385803e9dac210` |
| `WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.pdf` | archival input | `12f094e49c5c80f117e42d0f7f962b843f34508ab58d7f1d8def5f50fef532ed` |
| `WS-REV-001-review-lifecycle-specification.md` | revised archival input | `fffadc271c267801250b044edc570e515a250eff48afdc64f9c1f8753e6ab058` |
| `WS-REV-001-review-lifecycle-specification.pdf` | revised archival companion | `8c053bc752a7b0c64e04b3eda1873bb5dbc02bbdfef84bd17d07cbbf01bce2fd` |

The same values remain machine-checkable in `SHA256SUMS` and are bound by the
initiative source manifests. A checksum changes only when the human supplies a
replacement archival input; reconciliation never edits archival content.

The WS-CON initiative also records two exact inputs pending its CON-01
adoption: a revised `(2).pdf` archival input and a Markdown working
transcription. Their hashes and provenance live in the WS-CON source manifest.
The working transcription is historical, noncanonical material; it is neither
an archival input nor runtime authority.

The revised WS-REV Markdown includes section 4.6's closed action/permission
table, while the supplied PDF companion does not. They are separately preserved
archival artifacts rather than generated twins. The repository reconciles that
difference in the active contract without editing either file.

These inputs are not the repository's reconciled runtime contract. In
particular, Workstream retains the canonical `/api/v1` namespace even where an
archival input uses the old root-level version-one namespace. WS-AUTH-001 takes
precedence over the current token-role authorization bootstrap under accepted
ADR 0012. The reconciled
canonical authorization text lives in `docs/spec_authorization_service.md`.
The active review/revision contract lives in `docs/spec_review_lifecycle.md`.
Active repository documentation points to those contracts without editing the
eight checksum-listed archival files or treating the CON working transcription
as authority.
