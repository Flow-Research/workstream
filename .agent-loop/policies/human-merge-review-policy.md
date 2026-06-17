# Human Merge Review Policy

Humans do not need to read every generated line at equal depth, but humans own
load-bearing decisions.

## Human-Owned Decisions

- intent
- risk classification
- architecture direction
- product wording that affects operators, workers, reviewers, or payments
- merge decision
- accepted remaining risks
- when the next chunk begins

## Review Order

1. Read the PR trust bundle.
2. Read the chunk contract.
3. Review changed tests and gates.
4. Review load-bearing paths.
5. Review internal reviewer findings.
6. Review external reviewer findings.
7. Decide merge, send back, or abandon.

Do not merge code or process changes you cannot explain.
