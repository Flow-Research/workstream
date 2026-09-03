# Internal Review Evidence: WS-AUTH-001-02

## Chunk

`WS-AUTH-001-02` - Verified Issuer Token And JWKS Boundary

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: ad15c05ef24d08b38f9965080344b25cd3ba6ac1

Reviewed at: 2026-07-13T02:42:50Z

Reviewer run IDs: senior-engineering=/root/auth02_parallel_resume/auth02_eng_arch_review; architecture=/root/auth02_parallel_resume/auth02_eng_arch_review; reuse-dedup=/root/auth02_parallel_resume/auth02_eng_arch_review; security-auth=/root/auth02_parallel_resume/auth02_eng_arch_review; product-ops=/root/auth02_parallel_resume/auth02_eng_arch_review; docs=/root/auth02_parallel_resume/auth02_eng_arch_review; qa-test=/root/auth02_parallel_resume/auth02_qa_ci_review; test-delta=/root/auth02_parallel_resume/auth02_qa_ci_review; ci-integrity=/root/auth02_parallel_resume/auth02_qa_ci_review; evidence-engineering=/root/auth02_evidence_eng; evidence-qa=/root/auth02_evidence_qa

## Reviewed Change

Reviewed implementation SHA: `47dd5a77c588d1b2b4e7f00489faf4c633f26aa2`.
Final reviewed evidence-bound SHA: `ad15c05ef24d08b38f9965080344b25cd3ba6ac1`.

- Added pinned asymmetric JWT verification with mandatory issuer, audience,
  temporal, `jti`, subject-kind, and coarse-scope claims.
- Added bounded JWKS retrieval, eligible-key validation, rotation, cache,
  single-flight refresh, cooldown, and negative-`kid` behavior.
- Added optional required introspection with a distinct credential-bearing
  client boundary, exact-origin HTTPS policy, redirect refusal, deadlines,
  response bounds, and verified-identity matching.
- Retained one application-bound production verifier and process cache while
  preserving dynamic local test fixtures without admitting them to production.
- Kept issuer roles outside `VerifiedIssuerToken`; only a bounded human-only
  `LegacyAuthorizationCompatibilityContext` reaches the enumerated temporary
  compatibility dependency.
- Added bounded-cardinality verifier metrics without token, subject, `jti`,
  credential, key, or URL labels.
- Added the approved `PyJWT[crypto]>=2.13,<3.0` production dependency and moved
  existing HTTPX support to base dependencies under D12.
- Updated the API drill, canonical auth specification, operations runbook, and
  identity-metadata compatibility expectations.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | App-bound verifier ownership, cache lifecycle, current-main integration, and implementation boundaries are coherent. |
| QA/test | PASS | None | Independently reproduced 130 focused and changed tests; size, temporal, introspection, client-lifecycle, and role-bound branches are explicit. |
| security/auth | PASS | None | Production requests cannot select global issuer settings; signature, algorithm, JWKS, introspection, subject, scope, and role-authority paths fail closed. |
| product/ops | PASS | None | Compatibility remains human-only, identity metadata transition is documented, and no review/payment/product lifecycle semantics changed. |
| architecture | PASS | None | Existing verifier port/factory evolved in place; JWKS and introspection clients are distinct and operation-owned. |
| docs | PASS | None | Runbook evidence commands are executable, `jti` is mandatory, and null compatibility metadata behavior is explicit. |
| CI integrity | PASS | None | No workflow, threshold, ignore, skip, or bypass change; the approved dependency move installs cleanly. |
| reuse/dedup | PASS WITH LOW RISKS | None | Shared bounded role normalization replaces adapter drift; an unused compatibility wrapper remains low-risk cleanup. |
| test delta | PASS | None | No removed, skipped, xfailed, or weakened tests; all three additional changed actor/task metadata nodes pass independently. |

## Valid Findings Addressed

- Bound production request authentication to the exact verifier retained by
  the application instead of rebuilding from unrelated global settings.
- Added explicit injectable JWKS and introspection client factories and proved
  separate client instances close after each operation.
- Reused one bounded role normalizer for Flow and development adapters.
- Added total/header/payload token-size rejection with zero network access.
- Added independent within/outside-skew tests for `exp`, `iat`, and `nbf`.
- Added missing `iss`, `sub`, `aud`, and `jti` introspection-response tests.
- Reproduced the three changed identity-metadata tests in isolation and fixed
  the app-scoped development verifier behavior that exposed their dependency.
- Corrected the runbook to use `WORKSTREAM_TEST_DATABASE_URL` for pytest and
  map the same disposable database to the API drill.
- Made `jti` mandatory in the canonical specification and documented that
  compatibility actor responses do not copy issuer email/display name.
- Integrated PR #105 and PR #106 without changing their coverage ownership or
  activating later coverage work.

## Commands Run

```bash
(clean temporary venv) python -m pip install -e ./backend
(clean temporary venv) python -c 'import jwt, cryptography, httpx'
(clean temporary venv) python -m pip check
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && isolated-runner pytest -q tests/test_auth.py tests/test_config.py <three changed test nodes>)
(cd backend && isolated-runner pytest -q --ignore=tests/test_isolated_database_runner.py)
(cd backend && isolated-runner .venv/bin/python scripts/api_contract_e2e.py)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
git diff --check
```

Results:

- clean base install imported PyJWT 2.13.0, cryptography 49.0.0, and HTTPX
  0.28.1; `pip check` passed;
- focused auth/config plus the three changed tests: 130 passed;
- full backend suite: 680 passed in 7653.15 seconds;
- real API contract drill: passed through submission/checker/audit behavior;
- Ruff, wording, auth-doc, Markdown, loop-memory, dependency, and diff gates:
  passed;
- docstring coverage: 96.8 percent overall, gate passed.

## Evidence Gate

Evidence gate: PASS

Scope exception: 25 changed files, 2,727 additions, and 344 deletions (3,071
total changed lines) exceed the ordinary PR-size preference because this
approved L1 chunk atomically owns the
external-token contract, bounded JWKS/introspection implementation, exhaustive
negative proof matrix, compatibility boundary, metrics, configuration, API
drill, and operator contract. Splitting those coupled security guarantees would
create an intermediate production verifier with incomplete fail-closed proof.
No actor/grant migration, product permission cutover, review, contribution,
payment, frontend, token issuance, or later AUTH behavior entered scope.

## Remaining Risks

- Production issuer/JWKS/introspection values and live issuer behavior remain
  deployment inputs; deterministic injected transports prove code behavior but
  do not replace the later live proof.
- Development DI intentionally rebuilds through the process cache when tests
  change local settings; production always uses the app-retained verifier.
- `actor_id_from_flow_identity` remains an unused compatibility wrapper.
- Legacy role compatibility remains until its owning authorization cutover and
  removal chunks; it is not product authority in this chunk.

## Stop Condition

Stop after PR publication for human review. Do not merge without explicit user
approval and do not start `WS-AUTH-001-03`, `WS-POL-002-04`, REV, CON, or a
coverage successor automatically.
