# External Review Response: WS-SEC-001-01

## Comments Addressed

- Raised the backend `pytest-asyncio` lower bound to the tested 1.4 line so the
  declared range cannot select an earlier release that excludes pytest 9.
- Made the recorded verification sequence fail fast and added a hash-locked
  dry run for the retained mutation-tool requirements.
- Named the backend `pytest`/`pytest-asyncio` pair and mutation `pytest`/`uv`
  pair explicitly in the initiative outcome.
- Reverified that the direct pin, approval manifest, lock, and normative
  specification agree on `pypdf` 6.15.0. No additional change was required for
  that already-satisfied thread.
- Expanded the GitHub PR description to the repository trust-bundle structure.

## Comments Deferred

None.

## Human Decisions Needed

None beyond normal review and explicit merge approval.

## Commands Rerun

```bash
cd backend
uv lock --check
uv run python scripts/check_guide_extractor_dependencies.py
uv pip install --dry-run --require-hashes \
  -r ../scripts/mutation-requirements.txt
uv run pytest -q tests/test_guide_extractor_dependencies.py \
  tests/test_guide_pdf.py tests/test_mutation_policy.py
cd ..
python3 scripts/check_markdown_links.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
git diff --check
```

## Remaining Risks

The full semantic-lane and coverage suite remains the exact-head GitHub
Backend workflow's responsibility.
