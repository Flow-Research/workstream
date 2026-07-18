# Chunk Contract: WS-REV-001-07

## Goal

Provide authorized Review Context retrieval and verified finding/finding-response
evidence intake through Workstream-owned artifact capabilities.

## Risk class

L1 authorization, private data, and artifact integrity.

## Allowed files

```text
backend/app/modules/reviews/{repository,schemas,service,router}.py
backend/app/composition/review_lifecycle.py only to install exact merged ART packet-read and evidence ports
backend/tests/test_{reviews,artifacts,authorization,checkers,tasks,app}.py
docs/operations_reviewer_workflow.md
docs/template_review_packet.md
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-07.json
```

## Not allowed

```text
decision commit
raw CID/path/URL/provider credential acceptance
human token forwarding to storage
provider-specific imports in review services
review-authoritative search state
production `/api/v1` review-router registration
```

## Acceptance criteria

- Context read declares the `review.context.read` action mapped to
  `submission.read_for_review`, then requires an active owned lease. The
  separate review-chain endpoint declares `review.chain.read`; one endpoint
  never declares two primary actions.
- `review.chain.read` additionally requires one server-resolved relationship:
  the actor is the canonical contributor on the exact TaskAssignment associated
  with a Submission in the requested chain; owns the active lease anchored to
  the chain; authored a prior Review in the chain and still has the current
  exact current project `reviewer` grant; or holds the explicit Project Manager/Operator inspection
  permission. Arbitrary same-project reviewers, caller-selected unrelated
  chains, cross-project actors, and revoked grants are denied. Prior
  participation permits bounded metadata only, never content.
- Finding-evidence intake declares `review.finding_evidence.ingest` mapped to
  `review.decision`; the active owned lease and exact server-derived evidence
  scope are lifecycle/resource guards. Pre-intake denial creates no ART
  candidate, binding, or receipt.
- Merged ART-02A2 supplies preparation and ART-02A3 supplies the byte-only v2
  LocalStorage clean cut; neither satisfies this chunk's review-facing ART gate.
  REV imports no ART scratch/source or raw-store implementation. Chunk start
  requires ART submission/checker cutovers, a separately approved and merged
  ART-owner amendment for the currently unassigned narrow packet-read port, and a
  separately approved/merged `WS-ART-001-REV-EVIDENCE` candidate/finalize
  capability with canonical ART facts, guards, orphan retention, and tests.
- Binding finalization requires separately registered planned action
  `artifact.review_evidence.binding.create`, mapped only to
  `artifact.binding.create` and fixed identity `workstream.artifact.binding`.
  It is not an alias of either human evidence-ingest action, generic artifact
  retrieval, or Operator `artifact.binding.read`. AUTH activates it only after
  the hidden ART capability merges.
- The exact locked guide/policy/submission/checker/prior-review chain is
  disclosed as bounded history. Artifact bytes and complete binding metadata
  are retrievable only for the canonical current review packet anchored to the
  one Submission covered by the caller's active lease: that Submission's
  bindings, the bindings attached to
  `ReviewQueueEntry.admitting_checker_run_id`, its current
  finding-response evidence, and required locked-context/source-snapshot
  bindings. The server derives packet membership from canonical relations.
- Review service consumes the checker-owned context-reader port and task-owned
  public relationships; it imports neither CheckerRepository nor TaskRepository.
- Unauthorized, cross-project/task, guessed, and nonexistent bindings are
  concealment-equivalent and expose no binding existence or state. Distinct
  stable availability and integrity errors plus bounded audit are permitted only
  after exact in-scope authority and packet membership are established.
- Prior, later, sibling, and previously leased Submission artifacts fail closed
  without an active lease for that exact Submission. An expired or consumed
  lease grants no residual content authority; history remains metadata-only.
- Human tokens never enter artifact calls; service scope is least privilege.
- Finding evidence and response evidence enter the ART candidate port, become
  verified bindings, and create immutable REV-owned `ReviewEvidenceArtifact`
  relations referenced publicly only by ArtifactBinding ID.
- Reviewer finding evidence uses ART intake under the active lease before its
  ArtifactBinding ID is attached to ReviewFinding. Raw bytes and provider
  locations never enter the Review decision payload.
