# Chunk Contract: WS-REV-001-01 - Canonical Contract Adoption And Dependency Conformance

## Goal

Preserve the supplied revised WS-REV Markdown/PDF pair at its canonical
filenames as byte-immutable archival input, create one reconciled active
review-lifecycle contract, and align precedence material before runtime
implementation.

## Risk class

L1 specification and architecture boundary.

## Allowed files

```text
docs/reference_specs/README.md
docs/reference_specs/SHA256SUMS
docs/spec_review_lifecycle.md
docs/architecture_data_model.md
docs/architecture_lockdown.md
docs/architecture_lifecycle_state_machine.md
docs/architecture_system_architecture.md
docs/decision_0001_core_scope.md
docs/decision_0002_db_first_not_blockchain_first.md
docs/decision_0003_project_guides_are_first_class.md
docs/decision_*.md only when an approved decision requires it
docs/glossary.md
docs/principles.md
docs/product_principles.md
docs/operations_reviewer_workflow.md
docs/operations_revision_replay.md
docs/operations_queue_policy.md
docs/operations_payment_reputation.md
docs/operations_operator_workflow.md
docs/operations_project_operating_manual.md
docs/operations_roles_permissions.md
docs/product_first_user_flows.md
docs/risk_register.md
docs/roadmap_30_day_master_plan.md
docs/roadmap_day_by_day_execution_plan.md
docs/roadmap_implementation_backlog.md
docs/roadmap_pilot_plan.md
docs/roles_permissions.md
docs/template_review_packet.md
docs/template_revision_replay.md
docs/template_prior_feedback_checklist.md
docs/template_task_status.md
docs/template_project_guide.md
docs/spec_chunk_3_project_guide_foundation.md
docs/architecture_brief/task_lifecycle_sequence.puml
docs/architecture_brief/workstream_architecture_brief.md
docs/architecture_brief/workstream_architecture_brief.pdf
docs/architecture_brief/images/task_lifecycle_sequence.png
docs/architecture_brief/images/backend_v01_components.png
docs/architecture_brief/images/workstream_v01_container.png
docs/architecture_brief/render_pdf.sh
docs/diagrams/task_lifecycle_sequence.md
docs/diagrams/backend_v01_components.md
docs/diagrams/backend_v01_components.puml
docs/diagrams/rendered/backend_v01_components.svg
docs/diagrams/workstream_v01_container.md
docs/diagrams/workstream_v01_container.puml
docs/diagrams/rendered/workstream_v01_container.svg
README.md
scripts/check_stale_review_contracts.py
scripts/check_stale_artifact_contracts.py
scripts/check_stale_authorization_docs.py
scripts/test_agent_gates.py
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-01.json
```

## Not allowed

```text
backend/app/**
backend/alembic/**
backend/tests/**
docs/reference_specs/WS-REV-001-review-lifecycle-specification.md
docs/reference_specs/WS-REV-001-review-lifecycle-specification.pdf
docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md
docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.pdf
AUTH, ART, or CON runtime implementation
modification or replacement of any supplied archival reference byte
new provider choice
frontend work
```

## Acceptance criteria

- The supplied revised WS-REV Markdown/PDF pair and the WS-IMP pair remain
  byte-for-byte unchanged, separately hashed, and provenance-labelled as
  archival inputs. No `(2)` duplicate filename or one-sided pair edit remains.
  Verification compares each literal archival hash and byte diff to trusted
  base `0302bcf854a565d429e232ad6b076a1931ea74e4`, so changing an archive and its
  checksum line together cannot pass.
- Provenance explicitly records that the newest revised Markdown contains
  section 4.6's closed action/permission table while its PDF companion does not;
  adoption reconciles that difference without editing either archival file.
- `docs/spec_review_lifecycle.md` is the active normative implementation
  contract. It reconciles `/api/v1`, server-selected current work, artifact
  evidence, AUTH/CON ownership, LocalStorage/MinIO/AWS S3, and every approved
  repository decision, including WS-XINT-001 and ADR 0015, without claiming the
  supplied PDF is a generated twin.
- README, reference README, checksum manifest, architecture lockdown, and ADR
  precedence point to the active contract while retaining all archival hashes.
- ADR 0010 remains explicitly additive to revised submissions and is reconciled
  to the confirmed one-Project-Guide task pipeline: assignment binds to the
  task's initial lock; exact prior-Submission stamped guide identity/activation-
  sequence match with the currently active guide keeps context; any different
  active identity or sequence prepares the next attempt's complete context,
  including an intentional backward rebase; and the reviewer consumes
  the context stamped on the leased Submission without a separate guide/rebase.
