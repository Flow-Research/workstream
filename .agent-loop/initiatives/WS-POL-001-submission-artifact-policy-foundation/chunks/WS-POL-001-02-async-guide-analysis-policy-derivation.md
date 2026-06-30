# Chunk Contract: WS-POL-001-02 - Async Guide Analysis And Policy Derivation

## Parent Initiative

WS-POL-001 - Submission Artifact Policy Foundation

## Goal

Add the Workstream-owned agent-runtime contract, OpenAI Agents SDK adapter,
async guide sufficiency and submission artifact policy derivation paths, and
the trusted project pre-submit checker compiler that writes compiled
`PreSubmitCheckerPolicy` fields.

This chunk keeps the architecture project-scoped. It does not generate a
checker per task.

## Why This Chunk Exists

Chunk 1 created the records and activation dependency:

```text
GuideSourceSnapshot
-> GuideSufficiencyReport
-> SubmissionArtifactPolicy
-> EffectiveProjectSubmissionArtifactPolicy
-> project PreSubmitCheckerPolicy
```

Chunk 1 still relied on tests and local E2E helpers to mark the project
`PreSubmitCheckerPolicy` compiled. That temporary path must be replaced by a
trusted Workstream compiler.

This chunk also introduces the agent runtime boundary. Workstream owns the
domain contract. OpenAI Agents SDK is the first adapter. Other runtimes, such as
OmnicoreAgent, LangChain, or DeepAgents, can be evaluated later behind the same
contract without changing project setup services.

## Risk Class

L1

## SLA

P1

## Implementation Allowed Files

```text
backend/pyproject.toml
backend/app/core/config.py
backend/app/core/hashing.py
backend/app/core/project_agents.py
backend/app/interfaces/project_agents.py
backend/app/adapters/project_agents/**
backend/app/modules/projects/**
backend/app/modules/checkers/**
backend/tests/test_projects.py
backend/tests/test_checkers.py
backend/tests/test_tasks.py
backend/scripts/week1_api_e2e.py
README.md
docs/architecture_checker_framework.md
docs/decision_0011_submission_artifact_policy_drives_pre_submit.md
docs/spec_chunk_8_submission_artifact_policy_checkers.md
.agent-loop/LOOP_STATE.md
.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/**
```

## Implementation Not Allowed

```text
backend/app/modules/tasks/**
backend/app/modules/submissions/**
backend/app/adapters/auth/**
.github/workflows/**
demos/**
examples/**
frontend/**
payment/reputation/blockchain code
object-storage implementation
human review implementation
submission creation runtime rewiring
post-submit lifecycle changes
```

## Implementation Boundaries

- Project services orchestrate setup and own permission-aware state changes.
- Agent runtime code lives behind a Workstream port/interface.
- OpenAI Agents SDK code lives only in an adapter; services must not import SDK
  classes directly.
- The default test/local runtime must be deterministic and must not require
  network access or an OpenAI API key.
- OpenAI credentials are read only from runtime configuration/environment.
  Credentials must never be persisted in database records, emitted in logs or
  errors, embedded in evidence artifacts, or committed in fixtures.
- Agent output is untrusted until server-side validation and compiler checks
  pass.
- Guide text, imported docs, examples, rubrics, and source refs are untrusted
  data. They cannot grant agent authority, choose tools, alter fetch behavior,
  weaken Workstream defaults, or override server-side policy validation.
- The compiler owns deterministic checker bundle generation.
- Compiler output is the only path that marks `PreSubmitCheckerPolicy` as
  `compiled`.
- The compiler compiles once per effective project policy, not once per task.
- Workers and project owners cannot submit checker names, severities, versions,
  outcomes, compiler version, or compiled bundles.

## Acceptance Criteria

- [ ] A Workstream agent-runtime port exists for guide sufficiency analysis and
      submission artifact policy derivation.
- [ ] OpenAI Agents SDK adapter exists behind the port and is optional/configured,
      not imported by project services directly.
- [ ] Local/test default agent runtime is deterministic and async.
- [ ] Local/test default requires no network and no OpenAI API key.
- [ ] Tests prove OpenAI credentials are env/config-only, never persisted in
      project setup records, never emitted in API errors, and not required for
      deterministic local/test runtime.
- [ ] `ProjectGuideSufficiencyAgent` can run against an immutable
      `GuideSourceSnapshot` and persist a `GuideSufficiencyReport`.
- [ ] Malicious guide text and embedded prompt-injection instructions are
      treated as source content only and cannot influence agent authority,
      fetch behavior, policy strength, compiler behavior, or defaults.
- [ ] Unsafe source refs are rejected by server-side validation and cannot be
      introduced by agent output.
- [ ] Unsafe source-ref tests cover credential-bearing refs, token-bearing refs,
      signed URL material, and local filesystem paths according to the
      WS-POL-001-01 sanitization contract.
- [ ] Blocking guide gaps stop activation and produce project-owner
      clarification findings.
- [ ] `passed_with_warnings` reports require `admin` or `project_manager`
      acknowledgement before derivation can proceed.
- [ ] `SubmissionArtifactPolicyDerivationAgent` can run after sufficiency passes
      or warnings are acknowledged and persist a draft `SubmissionArtifactPolicy`.
- [ ] Agent-derived policy cannot weaken Workstream defaults.
- [ ] Derived report and policy bind to `source_snapshot_id` and
      `source_snapshot_hash`.
- [ ] Running agent setup twice for the same guide source snapshot is
      idempotent.
- [ ] New guide source snapshots make prior derived setup records stale for new
      activation.
- [ ] Trusted checker compiler emits only approved Workstream primitives.
- [ ] Trusted checker compiler rejects unknown primitives.
- [ ] Trusted checker compiler rejects omitted required artifact coverage.
- [ ] Trusted checker compiler rejects skipped evidence coverage.
- [ ] Trusted checker compiler rejects weakened severity for blocking platform
      defaults.
- [ ] Trusted checker compiler rejects missing Workstream default rules.
- [ ] Same effective policy plus same compiler version produces byte-stable
      compiled bundle hashes.
- [ ] `approve_submission_artifact_policy` compiles and persists the project
      `PreSubmitCheckerPolicy` bundle/hash through the compiler path.
- [ ] Guide activation succeeds after policy approval without test-only direct
      compiled-field mutation.
- [ ] Task runtime parameters remain non-authoritative and cannot override
      checks, severity, storage, forbidden artifacts, hash algorithm, or
      platform defaults.

## Verification Commands

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests/test_projects.py tests/test_checkers.py
cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest tests
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
git diff --check
```

## Required Reviewers

Every listed reviewer must end with one exact result value:

- `PASS`
- `PASS AFTER FIXES`
- `PASS WITH LOW RISKS`
- `N/A - with approved reason`

Required:

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta
- CI integrity

CI integrity is required because this chunk may touch `backend/pyproject.toml`
to declare the optional OpenAI Agents SDK extra.

## Human Review Focus

- Agent runtime interface boundaries.
- OpenAI adapter isolation.
- Sufficiency findings and clarification shape.
- Compiler primitive set and semantic coverage checks.
- Assurance that project checker compilation is project-scoped, not task-scoped.
- Assurance that task/submission runtime was not rewired in this chunk.
