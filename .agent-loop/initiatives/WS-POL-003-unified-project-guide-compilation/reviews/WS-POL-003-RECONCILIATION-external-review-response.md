# WS-POL-003 Planning Reconciliation External Review Response

Date: 2026-08-08
PR: #298

## Comments addressed

- Separated 12I's complete active inventory from explicitly historical and
  non-activatable 12E/12F3/legacy-12G inference rows.
- Added exact 12I permission, owner, principal, resource/PREP, and proof custody.
- Bound 12F4, POL-002 runtime, and CON consumption to complete compilation,
  result, component, catalogue, compiled-plan, and approval provenance.
- Clarified AUTH-14 owns `submission.create` authorization/evidence while ART
  and POL own Submission/checker product behavior.
- Narrowed the cleanup scanner to legacy standalone inference without blocking
  WS-POL-003 unified provider compilation.
- Marked POL-002 D1-D8 and remaining intent text explicitly historical.
- Replaced stale human-principal terminology with fixed setup-service terminology.
- Bound each POL-04B projection PREP to compilation, accepted result, and the
  matching component hash.
- Distinguished zero-call correction/recovery from a new-generation attempt
  with a new idempotency key.
- Applied the requested `end-to-end` wording correction.
- Expanded the PR description to the complete trust-bundle structure.

## Comments deferred

None.

## Human decisions needed

None. All comments reinforce the already approved unified-compilation design.

## Commands rerun

```text
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

## Remaining risks

Future planning skeletons still require then-current executable contracts
before implementation. This PR activates nothing.
