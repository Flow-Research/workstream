# Reconcile repository purpose

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Remove audited obsolete tooling, consolidate current documentation and retain the active proof behind each remaining tool.

## Intent

Follow the repository-purpose audit of merged PR #722. Every retained path needs
a current consumer or an explicit historical/source purpose. Git preserves deleted
experiments; no replacement archive or compatibility copy is needed.

## Bounded change

Allowed: README and current docs navigation/claims; restoration of the original
hash-bound AUTH source input; removal of unused agent-gate and mutation-runner
artifacts and obsolete documentation; relocation of mutation source-analysis
helpers used by the active ownership gate, with their required regressions;
exact ownership/lane inventories; current behavior contracts and Agent Gates
selection; explicit manual identity-browser qualification documentation. Repair
non-pre-cutover historical links to immutable source only.

Prohibited: product behavior, schema or retained-data changes; removal of active
local auth, runtime adapter packages, checker images or planned review storage;
new frameworks; percentage coverage gates; weaker ownership/test selection;
Commitrail history deletion or pre-cutover modification; deployment claims.

## Acceptance criteria

1. Trace deletions to their consumers. Retain source eligibility, safe-path,
   callable-delta and symlink protections used by ownership validation, with tests.
   Remove only the retired mutation execution/claim/calibration machinery.
2. Restore imported AUTH bytes from the original Git version matching SHA256SUMS.
3. Consolidate README instructions into existing canonical owners, reconcile
   acceptance and JSON-import claims, and remove superseded process documents.
4. Select the existing git-delta tests in Agent Gates. Document native CLI/browser
   qualification as manual, including its isolated Secret Service prerequisite;
   do not imply the signup CI case proves that separate interaction.
5. Run retained tooling tests, exact inventories, archive checksums, stale wording,
   Markdown links and Commitrail validation. Review a clean candidate before PR.

Required outcome: no current broken references, lost required proof, arbitrary
inventory-removal exemption or duplicate implementation. Roadmap capability status
is unchanged; reconcile affected navigation/claims only. No local sheet exports
are present.

## Risk and review routing

Risk: L2 tooling/documentation cleanup. Required focused tracks: architecture,
CI integrity, test delta and documentation. Human review should confirm that
retired tools have no remaining consumers, retained source-analysis protections
are unchanged, archive bytes match their original manifest, and current docs
preserve both automatic acceptance and the unfinished live human-review branch.

## Evidence

Retained source-analysis tests cover safe paths, eligibility, symlink rejection,
nested/decorated callable changes and merge-base mapping. Ownership and lane
catalogues retain exact membership guards. Original AUTH source bytes are restored
from `d5b0ca96c` and must match the unchanged archival SHA256SUMS.

The retired mutation runner was not independent: its source-analysis helpers were
used by the ownership gate. Only those live helpers and regressions move to
`behavior_source.py`; claim/execution/calibration-only tests are obsolete with
the retired workflow. Native browser/CLI qualification remains an explicit manual
proof requiring an isolated unlocked Secret Service, not a claimed CI result.
