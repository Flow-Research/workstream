# Future Identity, Task Contract, Settlement, And Reputation View

This diagram shows how the broader Workstream system can connect later to agent identity, task contract, settlement, and portable reputation rails.

This is not v0.1 implementation scope. It is the architecture direction that keeps separation of concern clear.

![Future Identity, Task Contract, Settlement, And Reputation View](rendered/future_identity_payment_reputation.svg)

Source: [future_identity_payment_reputation.puml](future_identity_payment_reputation.puml)

## Separation Of Concern

| Concern | Owner |
| --- | --- |
| Human identity and auth | Flow identity layer |
| Agent identity | ERC-8004 |
| Agent reputation read/write | ERC-8004, through a future Workstream adapter |
| Task contract and escrow reference | ERC-8183 |
| Evaluation lifecycle | Workstream |
| Reviewer/submitter contribution recognition | Workstream contribution record |
| Contribution policy, compensation award, and fulfillment status | Workstream contribution and compensation records |
| Payment request and settlement execution | x402, OmniClaw, USDC settlement rails |

## Future Flow

```text
Flow human identity + ERC-8004 agent identity
-> Workstream claim/submission gate
-> locked guide and policy context
-> submitted artifact packet with human id and agent id references
-> checks and human review
-> reviewer contribution for every valid human Review
-> submitter contribution only on accept
-> compensation award only when the frozen rule is payable
-> payment link / x402 request only for a payable money award
-> OmniClaw / USDC settlement
-> immutable fulfillment receipt and status projection
-> reputation event
-> optional ERC-8004 agent reputation write
```

## Non-v0.1 Boundary

The first implementation does not build ERC-8004 writes, ERC-8183 settlement, x402 payments, OmniClaw settlement orchestration, wallet flows, public marketplace discovery, or external source adapters. These are adapter boundaries that become useful after Workstream proves the internal evaluation loop with real tasks.
