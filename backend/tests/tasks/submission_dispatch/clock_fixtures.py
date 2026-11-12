"""Bound current revision source windows without disabling their custody guard."""

from contextlib import asynccontextmanager

from sqlalchemy import text

_SOURCE_GUARD_DEFINITION = (
    "SELECT pg_catalog.pg_get_functiondef("
    "'public.guard_task_post_submit_routing_source()'::regprocedure)"
)


@asynccontextmanager
async def source_window_clock(session, window_seconds):
    """Control source creation time and restore the complete guard in one transaction."""
    assert window_seconds in (-3_600, 60, 600, 136_800)
    # Resolve every required policy column before substituting the clock expression.
    await session.execute(text("""
        SELECT p.revision_deadline_hours,p.policy_generation,p.policy_hash,p.project_id,
            p.guide_version,p.semantics_status,s.task_id,s.locked_revision_policy_generation,
            s.locked_revision_policy_hash,s.locked_guide_version
        FROM public.submissions s
        JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
        WHERE false
    """))
    original = await session.scalar(text(_SOURCE_GUARD_DEFINITION))
    anchor = "NEW.created_at := pg_catalog.clock_timestamp();"
    assert original.count(anchor) == 1
    historical_clock = f"""NEW.created_at := (
        SELECT pg_catalog.clock_timestamp()
            -pg_catalog.make_interval(hours=>p.revision_deadline_hours)
            +pg_catalog.make_interval(secs=>{window_seconds})
        FROM public.submissions s
        JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
            AND p.policy_generation=s.locked_revision_policy_generation
            AND p.policy_hash=s.locked_revision_policy_hash AND p.project_id=NEW.project_id
            AND p.guide_version=s.locked_guide_version AND p.semantics_status='complete'
        WHERE s.id=NEW.submission_id AND s.task_id=NEW.task_id);"""
    await session.execute(text(original.replace(anchor, historical_clock)))
    try:
        yield original
    except BaseException:
        # The caller's root transaction rolls back the clock substitution and rows.
        raise
    else:
        await session.execute(text(original))
        assert await session.scalar(text(_SOURCE_GUARD_DEFINITION)) == original
        assert await session.scalar(text(
            "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled='D'"
        )) == 0

