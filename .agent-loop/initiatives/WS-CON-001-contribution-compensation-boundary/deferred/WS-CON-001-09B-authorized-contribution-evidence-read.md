# Deferred Proposal: WS-CON-001-09B - Optional Authorized Contribution Evidence Read

## Status

Deferred optional successor after separately approved and merged CON-09A. It is
not a prerequisite for core contribution/award reads. This file is deliberately
not an implementation contract and authorizes no file changes.

## Prospective risk

L1 disclosure, authorization, artifact-retention, and cross-subsystem read
boundary. Risk and scope must be reclassified against then-current ART/AUTH
contracts before promotion.

## Goal if separately approved

Expose a bounded evidence-export read through a separately proven ART read
capability and exact AUTH disclosure contract.

## Allowed files now

None. A separately human-approved, internally reviewed replacement chunk
contract must name exact allowed files before implementation.

## Prohibited changes

```text
runtime, route, schema, migration, dependency, workflow, AUTH, ART, or activation changes
CON-10A contribution/award truth or availability dependencies
public evidence route or provider/credential disclosure
reuse of the CON-09A write capability as an implicit read capability
```

## Promotion acceptance criteria

- [ ] CON-09A is separately approved, merged, and refreshed against trusted
  main; its absence or failure still cannot affect CON-10A.
- [ ] The replacement contract names exact ART read capability, projection
  schema/binding/retention, AUTH disclosure ActionIds/contexts/candidates, and
  self/project concealment rules without reviewer-private/provider/credential
  disclosure.
- [ ] Exact allowed files, prohibited changes, runtime tests, migration impact,
  coverage targets, reviewers, and stop conditions are approved before any
  implementation.
- [ ] Routes stay hidden until their own merged AUTH evaluator/activation and
  optional release gate pass.

## Mandatory refresh gate

- Re-review the then-current projection schema/binding/retention state and ART
  read port independently from the write port.
- Define exact self/project candidates, pre-filtering, concealment, media/schema
  validation, and no reviewer-private/provider/credential disclosure.
- Prove evidence absence/failure leaves PostgreSQL contribution/award truth and
  CON-10A reads unaffected.
- Keep routes hidden until its own AUTH evaluator/activation and optional release
  gate pass.

## Verification before promotion

Run from the repository root against the proposed replacement contract:

```bash
test -f docs/spec_artifact_storage_service.md
test -f docs/spec_authorization_service.md
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
git diff --check
if ! changed_files="$(git diff --name-only origin/main...HEAD)"; then
  exit 1
fi
allowed_paths='^\.agent-loop/REVIEW_LOG\.md$|^\.agent-loop/merge-intents/WS-CON-001-09B\.json$|^\.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/(CHUNK_MAP\.md|STATUS\.md|(chunks|deferred)/WS-CON-001-09B-authorized-contribution-evidence-read\.md|reviews/WS-CON-001-09B-[^/]+\.md)$'
if unexpected="$(printf '%s\n' "$changed_files" | rg -v "$allowed_paths")"; then
  printf '%s\n' "$unexpected"
  exit 1
else
  rg_status=$?
  test "$rg_status" -eq 1
fi
```

Pass only proves that a planning-only replacement contract is eligible for
internal review: every command exits zero, no runtime/workflow delta exists,
and the contract closes every promotion criterion above. It does not authorize
implementation.

## Required reviewers before promotion

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, ART boundary, AUTH boundary, CI integrity, and test delta.

## Stop

Do not start without separate human approval and a replacement internally
reviewed chunk contract. CON-10A proceeds independently.
