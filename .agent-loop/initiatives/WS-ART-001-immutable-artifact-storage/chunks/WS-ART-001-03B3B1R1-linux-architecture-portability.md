# WS-ART-001-03B3B1R1: Linux Architecture Portability

## Intent

Provide one copy-pasteable backend setup for contributors on macOS, Windows,
Linux ARM, and Linux x86_64 without weakening Workstream's Linux-only image
extractor isolation boundary.

## Scope

Extend the existing hash-bound Pillow approval from Linux glibc x86_64 to the
corresponding Linux glibc aarch64 wheels for CPython 3.11 and 3.12. Add a
native-architecture Linux development container, connect it to the
repository-managed services, and make Docker versus native setup explicit in
contributor-facing documentation.

## Allowed Files

- `README.md`
- `CONTRIBUTING.md`
- `.dockerignore`
- `backend/.env.example`
- `backend/app/modules/artifacts/guide_extraction.py`
- `backend/config/guide_extractor_dependencies.json`
- `backend/pyproject.toml`
- `backend/scripts/check_guide_extractor_dependencies.py`
- `backend/tests/test_guide_extractor_dependencies.py`
- `backend/tests/test_guide_extraction.py`
- `backend/uv.lock`
- `docker/backend/Dockerfile.dev`
- `docker-compose.yml`
- `docs/operations_backend_testing.md`
- `docs/spec_artifact_storage_service.md`
- this chunk contract

## Not Allowed

- macOS, Windows, musl, or 32-bit native parser support
- source distributions, unpinned packages, relaxed hashes, or index fallback
- a Pillow version change or unrelated dependency update
- parser output semantics, migrations, production images, or deployment
  configuration; only the fixed secret-free extraction child environment may change
- CI workflow, test-routing, or coverage changes
- automatic destructive database or volume resets

## Acceptance Criteria

- Pillow has exact URL and SHA-256 approvals for CPython 3.11 and 3.12 on both
  manylinux x86_64 and manylinux aarch64, with no sdist or fallback path.
- PEP 508 markers are mutually exclusive by Python version and machine and
  select only Linux artifacts.
- The dependency gate accepts only CPython 3.11/3.12 on Linux glibc x86_64 or
  aarch64 and continues to reject macOS, Windows, musl, unsupported Python, and
  other architectures.
- The Docker workflow uses the host Docker VM's native x86_64 or aarch64 Linux
  architecture, applies migrations, and serves `GET /api/v1/health` on host
  loopback.
- A real isolated image extraction succeeds inside the aarch64 development
  container with Workstream's inner seccomp filter active.
- The extraction child's fixed environment disables ARM OpenSSL acceleration
  without inheriting arbitrary parent variables, and real PDF extraction also
  succeeds inside the aarch64 development container.
- Native host setup is documented only for supported Linux glibc architectures;
  macOS and Windows users are directed to Docker.
- Tracked environment examples contain local-only values or placeholders, no
  deployable credentials, and `.env` remains ignored.
- Existing Postgres, Redis, and MinIO service workflows remain available.
- Setup, verification, shutdown, and explicitly destructive reset commands are
  clear and copy-pasteable.
- Any pull request changing the approval manifest requires fresh independent
  approval on its exact final head from a repository owner, member, or
  collaborator before merge.

## Risk

L1 supply-chain and native-runtime change. The implementation expands one
approved Linux architecture while preserving the Linux/glibc isolation model,
exact artifact hashes, and fail-closed platform checks.

## Verification

Supported native Linux checkout, after installing the locked development environment
(hosted CI runs the equivalent checks with its managed interpreter):

- `cd backend && uv lock --check`
- `cd backend && .venv/bin/python scripts/check_guide_extractor_dependencies.py`
- `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p pytest_cov.plugin tests/test_guide_extractor_dependencies.py --cov=scripts.check_guide_extractor_dependencies --cov-branch --cov-report=term-missing --cov-fail-under=90`
- `cd backend && .venv/bin/python -m scripts.authorization_boundary validate --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/IMPORT_LEDGER.md`
- `cd backend && .venv/bin/python -m scripts.test_structure_boundary validate --policy ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_POLICY.md --ledger ../.agent-loop/initiatives/WS-AUTH-003-module-boundary-recovery/TEST_STRUCTURE_DEBT.json`
- `cd backend && .venv/bin/python -m scripts.behavior_ownership validate`
- `cd backend && install -d -m 700 .ci/test-lanes`
- `cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python scripts/run_test_lanes.py --collect-only --metadata-dir .ci/test-lanes/collect --summary-json .ci/test-lanes/collect-summary.json`
- `cd backend && .venv/bin/python scripts/validate_test_lane_evidence.py --metadata-dir .ci/test-lanes/collect --summary-json .ci/test-lanes/collect-summary.json`

Native-architecture Docker:

- `docker compose run --rm --no-deps backend python -m pytest -q tests/test_guide_extraction.py -k real_isolated_image_runner`
- `docker compose run --rm --no-deps backend python -m pytest -q tests/test_guide_pdf.py -k isolated_runner`
- `docker compose config --quiet`
- `docker compose build backend`
- `docker compose up --wait backend`
- `curl --fail http://127.0.0.1:8000/api/v1/health`
- `docker compose run --rm --no-deps backend ruff check app tests scripts`

Repository-root checks:

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 -m unittest -v scripts.test_lightweight_agent_gates`
- `git diff --check`

## Reviewers

- security
- architecture
- QA/test
- CI integrity
- documentation
- reuse/deduplication
- senior engineering
