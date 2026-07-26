# Contributing To Workstream

Workstream welcomes contributions from humans and agents. Repository access is
governed by GitHub permissions and branch protection. The engineering loop
exists to make work understandable and reviewable; it is not a separate
authorization system.

## Simple Engineering Loop

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> Pull Request -> Human Merge
```

For a small change, record the intent and scope in the pull request. For larger
or higher-risk work, add a short initiative plan and chunk contract under
`.agent-loop/initiatives/`. Existing planning artifacts are useful context, not
runtime locks.

Contributors with GitHub write access may create a branch, implement a bounded
change, and open a pull request without a signed start event, administrator
dispatch, active-chunk lease, or loop-memory approval. Contributors without
write access may use a fork and open a normal pull request.

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

GitHub CI validates repository quality. It does not consult signed loop memory
or require a merge-intent file. CodeRabbit and internal agents supplement human
review. A maintainer must explicitly approve the final pull request before it
is merged.

Different initiatives may proceed concurrently in separate branches or
worktrees. If another pull request changes the base, inspect the new delta and
rerun affected checks; unchanged evidence does not need ceremonial repetition.

## Durable Records

Keep useful plans, contracts, review notes, and historical `.agent-loop/`
artifacts. They explain decisions but do not activate work or block pull
requests. Git and GitHub are the source of truth for commits, reviews, checks,
and merges.

The former signed-start, explicit-event, recovery-certificate, and generated
loop-memory runtimes were removed because derived process state must never
deadlock contribution or require self-authorizing recovery.
