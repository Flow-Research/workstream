# Historical Engineering Automation

The former signed local start, queue, and recovery automation has been retired.

Git and GitHub are now the source of truth for commits, checks, reviews, and
merges. Commitrail records under `.commitrail/` preserve only useful durable
context and never create contribution authority. A failed or stale derived
record must not block unrelated work.

Git history retains the removed automation as audit history. No workflow writes
or consumes it and contributors must not use it as a start gate.

For current contribution instructions, see [CONTRIBUTING.md](../CONTRIBUTING.md).
