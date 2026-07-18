# Human Merge Review Policy

Humans do not need to read every generated line at equal depth, but humans own
load-bearing decisions.

## Human-Owned Decisions

- intent
- risk classification
- architecture direction
- product wording that affects operators, contributors, reviewers, or compensation
- merge decision
- accepted remaining risks
- when the next chunk begins

## Product Wording Scope

Product wording includes names or text that users, operators, contributors,
reviewers, or compensation/reputation workflows rely on, including API field names,
environment variables, UI labels, public docs, task/review templates, test
assertion text that encodes product language, and docstrings that explain
product behavior. Borderline cases must be flagged for human decision instead
of being auto-approved.

## Review Order

1. Read the PR trust bundle.
2. Read the chunk contract.
3. Review changed tests and gates.
4. Review load-bearing paths.
5. Review internal reviewer findings.
6. Review external reviewer findings.
7. Decide merge, send back, or abandon.

Do not merge code or process changes you cannot explain.