- The active contract supersedes archival combined-role wording with independent
  `submitter`, `reviewer`, and `adjudicator` grants; review requires exact active
  reviewer authority, and adjudication remains unavailable.
- AUTH alone registers, owns activation custody, integrates evaluators, and
  changes availability. REV chunks produce hidden behavior, canonical typed
  facts/guards, and feature-manifest evidence before AUTH activation; REV-13 is
  a separate product release.
- The active contract names merged PR #140's exact gates:
  `WS-AUTH-001-REV-CUSTODY`, `WS-AUTH-001-PREP`,
  `WS-AUTH-001-REV-REG`, `WS-AUTH-001-REV-05/06/07/08/09A/11/12`, and
  `WS-AUTH-001-REV-LIFECYCLE`. It distinguishes the availability-neutral
  19-row custody transfer from later registration and activation.
- The active contract records merged AUTH-08 as 74 PermissionIds and 57
  ActionIds split into 9 active actions and 48 planned actions. It
  identifies that count as historical. It records current trusted main after
  AUTH-09C as 74 PermissionIds and 65 ActionIds split into 12 active and 53
  planned; AUTH-09B activated `actor.service.provision`, and AUTH-09C activates
  only `actor.profile.read` and `actor.identity_link.read`. It does not
  describe the authorization kernel as absent, claim a REV service identity was
  added, or treat any of the 24 REV dependencies as active.
- The active contract records AUTH-08's rollback-only dependency teardown,
  typed authorization-evidence `503` mapping, and route-owned canonical
  verification timestamps as required regression invariants. Chunk 01 changes
  no AUTH implementation.
- The active contract records merged ART-02A2 as the committed-source/private-
  scratch foundation and merged ART-02A3 as the active byte-only v2 LocalStorage
  clean cut. Review code never consumes `ArtifactScratchManager`,
  `PreparedArtifact`, `CommittedArtifactSource`, or the raw byte store, persists
  scratch state, or treats the store cutover as reviewer packet-read/evidence-
  intake readiness. Chunk 01 changes no ART implementation.
- The active contract's dependency inventory contains 24 non-executable review-lifecycle
  dependencies: registered planned `submission.create`, 19 registered planned
  review actions, and four approved but unregistered additions. The four
  proposed additions are
  `review.revision_obligation.close -> project.task.manage` for a covered
  Project Manager, `review.revision_context.repair -> project.task.manage` for a covered Project
  Manager and `review.revision_context.legacy_close -> operations.reconcile.run`
  for an Operator, plus
  `review.lifecycle.activation.manage -> operations.reconcile.run` for an
  Operator. Chunk 01 documents their typed resource/guard contract. Separately,
  ART/REV evidence finalization requires proposed service action
  `artifact.review_evidence.binding.create -> artifact.binding.create` for
  `workstream.artifact.binding`. Exact future counts are derived from the merged
  catalogue at each AUTH gate; 57/9/48 remains only the AUTH-08 snapshot. The
  four REV additions and ART service action are independently inventoried and
  cannot be silently collapsed into 61. No new REV PermissionId is introduced.
- The merged REV-01 active contract and its immutable SHA are the feature
  registration manifest for `WS-AUTH-001-REV-REG`. For each of the four additions
  it names principal class, typed resource and canonical facts, candidates,
  guards, surface, transaction owner, revalidation, and exact hidden-behavior
  dependency. Registration may then add four planned rows before REV-11/12A
  implementation; it activates nothing and does not claim hidden behavior exists.
- The same active contract publishes six separate service identity-to-ActionId
  manifests: `workstream.review.preference_expiry -> review.preference_expiry.run`,
  `workstream.review.lease_expiry -> review.lease_expiry.run`,
  `workstream.review.authority_invalidation_reconciliation -> review.reconcile.run`,
  `workstream.review.reconciliation -> review.reconcile.run`,
  `workstream.review.artifact_reference_reconciliation -> review.artifact_reference.reconcile`,
  and `workstream.review.projection -> review.projection.rebuild`. AUTH may create
  separately reviewed identity-specific extension
  contracts from that immutable manifest before the consuming REV chunk. Those
  extensions build on AUTH-09A's common schema but add exact enum, database
  constraint, matrix, provisioning, and admission coverage; AUTH-09A's seven ART
  identities contain no REV identity. Generic AUTH-09E admission never creates a
  catch-all identity.
