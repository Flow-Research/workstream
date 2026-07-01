# Internal Review Evidence: Submission Artifact Policy Architecture

Date: 2026-06-16

## Scope

This review covers the architecture documentation correction that locks submission intake before implementation continues.

Changed contract surfaces:

- `README.md`
- `docs/architecture_*.md`
- `docs/decision_0003_project_guides_are_first_class.md`
- `docs/decision_0011_submission_artifact_policy_drives_pre_submit.md`
- `docs/glossary.md`
- `docs/operations_*.md`
- `docs/product_*.md`
- `docs/roadmap_*.md`
- `docs/spec_*.md`
- `docs/template_*.md`
- `docs/current_system_data_flow.html`

The corrected contract is:

`ProjectGuide -> SubmissionArtifactPolicy + Workstream defaults -> EffectiveSubmissionArtifactPolicy -> generated PreSubmitCheckerPolicy -> blocking pre-submit checks -> Submission created`

## Reviewer Tracks

### Senior engineering

Finding: the earlier documentation mixed human-facing guide prose, evidence policy, checker policy, and submission intake enforcement.

Resolution: docs now separate `ProjectGuide` as the human-facing instruction from `SubmissionArtifactPolicy` as the machine-readable intake contract. The generated `PreSubmitCheckerPolicy` is derived from `EffectiveSubmissionArtifactPolicy`, not free-form guide prose.

Final result: no blocking findings after re-review.

### QA/test

Finding: the pre-submit contract needed deterministic failure behavior before a submission row exists.

Resolution: specs now state that blocking pre-submit failures create no submission row, no submission version, no `SUBMITTED` transition, and no submission-created audit event. The Chunk 5, 7, and 8 specs now align on this behavior.

Final result: no blocking findings after re-review.

### Security/auth

Finding: project-specific submission requirements could be interpreted as able to weaken Workstream default artifact checks.

Resolution: ADR 0011 and the submission artifact policy template now state that Workstream default submission artifact rules are inherited and non-bypassable. Project policy may add requirements or narrow allowed inputs, but it must not remove, weaken, downgrade, or bypass Workstream default checks.

Final result: no blocking findings after re-review.

### Product/ops

Finding: the terms `evidence policy`, `preflight evidence`, and broad checker-policy wording made the operator and worker workflow harder to reason about.

Resolution: docs now use `SubmissionArtifactPolicy`, `EffectiveSubmissionArtifactPolicy`, `PreSubmitCheckerPolicy`, and `PostSubmitCheckerPolicy` consistently. The Chunk 8 spec file was renamed to submission-artifact-policy wording, and templates now separate worker-facing guide expectations from machine-enforced intake requirements.

Final result: no blocking findings after re-review.

## Validation

## Follow-Up Review

CodeRabbit follow-up findings:

- Day 5 exit criteria named only no submission row for blocking pre-submit failures.
- HTML mini-flow arrows used unescaped `>` characters.
- Lifecycle guard wording in the checker policy template was too easy to miss.

CI follow-up finding:

- Backend CI failed two no-local-auth route tests because the FastAPI route list now includes an internal route-like object without a `path` attribute.
- A second backend CI run showed the first fix still depended on direct `app.routes` expansion. Fresh CI installed FastAPI `0.137.1`, where included routers are represented as wrappers in `app.routes`, while local validation had FastAPI `0.136.3`, where routes were directly expanded.

Resolutions:

- Day 5 exit criteria now list all four blocked consequences: no submission row, no submission version, no `SUBMITTED` transition, and no submission-created audit event.
- HTML mini-flow arrows now use `-&gt;`.
- Lifecycle guard wording now lives in a dedicated `Design Boundaries` section.
- The no-local-auth tests now combine `app.openapi()["paths"]`, direct route paths, and FastAPI included-router effective contexts. This preserves the forbidden-route assertions across FastAPI `0.136.3` and `0.137.1` while still covering hidden application routes when FastAPI exposes them through route contexts.

Follow-up reviewer results:

- senior engineering: no blocking findings
- QA/test: no blocking findings
- security/auth: no blocking findings
- product/ops: no blocking findings

## Validation

Passed:

```bash
git diff --cached --check
```

Passed:

```bash
rg -n "spec_chunk_8_evidence_policy_checkers|evidence_policy_checkers|Evidence Policy Checkers|evidence policy checkers|load project CheckerPolicy|locked project checker policy|checker policy present|missing checker policy|evidence policy|Evidence Policy|preflight evidence|non-authoritative pre-submit|where possible|rejected or normalized|forbidden by the project guide|Project guides can override" README.md docs/architecture_*.md docs/decision_*.md docs/glossary.md docs/spec_*.md docs/template_*.md docs/product_*.md docs/operations_*.md docs/roadmap_*.md docs/principles.md docs/risk_register.md docs/current_system_data_flow.html -S
```

Result: no matches.

Passed:

```bash
python3 - <<'PY'
from pathlib import Path
import re
root = Path('.')
missing = []
link_re = re.compile(r'\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)')
for path in sorted(root.glob('**/*.md')):
    if any(part in {'.git', '.venv', 'node_modules'} for part in path.parts):
        continue
    text = path.read_text(encoding='utf-8')
    for match in link_re.finditer(text):
        target = match.group(1).split('#', 1)[0].strip()
        if not target or target.startswith('<') or target.startswith('app://'):
            continue
        candidate = (path.parent / target).resolve()
        if not candidate.exists():
            missing.append((str(path), target))
if missing:
    for source, target in missing:
        print(f'{source}: missing {target}')
    raise SystemExit(1)
print('Markdown links OK')
PY
```

Result: `Markdown links OK`.

Passed:

```bash
cd backend && .venv/bin/python -m ruff check tests/test_app.py tests/test_auth.py
```

Result: `All checks passed!`

Passed:

```bash
cd backend && .venv/bin/python -m pytest tests/test_app.py tests/test_auth.py -q
```

Result: `23 passed`.

Passed against a clean PR worktree with a fresh dependency install:

```bash
cd /tmp/workstream-pr22-clean/backend && .venv/bin/python -m pytest tests/test_app.py tests/test_auth.py -q
```

Result: `23 passed`.

Passed:

```bash
find sheets -maxdepth 2 -type f
```

Result: no local sheet exports present.

## Closure

valid findings addressed

open sub-agent sessions: none
