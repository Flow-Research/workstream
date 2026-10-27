# Exact setup evaluation-context declarations

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Setup specifications truthfully declare the already-supported selected POST revision context, with exact agreement against approved registry configuration.

## Intent

A real Terminal Systems setup drill needs predecessor findings and the predecessor
archive. Runtime already provides those explicitly selected roles. Setup currently
can express only broad `task_context/runtime_gap`, which correctly prevents a
supported binding. Extend the existing declaration and policy validation; no new
runtime authority or materialization path is needed.

## Bounded change

Allowed: `backend/app/interfaces/project_agents.py`,
`backend/app/modules/checkers/api/external_policy.py`,
`backend/app/core/project_guide_instructions.py`, strict proposal decoding in
`cli/internal/api/guide_proposal.go`, focused setup/external-policy/CLI tests and the strict provider fixture in
`backend/tests/test_agent_runtime.py`,
`mcp_server/contracts/guide_proposal_get.json`,
`mcp_server/contracts/guide_post_policy_get.json`, `docs/spec_chunk_3_project_guide_foundation.md` and
`docs/roadmap_status.md`, and this record.

Prohibited: runtime transport/authority changes, broad task/guide-context access,
schema migration, dependencies, CI weakening, external service/cloud changes,
unrelated cleanup, retained data changes, push/PR before lead review.

1. Add exact `evaluation_context` input and dependency; require a typed, canonical
   role tuple on that input only, using the existing supported role vocabulary.
   Exclude the absent field so retained compilation hashes remain stable.
2. Require paired input/dependency, `current_runner`, `material_unavailable` and
   POST background scope. Keep broad task/guide context unavailable.
3. Use one public external-policy helper for symmetric exact declared roles versus
   selected v1 configuration, with canonical registry validation in both proposal
   projection and approval-time actual resolution.
4. Update setup instructions and strict CLI decoding, then prove positive model
   and trial declarations, denial boundaries and retained serialization.

## Acceptance criteria

- Model-only and trial POST revision specifications admit exact selected roles.
- PRE, missing/unknown/duplicate/noncanonical roles, misplaced role fields,
  missing/extra declaration or selection, and role mismatch fail closed.
- Unsupported actual registry schemas fail approval before policy persistence.
- Broad task/guide context remains a gap and retained input serialization/hashes
  remain unchanged when the new field is absent.
- Run focused Python tests, strict CLI integration/unit checks, applicable lint,
  boundary, Commitrail, stale wording and Markdown-link checks. Assess generated
  OpenAPI exposure and roadmap claims; update only affected capability wording.

## Risk and review routing

Risk: L1, policy-admission/public contract. Required internal reviewer tracks:
architecture, security, QA/test_delta, documentation/reuse as scoped by the lead.
Independent pre-implementation plan review: `/root/real_trial_plan_review`.
Human review focus: declaration is descriptive only; exact selectors cannot gain
undeclared material; approval rechecks the actual registry; retained hashes stay
stable. Lead owns final clean-target reviewer routing and complete-suite evidence.


## Evidence

Focused owner tests pass, including real model/trial configuration validators,
projection/actual-registry symmetry and an approval compiler probe that supplies
a valid projection with an unsupported actual publication and rejects before any
session write. Strict CLI HTTP integration accepts the exact public field and
rejects malformed roles or missing paired declarations. Existing retained-result
hash tests and the new absent-field serialization probe pass. Runtime custody and
materialization are unchanged; this repair does not approve a project, qualify a
native trial or establish a live revision journey.

Roadmap assessment: update the compilation scoreboard and detailed Terminal
Systems setup boundary to name the exact declaration contract. Executive,
dependency and remaining-gate claims retain their existing supported branches and
requirements: this repair adds no lifecycle dependency or delivered journey.
No local spreadsheet exports are present in this worktree.

The expanded instruction initially exceeded the existing 16,000-character bound;
condensing the same specification/dependency guidance fixed it without raising the
limit. The actual SDK parser also required the new nullable input member in its
strict provider fixtures; those fixtures now include null, while canonical stored
and public inputs omit absent roles. Existing prompt-rule assertions are retained.
The exact pinned OpenAI runtime/contract regression suite passes. An isolated
in-memory removal of both agreement guards makes the named mismatch regression
fail its expected-exception assertion.
