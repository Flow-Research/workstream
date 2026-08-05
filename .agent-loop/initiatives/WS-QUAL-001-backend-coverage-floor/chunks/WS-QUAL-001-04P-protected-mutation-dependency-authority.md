# Chunk Contract: WS-QUAL-001-04P — Protected Mutation Dependency Authority

## Goal

Place one reviewed, exactly pinned, hash-verified mutation-tool dependency
authority on protected `main` before the separately started 04M pilot.

## Why this chunk exists

04M must not install a mutation toolchain selected by its own pull request.
Protected `main` therefore needs to own the approved engine and complete
transitive dependency manifest first.

## Risk class

L1 — development/CI supply-chain prerequisite.

## Allowed files

```text
scripts/mutation-requirements.in
scripts/mutation-requirements.txt
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/CHUNK_MAP.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/STATUS.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/chunks/README.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/chunks/WS-QUAL-001-04M-changed-scope-mutation-pilot.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/chunks/WS-QUAL-001-04P-protected-mutation-dependency-authority.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/reviews/WS-QUAL-001-04P-internal-review-evidence.md
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/reviews/WS-QUAL-001-04P-pr-trust-bundle.md
```

## Not allowed

```text
workflow or mutation execution
backend application, test, pyproject, or uv.lock changes
production dependency changes
coverage-threshold or existing CI changes
automatic start of 04M or 05M
```

## Acceptance criteria

- [ ] `mutmut==3.7.0` is the sole mutation engine.
- [ ] The complete transitive closure is exactly pinned and every requirement
      carries one or more SHA-256 hashes.
- [ ] The mutation runner uses the backend-aligned `pytest==8.4.2` and
      `coverage==7.15.2` versions, and every other overlapping package matches
      `backend/uv.lock`.
- [ ] A clean Python 3.12 `pip --require-hashes` dry run accepts the manifest,
      and Python 3.11 resolves a complete compatible hashed wheel set.
- [ ] The manifest contains no project production dependency or index override.
- [ ] 04M may read only the protected base-revision manifest and cannot modify
      either authority file.
- [ ] Apart from `scripts/mutation-requirements.in` and its compiled manifest,
      no workflow, Backend runtime, test, production dependency, lockfile, or
      coverage gate changes.

## Verification commands

```bash
mutation_tmp=$(mktemp -d)
python3.12 -m venv "$mutation_tmp/venv"
"$mutation_tmp/venv/bin/python" --version
"$mutation_tmp/venv/bin/python" -m pip install --dry-run --require-hashes -r scripts/mutation-requirements.txt
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py
git diff --check
```

## Required reviewers

- security/auth
- CI integrity
- reuse/dedup
- docs

## Human review focus

Confirm the manifest is development/CI-only, exactly pinned and hashed, aligned
with the backend test toolchain, and immutable to 04M PR-head code.

## Stop conditions

Stop if the engine cannot coexist with the backend's Python 3.11/3.12 contract,
requires a production dependency change, or cannot be installed with hash
checking enabled.
