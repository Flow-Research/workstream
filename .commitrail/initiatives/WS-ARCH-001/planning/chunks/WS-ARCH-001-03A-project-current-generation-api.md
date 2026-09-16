# Chunk Contract: WS-ARCH-001-03A PROJECT Current Generation API

Adopted implementation contract: [ARCH-03A](../../WS-ARCH-001-03A.md).

Status: Complete; CP08 is next; CP09 cleanup remains later. Risk: L1. Outcome: PROJECTS exposes immutable current approved unified
guide, its exact guide-bound ContributionPolicyVersion, setup, pre-submit and
post-submit identities/hashes through its public API.

Allowed: `backend/app/modules/projects/api/**`, the smallest PROJECTS-owned
repository/service extraction, focused PROJECT tests, boundary ledgers, and
this initiative's evidence/status. Not allowed: TASK/ART/CHECKER/REV behavior,
AUTH activation, ORM leakage, compatibility aliases, or another inference
path.

Reuse the existing `CanonicalJsonObject` and
`ProjectLockedPolicyContextPort`; extend their public vocabulary unless a
reviewed current-main delta proves that a new type is necessary. Do not create
a parallel canonical-JSON, hash, locked-policy, or current-generation surface.

Distinguish two reads within this existing port: selecting the complete active
guide context for a new Task lock, and resolving an existing attempt's exact
persisted guide/policy tuple. The latter must not look up the newest guide or
CON selector. Later guide replacement/publication does not invalidate frozen
work; missing, internally inconsistent or cross-project locked facts still
deny. Return contribution, review and revision policy lineage alongside both
checker policies, not just a ContributionPolicy identifier. CP07 already owns
activation writes and its response; do not implement them again here.

The complete public internal fact graph includes guide ID/version and CP07 activation operation, per-guide generation and timestamp; source snapshot/setup/compilation and result/component identities;
artifact/effective/pre/post policy IDs, canonical hashes, required locked bodies
and persisted catalogue identity/version/schema/manifest-hash tuples; review/revision ID-generation-hash triples; and the
guide-bound ContributionPolicy version plus activation provenance. Fields use
canonical typed immutable values and are not automatically public HTTP fields.
Historical resolution accepts the caller's exact locked selectors without
reading TASK internals or consulting global CON selection.

The adopted implementation contract above enumerates exact files, commands,
migration head, future proof and reviewers.

Acceptance: one transaction-bound port returns only canonical immutable facts;
guide activation has validated and bound one same-project published, complete,
binding-valid immutable ContributionPolicyVersion as
`ProjectGuide.contribution_policy_version_id`; stale, mixed-generation,
incomplete or unapproved chains deny. Superseded current candidates deny new
binding, while valid earlier frozen attempts remain readable;
all touched private edges shrink. Verify focused PROJECT tests, PostgreSQL
locking/race tests, boundary validators, Ruff and hosted coverage. Required
reviews: architecture, security, product/ops, QA, senior, reuse and test delta.

## Merge state

- Outcome on merge: `Complete`
