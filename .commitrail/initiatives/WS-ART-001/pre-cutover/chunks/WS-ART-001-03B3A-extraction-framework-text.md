# Chunk Contract: WS-ART-001-03B3A - Extraction Framework And Text Formats

Initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 03B2

## Goal

Prove the isolated extraction framework, canonical content/usage provenance,
and standard-library text, Markdown, JSON, and CSV extraction.

## Allowed Files

- typed extraction capability/registry and explicit composition entries;
- isolated no-network subprocess and versioned extraction policy;
- content-derived extraction and binding/generation usage models, one migration,
  repository, and schemas;
- focused isolation, limit, cancellation, cleanup, determinism, provenance,
  text/Markdown/JSON/CSV, and coverage tests; related docs/evidence.

## Not Allowed

- production parser dependencies, PDF/OOXML/image parsing, plugin discovery,
  in-process untrusted parsing, provider writes/access, agent invocation, OCR,
  audio/video, legacy cutover, or AUTH availability edits.

## Acceptance Criteria

- no-network subprocess enforces input/output, CPU/time/memory, row/cell,
  encoding, nesting, cancellation, and cleanup limits;
- after trusted standard-library imports, the Linux child installs a
  default-deny libseccomp filter with an explicit syscall allowlist before
  parsing. Network/process creation, new file opens, filesystem mutation, and
  kernel-introspection surfaces return `EPERM`. Parsing is
  descriptor-only over pre-opened stdin/stdout/stderr; missing filter support
  fails closed as `parser_failure`. Launch uses `shell=False`, closed
  extraneous file descriptors, one scratch-owned working directory, and a minimal
  allowlisted environment containing no provider, proxy, database, OpenAI, or
  authorization secrets;
- the framework rejects parser input above 32 MiB, canonical output above
  4 MiB, CPU use beyond 30 seconds, wall execution beyond 60 seconds,
  address-space use above 512 MiB, output files above 4 MiB, more than 32 open
  descriptors, any child process, or any core dump. Numeric resource breaches
  record `limit_exceeded`; prohibited process creation, unavailable isolation,
  or abnormal child termination records `parser_failure`;
  CSV rejects more than 100,000 rows, 1,000,000 cells, or 32,768 characters in
  one cell; every CSV numeric breach records `limit_exceeded`;
- text-family input accepts UTF-8 only, permits at most one leading UTF-8 BOM,
  normalizes CRLF and CR to LF, rejects NUL and control characters other than
  tab/LF, and otherwise preserves text exactly. Markdown uses the same rules
  without rendering or parsing;
- JSON rejects duplicate object keys, non-finite numbers, invalid UTF-8, and
  nesting deeper than 64 containers; it canonicalizes with recursively sorted
  keys, compact separators, UTF-8 characters unescaped where JSON permits, and
  no trailing newline. CSV uses the fixed Python `excel` dialect with strict
  quoting, preserves empty/ragged cells, and canonicalizes to compact UTF-8 JSON
  containing the exact row arrays;
- tests cover each exact boundary and one-over boundary, timeout and memory
  termination, cancellation, executor loss, scratch cleanup, and retry through
  fresh materialization and fresh authority with no partial durable output;
- extraction revalidates exact 03B2 digest/binding/format/policy provenance;
- deterministic content records are keyed by content, format, extractor/version,
  and policy; separate usage records name item, binding, run, and generation;
- text/Markdown/JSON/CSV canonicalization and error statuses are deterministic;
- unsupported raw input never reaches an agent or provider write;
- failed attempts may persist one bounded status/error record, but only an
  `extracted` current-generation result may retain canonical output and create a
  usage record; failure, cancellation, or executor loss creates no successful
  usage, report, or partial output payload;
- transient failure evidence is attempt-scoped and cannot occupy or poison the
  deterministic successful content key; a later fresh-authority/materialization
  retry may publish the one immutable successful content record;
- a durable exact-lineage budget reserves at most the initial materialization
  and one retry. Only `parser_failure` or current-lineage cancellation may use
  the second slot; deterministic terminal outcomes replay without another
  provider read;
- changed subsystem coverage is at least 90%; repository coverage stays 78%.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && WORKSTREAM_TEST_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/pytest tests/test_alembic.py tests/test_guide_bindings.py tests/test_guide_extraction.py -q --cov=app --cov-report=term-missing --cov-fail-under=0)
(cd backend && .venv/bin/coverage report --precision=2 --fail-under=78)
(cd backend && .venv/bin/coverage report --include='app/modules/artifacts/*,app/core/config.py,app/interfaces/artifacts.py' --precision=2 --fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

Architecture/security tests must also prove that 03B3A introduces no direct
provider read/write, concrete adapter import, public raw-extraction route,
in-process untrusted parser, plugin discovery, production parser dependency,
agent invocation, AUTH availability edit, secret-bearing child environment, or
cross-lineage extraction lookup. A real child probe must fail DNS/socket access.
The same probe must fail reads of a known outside-scratch file and writes both
inside and outside scratch after the descriptor-only filter is installed.

The exact PR head must pass hosted `Backend / test` and `Agent Gates / agent-gates`.
Every changed production module, including repository, schema, migration-owned
service, and composition surfaces, must be included in a dedicated retained
90% coverage report or an explicitly reviewed existing subsystem report.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
