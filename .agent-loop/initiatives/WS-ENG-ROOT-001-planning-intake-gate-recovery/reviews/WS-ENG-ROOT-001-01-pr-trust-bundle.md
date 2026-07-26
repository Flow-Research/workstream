# PR Trust Bundle: WS-ENG-ROOT-001-01

## Goal

Restore the documented first-planning-intake path after PR #203 accidentally
made it impossible to enter, using one exact consumed root recovery.

## Scope and behavior

Only trusted engineering gates, their tests, the independent memory checker,
and the exact recovery certificate change. Product behavior is unchanged.
Ordinary work remains signed-start-only.

## Why root recovery is required

Trusted base code rejects both the repair and every normal planning intake, so
no ordinary signed contract can authorize the correction. The exact recovery
is bound to current signed main and this single identity, then consumed.

## Human review focus

- Closed planning tree grammar and signed-history absence.
- No candidate implementation self-authorization.
- Exact recovery certificate, consumption, and replay inertness.
- Continued signed-start requirement for ordinary chunks.

## Human merge ownership

The owner must explicitly approve this specific repair PR. A failing old scope
check is the defect being repaired and must not be represented as passing.
