---
name: reuse-dedup-review
description: Review a diff for duplicated helpers, missed existing abstractions, redundant logic, and code reuse blindness.
---

# Reuse / Dedup Review

Agents often create new helpers instead of reusing existing code. Check for that.

## Focus

- New helper duplicates existing helper.
- New validation logic duplicates old validation logic.
- New policy path bypasses existing policy path.
- Naming convention forks.
- Similar abstractions now exist in multiple places.
- Shared behavior belongs in existing module.

## Output

```text
Result: PASS / PASS WITH LOW RISKS / FAIL
Possible duplicates:
Existing code to reuse:
Required fixes:
```
