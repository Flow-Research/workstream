# WS-ENG-001-04B Internal Review Evidence

Reviewed code SHA: `da9b2291275ce28b3f839b9e18ebac7dba9c9de0`

Reviewed at: 2026-07-20T23:56:00Z

Reviewer run IDs: senior-engineering/architecture/reuse-dedup=`timeout_senior_docs`; QA/test/CI-integrity/test-delta=`timeout_ci_qa`; security/auth/product/ops/docs=`timeout_sec_ops`

Open sub-agent sessions: none

Valid findings addressed: yes

Reviewed against trusted main: `61bc0390947ad397a0b9bdd088c5111bd5477da1`

## Deterministic evidence

- 151 relevant tests pass with plugin autoload disabled; the final repair-focused
  run passes 134 tests, including historical cutover and workflow mutations.
- `update_post_merge_memory.py` passes its independent 90 percent branch gate
  at 90.16 percent; `check_loop_memory_state.py` passes at 91.07 percent.
- Ruff, compilation, merge-intent validation, Markdown links, stale wording,
  hash-pinned dependency resolution, workflow structure, and diff checks pass.
- Remote publication failure leaves the canonical remote tip unchanged.
- Live environment inspection returned 404; deployment remained blocked until
  the protected approval environment was configured and evidenced. The user
  approved reuse of the existing loop-memory signing identity after this review.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| Senior engineering | Pass after fixes | None | Global and initiative lifecycle state are coherent and maintainable. |
| QA/test | Pass after fixes | None | Full authority, cutover, replay, tamper, and atomicity matrix passes. |
| Security/auth | Pass after fixes | None | Authority, approval, tip, input, secret, and publication boundaries fail closed. |
| Product/ops | Pass after fixes | None | Operator recovery and one-use cutover semantics are explicit. |
| Architecture | Pass after fixes | None | Every authority transition binds to its exact preceding signed basis. |
| CI integrity | Pass after fixes | None | Required independent coverage gates pass; no prior gate is weakened. |
| Docs | Pass after fixes | None | Dispatch, audit, recovery, and unsupported key rotation are documented. |
| Reuse/dedup | Pass after fixes | None | Both workflows use one repository-owned publication boundary. |
| Test delta | Pass after fixes | None | Additive mutation tests cover every demonstrated unsafe variant. |

## Findings resolved

- Removed shell interpolation of dispatch inputs and bound approval history to
  the exact `loop-memory-start` environment.
- Bound the signed prior tip to the actual state-branch HEAD and rechecked it at
  publication.
- Separated coherent global merge state from initiative-local authority state,
  including deterministic reduction of two simultaneous active initiatives.
- Added a typed cutover, exact one-use exemption consumption, and exact active
  merge closure.
- Bound nested authority source, metadata, initiative, successor, and transition
  to the latest preceding signed lifecycle in both independent validators.
- Centralized empty-index tree creation, validation, parent binding, commit, and
  fixed fast-forward push for both workflows.
- Replaced unsafe key-rotation guidance with a fail-closed incident boundary.
- Made the one-time cutover an explicit workflow argument, loaded its inventory
  from the immutable cutover merge, and pinned the exact production arguments.
- Scoped merge replay to `loop-memory.yml`; failed start/cancel events require a
  fresh protected and attributable dispatch.

## Deployment evidence

GitHub environment `loop-memory-start` is configured as environment ID
`18466331045` with `durutheguru` as required reviewer, self-review disabled,
administrator bypass disabled, and protected-branch-only deployment. The
existing repository secret `LOOP_MEMORY_SIGNING_KEY` is present; no second key
was created or transferred.

## Remaining gate

Internal review and environment configuration are complete. Hosted checks and
human approval passed on pre-repair PR head `e8ade1f8`. After the repaired
evidence head is pushed, fresh hosted checks, CodeRabbit re-review, and any
branch-policy-required renewed human approval remain before user-owned merge.
