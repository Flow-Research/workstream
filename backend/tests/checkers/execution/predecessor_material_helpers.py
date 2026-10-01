"""Pre-0010 persisted receipt shape for the distinct 0008-to-0009 migration proof."""
from app.core.identifiers import new_record_id
from .material_storage_helpers import stage_terminal


async def write_terminal(session, facts, material):
    """Represent a predecessor receipt; current schema must reject this unprovable ID."""
    await stage_terminal(session, facts, material, new_record_id())
