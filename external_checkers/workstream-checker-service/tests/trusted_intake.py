"""Opt-in real-node intake proof, separate from public API/transaction proof.

Run with backend dependencies and PYTHONPATH=backend against an isolated Smol node
configured with maximum_parallel=1. No authority or acceptance facts are fabricated.
The PRE grant proves retained ART custody only; the public drill proves its business
reservation. Host ZIP parsing/default evaluation are deliberately poisoned.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
import zipfile

from app.adapters.artifacts import trusted_submission_intake
from app.core.config import Settings
from app.core.identifiers import new_record_id
from app.interfaces.external_services import ExternalServiceAdapterError
from app.interfaces.trusted_submission_intake import (
    TrustedDefaultBinding,
    TrustedIntakePreparation,
)
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveLimits,
    SubmissionArchiveRejectedError,
)
from app.modules.artifacts.preparation import (
    ArtifactPreparationLimits,
    ArtifactPreparationService,
    ArtifactScratchManager,
    ExternalMaterialFile,
    ExternalMaterialGrantRequest,
)
from app.modules.artifacts.submission_archive import exported_submission_tree
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.artifacts.trusted_intake import TrustedArchiveInspector
from app.modules.checkers.api.default_checker import (
    WorkstreamDefaultCheckerInput,
    workstream_default_input_sha256,
)
from app.modules.checkers.api.material import SubmissionMaterialEntry
from app.modules.checkers.api.pre_submit_material import SubmissionPacketView

POLICY = "sha256:" + "a" * 64
CONTENT = b'fn main() { println!("verified"); }\n'
LIMITS = SubmissionArchiveLimits()


def request(phase="pre_submit", deadline_ms=120000):
    return TrustedIntakePreparation(phase, POLICY, LIMITS, deadline_ms)


async def bytes_source(data):
    yield data


async def recovered_capacity(adapter):
    """A new ready VM proves that the sole execution slot was returned."""
    deadline = time.monotonic() + 30
    while True:
        try:
            session = await adapter.prepare(request())
        except ExternalServiceAdapterError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.1)
        else:
            await session.close()
            return


async def retained_material(adapter, root, data, phase):
    started = time.monotonic()
    manager = ArtifactScratchManager(
        root=root,
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=1024 * 1024**2,
            minimum_free_bytes=0,
            total_deadline_seconds=120,
            reservation_ttl_seconds=150,
            cleanup_margin_seconds=5,
            maximum_source_bytes=1024**2,
        ),
    )
    preparation = ArtifactPreparationService(manager)
    session = await adapter.prepare(request(phase))
    prepared = await preparation.prepare(
        bytes_source(data), media_type="application/zip"
    )
    try:
        inspection = await prepared.inspect(
            TrustedArchiveInspector(session, prepared.commitment),
            on_cancel=session.abort,
        )
        manifest = build_submission_manifest(inspection)
        attempt = new_record_id()

        class Processor:
            def abort(self):
                session.abort()

            async def process(self, reader, workspace):
                # Export is blocking transport I/O. Keep its context on one thread
                # while the async default and close operations run on the event loop.
                context = exported_submission_tree(
                    session.export, workspace, expected=inspection, limits=LIMITS
                )
                tree = await asyncio.to_thread(context.__enter__)
                try:
                    assert tree.read_file("src/work.rs", maximum_bytes=1024) == CONTENT
                    if phase == "pre_submit":
                        value = WorkstreamDefaultCheckerInput(
                            prepared.commitment.sha256,
                            prepared.commitment.byte_count,
                            "application/zip",
                            manifest.sha256,
                            tuple(
                                SubmissionMaterialEntry(**asdict(entry))
                                for entry in inspection.entries
                            ),
                            None,
                            False,
                            None,
                            POLICY,
                            None,
                            SubmissionPacketView("Completed", "Authorized"),
                        )
                        binding = TrustedDefaultBinding(
                            attempt,
                            POLICY,
                            POLICY,
                            manifest.sha256,
                            workstream_default_input_sha256(value),
                        )
                        assert (await session.evaluate_default(binding, value)).eligible
                    await (
                        session.close()
                    )  # Acknowledged cleanup precedes any project grant.
                    if phase == "pre_submit":
                        grant_request = ExternalMaterialGrantRequest(
                            POLICY,
                            str(prepared.generation_id),
                            str(attempt),
                            POLICY,
                            prepared.commitment.sha256,
                            prepared.commitment.byte_count,
                            manifest.sha256,
                            tuple(
                                e.normalized_path
                                for e in inspection.entries
                                if e.entry_type == "directory"
                            ),
                            tuple(
                                ExternalMaterialFile(
                                    e.normalized_path,
                                    e.byte_count,
                                    e.sha256,
                                    e.executable,
                                )
                                for e in inspection.entries
                                if e.entry_type == "file"
                            ),
                        )
                        with preparation.external_material_grant(
                            prepared, workspace, grant_request
                        ) as grant:
                            assert grant.grant_id.startswith("extract_")
                    # The same one-slot node can serve another job while ART retains
                    # the verified callback material: no intake/project slot deadlock.
                    await recovered_capacity(adapter)
                finally:
                    await asyncio.to_thread(context.__exit__, None, None, None)

        await preparation._process_prepared_submission(
            prepared,
            Processor(),
            reserved_bytes=inspection.total_expanded_bytes,
            maximum_entries=inspection.entry_count + 1,
        )
    finally:
        await prepared.close()
        await session.close()
        assert not list((root / "workspaces").iterdir())
        assert preparation.pending_cleanup_count == 0
        manager.close()
    print(
        json.dumps(
            {
                "case": "retained_material",
                "phase": phase,
                "seconds": time.monotonic() - started,
            }
        ),
        flush=True,
    )


async def run(args):
    adapter = trusted_submission_intake(
        Settings(
            artifact_intake_service_socket=args.socket,
            artifact_intake_image_digest=args.image,
            artifact_intake_config_digest=args.config,
        )
    )
    assert (await adapter.health()).runtime == "smolvm"
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("src/work.rs", CONTENT)
    data = output.getvalue()
    with tempfile.TemporaryDirectory(prefix="ws-intake-proof-") as directory:
        with (
            patch(
                "app.modules.artifacts.submission_archive.SubmissionArchiveInspector.inspect",
                side_effect=AssertionError("host ZIP parsing"),
            ),
            patch(
                "app.modules.checkers.default_checker.evaluate_verified_archive",
                side_effect=AssertionError("host default evaluation"),
            ),
        ):
            for phase in ("pre_submit", "post_submit"):
                await retained_material(adapter, Path(directory) / phase, data, phase)

    session = await adapter.prepare(request())
    session.abort()  # An upload disappears after preparation, before a ZIP arrives.
    try:
        await session.close()
    except ExternalServiceAdapterError:
        pass  # Missing ACK is not reported as confirmed cleanup.
    else:
        raise AssertionError("aborted transport falsely acknowledged cleanup")
    await recovered_capacity(adapter)
    print(json.dumps({"case": "abandoned_upload", "capacity": "recovered"}), flush=True)

    pending = asyncio.create_task(adapter.prepare(request()))
    await asyncio.sleep(0.2)
    assert not pending.done(), "cancellation did not reach preparation"
    pending.cancel()
    try:
        await pending
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("preparation ignored cancellation")
    await recovered_capacity(adapter)
    print(
        json.dumps({"case": "cancelled_prepare", "capacity": "recovered"}), flush=True
    )

    # The absolute lease expires while no ZIP arrives; no explicit close releases it.
    started = time.monotonic()
    session = await adapter.prepare(request(deadline_ms=8000))
    await asyncio.sleep(max(0, started + 8.2 - time.monotonic()))
    await recovered_capacity(adapter)
    session.abort()
    print(json.dumps({"case": "idle_deadline", "capacity": "recovered"}), flush=True)

    session = await adapter.prepare(request())
    import hashlib

    malformed = b"not a ZIP"
    try:
        await asyncio.to_thread(
            session.inspect,
            BytesIO(malformed),
            archive_sha256="sha256:" + hashlib.sha256(malformed).hexdigest(),
            archive_byte_count=len(malformed),
        )
    except SubmissionArchiveRejectedError:
        pass
    else:
        raise AssertionError("malformed ZIP was admitted")
    finally:
        await session.close()
    await recovered_capacity(adapter)
    print(json.dumps({"case": "malformed_zip", "capacity": "recovered"}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--config", required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