- A stale-contract scanner rejects active Flow Node production, the archival
  noncanonical API prefix, full
  reviewer backlog, legacy severity, synthetic reject, direct
  payment/reputation, and bypass wording without scanning archival bytes as
  active policy. Its durable active-path classifier discovers tracked, staged,
  untracked, and newly added documentation, excludes archival inputs by exact
  path rather than broad directory suppression, and fails on an unclassified
  active document. Every tracked or untracked Markdown, PlantUML, and HTML
  documentation file is classified fail closed; only exact supplied archives,
  exact reviewed historical records, and the explicit non-product
  engineering-review protocol bypass active product scanning.
  Table-driven regression fixtures cover every prohibited category, adversarial
  lexical decoys, exact archival exclusion, unclassified-document rejection,
  and fail-closed invocation from `scripts/test_agent_gates.py`.
- Active reviewer/revision/queue/contribution flow docs and templates are reconciled
  now as contract/status documentation, clearly distinguishing planned
  unavailable endpoints from implemented behavior; the scanner has no temporary
  allowlist or exception that can outlive this chunk.
- The architecture brief render is byte-reproducible for the generated PDF and
  lifecycle PNG. The render command fixes the PDF identifier and embeds full
  fonts so repeated WeasyPrint runs do not create random subset names. Default
  rendering rebuilds only Chunk 01's lifecycle PNG and PDF. This chunk uses
  explicit source-specific rendering for the two reconciled context diagrams;
  the other two context images remain trusted-base bound.
- The three active roadmap documents are reconciled. Discovery at chunk start
  found neither ignored local export at `sheets/workstream_roadmap.xlsx` nor
  `sheets/workstream_roadmap.csv`, and final verification records the same
  absence. If either appears before completion, both must be updated together,
  the XLSX must contain only `WorkStream RoadMap`, both exports must contain the
  current Workstream definition, and no `sheets/` file may be committed.
- Principles, lifecycle-state, and project-operating docs state the same
  deterministic one-guide rebase rule and the WS-CON creation matrix. Every
  valid decision appends an immutable Review; every submitted finding and later
  resolution is immutable; every committed Review creates reviewer contribution.
  When the decision is `accept`, REV also creates one immutable FinalAcceptance,
  and the submitter contribution is sourced from that fact rather than inferred
  from `Review.decision`.
- The active contract defines every human lifecycle identity as canonical
  `ActorProfile.id`, defines distinct AUTH-09E fixed-service identities/static
  rows for protected jobs, removes retired compensation context from revision context,
  and records exact AUTH-first mutation choreography and REV/CON interleaving.
  It requires the opaque single-use prepared handle to match exact session,
  ActionId, actor-reference kind and ID, idempotency key, and canonical request
  digest before first feature mutation. AUTH alone validates those bindings,
  consumes the handle, evaluates, and stages evidence after REV recomposes final
  facts. Rejected wrong-binding, forged, serialized, or caller-constructed use
  preserves the legitimate unconsumed handle for one later exact first use;
  stale/already-consumed and concurrent duplicate use remains invalid and stages
  no new state. Evaluated authority/policy denial uses dirty-transaction rollback,
  clean unchanged AUTH denial-evidence restaging, and one route/service-command
  evidence commit with no feature/shared audit/outbox effects.
- The active contract defines REV-owned `ReviewPacketManifest` and
  `ReviewEvidenceArtifact`, ART v2 packet-read/candidate-finalize boundaries,
  exact binding service action, and no raw byte-store/provider access.
- The active contract maps XINT's conceptual `SubmissionVersion.artifact_hash`
  to a server-derived verified `artifact_hash` on the existing versioned
  `Submission`, copied to `ContributionRecord.artifact_hash`; caller
  `package_hash` is not trusted or silently renamed.
- Core contribution creation uses frozen `ContributionPolicyVersion`, a CON
  participant with ordered flush-only reviewer and submitter operations, no ART
  call, and no mandatory contribution-evidence projection. REV stages shared
  audit and outbox records inside the caller transaction; the request route or
  service command owns the caller `AsyncSession` and sole commit. CON owns its
  contribution/award behavior, public routes, and fulfillment transitions.
- Active contracts define FinalAcceptance as an internal immutable REV fact
  created only when a new Review has decision `accept`. It has unique
  task/source-Review/Submission lineage, exact ReviewPolicy and canonical actor
  links, no manual/public create API, and no separate AUTH action. The existing
  Submission is the version identity.
