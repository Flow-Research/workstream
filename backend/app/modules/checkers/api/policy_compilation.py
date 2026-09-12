"""Typed bundle-and-plan compilation; private implementation stays in CHECKERS."""

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.modules.checkers.api.pre_submit import EffectivePreSubmissionPlanningPort


@dataclass(frozen=True)
class CompiledPreSubmitCheckerPolicy:
    """Compiled bundle plus index projections persisted on policy rows."""

    compiler_version: str
    compiled_bundle: dict[str, Any]
    compiled_bundle_hash: str
    checker_names: list[str]
    checker_configs: dict[str, Any]



class PreSubmissionPolicyCompilationPort(EffectivePreSubmissionPlanningPort, Protocol):
    """The canonical catalogue supplies both compilation steps to approval."""

    def compile_policy_bundle(
        self, *, effective_policy: Mapping[str, object], effective_policy_hash: str,
    ) -> CompiledPreSubmitCheckerPolicy:
        """Compile the exact policy, raising ValueError for an unsupported contract."""
