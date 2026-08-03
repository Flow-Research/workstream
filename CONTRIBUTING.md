# Contributing To Workstream

Workstream welcomes contributions from humans and agents. Repository access is
governed by GitHub permissions and branch protection. The engineering loop
exists to make work understandable and reviewable; it is not a separate
authorization system.

Workstream itself is source-agnostic governed contribution infrastructure. Flow
Identity is its current v0.1 external authentication provider, not its product
owner or repository contribution authority. Read the complete product boundary
in [README.md](README.md) before changing product terminology or architecture.

## Simple Engineering Loop

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> Pull Request -> Human Merge
```

For a small change, record the intent and scope in the pull request. For larger
or higher-risk work, add a short initiative plan and chunk contract under
`.agent-loop/initiatives/`. Existing planning artifacts are useful context, not
runtime locks.

## Find The Current Contract

Before implementation, update from current `main` and read:

1. [README.md](README.md) for the product boundary and current v0.1 summary.
2. [Current v0.1 Status](docs/roadmap_status.md) for implemented, in-progress, and
   remaining capabilities.
3. [Architecture Lockdown](docs/architecture_lockdown.md), accepted ADRs, and
   the canonical specification for the subsystem being changed.

Code, migrations, tests, accepted ADRs, and canonical repository specifications
define implemented or required behavior. Open pull requests describe work in
progress. Calendar plans, early chunk specifications, imported files under
`docs/reference_specs/`, internal review records, and closed initiative records
are useful history unless a current document explicitly adopts them; they are
not by themselves current sequencing or proof that behavior is live.

Roadmaps and status documents must use capability milestones and evidence. Do
not introduce delivery promises such as day plans, numbered weeks, or rolling
time windows as repository authority.

Contributors with GitHub write access may create a branch, implement a bounded
change, and open a pull request. Contributors without write access may use a
fork and open a normal pull request.

## Before Opening A Pull Request

- Explain the goal, scope, non-goals, and important design decisions.
- Keep the change small enough to review.
- Run the relevant tests, lint, type checks, and coverage checks.
- Preserve security defaults and existing coverage floors.
- Record important reviewer findings and how they were resolved.
- Reconcile with current `main` and rerun affected checks.

Security, authorization, payments, workflow, architecture, and other high-risk
changes require focused internal review before they are ready to merge. Small
low-risk changes use proportionate review. Reviews are evidence, not permission
to contribute.

## Review And Merge

GitHub CI validates repository quality. CodeRabbit and internal agents
supplement human review. A maintainer must explicitly approve the final pull
request before it is merged.

Different initiatives may proceed concurrently in separate branches or
worktrees. If another pull request changes the base, inspect the new delta and
rerun affected checks; unchanged evidence does not need ceremonial repetition.

## Durable Records

Keep useful plans, contracts, review notes, and historical `.agent-loop/`
artifacts. They explain decisions and preserve evidence. Git and GitHub are the
source of truth for commits, reviews, checks, and merges.
