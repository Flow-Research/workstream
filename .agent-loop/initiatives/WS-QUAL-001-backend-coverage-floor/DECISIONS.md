# Decisions: WS-QUAL-001 Backend Coverage Floor

## D1: Preserve the 90-percent final target

The user-set target remains 90 percent for the complete backend application.

## D2: Treat historical QUAL machinery as completed or stopped evidence

PRs #103, #105, and #108 remain durable. Stopped parser/semantic-analysis
attempts and unimplemented 01B2 are not resumed.

## D3: Use the hosted combined report as baseline truth

The current baseline is the exact semantic-lane fan-in evidence, not a local
developer-machine timing or partial test selection.

## D4: Prefer behavior depth over infrastructure

The remaining coverage is added through meaningful tests at the cheapest valid
layer. Real PostgreSQL, MinIO, and HTTP remain mandatory only for behavior that
depends on those boundaries.

## D5: Separate tests from the threshold switch

The global floor changes only after a current exact head proves at least 90.25
percent. The enforced floor remains 90 percent; the extra 0.25 is merge-race
headroom.

## D6: Keep architecture and CI optimization separate

Service decomposition, typed ports/UnitOfWork, mutation/property testing, type
checking, and semantic-lane runtime optimization are worthwhile possible
initiatives but are not QUAL coverage-closure work.

## D7: Never create a mixed residual-coverage bucket

Project and checker test chunks retain one product owner each. If they do not
reach the required headroom, planning adds one exact owner-specific successor
from refreshed evidence rather than combining ART, AUTH, TASK, workers, and
adapters to chase a percentage.
