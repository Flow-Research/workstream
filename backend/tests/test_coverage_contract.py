from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import coverage_policy as policy  # noqa: E402

HEAD = "0016_artifact_domain"
SHA = "a" * 40
PEP695_INVALID = sys.version_info < (3, 12)


def write_json(path: Path, value: dict, *, canonical: bool = False) -> Path:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n" if canonical else json.dumps(value)
    path.write_text(text, encoding="utf-8")
    return path


def evidence(**updates) -> dict:
    value = {
        "schema_version": 1, "base_merge_sha": SHA, "measured_tree_sha": "b" * 40,
        "covered_lines": 3, "num_statements": 4, "measured_percent": "75.000000",
        "configured_floor": "75.000000", "minimum_milestone": "75.000000",
        "python_version": "3.12.0", "coverage_version": "7.1.0",
        "pytest_cov_version": "7.1.0", "database_name": "workstream_test_012345abcdef",
        "alembic_head": HEAD,
    }
    value.update(updates)
    return value


def config_text(report: str = "", run: str = "", pin: str = "pytest-cov==7.1.0",
                precision: int = 6, floor: int | str = 75, dev: str | None = None) -> str:
    dependencies = dev if dev is not None else f"['{pin}']"
    return (
        f"[project.optional-dependencies]\ndev={dependencies}\n[tool.coverage.run]\n{run}"
        f"\n[tool.coverage.report]\nprecision={precision}\nfail_under={floor}\n{report}"
    )


def coverage_file(tmp_path: Path, *, files: dict | None = None, covered=2, statements=3) -> tuple[Path, Path]:
    root = tmp_path / "backend"
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app/a.py").write_text("x = 1\n", encoding="utf-8")
    summary = {"summary": {"covered_lines": covered, "num_statements": statements}}
    data = {"files": files if files is not None else {"app/a.py": summary},
            "totals": {"covered_lines": covered, "num_statements": statements}}
    return write_json(tmp_path / "coverage.json", data), root


def test_compute_floor_validates_inventory_and_truncates(tmp_path: Path) -> None:
    path, root = coverage_file(tmp_path)
    assert policy.coverage_counts(path, root) == (2, 3)
    path, root = coverage_file(tmp_path, files={})
    with pytest.raises(policy.PolicyError, match="application_inventory_mismatch"):
        policy.coverage_counts(path, root)


@pytest.mark.parametrize(("covered", "statements", "expected"), [
    (0, 3, "0.000000"),
    (3, 3, "100.000000"),
    (2, 3, "66.666666"),
    (1, 7, "14.285714"),
    (10**100 - 1, 10**100, "99.999999"),
])
def test_six_place_percent_success_boundaries(covered: int, statements: int, expected: str) -> None:
    assert policy.six_place_percent(covered, statements) == expected


@pytest.mark.parametrize(("files", "code"), [
    ({"app/a.py": {}}, "invalid_file_coverage"),
    ({"app/a.py": {"summary": {"covered_lines": 1, "num_statements": 3}}}, "coverage_totals_mismatch"),
])
def test_coverage_counts_reconciles_file_summaries(tmp_path: Path, files: dict, code: str) -> None:
    path, root = coverage_file(tmp_path, files=files)
    with pytest.raises(policy.PolicyError, match=code):
        policy.coverage_counts(path, root)


@pytest.mark.parametrize(("covered", "statements"), [(-1, 3), (4, 3), (0, 0), (True, 3)])
def test_coverage_counts_reject_invalid_totals(tmp_path: Path, covered, statements) -> None:
    path, root = coverage_file(tmp_path, covered=covered, statements=statements)
    with pytest.raises(policy.PolicyError, match="invalid_coverage"):
        policy.coverage_counts(path, root)