- Human reject uses canonical task `rejected`; approved administrative
  revision-obligation closure uses `cancelled` with a bounded reason. No active
  `closed/review_rejected` status token is introduced.
- Initiative state records PLAN merged through PR #128 at trusted main
  `0302bcf854a565d429e232ad6b076a1931ea74e4`, marks Chunk 01 active, and
  reconciles `STATUS.md`, `CHUNK_MAP.md`, and `SOURCE_MANIFEST.md`. Generated
  loop memory is not edited manually.

## Verification

The final PR-scope check intentionally uses trusted current main
`0ffdabf3dbb77e4e066683fde1a095d744ff1f43`, rather than the original planning
base `0302bcf854a565d429e232ad6b076a1931ea74e4`. Current main includes reviewed
sibling AUTH, CON, and ART changes that are dependencies of this chunk but are
not part of its PR scope. The committed reviewed-scope manifest records each
path's exact added or modified status. Rename detection is disabled so a rename
appears as a deletion plus an addition; any addition, deletion, rename, or
status change fails closed. This pinned comparison is a required local and
reviewer proof for this chunk, not a permanent repository-wide CI rule tied to
one historical base. Archival byte-integrity checks continue to use the
original planning base because those supplied inputs must remain unchanged
across the entire initiative.

```text
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
sha256sum -c docs/reference_specs/SHA256SUMS
printf '%s  %s\n' \
  fffadc271c267801250b044edc570e515a250eff48afdc64f9c1f8753e6ab058 docs/reference_specs/WS-REV-001-review-lifecycle-specification.md \
  8c053bc752a7b0c64e04b3eda1873bb5dbc02bbdfef84bd17d07cbbf01bce2fd docs/reference_specs/WS-REV-001-review-lifecycle-specification.pdf \
  e2116bce55fda1cce46a93e64bedcb47133d3898c1d4a51863385803e9dac210 docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md \
  12f094e49c5c80f117e42d0f7f962b843f34508ab58d7f1d8def5f50fef532ed docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.pdf | sha256sum -c -
git diff --exit-code 0302bcf854a565d429e232ad6b076a1931ea74e4 -- docs/reference_specs/WS-REV-001-review-lifecycle-specification.md docs/reference_specs/WS-REV-001-review-lifecycle-specification.pdf docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.md docs/reference_specs/WS-IMP-001-workstream-v0.1-coding-agent-implementation-specification.pdf
git check-attr diff merge text -- docs/reference_specs/*.pdf | awk '$3 != "unset" {bad=1} END {exit bad}'
: "${PLANTUML_JAR:?Set PLANTUML_JAR to the pinned PlantUML 1.2026.6 jar}"
printf '%s  %s\n' 89948f14c93756c7a3fb7b69078ff37e8489fd79dd430c582b931e2f65358690 "$PLANTUML_JAR" | sha256sum -c -
java -jar "$PLANTUML_JAR" -version | grep -F "PlantUML version 1.2026.6"
./docs/architecture_brief/render_pdf.sh --review-context
./docs/architecture_brief/render_pdf.sh --review-context
git diff --exit-code -- docs/diagrams/rendered/backend_v01_components.svg docs/diagrams/rendered/workstream_v01_container.svg docs/architecture_brief/images/backend_v01_components.png docs/architecture_brief/images/workstream_v01_container.png docs/architecture_brief/workstream_architecture_brief.pdf docs/architecture_brief/images/task_lifecycle_sequence.png
git diff --exit-code 0302bcf854a565d429e232ad6b076a1931ea74e4 -- docs/architecture_brief/images/future_identity_payment_reputation.png docs/architecture_brief/images/workstream_context.png
test ! -e sheets/workstream_roadmap.xlsx
test ! -e sheets/workstream_roadmap.csv
test -z "$(git ls-files sheets/)"
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
test -z "$(git status --porcelain=v1 --untracked-files=all)"
git diff --name-status --no-renames 0ffdabf3dbb77e4e066683fde1a095d744ff1f43...HEAD | LC_ALL=C sort -k2,2 -k1,1 | diff -u .agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/reviews/WS-REV-001-01-reviewed-scope.txt -
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, and CI integrity because scanner/tests change.

## Human review focus

Archival provenance, active-contract precedence, no semantic drift beyond the
approved planning decisions, and clear Markdown-over-archival-PDF authority.

## Stop condition

Merge, record automated memory, and stop. Do not start 02.
