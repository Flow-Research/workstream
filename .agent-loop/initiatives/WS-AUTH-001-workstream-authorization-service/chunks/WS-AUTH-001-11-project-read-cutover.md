# Chunk Contract: WS-AUTH-001-11 - Project Read Cutover Planning Parent

## Status

Planning-only parent authorized by successful signed explicit-start workflow
run `30167274426` on exact trusted-main SHA
`bba4ba5f171a4438b072740707a5cf8bde49d9af`. Runtime implementation is
prohibited. Signed automation remains the live-state authority; authored
`STATUS.md` does not mirror conversational activity. This chunk defines the
complete hard-cutover inventory and four separately started L1 children.

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Replace token-role authorization on every current project GET surface with
registered local authority, without retaining a fallback or changing project
mutations. This parent resolves the design and sequencing only.

## Why this chunk exists

The inherited contract combined catalogue migration, a new actor-context API,
minimal contributor projection, and sensitive setup/policy/guide disclosures.
Those boundaries need independent evidence and review. The split preserves a
hard cutover while keeping each runtime change reviewable.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Allowed files

```text
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/merge-intents/WS-AUTH-001-11.json
```

## Not allowed

```text
backend/**
runtime authorization or route changes
permission or action activation
compatibility aliases, token-role fallback, or dual authorization paths
project create/update, guide/source mutation, policy approval, or activation
task/submission/checker authorization
```

## Exact surface and action inventory

Targets preserve the current project/guide/child-resource hierarchy. Project
identity and active-guide actions map to existing `PermissionId.PROJECT_READ`.
11A introduces the read-only `project.setup_diagnostic.read` and
`project.effective_policy.read` permissions so inspection never borrows a
management permission. Project Manager, Operator, and Audit Authority receive
those permissions under their existing scopes; Finance Authority, Access
Administrator, and contributor grants do not. The actor-context action maps to
existing `PermissionId.ACTOR_PROFILE_READ_SELF`.

| ActionId | Surface | Target and principal boundary | Child |
|---|---|---|---|
| `project.read` | `GET /api/v1/projects/{project_id}` | exact project; eligible admin grants or active exact-project submitter/reviewer/adjudicator grant | 11B |
| `actor.authorization_context.read` | new `GET /api/v1/actors/me/authorization-context?project_id=...` | self actor plus canonical project; disclose only effective caller authority for that project | 11B |
| `project.setup_run.read` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest` | exact project and child guide/version/setup run; `project.setup_diagnostic.read` | 11C1 |
| `project.guide_sufficiency_report.list` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports` | exact project and child guide/version; `project.setup_diagnostic.read` | 11C1 |
| `project.guide_sufficiency_report.read` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/sufficiency-reports/{report_id}` | exact project, guide/version, and child report; `project.setup_diagnostic.read` | 11C1 |
| `project.submission_artifact_policy.list` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies` | exact project and child guide/version; `project.effective_policy.read` | 11C1 |
| `project.submission_artifact_policy.read` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/submission-artifact-policies/{policy_id}` | exact project, guide/version, and child policy; `project.effective_policy.read` | 11C1 |
| `project.post_submit_checker_policy_setup.read` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/post-submit-checker-policy/setup` | exact project and child guide/version; `project.effective_policy.read` | 11C1 |
| `project.effective_submission_artifact_policy.read` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/effective-submission-artifact-policy` | exact project and child guide/version; `project.effective_policy.read` | 11C2 |
| `project.pre_submit_checker_policy.read` | `GET /api/v1/projects/{project_id}/guides/{guide_id}/pre-submit-checker-policy` | exact project and child guide/version; `project.effective_policy.read` | 11C2 |
| `project.active_guide.read` | `GET /api/v1/projects/{project_id}/active-guide` | exact project; explicit safe projection by principal class | 11C2 |

There is no project collection/list route in the current API. Count/cursor
criteria from the inherited contract are removed rather than inventing a new
surface.

## Child sequence

1. `WS-AUTH-001-11A` registers the eleven actions as planned, adds action-aware
   evidence parity in migration `0035`, and activates no route.
2. `WS-AUTH-001-11B` activates project identity and the new self authorization
   context. It defines the minimal contributor projection and concealed
   exact-project denial.
3. `WS-AUTH-001-11C1` hard-cuts the six setup and draft diagnostic reads to
   admin-grant authority.
4. `WS-AUTH-001-11C2` hard-cuts the three effective policy/guide reads and
   defines any contributor-safe active-guide projection explicitly.

Each child requires its own signed explicit start. No child may preserve
`require_any_role()` or token roles on any surface it activates.

## Acceptance criteria

- The complete current project GET inventory and the deferred actor-context
  surface are assigned exactly once.
- Generated OpenAPI/route-manifest proof matches every literal existing path to
  exactly one action owner and includes project, guide, and child identifiers.
- Every action has an exact PermissionId mapping, canonical target,
  principal boundary, owning child, and disclosure boundary.
- The current migration head `0034_project_role_issue_evidence` is recorded;
  AUTH-11A alone reserves `0035` for the two new read permissions, exact role
  mappings, action registration, and evidence parity.
- The four child contracts state hard-cutover, concealment, evidence,
  migration, and verification requirements without compatibility behavior.
- This parent changes no runtime or feature availability.
- The merge intent names only `WS-AUTH-001-11A` as the same-initiative
  successor; it does not start that child.

## Verification commands

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Review the exact action ownership, the absence of token-role fallback, the
contributor/admin disclosure split, and whether the four children are bounded
enough for independent L1 proof.

## Stop conditions

Stop if any current GET route is unowned, if a child requires dual authority,
or if safe contributor disclosure cannot be specified without changing a
mutation or another product subsystem.
