from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import coverage_policy as policy  # noqa: E402

HEAD = "0006_history_read_authority"
SHA = "a" * 40
PEP695_INVALID = sys.version_info < (3, 12)


def test_sqlalchemy_async_coverage_preserves_source_line_custody(tmp_path: Path) -> None:
    """Actual SQLAlchemy switches must not attribute resumed app lines to callers."""
    app_source = tmp_path / "measured_app.py"
    app_source.write_text(
        "def work():\n"
        "    before = 'ready'\n"
        "    await_only(asyncio.sleep(0))\n"
        "    after = 'resumed'\n"
        "    await_only(asyncio.sleep(0))\n"
        "    return before, after\n",
        encoding="utf-8",
    )
    caller_source = tmp_path / "measured_caller.py"
    caller_source.write_text(
        "\n" * 40 + "async def call():\n    return await greenlet_spawn(work)\n",
        encoding="utf-8",
    )
    probe = """
import asyncio
import json
from pathlib import Path
import sys
from coverage import Coverage
from sqlalchemy.util.concurrency import await_only, greenlet_spawn

config, app, caller = map(Path, sys.argv[1:])
namespace = dict(asyncio=asyncio, await_only=await_only, greenlet_spawn=greenlet_spawn)
for path in (app, caller):
    exec(compile(path.read_text(), str(path), 'exec'), namespace)
coverage = Coverage(config_file=str(config), data_file=None, include=[str(app), str(caller)])
assert coverage.get_option('run:concurrency') == ['thread', 'greenlet']
coverage.start()
try:
    result = asyncio.run(namespace['call']())
finally:
    coverage.stop()
data = coverage.get_data()
print(json.dumps(dict(result=result, app=sorted(data.lines(str(app)) or []),
                      caller=sorted(data.lines(str(caller)) or []))))
"""
    # A child owns the probe tracer; inherited pytest-cov must not start a second one.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_"))
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            probe,
            str(SCRIPTS.parent / "pyproject.toml"),
            str(app_source),
            str(caller_source),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert json.loads(completed.stdout) == {
        "result": ["ready", "resumed"],
        "app": [2, 3, 4, 5, 6],
        "caller": [42],
    }


@pytest.mark.parametrize(
    ("source", "weak"),
    [
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
        (
            "import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.skipTest('disabled')",
            True,
        ),
        (
            "from unittest import TestCase as Case\nclass T(Case):\n def test_x(self): super().skipTest('disabled')",
            True,
        ),
        ("from pytest import *", True),
        ("import pytest\nif False: pytest.skip('dead')", True),
        ("import pytest\n[pytest.skip() for _ in ()]", True),
        ("import pytest\nvalue = (pytest.skip() for _ in ())", True),
        ("import pytest\nasync def f(xs): return [pytest.skip() async for _ in xs]", True),
        ("import pytest\nconsume(value=(pytest.skip() for _ in ()))", True),
        ("import pytest\npytest = Local()\npytest.skip()", True),
        ("import pytest\np = pytest\nq = p\nq.skip()", True),
        ("import pytest\na = b\nb = a\nb = pytest\na.skip()", True),
        (
            "import pytest, unittest\ncontrol = pytest.raises\ncontrol = unittest.skip\ncontrol()",
            True,
        ),
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
        (
            "import pytest\ndef outer():\n import local as pytest\n def inner(): pytest.skip()",
            False,
        ),
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
        (
            "def f[T: (lambda: int)](): pass\nclass C[T: (x for x in ())]: pass\ntype A[T: (lambda: int)] = T",
            PEP695_INVALID,
        ),
        ("import pytest\ndef f[T: (lambda: pytest.skip())](): pass", True),
        (
            "import unittest\nclass T(unittest.TestCase):\n def outer(self):\n  def inner(self): self.skipTest()",
            False,
        ),
        (
            "import unittest\nclass T(unittest.TestCase):\n def outer(self):\n  def inner(): self.skipTest()",
            True,
        ),
        (
            "import pytest\ndef a():\n p = pytest\n def b():\n  p = Local()\n  def c():\n   nonlocal p\n   p.skip()",
            False,
        ),
        ("import pytest\n[x for pytest.skip().field in xs]", True),
        ("import pytest\n(x for target[pytest.skip()] in xs)", True),
        ("import pytest\ntarget[pytest.skip()]: int = 1", True),
        ("import pytest\npytest.skip().field: int = 1", True),
        ("import pytest\ndef f(*args: pytest.skip()): pass", True),
        ("import pytest\ndef f(**kwargs: pytest.mark.xfail): pass", True),
        (
            "from __future__ import annotations\nimport pytest\ndef f(*args: pytest.skip()): pass",
            False,
        ),
        ("import pytest\n{(lambda: pytest.skip())() for pytest in ()}", False),
        ("import pytest\n{pytest: (lambda: pytest.skip())() for pytest in ()}", False),
        ("[(lambda value: value)(1) for _ in ()]", False),
        ("import pytest\n[(lambda: pytest.skip())() for _ in ()]", True),
        ("import pytest\n[[pytest.skip() for _ in ()] for _ in ()]", True),
        ("import pytest\n{{pytest.skip() for _ in ()} for _ in ()}", True),
        ("import pytest\n{key: {pytest.skip(): value for value in ()} for key in ()}", True),
    ],
)
def test_python_weakening_uses_lexical_syntax(tmp_path: Path, source: str, weak: bool) -> None:
    path = tmp_path / "test_policy.py"
    path.write_text(source, encoding="utf-8")
    assert policy.weak_python(path) is weak


@pytest.mark.parametrize(
    ("clean", "weakening", "assertion"),
    [
        (
            "def f[T: (lambda: int) = (x for x in ())](): pass",
            "import pytest\ndef f[T: (lambda: int) = (pytest.skip() for _ in ())](): pass",
            "import pytest\ndef f[T: (lambda: int) = (pytest.raises(ValueError) for _ in ())](): pass",
        ),
        (
            "def f[T: (x for x in ()) = (lambda: int)](): pass",
            "import pytest\ndef f[T: (pytest.skip() for _ in ()) = (lambda: int)](): pass",
            "import pytest\ndef f[T: (pytest.raises(ValueError) for _ in ()) = (lambda: int)](): pass",
        ),
        (
            "class C[T: (lambda: int) = (x for x in ())]: pass",
            "import pytest\nclass C[T: (lambda: int) = (pytest.skip() for _ in ())]: pass",
            "import pytest\nclass C[T: (lambda: int) = (pytest.raises(ValueError) for _ in ())]: pass",
        ),
        (
            "class C[T: (x for x in ()) = (lambda: int)]: pass",
            "import pytest\nclass C[T: (pytest.skip() for _ in ()) = (lambda: int)]: pass",
            "import pytest\nclass C[T: (pytest.raises(ValueError) for _ in ()) = (lambda: int)]: pass",
        ),
        (
            "type A[T: (lambda: int) = (x for x in ())] = T",
            "import pytest\ntype A[T: (lambda: int) = (pytest.skip() for _ in ())] = T",
            "import pytest\ntype A[T: (lambda: int) = (pytest.raises(ValueError) for _ in ())] = T",
        ),
        (
            "type A[T: (x for x in ()) = (lambda: int)] = T",
            "import pytest\ntype A[T: (pytest.skip() for _ in ()) = (lambda: int)] = T",
            "import pytest\ntype A[T: (pytest.raises(ValueError) for _ in ()) = (lambda: int)] = T",
        ),
    ],
)
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
