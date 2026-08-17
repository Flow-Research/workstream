"""Structural limits for the CP04B implementation surfaces."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SURFACES = (
    "app/modules/contributions/models.py",
    "app/modules/contributions/repository.py",
    "app/modules/contributions/service.py",
    "app/modules/contributions/policy_graph.py",
    "app/modules/contributions/policy_mutation_support.py",
    "app/modules/contributions/policy_publication.py",
)


def test_cp04b_application_files_remain_below_five_hundred_lines() -> None:
    sizes = {
        path: len((ROOT / path).read_text(encoding="utf-8").splitlines())
        for path in SURFACES
    }
    assert all(size < 500 for size in sizes.values()), sizes


def test_cp04b_behavior_tests_remain_below_five_hundred_lines() -> None:
    tests = Path(__file__).parent.glob("test_policy_*.py")
    sizes = {path.name: len(path.read_text(encoding="utf-8").splitlines()) for path in tests}
    assert all(size < 500 for size in sizes.values()), sizes