def test_intended_config_returns_exact_floor(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(config_text(), encoding="utf-8")
    assert policy.config_floor(path) == Decimal("75.000000")


@pytest.mark.parametrize(("kwargs", "code"), [
    ({"pin": "pytest-cov>=7"}, "pytest_cov_pin_missing"),
    ({"pin": "pytest-cov==7.1.0-malicious"}, "pytest_cov_pin_missing"),
    ({"dev": "['pytest-cov==7.1.0','pytest-cov>=9']"}, "pytest_cov_pin_missing"),
    ({"dev": "['pytest-cov==7.1.0','PYTEST..COV>=9']"}, "pytest_cov_pin_missing"),
    ({"dev": "['pytest-cov==7.1.0',' pytest_cov>=9']"}, "pytest_cov_pin_missing"),
    ({"dev": "'pytest-cov==7.1.0'"}, "invalid_coverage_config"),
    ({"precision": 5}, "coverage_precision_invalid"),
    ({"floor": 101}, "coverage_floor_invalid"),
    ({"floor": "true"}, "coverage_floor_invalid"),
    ({"floor": "'75'"}, "coverage_floor_invalid"),
    ({"floor": "nan"}, "coverage_floor_invalid"),
    ({"floor": "inf"}, "coverage_floor_invalid"),
    ({"floor": "75.1234567"}, "coverage_floor_invalid"),
    ({"report": "omit=[]\n"}, "coverage_exclusion_config"),
    ({"run": "source=['app']\n"}, "coverage_exclusion_config"),
    ({"run": "source_pkgs=['app.modules.projects']\n"}, "coverage_exclusion_config"),
    ({"run": "source_dirs=['app/modules/projects']\n"}, "coverage_exclusion_config"),
    ({"run": "include=[]\n"}, "coverage_exclusion_config"),
    ({"report": "exclude_lines=[]\n"}, "coverage_exclusion_config"),
])
def test_config_fails_closed(tmp_path: Path, kwargs: dict, code: str) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(config_text(**kwargs), encoding="utf-8")
    with pytest.raises(policy.PolicyError, match=code):
        policy.config_floor(path)


@pytest.mark.parametrize("text", [
    "[project.optional-dependencies]\ndev=['pytest-cov==7.1.0']\n[tool.coverage]\nreport=[]",
    "[project.optional-dependencies]\ndev=['pytest-cov==7.1.0']\n[tool.coverage]\nrun='source'\n[tool.coverage.report]\nprecision=6\nfail_under=75",
])
def test_config_rejects_malformed_tables(tmp_path: Path, text: str) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(policy.PolicyError, match="invalid_coverage_config"):
        policy.config_floor(path)


@pytest.mark.parametrize("pragma", ["pragma no cover", "PRAGMA:NO COVER", "pragma:   no   cover", "pragma:nocover"])
def test_application_coverage_pragma_is_rejected(tmp_path: Path, pragma: str) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app/a.py").write_text(f"x = 1  # {pragma}\n", encoding="utf-8")
    with pytest.raises(policy.PolicyError, match="coverage_pragma"):
        policy.validate_sources(tmp_path)
    (tmp_path / "app/a.py").write_text("MESSAGE = 'pragma: no cover'\n\"\"\"pragma: no cover\"\"\"\n", encoding="utf-8")
    policy.validate_sources(tmp_path)
    (tmp_path / "app/a.py").write_text("# This documentation mentions pragma: no cover\n# notapragmanocover\nx = 1\n", encoding="utf-8")
    policy.validate_sources(tmp_path)


def test_canonical_evidence_accepts_bounded_non_secret_schema(tmp_path: Path) -> None:
    path = write_json(tmp_path / "evidence.json", evidence(), canonical=True)
    assert policy.canonical_evidence(path, HEAD)["covered_lines"] == 3
    path.write_text(json.dumps(evidence()), encoding="utf-8")
    with pytest.raises(policy.PolicyError, match="evidence_not_canonical"):
        policy.canonical_evidence(path, HEAD)


@pytest.mark.parametrize(("updates", "code"), [
    ({"extra": 1}, "evidence_schema_invalid"),
    ({"schema_version": True}, "evidence_schema_invalid"),
    ({"base_merge_sha": "bad"}, "evidence_sha_invalid"),
    ({"covered_lines": 5}, "evidence_counts_invalid"),
    ({"measured_percent": "75"}, "evidence_decimal_invalid"),
    ({"configured_floor": "101.000000"}, "evidence_decimal_invalid"),
    ({"measured_percent": "74.000000"}, "evidence_percent_invalid"),
    ({"database_name": "workstream_test"}, "evidence_database_invalid"),
    ({"alembic_head": "old"}, "evidence_alembic_invalid"),
    ({"python_version": ""}, "evidence_version_invalid"),
    ({"python_version": "not-a-version"}, "evidence_version_invalid"),
    ({"python_version": "alice:hunter2@db.internal"}, "evidence_version_invalid"),
])
def test_evidence_schema_fails_closed(updates: dict, code: str) -> None:
    with pytest.raises(policy.PolicyError, match=code):
        policy.evidence_data(evidence(**updates), HEAD)


def test_runner_metadata_accepts_only_expected_tree_and_head(tmp_path: Path) -> None:
    value = {"schema_version": 1, "database_name": "workstream_test_012345abcdef",
             "alembic_head": HEAD, "tree_sha": SHA}
    path = write_json(tmp_path / "metadata.json", value)
    assert policy.runner_metadata(path, SHA, HEAD) == value
    value["tree_sha"] = "b" * 40
    write_json(path, value)
    with pytest.raises(policy.PolicyError, match="metadata_tree_mismatch"):
        policy.runner_metadata(path, SHA, HEAD)


def test_runner_metadata_rejects_matching_malformed_expectations(tmp_path: Path) -> None:
    value = {"schema_version": 1, "database_name": "workstream_test_012345abcdef",
             "alembic_head": "../head", "tree_sha": "not-a-sha"}
    path = write_json(tmp_path / "metadata.json", value)
    with pytest.raises(policy.PolicyError, match="metadata_alembic_mismatch"):
        policy.runner_metadata(path, "not-a-sha", "../head")


@pytest.mark.parametrize(("updates", "code"), [
    ({"database_name": "workstream_test"}, "metadata_invalid"),
    ({"schema_version": True}, "metadata_invalid"),
    ({"alembic_head": "old"}, "metadata_alembic_mismatch"),
    ({"extra": "secret"}, "metadata_invalid"),
])
def test_runner_metadata_fails_closed(tmp_path: Path, updates: dict, code: str) -> None:
    value = {"schema_version": 1, "database_name": "workstream_test_012345abcdef",
             "alembic_head": HEAD, "tree_sha": SHA, **updates}
    path = write_json(tmp_path / "metadata.json", value)
    with pytest.raises(policy.PolicyError, match=code):
        policy.runner_metadata(path, SHA, HEAD)


@pytest.mark.parametrize(("source", "weak"), [
    ("import pytest\npytest.skip('disabled')", True),
    ("import pytest as pt\npt.xfail('disabled')", True),
    ("from pytest import skip as stop\nstop('disabled')", True),
    ("import pytest\npytest.importorskip('optional')", True),
    ("import pytest\n@pytest.mark.skip\ndef test_x(): pass", True),
    ("from pytest import mark\npytestmark = mark.skipif", True),
    ("import unittest\n@unittest.skipUnless(True, 'reason')\ndef test_x(): pass", True),
    ("from unittest import expectedFailure\n@expectedFailure\ndef test_x(): pass", True),
    ("from unittest.case import SkipTest\nraise SkipTest('disabled')", True),
    ("import unittest.case as uc\nraise uc.SkipTest('disabled')", True),
    ("import unittest\nunittest.TestCase.skipTest", True),
    ("import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.skipTest('disabled')", True),
    ("from unittest import TestCase as Case\nclass T(Case):\n def test_x(self): super().skipTest('disabled')", True),
    ("from pytest import *", True),
    ("import pytest\nif False: pytest.skip('dead')", True),
    ("import pytest\n[pytest.skip() for _ in ()]", True),
    ("import pytest\nvalue = (pytest.skip() for _ in ())", True),
    ("import pytest\nasync def f(xs): return [pytest.skip() async for _ in xs]", True),
    ("import pytest\nconsume(value=(pytest.skip() for _ in ()))", True),
    ("import pytest\npytest = Local()\npytest.skip()", True),
    ("import pytest\np = pytest\nq = p\nq.skip()", True),
    ("import pytest\na = b\nb = a\nb = pytest\na.skip()", True),
    ("import pytest, unittest\ncontrol = pytest.raises\ncontrol = unittest.skip\ncontrol()", True),
    ("import pytest\ndef f():\n global pytest\n pytest.skip()", True),
    ("def outer():\n import pytest\n def inner(): pytest.skip()", True),
    ("def outer():\n import pytest\n def inner():\n  nonlocal pytest\n  pytest.skip()", True),
    ("value = 'pytest.skip and xfail are inert'\n# pytest.skip()", False),
    ("from .pytest import skip\nskip()", False),
    ("from local import pytest\npytest.skip()", False),
    ("import pytest\ndef f(pytest): pytest.skip()", False),
    ("import pytest\na = lambda pytest: pytest.skip(); b = lambda: pytest.skip()", True),
    ("import pytest\nvalues = (lambda: pytest.skip() for _ in ())", True),
    ("import pytest\ndef f():\n pytest.skip()\n pytest = Local()", False),
    ("import pytest\n[pytest.skip() for pytest in ()]", False),
    ("a = b\nb = a\na.skip()", False),
    ("class Local:\n def test_x(self): self.skipTest()", False),
    ("from unittest import TestCase\ncase = TestCase()\ncase.skipTest()", False),
    ("class Local:\n def skip(self): pass\nlocal = Local()\nlocal.skip()", False),
    ("from __future__ import annotations\nimport pytest\nvalue: pytest.mark.skip", False),
    ("import pytest\np = (pytest,)\np.skip()", False),
    ("import pytest\np = build(pytest)\np.skip()", False),
    ("from pytest import fixture\nfixture.skip()", False),
    ("from unittest import mock\nmock.skip()", False),
    ("import unittest.mock as mock\nmock.skip()", False),
    ("import pytest.fixture as fixture\nfixture.skip()", False),
    ("import unittest.mock\nunittest.skip()", True),
    ("import pytest\ndef outer():\n pytest = Local()\n def inner(): pytest.skip()", False),
    ("import pytest\ndef outer(pytest):\n def inner(): pytest.skip()", False),
    ("import pytest\ndef outer():\n import local as pytest\n def inner(): pytest.skip()", False),
    ("import pytest\nouter = lambda pytest: lambda: pytest.skip()", False),
    ("import pytest\n[(lambda: pytest.skip())() for pytest in ()]", False),
    ("import pytest\n[[pytest.skip() for _ in ()] for pytest in ()]", False),
    ("import unittest\nraise unittest.case.SkipTest('disabled')", True),
    ("import unittest\nunittest.case.skip('disabled')", True),
    ("import unittest.case\nunittest.case.expectedFailure", True),
    ("import unittest\nunittest.case.TestCase.skipTest", True),
    ("import pytest as p\nimport unittest as p\nprint(p)\nprint(p.foo)", False),
    ("from pytest import raises as f\nfrom unittest import TestCase as f\nprint(f)", False),
    ("import pytest as p\nimport unittest as p\np.skip()", True),
    ("def f[T](): pass\nclass C[T]: pass\ntype A[T] = list[T]", PEP695_INVALID),
    ("import pytest\ndef f[T: pytest.skip()](): pass", True),
    ("import pytest\ndef f[pytest](): pytest.skip()", PEP695_INVALID),
    ("import pytest\ntype Alias[pytest] = pytest.skip", PEP695_INVALID),
    ("def f[T: (lambda: int)](): pass\nclass C[T: (x for x in ())]: pass\ntype A[T: (lambda: int)] = T", PEP695_INVALID),
    ("import pytest\ndef f[T: (lambda: pytest.skip())](): pass", True),
    ("import unittest\nclass T(unittest.TestCase):\n def outer(self):\n  def inner(self): self.skipTest()", False),
    ("import unittest\nclass T(unittest.TestCase):\n def outer(self):\n  def inner(): self.skipTest()", True),
    ("import pytest\ndef a():\n p = pytest\n def b():\n  p = Local()\n  def c():\n   nonlocal p\n   p.skip()", False),
    ("import pytest\n[x for pytest.skip().field in xs]", True),
    ("import pytest\n(x for target[pytest.skip()] in xs)", True),
    ("import pytest\ntarget[pytest.skip()]: int = 1", True),
    ("import pytest\npytest.skip().field: int = 1", True),
    ("import pytest\ndef f(*args: pytest.skip()): pass", True),
    ("import pytest\ndef f(**kwargs: pytest.mark.xfail): pass", True),
    ("from __future__ import annotations\nimport pytest\ndef f(*args: pytest.skip()): pass", False),
    ("import pytest\n{(lambda: pytest.skip())() for pytest in ()}", False),
    ("import pytest\n{pytest: (lambda: pytest.skip())() for pytest in ()}", False),
    ("[(lambda value: value)(1) for _ in ()]", False),
    ("import pytest\n[(lambda: pytest.skip())() for _ in ()]", True),
    ("import pytest\n[[pytest.skip() for _ in ()] for _ in ()]", True),
    ("import pytest\n{{pytest.skip() for _ in ()} for _ in ()}", True),
    ("import pytest\n{key: {pytest.skip(): value for value in ()} for key in ()}", True),
])
def test_python_weakening_uses_lexical_syntax(tmp_path: Path, source: str, weak: bool) -> None:
    path = tmp_path / "test_policy.py"
    path.write_text(source, encoding="utf-8")
    assert policy.weak_python(path) is weak


@pytest.mark.parametrize(("source", "line", "blocked"), [
    ("assert result\n", 1, True),
    ("import pytest\npytest.raises(ValueError)\n", 2, True),
    ("from pytest import raises as expect\nexpect(ValueError)\n", 2, True),
    ("import pytest\nif False: pytest.raises(ValueError)\n", 2, True),
    ("import pytest\nvalue = (pytest.raises(ValueError) for _ in ())\n", 2, True),
    ("class T:\n def test_x(self): self.assertEqual(1, 1)\n", 2, True),
    ("class T:\n def test_x(other): other.assertEqual(1, 1)\n", 2, False),
    ("from .pytest import raises\nraises(ValueError)\n", 2, False),
    ("from pytest import fixture\nfixture.raises(ValueError)\n", 2, False),
    ("import pytest\n[(lambda: pytest.raises(ValueError))() for pytest in ()]\n", 2, False),
    ("import pytest\ndef a():\n r = pytest.raises\n def b():\n  r = print\n  def c():\n   nonlocal r\n   r(ValueError)\n", 8, False),
    ("import pytest\n[x for target[pytest.raises(ValueError)] in xs]\n", 2, True),
    ("import pytest\ntarget[pytest.raises(ValueError)]: int = 1\n", 2, True),
    ("import pytest\ndef f(*args: pytest.raises(ValueError)): pass\n", 2, True),
    ("import pytest\n[[pytest.raises(ValueError) for _ in ()] for _ in ()]\n", 2, True),
    ("MESSAGE = 'pytest.raises(ValueError)'\n", 1, False),
    ("def invalid(\n", 1, True),
])
def test_deleted_assertions_use_syntax(source: str, line: int, blocked: bool) -> None:
    deleted = source.splitlines()[line - 1]
    diff = f"@@ -{line},1 +{line},0 @@\n-{deleted}"
    assert policy.has_deleted_assertion(diff, source) is blocked


def test_deleted_assertions_fail_closed_without_base_source() -> None:
    assert policy.has_deleted_assertion("@@ -1,1 +1,0 @@\n-assert result", "") is True
    assert policy.has_deleted_assertion("", "") is False


@pytest.mark.parametrize(("clean", "weakening", "assertion"), [
    ("def f[T: (lambda: int) = (x for x in ())](): pass", "import pytest\ndef f[T: (lambda: int) = (pytest.skip() for _ in ())](): pass", "import pytest\ndef f[T: (lambda: int) = (pytest.raises(ValueError) for _ in ())](): pass"),
    ("def f[T: (x for x in ()) = (lambda: int)](): pass", "import pytest\ndef f[T: (pytest.skip() for _ in ()) = (lambda: int)](): pass", "import pytest\ndef f[T: (pytest.raises(ValueError) for _ in ()) = (lambda: int)](): pass"),
    ("class C[T: (lambda: int) = (x for x in ())]: pass", "import pytest\nclass C[T: (lambda: int) = (pytest.skip() for _ in ())]: pass", "import pytest\nclass C[T: (lambda: int) = (pytest.raises(ValueError) for _ in ())]: pass"),
    ("class C[T: (x for x in ()) = (lambda: int)]: pass", "import pytest\nclass C[T: (pytest.skip() for _ in ()) = (lambda: int)]: pass", "import pytest\nclass C[T: (pytest.raises(ValueError) for _ in ()) = (lambda: int)]: pass"),
    ("type A[T: (lambda: int) = (x for x in ())] = T", "import pytest\ntype A[T: (lambda: int) = (pytest.skip() for _ in ())] = T", "import pytest\ntype A[T: (lambda: int) = (pytest.raises(ValueError) for _ in ())] = T"),
    ("type A[T: (x for x in ()) = (lambda: int)] = T", "import pytest\ntype A[T: (pytest.skip() for _ in ()) = (lambda: int)] = T", "import pytest\ntype A[T: (pytest.raises(ValueError) for _ in ()) = (lambda: int)] = T"),
])
def test_typevar_bound_default_child_order(clean: str, weakening: str, assertion: str) -> None:
    if sys.version_info < (3, 13):
        for source in (clean, weakening, assertion):
            with pytest.raises(SyntaxError):
                policy.analyze_python(source)
        return
    assert policy.analyze_python(clean)[1].weak is False
    assert policy.analyze_python(weakening)[1].weak is True
    analysis = policy.analyze_python(assertion)[1]
    assert analysis.assertion_ranges
    line = next(iter(analysis.assertion_ranges))[0]
    deleted = assertion.splitlines()[line - 1]
    assert policy.has_deleted_assertion(f"@@ -{line},1 +{line},0 @@\n-{deleted}", assertion)


@pytest.mark.parametrize(("files", "rows", "source", "diff", "code"), [
    (["backend/app/a.py"], [], "", "", "scope_violation"),
    (["backend/tests/test_ok.py"], [("backend/tests/test_ok.py", 701, 0)], "assert True", "", "implementation_size_exceeded"),
    (["backend/tests/test_ok.py"], [("backend/tests/test_ok.py", 1, 0)], "import pytest\npytest.skip()", "", "test_skip_or_xfail"),
    (["backend/tests/test_ok.py"], [("backend/tests/test_ok.py", 1, 0)], "assert value", "@@ -1,1 +1,0 @@\n-assert value", "deleted_assertion"),
])
def test_delta_fails_closed(monkeypatch, tmp_path: Path, files, rows, source, diff, code) -> None:
    test = tmp_path / "backend/tests/test_ok.py"
    test.parent.mkdir(parents=True)
    test.write_text(source, encoding="utf-8")
    monkeypatch.setattr(policy, "REPO", tmp_path)
    monkeypatch.setattr(policy, "changed_files", lambda *_: files)
    monkeypatch.setattr(policy, "numstat", lambda *_: (0, 0, rows))
    monkeypatch.setattr(policy, "diff_text", lambda *_: diff)
    monkeypatch.setattr(policy, "maybe_run", lambda command: source if command[:2] == ["git", "show"] else "")
    with pytest.raises(policy.PolicyError, match=code):
        policy.validate_delta("base", 700, {"backend/tests/test_ok.py"})


def test_delta_accepts_memory_and_restores_cwd(monkeypatch, tmp_path: Path) -> None:
    test = tmp_path / "backend/tests/test_ok.py"
    test.parent.mkdir(parents=True)
    test.write_text("assert value", encoding="utf-8")
    files = ["backend/tests/test_ok.py", ".agent-loop/LOOP_STATE.md", f"{policy.QUAL_MEMORY}STATUS.md"]
    monkeypatch.setattr(policy, "REPO", tmp_path)
    monkeypatch.setattr(policy, "changed_files", lambda *_: files)
    monkeypatch.setattr(policy, "numstat", lambda *_: (0, 0, [(files[0], 1, 0), (files[1], 100, 0), (files[2], 100, 0)]))
    monkeypatch.setattr(policy, "diff_text", lambda *_: "+assert value")
    monkeypatch.setattr(policy, "maybe_run", lambda command: "assert value" if command[:2] == ["git", "show"] else "")
    previous = Path.cwd()
    policy.validate_delta("base", 1, {files[0]})
    assert Path.cwd() == previous


@pytest.mark.parametrize(("statuses", "renamed"), [
    ("R100\tbackend/tests/test_old.py\tbackend/tests/test_new.py", True),
    ("R100\tdocs/old.md\tdocs/new.md", False),
    ("M\tbackend/tests/test_ok.py", False),
])
def test_test_rename_detection(statuses: str, renamed: bool) -> None:
    assert policy.has_test_rename(statuses) is renamed


def test_compute_cli_is_read_only_and_stable(tmp_path: Path) -> None:
    files = {
        item.relative_to(policy.BACKEND).as_posix():
            {"summary": {"covered_lines": 0, "num_statements": 0}}
        for item in (policy.BACKEND / "app").rglob("*.py")
    }
    files[next(iter(files))]["summary"] = {"covered_lines": 2, "num_statements": 3}
    path = write_json(tmp_path / "coverage.json", {"files": files, "totals": {"covered_lines": 2, "num_statements": 3}})
    command = [sys.executable, str(SCRIPTS / "coverage_policy.py"), "--coverage-json", str(path)]
    result = subprocess.run([*command, "--compute-floor"], text=True, capture_output=True, check=False)
    assert (result.returncode, result.stdout, result.stderr) == (0, "66.666666\n", "")
    assert list(tmp_path.iterdir()) == [path]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert result.stderr == "coverage-policy: mode_required\n"
