"""Exact behavior-partition custody proof for CP02 additions."""

from scripts import behavior_ownership as ownership


def test_cp02_partition_additions_are_exact_and_owner_classified() -> None:
    assert ownership.ARCH_CP02_ADAPTER_BINDING_TARGETS == {
        "backend/app/modules/actors/api/compensation_adapter.py",
        "backend/app/modules/compensation/api/adapter_bindings.py",
        "backend/app/modules/compensation/repository.py",
        "backend/app/modules/compensation/service.py",
        "backend/app/modules/projects/api/compensation_binding.py",
    }
    assert {
        target: ownership.group_for_target(target)
        for target in ownership.ARCH_CP02_ADAPTER_BINDING_TARGETS
    } == {
        "backend/app/modules/actors/api/compensation_adapter.py": "shared",
        "backend/app/modules/compensation/api/adapter_bindings.py": "lifecycle",
        "backend/app/modules/compensation/repository.py": "lifecycle",
        "backend/app/modules/compensation/service.py": "lifecycle",
        "backend/app/modules/projects/api/compensation_binding.py": "lifecycle",
    }
