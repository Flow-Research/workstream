"""Bounded worker composition for audited submission-source reclamation."""
import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    create_artifact_store_bootstrap, create_submission_source_cleanup_provider,
    submission_source_cleanup_execution, submission_source_cleanup_candidates,
    abandon_expired_submission_foregrounds,
    configured_artifact_storage_namespace, IntakeCustodyConflict,
)
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db.session import get_database_url
from app.interfaces.artifacts import ArtifactStoreError, ArtifactStoreNamespaceClaim
from app.modules.artifacts.api.submission_cleanup import SubmissionSourceCleanupProfile
from workstream_external_services import ExternalServiceAdapterError


def _configuration(settings):
    profile = SubmissionSourceCleanupProfile.model_validate(settings.submission_source_cleanup_profile)
    bootstrap = create_artifact_store_bootstrap(settings)
    try:
        namespace = configured_artifact_storage_namespace(settings, bootstrap)
        claim = ArtifactStoreNamespaceClaim(bootstrap.identity, bootstrap.namespace_identity,
                                           namespace.namespace_fingerprint)
        return profile, namespace, claim
    finally:
        bootstrap.close()


async def validate_source_cleanup_startup():
    """Validate dedicated credentials, namespace and current service before consumption."""
    settings = get_settings()
    profile, namespace, claim = _configuration(settings)
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        async with asyncio.timeout(profile.run_seconds):
            await submission_source_cleanup_candidates(async_sessionmaker(engine, expire_on_commit=False), namespace, 1)
            provider = create_submission_source_cleanup_provider(
                settings=settings, namespace_claim=claim, upload_principal=profile.upload_principal)
            provider.close()
    finally:
        await engine.dispose()


async def sweep_submission_sources(sessions, settings):
    """One finite page; confirmed counts include already-confirmed replay."""
    profile, namespace, namespace_claim = _configuration(settings)
    candidates, confirmed, timed_out, provider, abandoned = (), 0, False, None, 0
    try:
        async with asyncio.timeout(profile.run_seconds):
            try:
                # Reserve at least half the envelope for source cleanup even
                # when expired foreground custody is blocked on a TASK lock.
                async with asyncio.timeout(profile.run_seconds / 2):
                    abandoned = await abandon_expired_submission_foregrounds(
                        sessions, namespace, profile.maximum_candidates, operation_timeout_seconds=profile.lease_seconds)
            except TimeoutError:
                timed_out = True
            candidates = await submission_source_cleanup_candidates(sessions, namespace, profile.maximum_candidates)
            if candidates:
                provider = create_submission_source_cleanup_provider(
                    settings=settings, namespace_claim=namespace_claim, upload_principal=profile.upload_principal)
                execution = submission_source_cleanup_execution(
                    sessions=sessions, provider=provider, lease_duration=timedelta(seconds=profile.lease_seconds))
                for operation in candidates:
                    try:
                        async with asyncio.timeout(profile.lease_seconds):
                            await execution.run(operation, new_record_id())
                    except (IntakeCustodyConflict, ArtifactStoreError, ExternalServiceAdapterError, TimeoutError):
                        # An uncertain attempt retains its claim/charge. A later
                        # sweep must regain authority and re-observe the target.
                        continue
                    confirmed += 1
    except TimeoutError:
        timed_out = True
    finally:
        if provider is not None:
            provider.close()
    return {"candidates": len(candidates), "confirmed": confirmed,
            "deferred": len(candidates) - confirmed, "timed_out": timed_out, "abandoned": abandoned}


async def run_source_cleanup_sweep():
    """Own DB/provider resources for one Celery process invocation."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        return await sweep_submission_sources(
            async_sessionmaker(engine, expire_on_commit=False), get_settings())
    finally:
        await engine.dispose()
