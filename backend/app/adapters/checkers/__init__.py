"""CHECKER-owned composition adapters."""

import asyncio
from typing import Any, BinaryIO, Protocol
from pathlib import Path

from app.modules.checkers.api import (
    PreSubmissionExecutionFacts,
    PreSubmissionInfrastructureUnavailableError,
)
from app.modules.checkers.catalogue import PreSubmissionCheckerCatalogue
from app.modules.checkers.pre_submit_execution import (
    DefaultPreSubmissionExecutionError,
    DefaultPreSubmissionExecutionInput,
    EffectivePreSubmissionProcessor,
)


class _ExecutionRequest(Protocol):
    plan: Any
    commitment: Any
    inspection: Any
    manifest: Any
    change_gate: Any
    packet: Any
    prepared_generation_id: Any
    storage_scheme: str


class _PublicFactsCheckerProcessor:
    """Project the private CHECKER processor result to public facts."""

    def __init__(self, processor: EffectivePreSubmissionProcessor) -> None:
        self._processor = processor

    def abort(self) -> None:
        self._processor.abort()

    async def process(
        self, reader: BinaryIO, workspace: Path
    ) -> PreSubmissionExecutionFacts:
        try:
            result = await asyncio.to_thread(
                self._processor.process_blocking, reader, workspace
            )
            return result.bounded_facts()
        except DefaultPreSubmissionExecutionError as exc:
            raise PreSubmissionInfrastructureUnavailableError(str(exc)) from exc


class PreSubmitCheckerExecutionAdapter:
    """Build the private CHECKER processor behind dependency-safe facts."""

    def __init__(self, *, catalogue: PreSubmissionCheckerCatalogue, archive_inspector: Any):
        self._catalogue = catalogue
        self._archive_inspector = archive_inspector

    @property
    def catalogue_manifest_sha256(self) -> str:
        return self._catalogue.manifest_sha256

    def build(self, request: _ExecutionRequest) -> _PublicFactsCheckerProcessor:
        return _PublicFactsCheckerProcessor(
            EffectivePreSubmissionProcessor(
                archive_inspector=self._archive_inspector,
                catalogue=self._catalogue,
                execution_input=DefaultPreSubmissionExecutionInput(
                    plan=request.plan,
                    commitment=request.commitment,
                    inspection=request.inspection,
                    manifest=request.manifest,
                    change_gate=request.change_gate,
                    packet=request.packet,
                    prepared_generation_id=request.prepared_generation_id,
                    storage_scheme=request.storage_scheme,
                ),
            )
        )