- Finding-evidence intake requires the active owned lease and exact finding
  evidence operation; response-evidence intake is owned by chunk 09A under
  `review.finding_response_evidence.ingest`, the contributor's owned active
  assignment, and a prepared revision context.
  Scope is derived server-side as exact project/task/submission/finding and
  operation. Intake uses the merged ART-owned two-phase capability: request
  preflight derives scope and ingests/verifies an unbound candidate outside
  review locks; finalization uses AUTH authority lock -> REV lease/assignment,
  Submission, evidence-slot and packet-lineage locks -> ART candidate/admission/
  binding locks -> final fact recomposition -> AUTH validation of exact bindings
  and current authority, single consumption, evaluation, and decision-evidence staging -> binding plus
  ReviewEvidenceArtifact flush. AUTH's opaque, non-Pydantic, single-use
  handle is bound to the exact session, ActionId, actor-reference kind and ID,
  idempotency key, and canonical request digest and is consumed by AUTH before the
  first binding or REV mutation. Wrong-binding, serialized, forged, or
  caller-constructed attempts against an unconsumed handle fail before canonical
  mutation, stage no AuthorizationDecision/evidence, preserve the legitimate
  handle, and permit its later exact first use. Stale/already-consumed and
  concurrent duplicate attempts remain invalid and stage no new state. Current-authority
  or policy denial after valid consumption follows AUTH's clean denial-evidence
  protocol. A mid-intake stale
  lease, revocation, assignment loss, preparation supersession, or cross-project
  mismatch creates no canonical Workstream binding/relation or lifecycle effect;
  an already uploaded unbound candidate remains only under ART retention and
  orphan cleanup. Decision/resubmission revalidates the binding again.
- If the merged ART contract lacks candidate/finalize and orphan-retention
  semantics, this chunk blocks for an ART-owned foundation change. Review code
  adds no private upload/candidate table or provider cleanup path.
- Retrieval is bounded and logs contain no content, signed capabilities, paths,
  credentials, or unrestricted finding text.
- LocalStorage and MinIO pass the same review-artifact contract tests.
- Production OpenAPI remains free of lifecycle routes; no private context is
  exposed before the final product release.
- REV supplies hidden read/evidence behavior and feature-manifest deltas while
  human actions remain planned. `WS-AUTH-001-REV-07` separately activates the
  three REV actions only after this chunk, and
  `WS-AUTH-001-ART-REV-EVIDENCE` activates the ART binding action only after its
  hidden ART capability and exact service identity merge.
- Authorization tests cover submitter, active reviewer, prior participating
  reviewer, takeover reviewer, Project Manager/Operator, arbitrary same-project
  reviewer, cross-project actor, expired lease, and revoked grant. Independent
  session/fault tests race lease expiry and grant revocation against reviewer
  evidence intake in both orders and prove only an ART orphan candidate may
  remain after failed finalization.

## Verification

```text
cd backend && pytest -q tests/test_reviews.py tests/test_artifacts.py tests/test_authorization.py tests/test_checkers.py tests/test_tasks.py tests/test_app.py
cd backend && ruff check app/modules/reviews app/modules/artifacts tests/test_reviews.py tests/test_artifacts.py tests/test_app.py
(metadata_dir="$(mktemp -d)" && trap 'rm -rf "$metadata_dir"' EXIT && (cd backend && WORKSTREAM_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/postgres .venv/bin/python scripts/run_isolated_tests.py --metadata-json "$metadata_dir/result.json" --timeout-seconds 12600 -- .venv/bin/python -m pytest -q --ignore=tests/test_isolated_database_runner.py --cov=app --cov-report=term-missing --cov-fail-under=78))
cd backend && for path in 'app/modules/reviews/*' app/composition/review_lifecycle.py; do coverage report --include="$path" --precision=2 --fail-under=90 || exit 1; done
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, and test-delta.

## Human review focus

Current-review-packet isolation, history/content separation, canonical packet
membership, scope derivation, token isolation, evidence classification,
integrity quarantine, and provider equivalence.

## Stop condition

Merge, record automated memory, and stop. Do not start 08.
