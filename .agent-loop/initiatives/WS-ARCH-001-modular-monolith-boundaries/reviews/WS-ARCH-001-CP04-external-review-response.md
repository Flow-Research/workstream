# WS-ARCH-001-CP04 External Review Response

## Comments addressed

- `EXT-CP04-001` High: review evidence named `445944a` after the PR head moved to
  `769e15e`. Valid. The committed evidence and trust bundle now label the old
  result historical and require fresh exact-head reviewer mirrors in the PR
  body.
- `EXT-CP04-002` High: CP04A/CP04B verification used broad pytest commands
  without criterion-to-test ownership. Valid. Both contracts now map each
  security/product criterion to named future test modules and distinguish local
  proof from hosted-only PostgreSQL/concurrency proof.
- `CR-CP04-001` Low: `DISCOVERY.md` summarized publication as starting with
  aggregate locks even though the executable contracts fence the operation and
  check immutable recovery first. Valid. The summary now states the exact
  fence/recovery-before-lock/PREP order and preserves no-second-effect recovery.

## Comments deferred

None.

## Human decisions needed

None beyond normal approval and merge ownership.

## Commands rerun

Final-head state, wording, Markdown-link, diff, upgraded internal review, hosted
CI, and thread-aware external-review checks must be rerun after this correction.

## Remaining risks

CodeRabbit has not yet supplied a fresh substantive final-head review. Future
CP04A/CP04B implementation must satisfy the named test matrices; this planning
correction does not itself prove runtime behavior.
