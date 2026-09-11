"""Run genuine public guide uploads with isolated storage and the real setup worker."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import dotenv_values

import external_api_drill as api


def environment(env, report):
    """Copy only approved model settings; never inherit another worktree's database."""
    report["guide_drill_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provider = dotenv_values(os.environ["WORKSTREAM_DRILL_PROVIDER_ENV"])
    if not provider.get("OPENAI_API_KEY"):
        raise api.ProbeFailure("model_key_missing")
    for key, value in provider.items():
        if key == "OPENAI_API_KEY" or key.startswith("WORKSTREAM_PROJECT_AGENT_"):
            if value is not None:
                env[key] = value
    endpoint = os.environ["WORKSTREAM_TEST_MINIO_ENDPOINT"]
    broker = os.environ["WORKSTREAM_DRILL_BROKER_URL"]
    if (urlsplit(endpoint).hostname not in {"127.0.0.1", "localhost"}
            or urlsplit(broker).hostname not in {"127.0.0.1", "localhost"}):
        raise api.ProbeFailure("nonlocal_drill_provider")
    env.update({
        "WORKSTREAM_ARTIFACT_STORE_BACKEND": "s3_compatible",
        "WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE": "minio",
        "WORKSTREAM_ARTIFACT_S3_REGION": "us-east-1",
        "WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL": endpoint,
        "WORKSTREAM_ARTIFACT_S3_BUCKET": os.environ["WORKSTREAM_TEST_MINIO_BUCKET"],
        "WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX": os.environ["WORKSTREAM_TEST_MINIO_PREFIX"],
        "WORKSTREAM_ARTIFACT_S3_ADDRESSING_STYLE": "path",
        "WORKSTREAM_ARTIFACT_S3_CREDENTIAL_MODE": "local_static",
        "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID": "workstream-minio",
        "WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY": "workstream-minio-secret-key",
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": os.environ["WORKSTREAM_DRILL_SCRATCH_ROOT"],
        "WORKSTREAM_CELERY_BROKER_URL": broker,
        "WORKSTREAM_CELERY_TASK_ALWAYS_EAGER": "false",
    })
    for scope, mib in (("TASK", 20), ("PRODUCER", 40), ("PROJECT", 64), ("DEPLOYMENT", 128)):
        env[f"WORKSTREAM_ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(mib * 1024 * 1024)
    report["limitations"] = [
        "local test Flow issuer, not deployed Flow Identity",
        "real isolated MinIO and Celery; approved model provider may incur usage",
        "public setup evidence is not manager approval or project activation",
        "no product SQL writes, trigger suppression or fabricated provider outputs",
    ]


async def stored_documents(env, originals):
    """Independently reread owned provider objects; no product locator is exposed."""
    from aiobotocore.session import AioSession
    from aiobotocore.config import AioConfig

    hashes = set()
    async with AioSession().create_client(
        "s3", endpoint_url=env["WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL"], region_name="us-east-1",
        aws_access_key_id=env["WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=env["WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY"],
        config=AioConfig(s3={"addressing_style": "path"}),
    ) as client:
        bucket = env["WORKSTREAM_ARTIFACT_S3_BUCKET"]
        paginator = client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=bucket, Prefix=env["WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX"]):
            for item in page.get("Contents", []):
                if item["Size"] > 10 * 1024 * 1024:
                    raise api.ProbeFailure("unexpected_large_provider_object")
                result = await client.get_object(Bucket=bucket, Key=item["Key"])
                async with result["Body"] as stream:
                    hashes.add(hashlib.sha256(await stream.read()).hexdigest())
    expected = {hashlib.sha256(content).hexdigest() for content in originals}
    if not expected.issubset(hashes):
        raise api.ProbeFailure("uploaded_originals_not_in_storage")
    return len(expected)


def sufficiency_matches(reports, setup):
    """Bind the one fresh guide's report to the completed public setup result."""
    if not isinstance(reports, list) or len(reports) != 1 or not isinstance(reports[0], dict):
        return False
    expected = {"id": setup["output_sufficiency_report_id"],
                "project_setup_run_id": setup["id"],
                **{key: setup[key] for key in ("project_id", "guide_id", "guide_version",
                                               "source_snapshot_id", "setup_generation")}}
    return (expected["id"] is not None
            and all(key in reports[0] and api.strict_equal(reports[0][key], value)
                    for key, value in expected.items()))


async def scenario(drill, issuer, env):
    """Act as separate administrator, manager and ungranted external clients."""
    paths = [Path(value) for value in json.loads(os.environ["WORKSTREAM_DRILL_GUIDE_PDFS"])]
    if len(paths) != 2 or any(path.suffix.lower() != ".pdf" or path.stat().st_size > 10 * 1024 * 1024 for path in paths):
        raise api.ProbeFailure("two_bounded_pdf_originals_required")
    originals = [path.read_bytes() for path in paths]
    if any(not content.startswith(b"%PDF-") for content in originals):
        raise api.ProbeFailure("invalid_pdf_input")
    report = drill.report
    report["input_documents"] = [{"name": path.name, "sha256": hashlib.sha256(content).hexdigest(),
                                   "byte_count": len(content)} for path, content in zip(paths, originals)]
    admin, manager, outsider = [issuer.issue(name) for name in ("admin", "manager", "outsider")]
    profiles = []
    for name, token in (("admin", admin), ("manager", manager), ("outsider", outsider)):
        profiles.append(await drill.call(name + "_profile", "GET", "/api/v1/actors/me", token=token))
    bootstrap = subprocess.run([sys.executable, "scripts/bootstrap_access_administrator.py",
        "--actor-profile-id", profiles[0]["actor_profile_id"], "--execute"],
        env=env, cwd=api.ROOT, capture_output=True, timeout=30)
    if bootstrap.returncode:
        raise api.ProbeFailure("bootstrap_failed")
    report["setup"].append("documented first Access Administrator bootstrap CLI")
    await drill.call("grant_manager", "POST", "/api/v1/admin-role-grants", token=admin, expected=201,
        payload={"target_actor_profile_id": profiles[1]["actor_profile_id"], "role": "project_manager",
                 "scope_type": "system", "reason": "Public guide upload drill"})
    service_profiles = {}
    for identity in ("artifact.put_resolver", "artifact.guide_reader", "project.setup"):
        service_profiles[identity] = await drill.call("provision_" + identity, "POST", "/api/v1/service-actors", token=admin, expected=201,
            payload={"service_identity": "workstream." + identity,
                     "subject": "drill-" + identity, "reason": "Isolated guide workflow"})
    project = await drill.call("create_project", "POST", "/api/v1/projects", token=manager, expected=201,
        payload={"name": "Workstream Public API Contract Audit", "slug": "public-api-contract-audit",
                 "description": "Reproducible field-level API evidence for external client integration."})
    route = "/api/v1/projects/{project_id}/guides"
    path = f'/api/v1/projects/{project["id"]}/guides'
    payload = {"version": "initial", "change_summary": "Original API audit guide and assignment example",
        "task_examples": [{"title": "Guide-create contract audit", "labels": ["api", "authorization"],
            "content": "Audit public guide creation at the assigned Workstream commit. Prove declared document order, exact replay, changed-key conflicts, and ungranted actor denial using real HTTP and isolated PostgreSQL."}],
        "documents": [{"label": value.name, "media_type": "application/pdf"} for value in paths]}
    key = {"Idempotency-Key": str(uuid4())}
    guide = await drill.call("create_guide", "POST", route, path=path, token=manager, payload=payload,
        headers=key, expected=201, **api.guide_expectations(payload, project["id"], profiles[1]["actor_profile_id"]))
    await drill.call("replay_guide", "POST", route, path=path, token=manager, payload=payload,
        headers=key, expected=201, values=guide, exact_fields=guide.keys())
    setup_route = route + "/{guide_id}/setup-runs/latest"
    setup_path = path + "/" + guide["id"] + "/setup-runs/latest"
    await drill.call("waiting_setup", "GET", setup_route, path=setup_path, token=manager,
        values={"id": guide["setup"]["id"], "status": "awaiting_documents", "documents_ready_at": None})
    worker = subprocess.Popen([sys.executable, "-m", "celery", "-A", "app.workers.celery_app",
        "worker", "--pool=solo", "--concurrency=1", "--without-gossip", "--without-mingle",
        "--without-heartbeat", "--loglevel=WARNING"], cwd=api.ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        upload_route = route + "/{guide_id}/documents/{document_id}/content"
        for index, (document, content) in enumerate(zip(guide["documents"], originals)):
            upload_path = path + "/" + guide["id"] + "/documents/" + document["document_id"] + "/content"
            headers = {"Idempotency-Key": str(uuid4()), "Content-Type": "application/pdf"}
            await drill.call(f"ungranted_upload_{index}", "POST", upload_route, path=upload_path,
                token=outsider, content=content, headers=headers, expected=404)
            await drill.call(f"wrong_media_{index}", "POST", upload_route, path=upload_path,
                token=manager, content=content, headers=headers | {"Content-Type": "text/plain"}, expected=422)
            commitment = {"document_id": document["document_id"], "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                          "byte_count": len(content), "replayed": False}
            uploaded = await drill.call(f"upload_{index}", "POST", upload_route, path=upload_path,
                token=manager, content=content, headers=headers, expected=202,
                values=commitment | {"status": "document_stored"},
                exact_fields=(*commitment, "status"))
            def replay_status(value):
                report.setdefault("upload_replay_statuses", []).append(value)
                return value == "object_confirmed"
            try:
                await drill.call(f"upload_replay_{index}", "POST", upload_route, path=upload_path,
                    token=manager, content=content, headers=headers, expected=202,
                    values=commitment | {"replayed": True}, checks={"status": replay_status},
                    exact_fields=uploaded.keys())
            except api.ProbeFailure as exc:
                # Preserve the failed case and final nonzero result, but inspect
                # independent uploads/setup after this reproduced terminal replay defect.
                if (str(exc) != "response_predicate_failed"
                        or report.get("upload_replay_statuses", [])[-1:] != ["stale"]):
                    raise
                print("API-DRILL-010: stored upload replay returned stale; case remains failed", flush=True)
            if index == 0:
                await drill.call("partial_documents_wait", "GET", setup_route, path=setup_path,
                    token=manager, values={"status": "awaiting_documents", "documents_ready_at": None})
        report["stored_originals_verified"] = await stored_documents(env, originals)
        deadline = time.monotonic() + 1800
        for attempt in range(121):
            manager = issuer.issue("manager")
            if worker.poll() is not None:
                raise api.ProbeFailure("worker_exited")
            status = await drill.call(f"setup_progress_{attempt}", "GET", setup_route,
                path=setup_path, token=manager, values={"id": guide["setup"]["id"], "guide_id": guide["id"]})
            report["setup_outcome"] = status
            if status["finished_at"] is not None:
                if status["output_sufficiency_report_id"] is None:
                    raise api.ProbeFailure("setup_finished_without_sufficiency")
                reports = await drill.call("sufficiency_findings", "GET", route + "/{guide_id}/sufficiency-reports",
                    path=path + "/" + guide["id"] + "/sufficiency-reports", token=manager,
                    checks={"$": lambda value: sufficiency_matches(value, status)})
                # Original shareable project material only; this report remains
                # private/out-of-tree. Do not print model-generated findings.
                report["sufficiency_reports"] = reports
                resolver_id = service_profiles["artifact.put_resolver"]["actor_profile_id"]
                await drill.call("deactivate_completed_upload_resolver", "POST",
                    "/api/v1/actors/{actor_profile_id}/deactivate",
                    path=f"/api/v1/actors/{resolver_id}/deactivate", token=issuer.issue("admin"),
                    payload={"reason": "Verify current authority on completed upload replay"})
                await drill.call("inactive_resolver_replay_denied", "POST", upload_route,
                    path=upload_path, token=manager, content=content, headers=headers, expected=404,
                    values={"error.code": "resource_not_found"})
                await drill.call("setup_unchanged_after_denied_replay", "GET", setup_route,
                    path=setup_path, token=manager, values=status, exact_fields=status.keys())
                report["stored_originals_after_denial_verified"] = await stored_documents(env, originals)
                return
            # The dispatch fence is recorded before inference, so the public
            # unresolved outcome can also describe an invocation still running.
            # Observe that same run; never submit a retry or treat it as success.
            if (status["error_code"] not in {None, "provider_outcome_unresolved"}
                    or time.monotonic() >= deadline):
                raise api.ProbeFailure("setup_requires_diagnosis")
            print("guide setup state: " + status["status"], flush=True)
            await asyncio.sleep(15)
        raise api.ProbeFailure("setup_observation_timeout")
    finally:
        api.stop_server(worker, preserving_failure=sys.exc_info()[0] is not None)


if __name__ == "__main__":
    raise SystemExit(api.main(scenario=scenario, environment=environment))
