# Agent SLA Policy

Agent work is not real-time by default.

## P0 - Immediate

Broken main, security issue, payment blocker, production outage, or data
corruption risk.

## P1 - Same Day

Active sprint chunk, CodeRabbit blocker, CI failure on active PR, or critical
architecture correction.

## P2 - Normal

Planned implementation chunks, docs hardening, tests, refactors, or process
improvements.

## P3 - Backlog

Nice-to-have cleanup, optional docs polish, or non-urgent reports.

This bootstrap chunk is P1 because it governs how all future chunks are built.
