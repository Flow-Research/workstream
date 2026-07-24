# Risks: WS-ENG-008 — Repository-Native SDLC Assurance

| ID | Risk | Impact | Control |
|---|---|---|---|
| R1 | Scope patterns are ambiguous or bypassable | Unauthorized files enter a chunk | Closed JSON schema, canonical paths, status-aware diff, traversal/symlink/rename/submodule/case mutations. |
| R1A | Git path bytes or Unicode aliases bypass line parsing | A hidden path escapes scope | NUL-delimited byte-preserving diff, strict UTF-8/NFC policy, control rejection, normalization/casefold collision tests. |
| R2 | Forward ratchet breaks historical PRs | Existing maintenance becomes impossible | Enforce only new/materially changed contracts; test unchanged legacy behavior. |
| R3 | Scheduled audit obtains write authority | A diagnostic becomes a second state writer | Read-only permissions, no secret, no publish/recovery command, semantic workflow tests. |
| R4 | Drift audit is stale relative to concurrent merges | False incident or missed state | Resolve exact current main and automation tip at run time; distinguish transient advancement from corruption. |
| R5 | Adversarial evidence becomes checkbox theater | Review cost without assurance | Require attempted attack, expected denial, observed evidence, and untested surfaces. |
| R6 | Property tests become flaky or slow | CI reliability regresses | Deterministic bounded profiles, reproducible examples, measured hosted runtime. |
| R7 | AUTH property work conflicts with AUTH-10C | Stale or contradictory tests | Wait for canonical AUTH merge/stop, re-discover action/catalogue state, then start. |
| R8 | Mutation score is gamed or too expensive | False confidence or unusable CI | Complete counts, survivor classification, changed eligible modules only, non-blocking pilot. |
| R9 | Dormant QUALITY work is treated as authority | Unsigned stale implementation is published | Preserve as discovery input only; recreate accepted ideas after ENG-008 signed start. |
| R10 | Review-log migration loses or rewrites history | Durable evidence becomes unverifiable | Byte/digest preservation, link map, archives, exact reconstruction tests, no deletion before proof. |
| R11 | Root-log migration conflicts with active PRs | Entries disappear during rebase | Run last and reconcile every active/root-log-writing PR before review and merge. |
| R12 | ENG-008 blocks unrelated active initiatives | Reduced delivery throughput | Initiative-local authority, disjoint early paths, overlap audit before every chunk. |
