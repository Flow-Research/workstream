# <Change ID> — <Outcome>

- Initiative: `<initiative ID or None>`
- Durable disposition: `Planned | Complete | Stopped | Superseded`
- Intended merge outcome: `<one sentence>`

## Intent

What human outcome does this change deliver, and why does it matter?

## Current behavior

What does the repository do now? Cite concrete files, symbols, tests, or
specifications.

## Bounded change

### Allowed

- `<paths and behavior>`

### Not allowed

- `<explicit non-goals and protected boundaries>`

## Design and decisions

Describe the smallest chosen design and material rejected alternatives.

## Acceptance criteria

- [ ] `<observable result>`

## Risk and review routing

- Risk class: `<L0 | L1 | L2>`
- Required reviewers: `<only affected specialties>`
- Human review focus: `<material decisions or uncertainty>`

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| `<claim>` | `<test/check/inspection>` | `<result>` | `<honest limit>` |

Review conclusions bind to one exact committed candidate. A later push
invalidates only affected conclusions. Never copy private session receipts,
credentials, tokens, or unnecessary personal data into this record.

## Review findings

Record material findings and their disposition. GitHub conversations remain on
GitHub; do not duplicate transient approval state here.

## Reconciliation

- Base reviewed: `<commit>`
- Candidate reviewed: `<commit>`
- Rebase impact: `<affected evidence rerun or None>`
- Remaining risks: `<risks accepted by the human or None>`
