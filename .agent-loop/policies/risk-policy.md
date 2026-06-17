# Risk Policy

## Blast Radius Questions

1. What breaks if this is wrong?
2. Does it touch identity, money, permissions, data, production, CI, or audit?
3. Does it change product lifecycle or engineering lifecycle?
4. Does it create or rename a durable token, state, role, policy, or checker?
5. Will future contributors treat this as a source of truth?
6. Does it alter tests or CI?

## Risk Escalators

```text
auth authentication authorization permission role token secret payment payout billing invoice escrow policy audit ledger migration schema workflow ci deploy security tenant pii prompt injection checker lifecycle review revision reputation contribution
```

Any naming with product, security, lifecycle, or payment impact must use precise
subsystem- or actor-specific terms. Vague names require reviewer discussion.
