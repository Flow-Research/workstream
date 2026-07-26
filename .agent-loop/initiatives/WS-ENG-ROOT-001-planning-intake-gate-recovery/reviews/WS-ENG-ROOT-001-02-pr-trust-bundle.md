# PR Trust Bundle: WS-ENG-ROOT-001-02

## Intent and scope

Fix only the post-merge recollection loss that prevented PR #205 reconciliation.
The closed schema-v8 policy names PR #205 as the sole recovered merge and this
chunk as the sole activation, with a null successor.

## Design

Recovery preparation and reconciliation use the same immutable target policy.
Both adjacent records receive recovery-only evidence, are admitted through the
ephemeral exemption inventory, and must be fully consumed.

## Evidence

Pending deterministic checks and required internal review evidence.

## Risks and human focus

Review the exact SHA/PR/chunk bindings, first-parent adjacency, independent
validator parity, mutation coverage, and absence of reusable authority.

## Stop

Human approval is required before push, PR, or merge action.
