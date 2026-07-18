# Chunk Contract: WS-ART-001-OBJECT-STORAGE-AMENDMENT - Object Storage Planning Amendment

Initiative: `WS-ART-001` | Risk: L1 | Status: Merged through PR #120

## Goal

Replace the deferred Flow Node-first v0.1 plan with one provider-neutral object-storage
contract using AWS S3 as the only production provider, MinIO for local/CI
protocol proof, LocalStorage for focused development, and separately deferred
R2 and Flow Node adapter plans. It also records the user's separately explicit
repository-wide external-service adapter convention while leaving every
non-artifact capability migration to its own initiative. This chunk changes
planning and guardrails only.

## Allowed Files

- `AGENTS.md`, `README.md`, and artifact-related active architecture/spec/ADR/
  glossary/template documentation;
- `docs/decision_0014_external_service_adapter_convention.md` for the explicitly
  approved repository-wide adapter/factory convention only;
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/` planning,
  chunk contracts, decisions, risks, status, and planning review evidence;
- `.agent-loop/initiatives/FN-ART-002-deferred-flow-node-artifact-store/`;
- `docs/spec_authorization_service.md` and
  `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/`
  `DECISIONS.md`, `STATUS.md`, `CHUNK_MAP.md`, the completed `04B` contract only
  to repair its stale WS-ART reference, and proposed WS-AUTH contracts `07`,
  `08`, `09`, `12`, `14`, and `15` only to register and map the exact artifact
  permissions that later WS-ART chunks consume;
- `.agent-loop/MEMORY.md`, `.agent-loop/LOOP_STATE.md`,
  `.agent-loop/WORK_QUEUE.md`, `.agent-loop/REVIEW_LOG.md`, and
  `.agent-loop/policies/engineering-review-policy.md` only where the planning
  contract requires durable state or clarification;
- `.agent-loop/policies/repository-engineering-policy.md` only to align its
  active storage-provider rule with this amendment;
- `scripts/check_stale_artifact_contracts.py`,
  `scripts/agent-gate-requirements.txt`, focused gate tests, and exact
  Agent Gates/backend coverage workflow controls.

## Not Allowed

- backend application, migration, product dependency, Compose service, or
  product-runtime workflow implementation;
- active ArtifactStore, LocalStorage, S3, MinIO, Flow Node, Celery, API,
  authorization, guide, task, submission, checker, or review behavior changes;
- backward-compatibility aliases, dual providers, runtime fallbacks, or product
  role/decision changes;
- implementation of any proposed chunk.

## Acceptance Criteria

- AWS S3 is the only v0.1 production provider behind
  `S3CompatibleArtifactStore`; MinIO is local/CI protocol proof and LocalStorage
  is not production eligible;
- AWS production uses a dedicated Workstream artifact bucket. Runtime IAM
  allows put/get only on the completed-object ARN and `s3:ListBucket` only on
  that bucket so missing `HeadObject` returns 404; the port/application exposes
  no object-list operation and every 403 remains provider unavailable;
- every untrusted byte source is server-hashed before provider I/O and the v2
  port accepts only a sealed `CommittedArtifactSource`;
- Chunk 02C1 owns one generic durable-byte admission ledger before any guide,
  contributor, or checker-output cutover; 04A owns only contributor
  upload-session slot expiry in addition to consuming that shared ledger;
- R2 has no provider adapter, credential issuer, provider profile, deployment
  service, or implementation chunk. Existing caller-declared `r2://` transport
  values are legacy input contracts owned by the clean Chunks 03 and 05
  cutovers and are removed there without an alias or compatibility path;
- deferred Flow Node is fully planned but absent from the v0.1 dependency graph;
- active v0.1 implementation is split into reviewable L1 chunks with exact
  scope, acceptance criteria, runnable commands, 90 percent changed-subsystem
  coverage, and the 78 percent repository floor; deferred Flow Node commands
  remain placeholders until mandatory discovery activates that initiative;
- active-doc stale checks are discovery-based and historical evidence/reference
  paths are explicitly excluded; active provider clauses accept R2 only when
  they explicitly keep it deferred/outside v0.1, and runtime Cloudflare/R2
  symbols fail closed;
- every artifact coverage phase is parsed from its contract, bound to the
  stale-contract phase marker, and the backend full-suite coverage step is
  checked as one exact command and environment contract;
- no application/runtime files differ from the planning chunk base.

## Verification

```bash
git diff --check ab49b731b1774421af5088a6063461b7b7f29f86...HEAD
python3 scripts/check_markdown_links.py --changed-only ab49b731b1774421af5088a6063461b7b7f29f86...HEAD
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
(agent_gate_venv="$(mktemp -d)" && \
  trap 'rm -rf "$agent_gate_venv"' EXIT && \
  python3 -m venv "$agent_gate_venv" && \
  "$agent_gate_venv/bin/python" -m pip install --disable-pip-version-check --require-hashes -r scripts/agent-gate-requirements.txt && \
  "$agent_gate_venv/bin/python" scripts/test_agent_gates.py)
git diff --name-only ab49b731b1774421af5088a6063461b7b7f29f86...HEAD -- backend/app backend/alembic backend/pyproject.toml docker-compose.yml
```

The final command must print no paths.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is object storage simpler than operating Flow Node while preserving future
  portability?
- Is AWS S3 production-ready without coupling product services to its adapter?
- Are implementation chunks narrow enough to review and stop independently?
