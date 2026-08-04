# WS-QUAL-001-PLAN2 External Review Response

## Comments addressed

The hosted Agent Gates stale-authorization scanner rejected two newly changed
planning lines for ambiguous role-like vocabulary. The plan meant asynchronous
background-job modules, not a product actor class. Both lines now use explicit
background-job terminology.

CodeRabbit's completed review identified six documentation gaps. The repair:

- gives the superseded 01B2 contract an unambiguous machine-readable
  non-executable status;
- defines the exact integer 90.25-percent hosted-evidence calculation and the
  fields that 04R must record;
- limits any additional test chunk to the case where 02R and 03R cannot create
  the required headroom;
- adds the omitted authorization and artifact scanners to deterministic
  evidence; and
- adds a closed-path diff check proving PLAN2 changes only its initiative tree.

## Comments deferred

None. CodeRabbit's fresh review completed and every actionable and nitpick
finding was addressed in this repair.

## Human decisions needed

None beyond normal PR review and explicit merge approval.

## Commands rerun

- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 scripts/check_markdown_links.py`
- `PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py`
- `git diff --name-only origin/main...HEAD | awk 'index($0, ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/") != 1 { print; bad=1 } END { exit bad }'`
- `git diff --check`

## Remaining risks

Hosted Agent Gates, Backend, and CodeRabbit must pass on the repaired exact
head. No backend, test, workflow, or threshold file changes originate in this
repair. PLAN2 also reconciles merged PRs #258 and #249 and uses PR #249's final
hosted coverage evidence as the current baseline.
