"""Project sample descriptors and synthetic requests; no live custody or authority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
    ExternalCheckerResourceLimits,
    ExternalCheckerSchema,
    Identifier,
    SchemaVersion,
    external_checker_json_hash,
    make_external_checker_execution_request,
    safe_finding_path,
    ExternalCheckerExecutionIdentity,
    ExternalCheckerMaterial,
)
from scripts.checker_image_process import ImageError


class Sample(BaseModel):
    """One independently chosen positive or negative project example."""

    model_config = ConfigDict(extra="forbid", strict=True)
    name: Identifier
    directory: str
    expected: Literal["passed", "failed"]
    expected_codes: Annotated[list[Identifier], Field(max_length=256)] = []
    configuration: dict[str, JsonValue]
    input: dict[str, JsonValue]


class Descriptor(BaseModel):
    """Small project-owned manifest; hashes and protocol envelopes are derived."""

    model_config = ConfigDict(extra="forbid", strict=True)
    project: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")]
    capability_id: Identifier
    capability_version: SchemaVersion
    phase: Literal["pre_submit", "post_submit"]
    configuration_schema: dict[str, JsonValue]
    input_schema: dict[str, JsonValue]
    resources: ExternalCheckerResourceLimits
    samples: Annotated[list[Sample], Field(min_length=2, max_length=100)]

    def spec(self, digest: str) -> ExternalCheckerRegistrySpec:
        """Derive registration input using the canonical public CHECKERS contract."""

        def schema(name: str, document: dict) -> ExternalCheckerSchema:
            return ExternalCheckerSchema(
                schema_id=name,
                schema_version="v1",
                document=document,
                schema_sha256=external_checker_json_hash(document),
            )

        return ExternalCheckerRegistrySpec(
            capability_id=self.capability_id,
            capability_version=self.capability_version,
            phase=self.phase,
            image_digest=digest,
            resources=self.resources,
            configuration_schema=schema("checker.configuration", self.configuration_schema),
            input_schema=schema(f"external_checker_{self.phase}_input", self.input_schema),
            output_schema=schema("external_checker_result", {"type": "object"}),
        )


def load_descriptor(context: Path) -> Descriptor:
    """Reject malformed plans before invoking Docker or AWS."""
    path = context / "checker.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ImageError("checker.json must be a regular file of at most 2 MiB")
    descriptor = Descriptor.model_validate_json(path.read_bytes())
    if {s.expected for s in descriptor.samples} != {"passed", "failed"}:
        raise ImageError("provide at least one passing and one failing sample")
    if len({s.name for s in descriptor.samples}) != len(descriptor.samples):
        raise ImageError("sample names must be unique")
    spec = descriptor.spec("sha256:" + "0" * 64)
    for sample in descriptor.samples:
        if sample.expected == "failed" and not sample.expected_codes:
            raise ImageError("failing samples must name their expected finding codes")
        sample_directory(context, sample.directory)
        spec.configuration_schema.validate_instance(sample.configuration)
        spec.input_schema.validate_instance(sample.input)
    return descriptor


def sample_directory(context: Path, name: str) -> Path:
    """Samples are local directories within the selected project build context."""
    if not safe_finding_path(name):
        raise ImageError("sample directory must be a safe relative path")
    path = context
    for part in Path(name).parts:
        path = path / part
        if path.is_symlink():
            raise ImageError("sample directories cannot contain symlinks")
    if not path.is_dir() or not path.resolve().is_relative_to(context.resolve()):
        raise ImageError("sample directory must exist inside the build context")
    return path


def snapshot_sample(source: Path, destination: Path) -> str:
    """Copy bounded regular sample files into private scratch and record their identity."""
    destination.mkdir(mode=0o755)
    entries = []
    total = 0
    for root, directories, files in os.walk(source, followlinks=False):
        for name in sorted(directories + files):
            path = Path(root) / name
            relative = path.relative_to(source).as_posix()
            if len(entries) >= 10000 or not safe_finding_path(relative):
                raise ImageError("sample has too many entries or an unsafe path")
            info = path.lstat()
            target = destination / relative
            if stat.S_ISDIR(info.st_mode):
                target.mkdir(mode=0o755)
                entries.append({"path": relative, "type": "directory"})
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ImageError("sample contains a symlink or special file")
            with os.fdopen(
                os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb"
            ) as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ImageError("sample file changed type")
                content = handle.read(128 * 1024 * 1024 - total + 1)
            total += len(content)
            if total > 128 * 1024 * 1024:
                raise ImageError("sample exceeds the 128 MiB dry-run limit")
            target.write_bytes(content)
            executable = bool(info.st_mode & 0o111)
            target.chmod(0o555 if executable else 0o444)
            entries.append(
                {
                    "path": relative,
                    "type": "file",
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "executable": executable,
                }
            )
    return external_checker_json_hash(sorted(entries, key=lambda item: item["path"]))


def sample_request(descriptor: Descriptor, sample: Sample, image_id: str, sample_digest: str):
    """Create explicitly synthetic wire identities, never registry or ART records."""
    spec = descriptor.spec(image_id)
    now = datetime.now(UTC)
    entry = ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=UUID("00000000-0000-7000-8000-000000000001"),
        entry_digest=spec.spec_digest,
        registration_operation_id=uuid4(),
        registered_by_actor_profile_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        created_at=now,
    )
    identity = {
        "phase": descriptor.phase,
        "project_id": uuid4(),
        "task_id": uuid4(),
        "assignment_id": uuid4(),
        "attempt_id": uuid4(),
    }
    material = {
        "phase": descriptor.phase,
        "role": "submission_archive",
        "semantic_manifest_sha256": sample_digest,
        "media_type": "application/zip",
    }
    if descriptor.phase == "pre_submit":
        identity.update(
            operation_id=uuid4(),
            source_sha256=sample_digest,
            lease_id=uuid4(),
            lease_generation=1,
            attempt_request_digest=sample_digest,
            effective_plan_sha256=sample_digest,
        )
        material.update(
            {
                key: identity[key]
                for key in (
                    "operation_id", "source_sha256", "lease_id", "lease_generation",
                    "attempt_id", "attempt_request_digest",
                )
            }
        )
        material.update(archive_sha256=sample_digest, archive_byte_count=0)
    else:
        identity.update(
            submission_id=uuid4(),
            submission_version=1,
            evaluation_request_id=uuid4(),
            evaluation_request_digest=sample_digest,
            evaluation_generation=1,
            result_id=uuid4(),
            lease_id=uuid4(),
            lease_generation=1,
            lease_expires_at=now + timedelta(hours=1),
        )
        material.update(
            submission_id=identity["submission_id"],
            submission_version=1,
            content_sha256=sample_digest,
            byte_count=0,
            verification_generation=1,
            namespace_fingerprint=sample_digest,
        )
        material.update(
            {
                key: uuid4()
                for key in (
                    "binding_id",
                    "content_id",
                    "replica_id",
                    "evidence_id",
                    "verification_receipt_id",
                    "verification_job_id",
                )
            }
        )
    # JSON parsing converts the UUID/datetime discriminated unions through their
    # strict wire contract, without relaxing the production model's strict fields.
    return make_external_checker_execution_request(
        registry=entry,
        identity=TypeAdapter(ExternalCheckerExecutionIdentity).validate_json(
            json.dumps(identity, default=str)
        ),
        materials=(
            TypeAdapter(ExternalCheckerMaterial).validate_json(json.dumps(material, default=str)),
        ),
        configuration=sample.configuration,
        configuration_sha256=external_checker_json_hash(sample.configuration),
        input=sample.input,
        input_sha256=external_checker_json_hash(sample.input),
    )
