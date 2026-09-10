"""OpenAI Agents SDK implementation of the single guide-compilation port."""

from __future__ import annotations

import asyncio
import os
import json
from dataclasses import replace
from typing import Literal

from pydantic import ValidationError

from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities
from app.adapters.project_agents.openai_workspace import OpenAIGuideWorkspace, cleanup_owned_resources
from app.adapters.project_agents.provider_resilience import (
    ModelCircuitAdmission, model_retry_settings,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.interfaces.project_agents import (
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    project_guide_compilation_prompt_bytes,
    require_complete_project_guide_compilation_result,
    validate_project_guide_compilation_result,
)


_INVALID_SCHEMA_OUTPUT = object()


class OpenAIAgentSdkProjectGuideRuntime:
    """Investigate assigned originals in one bounded isolated SDK run."""

    def __init__(self, configuration: ProjectGuideRuntimeConfiguration) -> None:
        """Validate the installed adapter and credentials before the dispatch fence."""
        if configuration.runtime_key != "openai_agents_sdk":
            raise ProjectAgentRuntimeConfigurationError("project guide runtime is unsupported")
        try:
            import agents  # noqa: F401
            import openai  # noqa: F401
        except ImportError:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime is unavailable"
            ) from None
        if not os.environ.get("OPENAI_API_KEY"):
            raise ProjectAgentRuntimeConfigurationError(
                "project guide model credentials are unavailable"
            )
        self._configuration = configuration
        self._admission: ModelCircuitAdmission | None = None

    def admit_execution(self) -> None:
        """Acquire one process-local provider lease before the product dispatch fence."""
        if self._admission is not None:
            raise ProjectAgentRuntimeError("project guide runtime admission already acquired")
        self._admission = ModelCircuitAdmission(self._configuration)

    async def cleanup_resources(self, custody) -> bool:
        """Retry exact recorded cleanup independently of inference circuit admission."""
        from openai import AsyncOpenAI

        try:
            async with asyncio.timeout(self._configuration.cleanup_timeout_seconds):
                async with AsyncOpenAI(max_retries=0, timeout=self._configuration.request_timeout_seconds) as client:
                    await cleanup_owned_resources(client, custody)
                    return not await custody.cleanup_resources()
        except Exception:
            return False

    async def aclose(self) -> None:
        """Release pre-fence admission after completion, cancellation, or a lost fence."""
        if self._admission is not None:
            self._admission.close()

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Expose the immutable identity checked by the shared factory."""
        return self._configuration.adapter_identity

    async def compile_project_guide(
        self,
        context: ProjectGuideCompilationContext,
        capabilities: GuideRuntimeCapabilities,
    ) -> ProjectGuideCompilationResult:
        """Run one exact attempt with its recorded model and instruction configuration."""
        if context.runtime_configuration != self._configuration:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime configuration mismatch"
            )
        if self._admission is None:
            raise ProjectAgentRuntimeError("project guide runtime was not admitted")
        prompt = project_guide_compilation_prompt_bytes(context)
        if len(prompt) > self._configuration.maximum_manifest_bytes:
            raise ProjectAgentRuntimeError("project guide prompt exceeds configured size limit")
        runtime_failure = None
        invalid_failure = None
        output = None
        try:
            output = await asyncio.wait_for(
                self._run(context, prompt.decode("utf-8"), capabilities),
                timeout=self._configuration.timeout_seconds,
            )
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            runtime_failure = "project guide run cancelled"
        except TimeoutError:
            runtime_failure = "project guide run timed out"
        except ProjectGuideCompilationInvalidOutputError as error:
            invalid_failure = error.failure_code
        except Exception:
            runtime_failure = "project guide run failed"
        # Raise outside provider/validation handlers so hidden exception chains
        # cannot retain source text in their traceback frames.
        if runtime_failure is not None:
            raise ProjectAgentRuntimeError(runtime_failure) from None
        if invalid_failure is not None:
            raise ProjectGuideCompilationInvalidOutputError(invalid_failure) from None
        if output is _INVALID_SCHEMA_OUTPUT:
            raise ProjectGuideCompilationInvalidOutputError("schema_invalid") from None
        try:
            return await self._validate_output(context, output, capabilities)
        except (TypeError, ValueError) as exc:
            invalid_failure = _invalid_compilation_failure_code(exc)
        output = None
        raise ProjectGuideCompilationInvalidOutputError(invalid_failure) from None

    async def _validate_output(self, context, output, capabilities):
        """Keep rejected values out of the sanitized caller's traceback frame."""
        if isinstance(output, ProjectGuideCompilationResult):
            result = output
        elif isinstance(output, str):
            result = ProjectGuideCompilationResult.model_validate_json(output)
        else:
            result = ProjectGuideCompilationResult.model_validate(output)
        require_complete_project_guide_compilation_result(result)
        validate_project_guide_compilation_result(context, result)
        if result.agent_version != context.agent_version:
            raise ValueError("compilation result agent version is invalid")
        opened = await capabilities.resources.opened_handles()
        if not opened:
            raise ValueError("compilation has no opened document evidence")
        document_handles = {
            (item.source_item_id, item.ingest_id): context.material.handle_for(item)
            for item in context.material.documents
        }
        references = (
            *(ref for finding in result.findings for ref in finding.evidence_refs),
            *(ref for requirement in result.requirements for ref in requirement.evidence_refs),
            *(ref for suggestion in result.capability_suggestions for ref in suggestion.evidence_refs),
        )
        cited_handles = {document_handles[(ref.source_item_id, ref.document_version_id)]
                         for ref in references}
        if not cited_handles <= opened:
            raise ValueError("compilation cites unopened source material")
        if result.status != "guide_blocked" and cited_handles != set(document_handles.values()):
            raise ValueError("ready compilation does not account for every assigned document")
        return result

    async def _run(self, context: ProjectGuideCompilationContext, prompt: str,
                   capabilities: GuideRuntimeCapabilities):
        """Keep provider resources, tool execution and SDK parsing inside the adapter."""
        from agents import (
            Agent, AgentOutputSchema, CodeInterpreterTool, ModelSettings,
            OpenAIResponsesModel, RunConfig, Runner, function_tool,
        )
        from agents.exceptions import ModelBehaviorError
        from openai import AsyncOpenAI

        parser_rejected = False
        configuration = self._configuration
        admission = self._admission

        class CompilationOutputSchema(AgentOutputSchema):
            """Preserve native SDK parser redaction while identifying known rejection."""

            def validate_json(self, json_str: str):
                nonlocal parser_rejected
                try:
                    return super().validate_json(json_str)
                except ModelBehaviorError:
                    parser_rejected = True
                    raise

        class BoundedResponsesModel(OpenAIResponsesModel):
            """Bound hosted work across every model turn and compact carried input."""

            hosted_calls = 0

            async def get_response(self, system_instructions, input, model_settings, tools,
                                   output_schema, handoffs, tracing, previous_response_id=None,
                                   conversation_id=None, prompt=None):
                remaining = configuration.maximum_hosted_tool_calls - self.hosted_calls
                if remaining <= 0 or previous_response_id is not None or conversation_id is not None:
                    raise RuntimeError("guide runtime work boundary exceeded")
                if isinstance(input, list):
                    compacted = [i for i, item in enumerate(input)
                                 if isinstance(item, dict) and item.get("type") == "compaction"]
                    if compacted:
                        input = input[compacted[-1]:]
                model_settings = replace(model_settings, extra_args={"max_tool_calls": remaining})
                admission.before_request()
                try:
                    response = await super().get_response(
                        system_instructions, input, model_settings, tools, output_schema,
                        handoffs, tracing, previous_response_id=None, conversation_id=None,
                        prompt=prompt,
                    )
                except Exception as error:
                    admission.request_failed(error)
                    raise
                admission.request_succeeded()
                self.hosted_calls += sum(
                    getattr(item, "type", None) == "code_interpreter_call"
                    for item in response.output
                )
                if self.hosted_calls > configuration.maximum_hosted_tool_calls:
                    raise RuntimeError("guide runtime hosted work limit exceeded")
                return response

        async with AsyncOpenAI(max_retries=0, timeout=min(configuration.request_timeout_seconds, configuration.timeout_seconds)) as client:
            workspace = OpenAIGuideWorkspace(client, configuration, context.material, capabilities)
            try:
                await workspace.start()

                @function_tool(failure_error_function=None)
                async def open_guide_document(handle: str) -> str:
                    """Open one assigned original by opaque handle, returning its workspace path."""
                    return json.dumps(await workspace.open_document(handle))

                agent = Agent(
                    name="ProjectGuideCompilationAgent",
                    instructions=configuration.instructions,
                    model=BoundedResponsesModel(model=configuration.model, openai_client=client),
                    model_settings=ModelSettings(
                        store=False, parallel_tool_calls=False,
                        retry=model_retry_settings(configuration),
                        response_include=["code_interpreter_call.outputs"],
                        context_management=[{"type": "compaction",
                                             "compact_threshold": configuration.compaction_threshold_tokens}],
                    ),
                    output_type=CompilationOutputSchema(ProjectGuideCompilationResult,
                                                        strict_json_schema=True),
                    tools=[open_guide_document, CodeInterpreterTool(tool_config={
                        "type": "code_interpreter", "container": workspace.container_id,
                    })],
                    handoffs=[],
                )
                try:
                    result = await Runner.run(
                        agent, prompt, max_turns=configuration.maximum_turns,
                        run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
                    )
                except ModelBehaviorError:
                    if not parser_rejected:
                        raise
                else:
                    return result.final_output
                return _INVALID_SCHEMA_OUTPUT
            finally:
                await workspace.close()


def _invalid_compilation_failure_code(
    error: TypeError | ValueError,
) -> Literal["schema_invalid", "unsafe_text"]:
    """Classify only a proven unsafe-text validation without exposing output."""
    if isinstance(error, ValidationError):
        for item in error.errors(include_url=False, include_input=False):
            context = item.get("ctx") or {}
            cause = context.get("error")
            if isinstance(cause, ValueError) and str(cause) == "model-produced text is unsafe":
                return "unsafe_text"
    if str(error) == "model-produced text is unsafe":
        return "unsafe_text"
    return "schema_invalid"
